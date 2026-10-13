"""A scoped MCP: fixed read-only collectors, pinned SSH host, aggregate output."""
import base64
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional
import paramiko
from dotenv import load_dotenv
from fastmcp import FastMCP
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.trace_middleware import TraceMiddleware

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
PIN = ROOT / '.runtime' / 'known_hosts'
EXPECTED = '3cf7250afe30931a54621093638e1b0f76f64169'
mcp = FastMCP('Hub observations (read only)')
mcp.add_middleware(TraceMiddleware('Hub observations (read only)'))

# --- PM2 read-only tools: validation and helpers ---

_PM2_APP_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
_PM2_MAX_LINES = 500


def _valid_pm2_app_name(name: str) -> bool:
    """Validates a PM2 app name against a strict allowlist pattern."""
    return bool(name and _PM2_APP_RE.match(name))


def _clamp_lines(n: int) -> int:
    """Clamps line count to [1, _PM2_MAX_LINES]."""
    return max(1, min(int(n), _PM2_MAX_LINES))


def _ssh_exec(command: str) -> str:
    """Opens an SSH session to the server, runs one command and returns stdout.
    Raises RuntimeError on any failure. Reuses the same host-key pin,
    credentials and timeouts as observe_hub."""
    client = paramiko.SSHClient()
    try:
        client.load_host_keys(str(PIN))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        key = paramiko.RSAKey.from_private_key_file(
            os.getenv('SRV_API_KEY_PATH', r'C:\KIOSK\SRV-API_key.pem'))
        client.connect(
            os.getenv('SRV_API_HOST', '191.233.18.195'),
            port=int(os.getenv('SRV_API_PORT', '22')),
            username=os.getenv('SRV_API_USER', 'ti-kiosk'),
            pkey=key, timeout=10,
            banner_timeout=10, auth_timeout=10,
            allow_agent=False, look_for_keys=False)
        _, stdout, _ = client.exec_command(command, timeout=30)
        data = stdout.read(256 * 1024 + 1)
        if len(data) > 256 * 1024:
            raise ValueError('Oversized response')
        return data.decode('utf-8')
    except Exception:
        raise RuntimeError('SSH_UNAVAILABLE') from None
    finally:
        client.close()


def command_for(environment):
    if environment not in ('production','hml'):
        raise ValueError('Invalid environment')
    directory = '/home/ti-kiosk/hub' if environment == 'production' else '/home/ti-kiosk/hub-homolog'
    since = (datetime.now(timezone.utc)-timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ')
    worker = '1' if environment == 'production' else '0'
    return f'cd {directory} && sudo -n node scripts/post-deploy-check.js --environment {environment} --expected-sha {EXPECTED} --samples 2 --interval-ms 1000 --since {since} --worker-enabled {worker}'


def normalize(report, environment):
    if not isinstance(report,dict) or report.get('environment') != environment or report.get('expectedSha') != EXPECTED:
        raise ValueError('Invalid source contract')
    samples = report.get('snapshots')
    if not isinstance(samples,list) or len(samples) != 2:
        raise ValueError('Invalid source samples')
    clean = []
    fields = {'process':('status','restarts','uptime','memoryBytes'),
              'internal':('status','environment','revision','emissionEnabled','version','workerEnabled','httpStatus'),
              'external':('status','environment','revision','emissionEnabled','version','workerEnabled','httpStatus'),
              'database':('ok','pending','processing','failed','errorsSinceDeploy','automaticShops','rateLimitsSinceDeploy','terminalErrorsSinceDeploy','logisticsReviewJobs','multipleVolumeReviewJobs')}
    for sample in samples:
        if not isinstance(sample,dict) or not isinstance(sample.get('ok'),bool):
            raise ValueError('Invalid source assessment')
        item = {'at':sample.get('at'), 'ok':sample['ok']}
        for group, keys in fields.items():
            value = sample.get(group) or {}
            item[group] = {k:value[k] for k in keys if k in value and isinstance(value[k],(str,int,float,bool)) and len(str(value[k])) <= 160}
        # The server script emits fixed assessment messages; never forward raw errors/logs.
        reasons = {
            'erros registrados desde o deploy': 'Erros registrados na janela de observação.',
            'objeto logístico ausente; jobs aguardam revisão': 'Objeto logístico ausente; jobs aguardam revisão.',
            'múltiplos volumes; jobs aguardam definição do contrato': 'Múltiplos volumes; contrato pendente.',
            'processo PM2 indisponível': 'Processo PM2 indisponível.',
            'reinício durante observação': 'Reinício durante a observação.',
            'banco indisponível para leitura': 'Banco indisponível para leitura.',
            'falhas de fila cresceram': 'Falhas de fila cresceram entre as amostras.',
        }
        item['failure_reasons'] = [reasons[value] for value in sample.get('failures',[]) if isinstance(value,str) and value in reasons]
        item['failure_count'] = len(sample.get('failures',[]))
        item['warning_count'] = len(sample.get('warnings',[]))
        clean.append(item)
    return {'environment':environment,'expected_sha':EXPECTED,'window_start':report.get('since'),
            'window_seconds':300,'ok':all(s['ok'] for s in clean),'snapshots':clean,
            'source':'hub/post-deploy-check','schema_version':1}


@mcp.tool()
def observe_hub(environment: Literal['production','hml'], task_id: Optional[str] = None) -> dict:
    """Read PM2, health and aggregate SQLite counters. No order or fiscal payloads. Task_id: optional label that groups this call with others of the same task."""
    command = command_for(environment)
    client = paramiko.SSHClient()
    try:
        client.load_host_keys(str(PIN))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        key = paramiko.RSAKey.from_private_key_file(os.getenv('SRV_API_KEY_PATH', r'C:\KIOSK\SRV-API_key.pem'))
        client.connect(os.getenv('SRV_API_HOST','191.233.18.195'),port=int(os.getenv('SRV_API_PORT','22')),
                       username=os.getenv('SRV_API_USER','ti-kiosk'),pkey=key,timeout=10,
                       banner_timeout=10,auth_timeout=10,allow_agent=False,look_for_keys=False)
        _, stdout, stderr = client.exec_command(command,timeout=25)
        data = stdout.read(65537)
        if len(data)>65536:
            raise ValueError('Oversized source response')
        # Exit 1 can represent a valid unhealthy assessment, rather than a failed transport.
        return normalize(json.loads(data.decode('utf-8')),environment)
    except Exception:
        raise RuntimeError('OBSERVATION_SOURCE_UNAVAILABLE') from None
    finally:
        client.close()


@mcp.tool()
def pm2_status(task_id: Optional[str] = None) -> list:
    """Lists all PM2 processes on the server (read-only). Returns JSON array with name, status, cpu, memory and pm_id for each process. Task_id: optional label that groups this call with others of the same task."""
    raw = _ssh_exec('sudo -n pm2 jlist')
    try:
        processes = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        raise RuntimeError('PM2_INVALID_RESPONSE') from None
    if not isinstance(processes, list):
        raise RuntimeError('PM2_INVALID_RESPONSE')
    # Return only safe, observable fields — never env vars or config.
    safe = []
    for p in processes:
        if not isinstance(p, dict):
            continue
        env = p.get('pm2_env') or {}
        monit = p.get('monit') or {}
        safe.append({
            'pm_id': p.get('pm_id'),
            'name': p.get('name'),
            'status': env.get('status'),
            'restarts': env.get('restart_time'),
            'uptime': env.get('pm_uptime'),
            'memory': monit.get('memory'),
            'cpu': monit.get('cpu'),
        })
    return safe


@mcp.tool()
def pm2_logs(app_name: str, lines: int = 100, task_id: Optional[str] = None) -> str:
    """Reads the last N lines of a PM2 app log (read-only, max 500). app_name must match a running process name (e.g. 'hub', 'api-jt-bling'). Task_id: optional label that groups this call with others of the same task."""
    if not _valid_pm2_app_name(app_name):
        raise RuntimeError(f'INVALID_APP_NAME: "{app_name}" rejected by validation')
    safe_lines = _clamp_lines(lines)
    return _ssh_exec(f'sudo -n pm2 logs {app_name} --lines {safe_lines} --nostream')


if __name__ == '__main__':
    mcp.run()
