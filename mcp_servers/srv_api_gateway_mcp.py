import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import paramiko
from fastmcp import FastMCP

# Carregar variáveis de ambiente
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

HOST = os.getenv("SRV_API_HOST", "191.233.18.195")
USER = os.getenv("SRV_API_USER", "ti-kiosk")
PORT = int(os.getenv("SRV_API_PORT", "22"))
KEY_PATH = os.getenv("SRV_API_KEY_PATH", r"C:\KIOSK\SRV-API_key.pem")

mcp = FastMCP("SRV-API Gateway")

RUNTIME_DIR = BASE_DIR / ".runtime"
KNOWN_HOSTS = RUNTIME_DIR / "known_hosts"
AUDIT_LOG = RUNTIME_DIR / "gateway-audit.jsonl"
# Comandos arbitrários só com opt-in explícito no .env (SRV_API_ALLOW_ARBITRARY=1).
ALLOW_ARBITRARY = os.getenv("SRV_API_ALLOW_ARBITRARY", "0") == "1"

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}$")
MAX_LOG_LINES = 500


def _audit(tool: str, command: str, outcome: str, exit_code: Optional[int] = None) -> None:
    """Registra cada chamada (quando, qual ferramenta, qual comando, resultado). Nunca interrompe a chamada."""
    try:
        RUNTIME_DIR.mkdir(exist_ok=True)
        entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "tool": tool,
                 "command": command[:500], "outcome": outcome, "exit_code": exit_code}
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


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

def _exec_command(cmd: str, timeout: int = 30, tool: str = "exec") -> Dict[str, Any]:
    client = None
    try:
        client = _get_ssh_client()
        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        exit_code = stdout.channel.recv_exit_status()
        _audit(tool, cmd, "executed", exit_code)
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": out.strip(),
            "stderr": err.strip()
        }
    except Exception as e:
        _audit(tool, cmd, f"error: {type(e).__name__}", -1)
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
def srv_api_health_check() -> Dict[str, Any]:
    """
    Testa a conectividade com o servidor SRV-API e retorna informações de uptime e sistema operacional.
    """
    res = _exec_command("hostname; uname -a; uptime", tool="health_check")
    return {
        "status": "online" if res["success"] else "error",
        "host": HOST,
        "details": res["stdout"] if res["success"] else res["stderr"]
    }

@mcp.tool()
def srv_api_resource_usage() -> Dict[str, Any]:
    """
    Retorna o uso de recursos do servidor: memória RAM (free -h), espaço em disco (df -h) e carga de CPU.
    """
    cmd = "echo '=== MEMORIA ===' && free -h && echo '=== DISCO ===' && df -h / && echo '=== CPU / CARGA ===' && uptime"
    res = _exec_command(cmd, tool="resource_usage")
    return {
        "success": res["success"],
        "output": res["stdout"] if res["success"] else res["stderr"]
    }

@mcp.tool()
def srv_api_list_services() -> Dict[str, Any]:
    """
    Lista os containers Docker ativos (ou serviços em execução) no servidor SRV-API.
    """
    cmd = "if command -v docker >/dev/null 2>&1; then docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'; else systemctl list-units --type=service --state=running | head -n 25; fi"
    res = _exec_command(cmd, tool="list_services")
    return {
        "success": res["success"],
        "services": res["stdout"] if res["success"] else res["stderr"]
    }

@mcp.tool()
def srv_api_view_logs(service_name: str, lines: int = 50) -> str:
    """
    Recupera as últimas linhas de log de um container Docker ou serviço systemd no servidor.
    Args:
        service_name: Nome do container ou serviço (ex: 'api', 'nginx', 'postgres')
        lines: Quantidade de linhas a visualizar (padrão: 50)
    """
    if not _SAFE_NAME.match(service_name or ""):
        return "Erro: service_name inválido (use só letras, números, '.', '_', '-', '@'; máx. 64 caracteres)."
    try:
        lines = max(1, min(int(lines), MAX_LOG_LINES))
    except (TypeError, ValueError):
        return "Erro: 'lines' deve ser um número inteiro."
    cmd = f"if command -v docker >/dev/null 2>&1 && docker ps -a --format '{{{{.Names}}}}' | grep -qw '{service_name}'; then docker logs --tail {lines} {service_name}; else journalctl -u {service_name} -n {lines} --no-pager 2>&1 || echo 'Serviço não encontrado'; fi"
    res = _exec_command(cmd, tool="view_logs")
    return res["stdout"] if res["success"] else f"Erro ao ler logs: {res['stderr']}"

# Comandos de inspeção aceites por omissão (só leitura). Defesa em camadas, não uma fronteira de segurança:
# a fronteira real é o utilizador SSH ter só permissões de leitura no servidor.
_READ_ONLY_COMMANDS = {
    "ls", "cat", "head", "tail", "ps", "df", "du", "free", "uptime", "hostname", "uname",
    "whoami", "date", "journalctl", "grep", "wc", "docker", "systemctl", "find",
}
_DOCKER_READ_ONLY = {"ps", "logs", "inspect", "stats", "images", "top", "version", "info"}
_SYSTEMCTL_READ_ONLY = {"status", "list-units", "is-active", "is-enabled", "show", "list-unit-files"}
_SHELL_META = re.compile(r"[;&|<>`$(){}\\\n\r]")
_SENSITIVE_FRAGMENTS = (".pem", ".env", "id_rsa", "id_ed25519", "/etc/shadow", "sudoers", ".ssh/", ".private.json")


def _check_read_only(command: str) -> str:
    """Devolve '' se o comando é de inspeção aceite, senão o motivo da recusa."""
    if _SHELL_META.search(command):
        return "contém encadeamento, redirecionamento ou substituição de shell"
    parts = command.split()
    if not parts:
        return "comando vazio"
    prog = parts[0]
    if prog not in _READ_ONLY_COMMANDS:
        return f"'{prog}' não está na lista de comandos de inspeção"
    if prog == "docker" and (len(parts) < 2 or parts[1] not in _DOCKER_READ_ONLY):
        return "só subcomandos docker de leitura (ps, logs, inspect, stats, images, top, version, info)"
    if prog == "systemctl" and (len(parts) < 2 or parts[1] not in _SYSTEMCTL_READ_ONLY):
        return "só subcomandos systemctl de leitura (status, list-units, is-active, ...)"
    if prog == "find" and any(a in parts for a in ("-exec", "-execdir", "-delete", "-ok", "-fprint")):
        return "find com ação de escrita/execução"
    lowered = command.lower()
    for frag in _SENSITIVE_FRAGMENTS:
        if frag in lowered:
            return f"referência a caminho sensível ('{frag}')"
    return ""


@mcp.tool()
def srv_api_run_safe_command(command: str) -> Dict[str, Any]:
    """
    Executa comandos de INSPEÇÃO (só leitura) no servidor remoto, sem encadeamento de shell.
    Aceita: ls, cat, head, tail, ps, df, du, free, uptime, hostname, uname, whoami, date, journalctl,
    grep, wc, find (sem -exec/-delete), docker (ps, logs, inspect, stats, images, top, version, info)
    e systemctl (status, list-units, is-active, ...). Tudo o resto é recusado e registado.
    Todas as chamadas ficam em .runtime/gateway-audit.jsonl.
    Args:
        command: Comando simples, ex: 'ls -la /var/www', 'docker ps', 'ps aux'
    """
    forbidden = ["rm -rf", "mkfs", "dd if=", ":(){ :|:& };:", "shutdown", "reboot", "init 0"]
    for danger in forbidden:
        if danger in command:
            _audit("run_safe_command", command, f"blocked: {danger}")
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Comando bloqueado por política de segurança do MCP: contém '{danger}'"
            }

    if not ALLOW_ARBITRARY:
        reason = _check_read_only(command)
        if reason:
            _audit("run_safe_command", command, f"refused: {reason}")
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Recusado: {reason}. Fora da inspeção é preciso autorização humana e SRV_API_ALLOW_ARBITRARY=1 no .env."
            }

    return _exec_command(command, tool="run_safe_command")

if __name__ == "__main__":
    mcp.run()
