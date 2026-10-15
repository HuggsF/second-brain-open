"""GitHub Gateway MCP — Full API Coverage.

Expõe todas as funcionalidades úteis da GitHub REST API v3:
  - Autenticação & Status
  - Repositórios (list, details, contents, branches, tags, commits)
  - Pull Requests (CRUD, merge, files, reviews, reviewers)
  - Issues (CRUD, comments, labels)
  - Releases (CRUD, generate notes)
  - Actions / Workflows (list, trigger, runs, jobs, logs)
  - Search (code, issues, repos)
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
import httpx
from fastmcp import FastMCP
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.trace_middleware import TraceMiddleware

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

API = "https://api.github.com"

# ─────────────────────────────────────────────────────────────────────────────
# MULTI-TOKEN SUPPORT
# Loads GITHUB_TOKEN_KIOSK and GITHUB_TOKEN_HUGGS from .env, resolves each
# to its GitHub username, and auto-routes API calls based on the repo owner.
# Falls back to legacy GITHUB_TOKEN if specific tokens are not found.
# ─────────────────────────────────────────────────────────────────────────────

_NAMED_TOKENS: Dict[str, str] = {}  # env_suffix → raw token
_TOKEN_BY_USERNAME: Dict[str, str] = {}  # github_username (lowercase) → raw token
_DEFAULT_TOKEN: str = ""  # fallback


def _init_tokens() -> None:
    """Populate _NAMED_TOKENS, _TOKEN_BY_USERNAME and _DEFAULT_TOKEN at import."""
    global _DEFAULT_TOKEN

    # Collect all GITHUB_TOKEN_* env vars
    for key, val in os.environ.items():
        if key.startswith("GITHUB_TOKEN_") and val:
            suffix = key[len("GITHUB_TOKEN_"):]
            _NAMED_TOKENS[suffix] = val

    # Legacy single-token fallback
    legacy = os.getenv("GITHUB_TOKEN", "")

    # Resolve each named token to a GitHub username
    for suffix, token in _NAMED_TOKENS.items():
        try:
            with httpx.Client(timeout=10.0) as c:
                r = c.get(
                    f"{API}/user",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                        "User-Agent": "KIOSK-Second-Brain-MCP",
                    },
                )
                if r.status_code == 200:
                    username = r.json().get("login", "").lower()
                    if username:
                        _TOKEN_BY_USERNAME[username] = token
        except Exception:
            pass  # Token inválido ou sem rede — ignora silenciosamente

    # Set default token: first named token found, or legacy
    if _NAMED_TOKENS:
        _DEFAULT_TOKEN = next(iter(_NAMED_TOKENS.values()))
    elif legacy:
        _DEFAULT_TOKEN = legacy

    # Also resolve legacy token if not already mapped
    if legacy and not _TOKEN_BY_USERNAME:
        try:
            with httpx.Client(timeout=10.0) as c:
                r = c.get(
                    f"{API}/user",
                    headers={
                        "Authorization": f"Bearer {legacy}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                        "User-Agent": "KIOSK-Second-Brain-MCP",
                    },
                )
                if r.status_code == 200:
                    username = r.json().get("login", "").lower()
                    if username:
                        _TOKEN_BY_USERNAME[username] = legacy
        except Exception:
            pass


# Initialize on module import
_init_tokens()


def _resolve_token(owner: Optional[str] = None) -> str:
    """Pick the correct token for a given repo owner.

    Resolution order:
    1. Exact match on owner username (case-insensitive) → that token
    2. Default token (first named token or legacy GITHUB_TOKEN)
    """
    if owner:
        token = _TOKEN_BY_USERNAME.get(owner.lower())
        if token:
            return token
    return _DEFAULT_TOKEN


mcp = FastMCP("GitHub Gateway")
mcp.add_middleware(TraceMiddleware("GitHub Gateway"))


def _headers(owner: Optional[str] = None) -> Dict[str, str]:
    token = _resolve_token(owner)
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "KIOSK-Second-Brain-MCP",
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _get(path: str, params: Optional[dict] = None, timeout: float = 20.0, owner: Optional[str] = None) -> Any:
    """GET helper — returns parsed JSON or error dict."""
    with httpx.Client(timeout=timeout) as c:
        r = c.get(f"{API}{path}", headers=_headers(owner), params=params)
        if r.status_code in (200, 201):
            return r.json()
        return {"error": f"HTTP {r.status_code}", "message": r.text[:500]}


def _post(path: str, body: Optional[dict] = None, timeout: float = 20.0, owner: Optional[str] = None) -> Any:
    with httpx.Client(timeout=timeout) as c:
        r = c.post(f"{API}{path}", headers=_headers(owner), json=body)
        if r.status_code in (200, 201, 204):
            return r.json() if r.content else {"ok": True}
        return {"error": f"HTTP {r.status_code}", "message": r.text[:500]}


def _patch(path: str, body: Optional[dict] = None, timeout: float = 20.0, owner: Optional[str] = None) -> Any:
    with httpx.Client(timeout=timeout) as c:
        r = c.patch(f"{API}{path}", headers=_headers(owner), json=body)
        if r.status_code in (200, 201):
            return r.json()
        return {"error": f"HTTP {r.status_code}", "message": r.text[:500]}


def _put(path: str, body: Optional[dict] = None, timeout: float = 20.0, owner: Optional[str] = None) -> Any:
    with httpx.Client(timeout=timeout) as c:
        r = c.put(f"{API}{path}", headers=_headers(owner), json=body)
        if r.status_code in (200, 204):
            return r.json() if r.content else {"ok": True}
        return {"error": f"HTTP {r.status_code}", "message": r.text[:500]}


def _delete(path: str, timeout: float = 20.0, owner: Optional[str] = None) -> Any:
    with httpx.Client(timeout=timeout) as c:
        r = c.delete(f"{API}{path}", headers=_headers(owner))
        if r.status_code in (200, 204):
            return {"ok": True}
        return {"error": f"HTTP {r.status_code}", "message": r.text[:500]}


def _check(owner: Optional[str] = None) -> Optional[dict]:
    token = _resolve_token(owner)
    if not token:
        return {"error": "Nenhum GITHUB_TOKEN configurado no .env"}
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 1. AUTH & STATUS
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def github_check_status(task_id: Optional[str] = None) -> Dict[str, Any]:
    """Verifica se o token GitHub é válido e retorna o usuário autenticado (usa token padrão).
    task_id: optional label that groups this call with others of the same task
    """
    err = _check()
    if err:
        return err
    data = _get("/user")
    if "error" in data:
        return data
    return {
        "status": "authenticated",
        "username": data.get("login"),
        "name": data.get("name"),
        "company": data.get("company"),
        "total_private_repos": data.get("total_private_repos", 0),
        "public_repos": data.get("public_repos", 0),
        "configured_accounts": list(_TOKEN_BY_USERNAME.keys()),
    }


@mcp.tool()
def github_check_all_tokens(task_id: Optional[str] = None) -> Dict[str, Any]:
    """Verifica todos os tokens GitHub configurados e mostra qual usuário cada um autentica.
    Mostra o mapeamento completo owner→token para debug.
    task_id: optional label that groups this call with others of the same task
    """
    results: Dict[str, Any] = {
        "named_tokens": {},
        "token_by_username": {k: "***" + v[-4:] for k, v in _TOKEN_BY_USERNAME.items()},
        "default_token_suffix": "***" + _DEFAULT_TOKEN[-4:] if _DEFAULT_TOKEN else "none",
    }

    for suffix, token in _NAMED_TOKENS.items():
        try:
            with httpx.Client(timeout=10.0) as c:
                r = c.get(
                    f"{API}/user",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                        "User-Agent": "KIOSK-Second-Brain-MCP",
                    },
                )
                if r.status_code == 200:
                    user_data = r.json()
                    results["named_tokens"][suffix] = {
                        "status": "valid",
                        "username": user_data.get("login"),
                        "name": user_data.get("name"),
                        "scopes": r.headers.get("x-oauth-scopes", "N/A"),
                    }
                else:
                    results["named_tokens"][suffix] = {
                        "status": "invalid",
                        "http_code": r.status_code,
                        "message": r.text[:200],
                    }
        except Exception as e:
            results["named_tokens"][suffix] = {"status": "error", "message": str(e)[:200]}

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 2. REPOSITORIES
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def github_list_repositories(
    org_name: Optional[str] = None,
    per_page: int = 30,
    task_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lista repositórios da conta pessoal ou de uma organização.
    Args:
        org_name: Nome da organização (ex: 'kiosk-brands'). Se omitido, lista do usuário.
        per_page: Máximo de repos a retornar (padrão: 30).
    task_id: optional label that groups this call with others of the same task
    """
    err = _check()
    if err:
        return [err]
    path = f"/orgs/{org_name}/repos" if org_name else "/user/repos"
    data = _get(path, {"per_page": per_page, "sort": "updated", "direction": "desc"})
    if isinstance(data, dict) and "error" in data:
        return [data]
    return [
        {
            "name": r.get("name"),
            "full_name": r.get("full_name"),
            "private": r.get("private"),
            "html_url": r.get("html_url"),
            "description": r.get("description"),
            "language": r.get("language"),
            "default_branch": r.get("default_branch"),
            "updated_at": r.get("updated_at"),
        }
        for r in data
    ]


@mcp.tool()
def github_get_repository_details(
    owner: str, repo: str, task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Detalhes aprofundados de um repositório (branches, último commit, linguagens).
    Args:
        owner: Proprietário ou organização (ex: 'HuggsF').
        repo: Nome do repositório.
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return err
    repo_data = _get(f"/repos/{owner}/{repo}", owner=owner)
    if "error" in repo_data:
        return repo_data
    commits = _get(f"/repos/{owner}/{repo}/commits", {"per_page": 1}, owner=owner)
    last_commit = None
    if isinstance(commits, list) and commits:
        c = commits[0]
        last_commit = {
            "sha": c.get("sha", "")[:7],
            "message": c.get("commit", {}).get("message"),
            "author": c.get("commit", {}).get("author", {}).get("name"),
            "date": c.get("commit", {}).get("author", {}).get("date"),
        }
    return {
        "name": repo_data.get("name"),
        "full_name": repo_data.get("full_name"),
        "description": repo_data.get("description"),
        "default_branch": repo_data.get("default_branch"),
        "is_private": repo_data.get("private"),
        "language": repo_data.get("language"),
        "open_issues_count": repo_data.get("open_issues_count"),
        "forks_count": repo_data.get("forks_count"),
        "stargazers_count": repo_data.get("stargazers_count"),
        "last_commit": last_commit,
    }


@mcp.tool()
def github_list_contents(
    owner: str, repo: str, path: str = "", ref: Optional[str] = None,
    task_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lista arquivos e diretórios de um caminho dentro do repositório.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        path: Caminho relativo (padrão: raiz).
        ref: Branch/tag/SHA (padrão: branch default).
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return [err]
    clean = path.strip("/")
    p = f"/repos/{owner}/{repo}/contents/{clean}" if clean else f"/repos/{owner}/{repo}/contents"
    params = {"ref": ref} if ref else None
    data = _get(p, params, owner=owner)
    if isinstance(data, dict) and "error" in data:
        return [data]
    items = data if isinstance(data, list) else [data]
    return [
        {"name": i.get("name"), "path": i.get("path"), "type": i.get("type"), "size": i.get("size")}
        for i in items
    ]


@mcp.tool()
def github_list_branches(
    owner: str, repo: str, per_page: int = 30, task_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lista as branches de um repositório.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        per_page: Máximo de branches a retornar (padrão: 30).
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return [err]
    data = _get(f"/repos/{owner}/{repo}/branches", {"per_page": per_page}, owner=owner)
    if isinstance(data, dict) and "error" in data:
        return [data]
    return [
        {"name": b.get("name"), "sha": b.get("commit", {}).get("sha", "")[:7], "protected": b.get("protected")}
        for b in data
    ]


@mcp.tool()
def github_list_tags(
    owner: str, repo: str, per_page: int = 30, task_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lista as tags de um repositório.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        per_page: Máximo (padrão: 30).
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return [err]
    data = _get(f"/repos/{owner}/{repo}/tags", {"per_page": per_page}, owner=owner)
    if isinstance(data, dict) and "error" in data:
        return [data]
    return [{"name": t.get("name"), "sha": t.get("commit", {}).get("sha", "")[:7]} for t in data]


@mcp.tool()
def github_list_commits(
    owner: str, repo: str, sha: Optional[str] = None,
    per_page: int = 20, task_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lista os commits recentes de um repositório ou branch.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        sha: Branch ou SHA base (padrão: default branch).
        per_page: Máximo (padrão: 20).
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return [err]
    params: dict = {"per_page": per_page}
    if sha:
        params["sha"] = sha
    data = _get(f"/repos/{owner}/{repo}/commits", params, owner=owner)
    if isinstance(data, dict) and "error" in data:
        return [data]
    return [
        {
            "sha": c.get("sha", "")[:7],
            "message": (c.get("commit", {}).get("message") or "")[:200],
            "author": c.get("commit", {}).get("author", {}).get("name"),
            "date": c.get("commit", {}).get("author", {}).get("date"),
        }
        for c in data
    ]


@mcp.tool()
def github_compare_commits(
    owner: str, repo: str, base: str, head: str, task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Compara duas refs (branches, tags, SHAs) e retorna diferenças.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        base: Ref base (ex: 'main').
        head: Ref head (ex: 'fix/my-branch').
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return err
    data = _get(f"/repos/{owner}/{repo}/compare/{base}...{head}", owner=owner)
    if "error" in data:
        return data
    return {
        "status": data.get("status"),
        "ahead_by": data.get("ahead_by"),
        "behind_by": data.get("behind_by"),
        "total_commits": data.get("total_commits"),
        "files_changed": len(data.get("files", [])),
        "commits": [
            {"sha": c.get("sha", "")[:7], "message": (c.get("commit", {}).get("message") or "")[:120]}
            for c in data.get("commits", [])[:20]
        ],
        "files": [
            {"filename": f.get("filename"), "status": f.get("status"), "additions": f.get("additions"), "deletions": f.get("deletions")}
            for f in data.get("files", [])[:50]
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. PULL REQUESTS
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def github_list_pull_requests(
    owner: str, repo: str, state: str = "open", per_page: int = 20,
    task_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lista pull requests de um repositório.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        state: 'open', 'closed' ou 'all' (padrão: 'open').
        per_page: Máximo (padrão: 20).
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return [err]
    data = _get(f"/repos/{owner}/{repo}/pulls", {"state": state, "per_page": per_page, "sort": "updated", "direction": "desc"}, owner=owner)
    if isinstance(data, dict) and "error" in data:
        return [data]
    return [
        {
            "number": pr.get("number"),
            "title": pr.get("title"),
            "state": pr.get("state"),
            "user": pr.get("user", {}).get("login"),
            "head": pr.get("head", {}).get("ref"),
            "base": pr.get("base", {}).get("ref"),
            "created_at": pr.get("created_at"),
            "updated_at": pr.get("updated_at"),
            "html_url": pr.get("html_url"),
            "draft": pr.get("draft"),
            "mergeable_state": pr.get("mergeable_state"),
        }
        for pr in data
    ]


@mcp.tool()
def github_get_pull_request(
    owner: str, repo: str, pull_number: int, task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Obtém detalhes de uma pull request específica.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        pull_number: Número da PR.
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return err
    data = _get(f"/repos/{owner}/{repo}/pulls/{pull_number}", owner=owner)
    if "error" in data:
        return data
    return {
        "number": data.get("number"),
        "title": data.get("title"),
        "body": (data.get("body") or "")[:2000],
        "state": data.get("state"),
        "user": data.get("user", {}).get("login"),
        "head": data.get("head", {}).get("ref"),
        "base": data.get("base", {}).get("ref"),
        "mergeable": data.get("mergeable"),
        "merged": data.get("merged"),
        "commits": data.get("commits"),
        "additions": data.get("additions"),
        "deletions": data.get("deletions"),
        "changed_files": data.get("changed_files"),
        "html_url": data.get("html_url"),
        "labels": [l.get("name") for l in data.get("labels", [])],
        "reviewers": [r.get("login") for r in data.get("requested_reviewers", [])],
    }


@mcp.tool()
def github_create_pull_request(
    owner: str, repo: str, title: str, head: str, base: str,
    body: str = "", draft: bool = False, task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Cria uma nova pull request.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        title: Título da PR.
        head: Branch de origem (ex: 'fix/my-branch').
        base: Branch destino (ex: 'main').
        body: Corpo/descrição da PR (markdown).
        draft: Se True, cria como rascunho.
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return err
    payload = {"title": title, "head": head, "base": base, "body": body, "draft": draft}
    data = _post(f"/repos/{owner}/{repo}/pulls", payload, owner=owner)
    if "error" in data:
        return data
    return {
        "number": data.get("number"),
        "html_url": data.get("html_url"),
        "state": data.get("state"),
        "title": data.get("title"),
        "created_at": data.get("created_at"),
    }


@mcp.tool()
def github_update_pull_request(
    owner: str, repo: str, pull_number: int,
    title: Optional[str] = None, body: Optional[str] = None,
    state: Optional[str] = None, base: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Atualiza uma pull request existente (título, corpo, estado, base).
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        pull_number: Número da PR.
        title: Novo título (opcional).
        body: Novo corpo (opcional).
        state: 'open' ou 'closed' (opcional).
        base: Nova branch base (opcional).
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return err
    payload = {k: v for k, v in {"title": title, "body": body, "state": state, "base": base}.items() if v is not None}
    data = _patch(f"/repos/{owner}/{repo}/pulls/{pull_number}", payload, owner=owner)
    if "error" in data:
        return data
    return {"number": data.get("number"), "state": data.get("state"), "html_url": data.get("html_url"), "updated_at": data.get("updated_at")}


@mcp.tool()
def github_merge_pull_request(
    owner: str, repo: str, pull_number: int,
    merge_method: str = "merge",
    commit_title: Optional[str] = None,
    commit_message: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Faz merge de uma pull request.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        pull_number: Número da PR.
        merge_method: 'merge', 'squash' ou 'rebase' (padrão: 'merge').
        commit_title: Título do commit de merge (opcional).
        commit_message: Mensagem do commit de merge (opcional).
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return err
    payload: Dict[str, Any] = {"merge_method": merge_method}
    if commit_title:
        payload["commit_title"] = commit_title
    if commit_message:
        payload["commit_message"] = commit_message
    return _put(f"/repos/{owner}/{repo}/pulls/{pull_number}/merge", payload, owner=owner)


@mcp.tool()
def github_list_pr_files(
    owner: str, repo: str, pull_number: int, task_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lista os arquivos modificados em uma PR.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        pull_number: Número da PR.
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return [err]
    data = _get(f"/repos/{owner}/{repo}/pulls/{pull_number}/files", {"per_page": 100}, owner=owner)
    if isinstance(data, dict) and "error" in data:
        return [data]
    return [
        {
            "filename": f.get("filename"),
            "status": f.get("status"),
            "additions": f.get("additions"),
            "deletions": f.get("deletions"),
            "changes": f.get("changes"),
            "patch": (f.get("patch") or "")[:500],
        }
        for f in data
    ]


@mcp.tool()
def github_create_pr_review(
    owner: str, repo: str, pull_number: int,
    event: str = "COMMENT", body: str = "",
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Cria uma review em uma PR.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        pull_number: Número da PR.
        event: 'APPROVE', 'REQUEST_CHANGES' ou 'COMMENT'.
        body: Comentário da review.
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return err
    return _post(f"/repos/{owner}/{repo}/pulls/{pull_number}/reviews", {"event": event, "body": body}, owner=owner)


@mcp.tool()
def github_request_reviewers(
    owner: str, repo: str, pull_number: int,
    reviewers: List[str], task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Solicita revisores para uma PR.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        pull_number: Número da PR.
        reviewers: Lista de usernames dos revisores.
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return err
    return _post(f"/repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers", {"reviewers": reviewers}, owner=owner)


# ─────────────────────────────────────────────────────────────────────────────
# 4. ISSUES
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def github_list_issues(
    owner: str, repo: str, state: str = "open", labels: Optional[str] = None,
    per_page: int = 20, task_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lista issues de um repositório.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        state: 'open', 'closed' ou 'all' (padrão: 'open').
        labels: Filtrar por labels separadas por vírgula (ex: 'bug,priority').
        per_page: Máximo (padrão: 20).
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return [err]
    params: dict = {"state": state, "per_page": per_page, "sort": "updated", "direction": "desc"}
    if labels:
        params["labels"] = labels
    data = _get(f"/repos/{owner}/{repo}/issues", params, owner=owner)
    if isinstance(data, dict) and "error" in data:
        return [data]
    return [
        {
            "number": i.get("number"),
            "title": i.get("title"),
            "state": i.get("state"),
            "user": i.get("user", {}).get("login"),
            "labels": [l.get("name") for l in i.get("labels", [])],
            "created_at": i.get("created_at"),
            "html_url": i.get("html_url"),
            "is_pull_request": "pull_request" in i,
        }
        for i in data
    ]


@mcp.tool()
def github_create_issue(
    owner: str, repo: str, title: str, body: str = "",
    labels: Optional[List[str]] = None,
    assignees: Optional[List[str]] = None,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Cria uma nova issue.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        title: Título da issue.
        body: Corpo/descrição (markdown).
        labels: Lista de labels (ex: ['bug', 'priority']).
        assignees: Lista de usernames para assignar.
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return err
    payload: Dict[str, Any] = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels
    if assignees:
        payload["assignees"] = assignees
    data = _post(f"/repos/{owner}/{repo}/issues", payload, owner=owner)
    if "error" in data:
        return data
    return {"number": data.get("number"), "html_url": data.get("html_url"), "state": data.get("state"), "title": data.get("title")}


@mcp.tool()
def github_update_issue(
    owner: str, repo: str, issue_number: int,
    title: Optional[str] = None, body: Optional[str] = None,
    state: Optional[str] = None,
    labels: Optional[List[str]] = None,
    assignees: Optional[List[str]] = None,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Atualiza uma issue existente (título, corpo, estado, labels, assignees).
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        issue_number: Número da issue.
        title: Novo título (opcional).
        body: Novo corpo (opcional).
        state: 'open' ou 'closed' (opcional).
        labels: Nova lista de labels (substitui todas).
        assignees: Nova lista de assignees.
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return err
    payload = {k: v for k, v in {"title": title, "body": body, "state": state, "labels": labels, "assignees": assignees}.items() if v is not None}
    data = _patch(f"/repos/{owner}/{repo}/issues/{issue_number}", payload, owner=owner)
    if "error" in data:
        return data
    return {"number": data.get("number"), "state": data.get("state"), "html_url": data.get("html_url")}


@mcp.tool()
def github_create_issue_comment(
    owner: str, repo: str, issue_number: int, body: str,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Adiciona um comentário a uma issue ou PR (PRs também são issues).
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        issue_number: Número da issue ou PR.
        body: Texto do comentário (markdown).
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return err
    data = _post(f"/repos/{owner}/{repo}/issues/{issue_number}/comments", {"body": body}, owner=owner)
    if "error" in data:
        return data
    return {"id": data.get("id"), "html_url": data.get("html_url"), "created_at": data.get("created_at")}


@mcp.tool()
def github_add_labels(
    owner: str, repo: str, issue_number: int, labels: List[str],
    task_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Adiciona labels a uma issue ou PR.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        issue_number: Número da issue/PR.
        labels: Lista de labels a adicionar.
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return [err]
    data = _post(f"/repos/{owner}/{repo}/issues/{issue_number}/labels", {"labels": labels}, owner=owner)
    if isinstance(data, dict) and "error" in data:
        return [data]
    return [{"name": l.get("name"), "color": l.get("color")} for l in data]


# ─────────────────────────────────────────────────────────────────────────────
# 5. RELEASES
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def github_list_releases(
    owner: str, repo: str, per_page: int = 10, task_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lista releases de um repositório.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        per_page: Máximo (padrão: 10).
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return [err]
    data = _get(f"/repos/{owner}/{repo}/releases", {"per_page": per_page}, owner=owner)
    if isinstance(data, dict) and "error" in data:
        return [data]
    return [
        {
            "id": r.get("id"),
            "tag_name": r.get("tag_name"),
            "name": r.get("name"),
            "draft": r.get("draft"),
            "prerelease": r.get("prerelease"),
            "created_at": r.get("created_at"),
            "html_url": r.get("html_url"),
            "body": (r.get("body") or "")[:500],
        }
        for r in data
    ]


@mcp.tool()
def github_create_release(
    owner: str, repo: str, tag_name: str, name: str = "",
    body: str = "", draft: bool = False, prerelease: bool = False,
    target_commitish: Optional[str] = None,
    generate_release_notes: bool = False,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Cria uma nova release.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        tag_name: Nome da tag (ex: 'v1.0.0').
        name: Título da release.
        body: Notas da release (markdown).
        draft: Se True, cria como rascunho.
        prerelease: Se True, marca como pre-release.
        target_commitish: Branch ou SHA alvo (padrão: default branch).
        generate_release_notes: Se True, auto-gera notas baseadas nos commits.
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return err
    payload: Dict[str, Any] = {
        "tag_name": tag_name, "name": name or tag_name, "body": body,
        "draft": draft, "prerelease": prerelease, "generate_release_notes": generate_release_notes,
    }
    if target_commitish:
        payload["target_commitish"] = target_commitish
    data = _post(f"/repos/{owner}/{repo}/releases", payload, owner=owner)
    if "error" in data:
        return data
    return {"id": data.get("id"), "tag_name": data.get("tag_name"), "html_url": data.get("html_url")}


@mcp.tool()
def github_generate_release_notes(
    owner: str, repo: str, tag_name: str,
    previous_tag_name: Optional[str] = None,
    target_commitish: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Gera notas de release automaticamente baseadas nos commits entre tags.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        tag_name: Tag alvo para gerar notas.
        previous_tag_name: Tag anterior para comparar (opcional, auto-detecta).
        target_commitish: Branch ou SHA alvo.
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return err
    payload: Dict[str, Any] = {"tag_name": tag_name}
    if previous_tag_name:
        payload["previous_tag_name"] = previous_tag_name
    if target_commitish:
        payload["target_commitish"] = target_commitish
    return _post(f"/repos/{owner}/{repo}/releases/generate-notes", payload, owner=owner)


# ─────────────────────────────────────────────────────────────────────────────
# 6. ACTIONS / WORKFLOWS
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def github_list_workflows(
    owner: str, repo: str, task_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lista os workflows do GitHub Actions de um repositório.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return [err]
    data = _get(f"/repos/{owner}/{repo}/actions/workflows", owner=owner)
    if "error" in data:
        return [data]
    return [
        {"id": w.get("id"), "name": w.get("name"), "state": w.get("state"), "path": w.get("path")}
        for w in data.get("workflows", [])
    ]


@mcp.tool()
def github_list_workflow_runs(
    owner: str, repo: str, workflow_id: Optional[int] = None,
    status: Optional[str] = None, branch: Optional[str] = None,
    per_page: int = 10, task_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lista execuções de workflows (runs) do GitHub Actions.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        workflow_id: Filtrar por workflow específico (opcional).
        status: 'queued', 'in_progress', 'completed', 'success', 'failure' (opcional).
        branch: Filtrar por branch (opcional).
        per_page: Máximo (padrão: 10).
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return [err]
    path = f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs" if workflow_id else f"/repos/{owner}/{repo}/actions/runs"
    params: dict = {"per_page": per_page}
    if status:
        params["status"] = status
    if branch:
        params["branch"] = branch
    data = _get(path, params, owner=owner)
    if "error" in data:
        return [data]
    return [
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "status": r.get("status"),
            "conclusion": r.get("conclusion"),
            "head_branch": r.get("head_branch"),
            "event": r.get("event"),
            "created_at": r.get("created_at"),
            "html_url": r.get("html_url"),
            "run_number": r.get("run_number"),
        }
        for r in data.get("workflow_runs", [])
    ]


@mcp.tool()
def github_trigger_workflow(
    owner: str, repo: str, workflow_id: int,
    ref: str = "main", inputs: Optional[Dict[str, str]] = None,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Dispara manualmente um workflow do GitHub Actions (workflow_dispatch).
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        workflow_id: ID do workflow (obtido via github_list_workflows).
        ref: Branch ou tag para executar (padrão: 'main').
        inputs: Parâmetros de input definidos no workflow (opcional).
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return err
    payload: Dict[str, Any] = {"ref": ref}
    if inputs:
        payload["inputs"] = inputs
    return _post(f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches", payload, owner=owner)


@mcp.tool()
def github_get_workflow_run(
    owner: str, repo: str, run_id: int, task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Obtém detalhes de uma execução específica de workflow.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        run_id: ID da execução (run).
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return err
    data = _get(f"/repos/{owner}/{repo}/actions/runs/{run_id}", owner=owner)
    if "error" in data:
        return data
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "status": data.get("status"),
        "conclusion": data.get("conclusion"),
        "head_branch": data.get("head_branch"),
        "event": data.get("event"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "html_url": data.get("html_url"),
        "run_number": data.get("run_number"),
        "run_attempt": data.get("run_attempt"),
    }


@mcp.tool()
def github_cancel_workflow_run(
    owner: str, repo: str, run_id: int, task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Cancela uma execução de workflow em andamento.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        run_id: ID da execução a cancelar.
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return err
    return _post(f"/repos/{owner}/{repo}/actions/runs/{run_id}/cancel", owner=owner)


@mcp.tool()
def github_rerun_workflow(
    owner: str, repo: str, run_id: int, failed_only: bool = False,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Re-executa um workflow (todos os jobs ou apenas os falhados).
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        run_id: ID da execução a re-executar.
        failed_only: Se True, re-executa apenas os jobs que falharam.
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return err
    suffix = "rerun-failed-jobs" if failed_only else "rerun"
    return _post(f"/repos/{owner}/{repo}/actions/runs/{run_id}/{suffix}", owner=owner)


@mcp.tool()
def github_list_workflow_jobs(
    owner: str, repo: str, run_id: int, task_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lista os jobs de uma execução de workflow.
    Args:
        owner: Dono do repositório.
        repo: Nome do repositório.
        run_id: ID da execução.
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return [err]
    data = _get(f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs", owner=owner)
    if "error" in data:
        return [data]
    return [
        {
            "id": j.get("id"),
            "name": j.get("name"),
            "status": j.get("status"),
            "conclusion": j.get("conclusion"),
            "started_at": j.get("started_at"),
            "completed_at": j.get("completed_at"),
            "steps": [
                {"name": s.get("name"), "status": s.get("status"), "conclusion": s.get("conclusion")}
                for s in j.get("steps", [])
            ],
        }
        for j in data.get("jobs", [])
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 7. SEARCH
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def github_search_code(
    query: str, owner: Optional[str] = None, task_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Busca por código nos repositórios.
    Args:
        query: Termo de busca (ex: 'hub-sap', 'def process_order').
        owner: Filtrar por usuário ou organização (opcional).
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return [err]
    q = f"{query} user:{owner}" if owner else query
    data = _get("/search/code", {"q": q, "per_page": 15}, timeout=30.0, owner=owner)
    if isinstance(data, dict) and "error" in data:
        return [data]
    return [
        {"file_name": i.get("name"), "path": i.get("path"), "repo": i.get("repository", {}).get("full_name"), "html_url": i.get("html_url")}
        for i in data.get("items", [])
    ]


@mcp.tool()
def github_search_issues(
    query: str, owner: Optional[str] = None, state: Optional[str] = None,
    is_pr: Optional[bool] = None, per_page: int = 15,
    task_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Busca issues e/ou PRs por texto, labels, estado, etc.
    Args:
        query: Termo de busca (ex: 'bug deploy', 'label:P0').
        owner: Filtrar por usuário/org (opcional).
        state: 'open' ou 'closed' (opcional).
        is_pr: Se True filtra só PRs, se False só issues (opcional).
        per_page: Máximo (padrão: 15).
    task_id: optional label that groups this call with others of the same task
    """
    err = _check(owner)
    if err:
        return [err]
    parts = [query]
    if owner:
        parts.append(f"user:{owner}")
    if state:
        parts.append(f"state:{state}")
    if is_pr is True:
        parts.append("is:pr")
    elif is_pr is False:
        parts.append("is:issue")
    q = " ".join(parts)
    data = _get("/search/issues", {"q": q, "per_page": per_page, "sort": "updated"}, timeout=30.0, owner=owner)
    if isinstance(data, dict) and "error" in data:
        return [data]
    return [
        {
            "number": i.get("number"),
            "title": i.get("title"),
            "state": i.get("state"),
            "repo": i.get("repository_url", "").split("/repos/")[-1] if i.get("repository_url") else None,
            "html_url": i.get("html_url"),
            "labels": [l.get("name") for l in i.get("labels", [])],
            "is_pr": "pull_request" in i,
            "created_at": i.get("created_at"),
        }
        for i in data.get("items", [])
    ]


@mcp.tool()
def github_search_repos(
    query: str, language: Optional[str] = None,
    sort: str = "updated", per_page: int = 10,
    task_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Busca repositórios por nome, descrição ou tópicos.
    Args:
        query: Termo de busca (ex: 'kiosk', 'touti').
        language: Filtrar por linguagem (ex: 'python', 'typescript').
        sort: 'stars', 'forks', 'updated' (padrão: 'updated').
        per_page: Máximo (padrão: 10).
    task_id: optional label that groups this call with others of the same task
    """
    err = _check()
    if err:
        return [err]
    q = f"{query} language:{language}" if language else query
    data = _get("/search/repositories", {"q": q, "sort": sort, "per_page": per_page}, timeout=30.0)
    if isinstance(data, dict) and "error" in data:
        return [data]
    return [
        {
            "full_name": r.get("full_name"),
            "description": r.get("description"),
            "language": r.get("language"),
            "stargazers_count": r.get("stargazers_count"),
            "html_url": r.get("html_url"),
            "updated_at": r.get("updated_at"),
        }
        for r in data.get("items", [])
    ]


if __name__ == "__main__":
    mcp.run()
