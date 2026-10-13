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
    chat_model: str = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2:3b")
    default_profile: str = "kiosk"  # perfil usado quando BRAIN_PROFILE não está definido

    # Chunking Config
    chunk_size: int = 800
    chunk_overlap: int = 150

settings = Settings()
