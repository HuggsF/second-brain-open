import os
import re
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import paramiko
from fastmcp import FastMCP
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.trace_middleware import TraceMiddleware
from core.policy.commands import (
    DOCKER_READ_ONLY, READ_ONLY_COMMANDS, SHELL_META, SYSTEMCTL_READ_ONLY, blocked_phrase, check_read_only,
)
from core.tracing import emit_child

# Carregar variáveis de ambiente
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

HOST = os.getenv("SRV_API_HOST", "191.233.18.195")
USER = os.getenv("SRV_API_USER", "ti-kiosk")
PORT = int(os.getenv("SRV_API_PORT", "22"))
KEY_PATH = os.getenv("SRV_API_KEY_PATH", r"C:\KIOSK\SRV-API_key.pem")

mcp = FastMCP("SRV-API Gateway")
mcp.add_middleware(TraceMiddleware('SRV-API Gateway'))

RUNTIME_DIR = BASE_DIR / ".runtime"
KNOWN_HOSTS = RUNTIME_DIR / "known_hosts"
# Comandos arbitrários só com opt-in explícito no .env (SRV_API_ALLOW_ARBITRARY=1).
ALLOW_ARBITRARY = os.getenv("SRV_API_ALLOW_ARBITRARY", "0") == "1"

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}$")
MAX_LOG_LINES = 500


def _get_ssh_client() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    # Confia na chave do servidor na 1.ª conexão e a memoriza; se mudar depois, a conexão é recusada.
    RUNTIME_DIR.mkdir(exist_ok=True)
    if KNOWN_HOSTS.exists():
        client.load_host_keys(str(KNOWN_HOSTS))
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key = paramiko.RSAKey.from_private_key_file(KEY_PATH)
    client.connect(
        hostname=HOST,
        port=PORT,
        username=USER,
        pkey=key,
        timeout=15.0
    )
    client.save_host_keys(str(KNOWN_HOSTS))
    return client

def _exec_command(cmd: str, timeout: int = 30) -> Dict[str, Any]:
    client = None
    try:
        client = _get_ssh_client()
        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        exit_code = stdout.channel.recv_exit_status()
        emit_child("ssh.exec", "ok" if exit_code == 0 else "error", {"command": cmd, "exit_code": exit_code})
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": out.strip(),
            "stderr": err.strip()
        }
    except Exception as e:
        emit_child("ssh.exec", "error", {"command": cmd}, error_type=type(e).__name__)
        return {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Erro de conexão SSH: {str(e)}"
        }
    finally:
        if client:
            client.close()

@mcp.tool()
def srv_api_health_check(task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Testa a conectividade com o servidor SRV-API e retorna informações de uptime e sistema operacional.
    task_id: optional label that groups this call with others of the same task
    """
    res = _exec_command("hostname; uname -a; uptime")
    return {
        "status": "online" if res["success"] else "error",
        "host": HOST,
        "details": res["stdout"] if res["success"] else res["stderr"]
    }

@mcp.tool()
def srv_api_resource_usage(task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Retorna o uso de recursos do servidor: memória RAM (free -h), espaço em disco (df -h) e carga de CPU.
    task_id: optional label that groups this call with others of the same task
    """
    cmd = "echo '=== MEMORIA ===' && free -h && echo '=== DISCO ===' && df -h / && echo '=== CPU / CARGA ===' && uptime"
    res = _exec_command(cmd)
    return {
        "success": res["success"],
        "output": res["stdout"] if res["success"] else res["stderr"]
    }

@mcp.tool()
def srv_api_list_services(task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Lista os containers Docker ativos (ou serviços em execução) no servidor SRV-API.
    task_id: optional label that groups this call with others of the same task
    """
    cmd = "if command -v docker >/dev/null 2>&1; then docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'; else systemctl list-units --type=service --state=running | head -n 25; fi"
    res = _exec_command(cmd)
    return {
        "success": res["success"],
        "services": res["stdout"] if res["success"] else res["stderr"]
    }

@mcp.tool()
def srv_api_view_logs(service_name: str, lines: int = 50, task_id: Optional[str] = None) -> str:
    """
    Recupera as últimas linhas de log de um container Docker ou serviço systemd no servidor.
    Args:
        service_name: Nome do container ou serviço (ex: 'api', 'nginx', 'postgres')
        lines: Quantidade de linhas a visualizar (padrão: 50)
    task_id: optional label that groups this call with others of the same task
    """
    if not _SAFE_NAME.match(service_name or ""):
        return "Erro: service_name inválido (use só letras, números, '.', '_', '-', '@'; máx. 64 caracteres)."
    try:
        lines = max(1, min(int(lines), MAX_LOG_LINES))
    except (TypeError, ValueError):
        return "Erro: 'lines' deve ser um número inteiro."
    cmd = f"if command -v docker >/dev/null 2>&1 && docker ps -a --format '{{{{.Names}}}}' | grep -qw '{service_name}'; then docker logs --tail {lines} {service_name}; else journalctl -u {service_name} -n {lines} --no-pager 2>&1 || echo 'Serviço não encontrado'; fi"
    res = _exec_command(cmd)
    return res["stdout"] if res["success"] else f"Erro ao ler logs: {res['stderr']}"

# Política de comandos: fonte única em core.policy.commands (aliases mantidos para os testes).
_READ_ONLY_COMMANDS = READ_ONLY_COMMANDS
_DOCKER_READ_ONLY = DOCKER_READ_ONLY
_SYSTEMCTL_READ_ONLY = SYSTEMCTL_READ_ONLY
_SHELL_META = SHELL_META
_check_read_only = check_read_only


@mcp.tool()
def srv_api_run_safe_command(command: str, task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Executa comandos de INSPEÇÃO (só leitura) no servidor remoto, sem encadeamento de shell.
    Aceita: ls, cat, head, tail, ps, df, du, free, uptime, hostname, uname, whoami, date, journalctl,
    grep, wc, find (sem ações de escrita ou execução), journalctl (sem --vacuum/--rotate/--flush), date (sem -s/--set), hostname (sem argumentos), docker (ps, logs, inspect, stats, images, top, version, info)
    e systemctl (status, list-units, is-active, ...). Tudo o resto é recusado e registado.
    Todas as chamadas ficam em .runtime/trace-log.jsonl.
    Args:
        command: Comando simples, ex: 'ls -la /var/www', 'docker ps', 'ps aux'
    task_id: optional label that groups this call with others of the same task
    """
    danger = blocked_phrase(command)
    if danger:
        emit_child("ssh.refused", "refused", {"command": command, "reason": f"blocked: {danger}"})
        return {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Comando bloqueado por política de segurança do MCP: contém '{danger}'"
        }

    if not ALLOW_ARBITRARY:
        reason = _check_read_only(command)
        if reason:
            emit_child("ssh.refused", "refused", {"command": command, "reason": reason})
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Recusado: {reason}. Fora da inspeção é preciso autorização humana e SRV_API_ALLOW_ARBITRARY=1 no .env."
            }

    return _exec_command(command)

if __name__ == "__main__":
    mcp.run()
