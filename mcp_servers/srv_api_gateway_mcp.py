import os
import sys
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

def _get_ssh_client() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key = paramiko.RSAKey.from_private_key_file(KEY_PATH)
    client.connect(
        hostname=HOST,
        port=PORT,
        username=USER,
        pkey=key,
        timeout=15.0
    )
    return client

def _exec_command(cmd: str, timeout: int = 30) -> Dict[str, Any]:
    client = None
    try:
        client = _get_ssh_client()
        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        exit_code = stdout.channel.recv_exit_status()
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": out.strip(),
            "stderr": err.strip()
        }
    except Exception as e:
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
    res = _exec_command("hostname; uname -a; uptime")
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
    res = _exec_command(cmd)
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
    res = _exec_command(cmd)
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
    cmd = f"if command -v docker >/dev/null 2>&1 && docker ps -a --format '{{{{.Names}}}}' | grep -qw '{service_name}'; then docker logs --tail {lines} {service_name}; else journalctl -u {service_name} -n {lines} --no-pager 2>&1 || echo 'Serviço não encontrado'; fi"
    res = _exec_command(cmd)
    return res["stdout"] if res["success"] else f"Erro ao ler logs: {res['stderr']}"

@mcp.tool()
def srv_api_run_safe_command(command: str) -> Dict[str, Any]:
    """
    Executa comandos operacionais e de inspeção no servidor remoto de forma controlada.
    Comandos destrutivos diretos (como rm -rf, reboot, mkfs) são bloqueados por segurança.
    Args:
        command: Linha de comando a ser executada no servidor Linux (ex: 'ls -la /var/www', 'docker ps', 'ps aux')
    """
    forbidden = ["rm -rf", "mkfs", "dd if=", ":(){ :|:& };:", "shutdown", "reboot", "init 0"]
    for danger in forbidden:
        if danger in command:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Comando bloqueado por política de segurança do MCP: contém '{danger}'"
            }

    return _exec_command(command)

if __name__ == "__main__":
    mcp.run()
