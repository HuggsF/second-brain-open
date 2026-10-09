"""A scoped MCP: fixed read-only collectors, pinned SSH host, aggregate output."""
import base64
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
import paramiko
from dotenv import load_dotenv
from fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
PIN = ROOT / '.runtime' / 'known_hosts'
EXPECTED = '3cf7250afe30931a54621093638e1b0f76f64169'
mcp = FastMCP('Hub observations (read only)')


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
def observe_hub(environment: Literal['production','hml']) -> dict:
    """Read PM2, health and aggregate SQLite counters. No order or fiscal payloads."""
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


if __name__ == '__main__':
    mcp.run()
