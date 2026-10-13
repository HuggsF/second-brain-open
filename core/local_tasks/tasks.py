"""Tarefas locais: prompts, schema de saída e pós-processamento por tarefa."""
from __future__ import annotations

from core.local_tasks.profile import Profile
from core.protocol import registry


def output_schema(task: str, template: str | None) -> dict:
    if task == "classify":
        return registry.load_schema("classification@1")
    if task == "extract":
        return registry.load_schema(template)
    raise NotImplementedError(task)


def prompt(task: str, text: str, profile: Profile, schema: dict, target_words: int) -> tuple[str, str]:
    if task == "classify":
        vocab = "\n".join(f"- {k}: {', '.join(v)}" for k, v in profile.labels.items())
        system = (
            "Classify the text. Answer only with JSON that follows the schema. "
            "Use exactly one value of each allowed list for `type` and `team`; "
            "`tags` are short lowercase keywords. `confidence` is between 0 and 1.\n"
            f"Allowed values:\n{vocab}"
        )
        return system, text
    if task == "extract":
        system = (
            "Extract the fields of the template from the text. Answer only with JSON "
            "that follows the schema. Use only information present in the text; "
            "do not invent values."
        )
        return system, text
    raise NotImplementedError(task)


def _canon(value, vocabulary: list[str]) -> str:
    if not isinstance(value, str):
        return ""
    wanted = value.strip().casefold()
    for item in vocabulary:
        if item.casefold() == wanted:
            return item
    return ""


def postprocess(task: str, obj: dict, profile: Profile) -> tuple[dict | None, str | None]:
    """Devolve (payload, None) ou (None, reason)."""
    if task == "classify":
        labels = obj.get("labels") if isinstance(obj.get("labels"), dict) else {}
        kind = _canon(labels.get("type"), profile.labels.get("type", []))
        team = _canon(labels.get("team"), profile.labels.get("team", []))
        if not kind and not team:
            return None, "no_valid_label"
        tags: list[str] = []
        for tag in labels.get("tags") or []:
            if isinstance(tag, str) and tag.strip():
                low = tag.strip().lower()
                if low not in tags:
                    tags.append(low)
        # classification@1 exige strings em type/team (null não é aceito): "" = sem rótulo válido.
        return {"labels": {"type": kind, "team": team, "tags": tags},
                "confidence": obj.get("confidence")}, None
    if task == "extract":
        return obj, None
    raise NotImplementedError(task)
