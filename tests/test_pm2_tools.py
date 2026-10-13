"""Tests for PM2 read-only tools in hub_observability_mcp."""
import json
import unittest
from unittest import mock

import mcp_servers.hub_observability_mcp as obs


class TestPm2InputValidation(unittest.TestCase):
    """Validates that pm2 tools reject dangerous or malformed input."""

    def test_valid_app_names_accepted(self):
        for name in ['hub', 'api-jt-bling', 'webhook-getnet', 'hub_prod', 'Hub01']:
            self.assertTrue(obs._valid_pm2_app_name(name), name)

    def test_invalid_app_names_rejected(self):
        for name in ['', ' ', 'hub;id', 'hub&&ls', 'a' * 65, '../etc', 'hub$(id)',
                     'hub|cat', 'hub\nid', 'hub`id`']:
            self.assertFalse(obs._valid_pm2_app_name(name), name)

    def test_lines_clamped_to_max(self):
        self.assertEqual(obs._clamp_lines(1), 1)
        self.assertEqual(obs._clamp_lines(500), 500)
        self.assertEqual(obs._clamp_lines(999), 500)
        self.assertEqual(obs._clamp_lines(0), 1)
        self.assertEqual(obs._clamp_lines(-5), 1)


class TestPm2Status(unittest.TestCase):
    """pm2_status should SSH, run 'sudo pm2 jlist' and return parsed JSON."""

    @mock.patch.object(obs, '_ssh_exec')
    def test_returns_parsed_process_list(self, mock_ssh):
        mock_ssh.return_value = json.dumps([
            {'name': 'hub', 'pm2_env': {'status': 'online'}, 'pm_id': 0, 'monit': {'memory': 100, 'cpu': 1}},
        ])
        result = obs.pm2_status()
        mock_ssh.assert_called_once()
        cmd = mock_ssh.call_args[0][0]
        self.assertIn('sudo', cmd)
        self.assertIn('pm2 jlist', cmd)
        self.assertIsInstance(result, list)
        self.assertEqual(result[0]['name'], 'hub')

    @mock.patch.object(obs, '_ssh_exec')
    def test_raises_on_ssh_failure(self, mock_ssh):
        mock_ssh.side_effect = RuntimeError('SSH_UNAVAILABLE')
        with self.assertRaises(RuntimeError):
            obs.pm2_status()


class TestPm2Logs(unittest.TestCase):
    """pm2_logs should SSH, run 'sudo pm2 logs <app> --lines N --nostream'."""

    @mock.patch.object(obs, '_ssh_exec')
    def test_returns_log_output(self, mock_ssh):
        mock_ssh.return_value = '2026-10-13: Hub started on port 3000'
        result = obs.pm2_logs('hub', lines=50)
        cmd = mock_ssh.call_args[0][0]
        self.assertIn('sudo', cmd)
        self.assertIn('pm2 logs hub', cmd)
        self.assertIn('--lines 50', cmd)
        self.assertIn('--nostream', cmd)
        self.assertIn('Hub started', result)

    @mock.patch.object(obs, '_ssh_exec')
    def test_lines_clamped(self, mock_ssh):
        mock_ssh.return_value = ''
        obs.pm2_logs('hub', lines=9999)
        cmd = mock_ssh.call_args[0][0]
        self.assertIn('--lines 500', cmd)

    def test_rejects_invalid_app_name(self):
        with self.assertRaises(RuntimeError) as ctx:
            obs.pm2_logs('hub;id')
        self.assertIn('INVALID_APP_NAME', str(ctx.exception))

    @mock.patch.object(obs, '_ssh_exec')
    def test_raises_on_ssh_failure(self, mock_ssh):
        mock_ssh.side_effect = RuntimeError('SSH_UNAVAILABLE')
        with self.assertRaises(RuntimeError):
            obs.pm2_logs('hub')


if __name__ == '__main__':
    unittest.main()
