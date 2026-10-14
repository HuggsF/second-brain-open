"""Regras de comandos de inspeção (só leitura) para run_safe_command.

Defesa em camadas, não uma fronteira de segurança: a fronteira real é o
utilizador SSH ter só permissões de leitura no servidor.
"""
import re
import unicodedata

READ_ONLY_COMMANDS = frozenset({
    "ls", "cat", "head", "tail", "ps", "df", "du", "free", "uptime", "hostname", "uname",
    "whoami", "date", "journalctl", "grep", "wc", "docker", "systemctl", "find",
})
DOCKER_READ_ONLY = frozenset({"ps", "logs", "inspect", "stats", "images", "top", "version", "info"})
SYSTEMCTL_READ_ONLY = frozenset({"status", "list-units", "is-active", "is-enabled", "show", "list-unit-files"})
SHELL_META = re.compile(r"[;&|<>`$(){}\\\n\r]")
SENSITIVE_FRAGMENTS = (".pem", ".env", "id_rsa", "id_ed25519", "/etc/shadow", "sudoers", ".ssh/", ".private.json")
BLOCKED_PHRASES = ("rm -rf", "mkfs", "dd if=", ":(){ :|:& };:", "shutdown", "reboot", "init 0")


def blocked_phrase(command: str) -> str:
    """Devolve a primeira frase proibida contida no comando, ou ''."""
    for phrase in BLOCKED_PHRASES:
        if phrase in command:
            return phrase
    return ""


def check_read_only(command: str) -> str:
    """Devolve '' se o comando é de inspeção aceite, senão o motivo da recusa."""
    if any(unicodedata.category(ch) == "Cc" for ch in command):
        return "contém caracteres de controle"
    if SHELL_META.search(command):
        return "contém encadeamento, redirecionamento ou substituição de shell"
    parts = command.split()
    if not parts:
        return "comando vazio"
    prog = parts[0]
    if prog not in READ_ONLY_COMMANDS:
        return f"'{prog}' não está na lista de comandos de inspeção"
    if prog == "docker" and (len(parts) < 2 or parts[1] not in DOCKER_READ_ONLY):
        return "só subcomandos docker de leitura (ps, logs, inspect, stats, images, top, version, info)"
    if prog == "systemctl" and (len(parts) < 2 or parts[1] not in SYSTEMCTL_READ_ONLY):
        return "só subcomandos systemctl de leitura (status, list-units, is-active, ...)"
    if prog == "find" and any(a in parts for a in ("-exec", "-execdir", "-delete", "-ok", "-fprint")):
        return "find com ação de escrita/execução"
    lowered = command.lower()
    for frag in SENSITIVE_FRAGMENTS:
        if frag in lowered:
            return f"referência a caminho sensível ('{frag}')"
    return ""
