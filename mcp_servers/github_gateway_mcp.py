import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
import httpx
from fastmcp import FastMCP

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

mcp = FastMCP("GitHub Gateway")

def _get_headers() -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "KIOSK-Second-Brain-MCP"
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers

@mcp.tool()
def github_check_status() -> Dict[str, Any]:
    """
    Verifica se o token do GitHub configurado no .env é válido e retorna o usuário autenticado.
    """
    if not GITHUB_TOKEN:
        return {
            "status": "unconfigured",
            "message": "GITHUB_TOKEN não configurado no arquivo C:\\KIOSK\\second-brain\\.env"
        }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get("https://api.github.com/user", headers=_get_headers())
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "status": "authenticated",
                    "username": data.get("login"),
                    "name": data.get("name"),
                    "company": data.get("company"),
                    "total_private_repos": data.get("total_private_repos", 0),
                    "public_repos": data.get("public_repos", 0)
                }
            return {
                "status": "error",
                "http_status": resp.status_code,
                "message": resp.text
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
def github_list_repositories(org_name: Optional[str] = None, per_page: int = 30) -> List[Dict[str, Any]]:
    """
    Lista os repositórios disponíveis na conta ou em uma organização específica do GitHub.
    Args:
        org_name: (Opcional) Nome da organização da holding (ex: 'kiosk-brands'). Se omitido, lista da conta do usuário.
        per_page: Quantidade máxima de repositórios a retornar (padrão: 30).
    """
    if not GITHUB_TOKEN:
        return [{"error": "GITHUB_TOKEN não encontrado no .env"}]

    url = f"https://api.github.com/orgs/{org_name}/repos" if org_name else "https://api.github.com/user/repos"
    params = {"per_page": per_page, "sort": "updated", "direction": "desc"}

    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url, headers=_get_headers(), params=params)
            if resp.status_code == 200:
                repos = []
                for r in resp.json():
                    repos.append({
                        "name": r.get("name"),
                        "full_name": r.get("full_name"),
                        "private": r.get("private"),
                        "html_url": r.get("html_url"),
                        "description": r.get("description"),
                        "language": r.get("language"),
                        "updated_at": r.get("updated_at")
                    })
                return repos
            return [{"error": f"HTTP {resp.status_code}: {resp.text}"}]
    except Exception as e:
        return [{"error": str(e)}]

@mcp.tool()
def github_get_repository_details(owner: str, repo: str) -> Dict[str, Any]:
    """
    Recupera detalhes aprofundados de um repositório específico (branches, último commit, linguagens).
    Args:
        owner: Proprietário ou organização (ex: 'kioskbrands' ou seu usuário).
        repo: Nome do repositório.
    """
    if not GITHUB_TOKEN:
        return {"error": "GITHUB_TOKEN não configurado"}

    try:
        with httpx.Client(timeout=20.0) as client:
            # 1. Info básica
            resp_repo = client.get(f"https://api.github.com/repos/{owner}/{repo}", headers=_get_headers())
            if resp_repo.status_code != 200:
                return {"error": f"Repositório não encontrado ou sem permissão: HTTP {resp_repo.status_code}"}
            repo_data = resp_repo.json()

            # 2. Último commit
            resp_commits = client.get(f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=1", headers=_get_headers())
            last_commit = None
            if resp_commits.status_code == 200 and resp_commits.json():
                c = resp_commits.json()[0]
                last_commit = {
                    "sha": c.get("sha")[:7],
                    "message": c.get("commit", {}).get("message"),
                    "author": c.get("commit", {}).get("author", {}).get("name"),
                    "date": c.get("commit", {}).get("author", {}).get("date")
                }

            return {
                "name": repo_data.get("name"),
                "full_name": repo_data.get("full_name"),
                "description": repo_data.get("description"),
                "default_branch": repo_data.get("default_branch"),
                "is_private": repo_data.get("private"),
                "language": repo_data.get("language"),
                "last_commit": last_commit
            }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def github_search_code(query: str, owner: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Busca por termos de código (ex: 'Service Layer', 'SAP', 'Saurus') nos repositórios da conta.
    Args:
        query: Termo de busca (ex: 'hub-sap', 'HCO003').
        owner: (Opcional) Filtrar por usuário ou organização.
    """
    if not GITHUB_TOKEN:
        return [{"error": "GITHUB_TOKEN não configurado"}]

    full_query = f"{query} user:{owner}" if owner else query
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                "https://api.github.com/search/code",
                headers=_get_headers(),
                params={"q": full_query, "per_page": 10}
            )
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                results = []
                for item in items:
                    results.append({
                        "file_name": item.get("name"),
                        "path": item.get("path"),
                        "repo": item.get("repository", {}).get("full_name"),
                        "html_url": item.get("html_url")
                    })
                return results
            return [{"error": f"HTTP {resp.status_code}: {resp.text}"}]
    except Exception as e:
        return [{"error": str(e)}]

@mcp.tool()
def github_list_contents(owner: str, repo: str, path: str = "") -> List[Dict[str, Any]]:
    """
    Lista os arquivos e diretórios de um repositório no GitHub para auditoria de estrutura.
    Args:
        owner: Dono do repositório (ex: 'userTI10').
        repo: Nome do repositório (ex: 'projetodeengenharia').
        path: Caminho relativo dentro do repositório (opcional, padrão: raiz "").
    """
    if not GITHUB_TOKEN:
        return [{"error": "GITHUB_TOKEN não configurado"}]

    clean_path = path.strip("/")
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{clean_path}" if clean_path else f"https://api.github.com/repos/{owner}/{repo}/contents"

    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url, headers=_get_headers())
            if resp.status_code == 200:
                items = resp.json()
                if isinstance(items, list):
                    return [
                        {
                            "name": i.get("name"),
                            "path": i.get("path"),
                            "type": i.get("type"), # 'file' ou 'dir'
                            "size": i.get("size")
                        }
                        for i in items
                    ]
                elif isinstance(items, dict):
                    # Se for um único arquivo
                    return [{
                        "name": items.get("name"),
                        "path": items.get("path"),
                        "type": items.get("type"),
                        "size": items.get("size")
                    }]
            return [{"error": f"HTTP {resp.status_code}: {resp.text}"}]
    except Exception as e:
        return [{"error": str(e)}]

if __name__ == "__main__":
    mcp.run()

