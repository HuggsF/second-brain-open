import os
from pathlib import Path
from pydantic import BaseModel, Field, field_validator

BASE_DIR = Path(__file__).resolve().parent


def _caminho(variavel: str, padrao: Path) -> Path:
    """Caminho vindo do ambiente; relativo resolve contra a raiz do repositório, não contra o diretório atual."""
    caminho = Path(os.getenv(variavel, str(padrao)))
    return caminho if caminho.is_absolute() else BASE_DIR / caminho


class Settings(BaseModel):
    base_dir: Path = BASE_DIR
    # Vault: o repositório não traz um; aponte BRAIN_VAULT_DIR para o seu.
    vault_dir: Path = Field(default_factory=lambda: _caminho("BRAIN_VAULT_DIR", BASE_DIR / "vault"))
    adrs_dir: Path = Field(default_factory=lambda: _caminho("BRAIN_VAULT_DIR", BASE_DIR / "vault") / "adrs")
    systems_dir: Path = Field(default_factory=lambda: _caminho("BRAIN_VAULT_DIR", BASE_DIR / "vault") / "systems")
    domain_dir: Path = Field(default_factory=lambda: _caminho("BRAIN_VAULT_DIR", BASE_DIR / "vault") / "domain")
    daily_dir: Path = Field(default_factory=lambda: _caminho("BRAIN_VAULT_DIR", BASE_DIR / "vault") / "daily")
    fichas_dir: Path = BASE_DIR / "fichas"

    # Índice de busca: um arquivo SQLite derivado do vault, reconstruível, nunca commitado.
    index_path: Path = Field(default_factory=lambda: _caminho("BRAIN_INDEX_PATH", BASE_DIR / ".runtime" / "indice-busca.db"))
    space_id: str = Field(default_factory=lambda: os.getenv("BRAIN_SPACE_ID", "principal"))

    # Piso da busca. O score é BM25 (sem teto). Sem piso absoluto por padrão: ele depende do vault e
    # não foi medido neste repositório. `max_drop` é a queda tolerada em relação ao melhor resultado.
    retrieval_min_score: float = Field(default_factory=lambda: float(os.getenv("RETRIEVAL_MIN_SCORE", "0")))
    retrieval_max_drop: float = Field(default_factory=lambda: float(os.getenv("RETRIEVAL_MAX_DROP", "0.50")), validate_default=True)
    retrieval_max_per_doc: int = Field(default_factory=lambda: int(os.getenv("RETRIEVAL_MAX_PER_DOC", "1")))

    # Banco vetorial: campos mantidos só até a remoção do motor vetorial, no fim desta mudança.
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "second_brain")
    vector_size: int = 768
    embedding_model: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    # Servidor local de modelos: opcional, usado só para gerar a resposta do `ask`.
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    chat_model: str = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2:3b")
    default_profile: str = "example"  # perfil usado quando BRAIN_PROFILE não está definido

    # Environment file (for API keys loaded via load_dotenv)
    env_file: Path = Path(os.getenv("BRAIN_ENV_FILE", str(BASE_DIR / ".env")))

    # Chunking Config
    chunk_size: int = 800
    chunk_overlap: int = 150

    @field_validator("retrieval_max_drop")
    @classmethod
    def _queda_na_faixa(cls, valor: float) -> float:
        if not 0.0 <= valor <= 1.0:
            raise ValueError("RETRIEVAL_MAX_DROP deve estar entre 0 e 1")
        return valor


settings = Settings()
