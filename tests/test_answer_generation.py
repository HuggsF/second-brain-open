"""Resposta do assistente pela cadeia de provedores do perfil (ADR-038)."""
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from core.local_tasks.answer import ANSWER_SCHEMA, generate_answer
from core.local_tasks.ollama_client import Completion, LocalModelError
from core.local_tasks.providers import FallbackClient, ProviderSpec

CLOUD = ProviderSpec(kind="openai_compatible", name="nuvem", model="m-nuvem", base_url="http://nuvem.invalid",
                     api_key_env="ANSWER_TEST_KEY", price={"input": 1.0, "output": 2.0})
LOCAL = ProviderSpec(kind="ollama", name="ollama", model="m-local", base_url="http://ollama.invalid")


class FakeClient:
    def __init__(self, text='{"answer": "resposta"}', error=None, tokens=(100, 20)):
        self.text, self.error, self.tokens = text, error, tokens
        self.calls = []

    def chat(self, model, system, user, schema):
        self.calls.append((model, system, user, schema))
        if self.error is not None:
            raise self.error
        return Completion(text=self.text, tokens_in=self.tokens[0], tokens_out=self.tokens[1], ms=5, model=model)


class FakeTracker:
    def __init__(self, state="normal", fail_record=False):
        self.state, self.fail_record = state, fail_record
        self.records = []

    def status(self):
        return SimpleNamespace(state=self.state, limiting_period="daily", daily_spent=0.0, daily_limit=1.0,
                               monthly_spent=0.0, monthly_limit=10.0)

    def record(self, cost, **kwargs):
        if self.fail_record:
            raise RuntimeError("database is locked")
        self.records.append((cost, kwargs))


def profile(providers=(CLOUD, LOCAL)):
    return SimpleNamespace(name="teste", local_model="m-local", timeout_seconds=30, retries=0,
                           paid_reference={}, providers=tuple(providers), keep_alive="30m", budget=None)


class TestGenerateAnswer(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"ANSWER_TEST_KEY": "x"})
        env.start()
        self.addCleanup(env.stop)

    def test_cloud_answers_first(self):
        cloud, local = FakeClient(), FakeClient()
        result = generate_answer("sys", "usr", profile=profile(), client=FallbackClient([(CLOUD, cloud), (LOCAL, local)]))
        self.assertEqual((result.status, result.text, result.provider), ("ok", "resposta", "nuvem"))
        self.assertEqual(result.cost.tier, "cloud")
        self.assertAlmostEqual(result.cost.actual_usd, (100 * 1.0 + 20 * 2.0) / 1e6)
        self.assertEqual(local.calls, [])
        self.assertEqual(cloud.calls[0][3], ANSWER_SCHEMA)

    def test_cloud_failure_falls_back_to_local(self):
        cloud = FakeClient(error=LocalModelError("timeout", "nuvem lenta"))
        local = FakeClient(text='{"answer": "local"}')
        result = generate_answer("sys", "usr", profile=profile(), client=FallbackClient([(CLOUD, cloud), (LOCAL, local)]))
        self.assertEqual((result.status, result.text, result.provider), ("ok", "local", "ollama"))
        self.assertEqual(result.cost.tier, "local")
        self.assertEqual(result.cost.actual_usd, 0.0)

    def test_all_providers_failing_is_model_error(self):
        cloud = FakeClient(error=LocalModelError("timeout", "nuvem"))
        local = FakeClient(error=LocalModelError("local_unavailable", "ollama fora"))
        result = generate_answer("sys", "usr", profile=profile(), client=FallbackClient([(CLOUD, cloud), (LOCAL, local)]))
        self.assertEqual((result.status, result.text, result.provider), ("model_error", None, None))
        self.assertEqual(result.reason, "local_unavailable")

    def test_plain_text_reply_is_accepted(self):
        client = FallbackClient([(CLOUD, FakeClient(text="  resposta em texto livre  "))])
        result = generate_answer("sys", "usr", profile=profile(), client=client)
        self.assertEqual((result.status, result.text), ("ok", "resposta em texto livre"))

    def test_empty_reply_is_model_error(self):
        client = FallbackClient([(CLOUD, FakeClient(text='{"answer": ""}'))])
        result = generate_answer("sys", "usr", profile=profile(), client=client)
        self.assertEqual((result.status, result.reason), ("model_error", "empty_answer"))

    def test_exceeded_budget_uses_local_only(self):
        local = FakeClient(text='{"answer": "local"}')
        tracker = FakeTracker(state="exceeded")
        with mock.patch("core.local_tasks.providers.OllamaClient", return_value=local), \
                mock.patch("core.local_tasks.providers.OpenAICompatClient") as cloud_cls:
            result = generate_answer("sys", "usr", profile=profile(), budget_tracker=tracker)
        self.assertEqual((result.status, result.provider), ("ok", "ollama"))
        cloud_cls.assert_not_called()
        self.assertEqual(len(local.calls), 1)

    def test_exceeded_budget_without_local_provider_is_model_error(self):
        with mock.patch("core.local_tasks.providers.OpenAICompatClient") as cloud_cls:
            result = generate_answer("sys", "usr", profile=profile(providers=(CLOUD,)),
                                     budget_tracker=FakeTracker(state="exceeded"))
        self.assertEqual((result.status, result.reason), ("model_error", "budget_daily"))
        cloud_cls.assert_not_called()

    def test_cost_is_recorded_in_budget(self):
        tracker = FakeTracker()
        result = generate_answer("sys", "usr", profile=profile(), budget_tracker=tracker,
                                 client=FallbackClient([(CLOUD, FakeClient())]), trace_id="t-1")
        self.assertEqual(len(tracker.records), 1)
        cost, meta = tracker.records[0]
        self.assertIs(cost, result.cost)
        self.assertEqual((meta["task"], meta["trace_id"]), ("answer", "t-1"))
        self.assertTrue(meta["envelope_id"])

    def test_record_failure_keeps_answer(self):
        result = generate_answer("sys", "usr", profile=profile(), budget_tracker=FakeTracker(fail_record=True),
                                 client=FallbackClient([(CLOUD, FakeClient())]))
        self.assertEqual((result.status, result.text), ("ok", "resposta"))


class TestProfileGenerator(unittest.TestCase):
    """Gerador padrao do BrainRetriever: perfil ativo e o orcamento dele."""

    def test_unreadable_profile_is_model_error(self):
        from core.local_tasks.profile import ProfileNotFound
        from core.retriever import _profile_generator
        with mock.patch("core.local_tasks.profile.load_profile", side_effect=ProfileNotFound("x")):
            result = _profile_generator("sys", "usr")
        self.assertEqual((result.status, result.reason, result.provider), ("model_error", "profile_not_found", None))

    def test_uses_active_profile_and_its_budget(self):
        from core.retriever import _profile_generator
        prof, tracker = profile(), FakeTracker()
        with mock.patch("core.local_tasks.profile.load_profile", return_value=prof), \
                mock.patch("core.retriever.default_budget_tracker", return_value=tracker) as budget, \
                mock.patch("core.retriever.generate_answer") as generate:
            _profile_generator("sys", "usr")
        budget.assert_called_once_with(prof)
        generate.assert_called_once_with("sys", "usr", profile=prof, budget_tracker=tracker)


if __name__ == "__main__":
    unittest.main()
