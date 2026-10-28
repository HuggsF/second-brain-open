import os
from pathlib import Path
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent

class Settings(BaseModel):
    base_dir: Path = BASE_DIR
    # Vault Paths
    vault_dir: Path = BASE_DIR / "vault"
    adrs_dir: Path = BASE_DIR / "vault" / "adrs"
    systems_dir: Path = BASE_DIR / "vault" / "systems"
    domain_dir: Path = BASE_DIR / "vault" / "domain"
    daily_dir: Path = BASE_DIR / "vault" / "daily"
    hash_manifest_path: Path = BASE_DIR / ".brain_hashes.json"

    # Qdrant Config
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "kiosk_brain")
    vector_size: int = 768  # Standard for nomic-embed-text

    # Ollama Config (Local CPU)
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    embedding_model: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    # Prefixos de tarefa do nomic-embed-text; mudar qualquer um muda o esquema e exige rebuild.
    embed_query_prefix: str = os.getenv("OLLAMA_EMBED_QUERY_PREFIX", "search_query: ")
    embed_document_prefix: str = os.getenv("OLLAMA_EMBED_DOCUMENT_PREFIX", "search_document: ")
    chat_model: str = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2:3b")
    default_profile: str = "kiosk"  # perfil usado quando BRAIN_PROFILE não está definido

    # Environment file (for API keys loaded via load_dotenv)
    env_file: Path = Path(os.getenv("BRAIN_ENV_FILE", str(BASE_DIR / ".env")))

    # Chunking Config
    chunk_size: int = 800
    chunk_overlap: int = 150

    # Retrieval scope and selection
    space_id: str = os.getenv("BRAIN_SPACE", "kiosk")
    retrieval_min_score: float = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.65"))
    retrieval_max_drop: float = float(os.getenv("RETRIEVAL_MAX_DROP", "0.10"))
    retrieval_max_per_doc: int = int(os.getenv("RETRIEVAL_MAX_PER_DOC", "2"))

settings = Settings()
