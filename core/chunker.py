import re
from pathlib import Path
import yaml
from typing import Dict, List, Any
from config import settings

class MarkdownChunker:
    def __init__(self, chunk_size: int = settings.chunk_size, overlap: int = settings.chunk_overlap):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_file(self, file_path: Path, vault_dir: Path = settings.vault_dir) -> List[Dict[str, Any]]:
        text = file_path.read_text(encoding="utf-8")
        text, front = self._split_frontmatter(text)
        extra = {key: str(front[name]) for key, name in (("status", "status"), ("doc_type", "type")) if front.get(name) is not None}
        # Ontology-aware metadata from frontmatter
        for field in ("related", "bounded_context", "entities"):
            val = front.get(field)
            if val is not None:
                if isinstance(val, list):
                    extra[field] = ",".join(str(v) for v in val)
                else:
                    extra[field] = str(val)
        rel_path = file_path.relative_to(vault_dir).as_posix()
        category = file_path.parent.name if file_path.parent != vault_dir else "general"

        # Extrair título principal
        title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        doc_title = title_match.group(1).strip() if title_match else file_path.stem.replace("-", " ").title()

        # Quebrar em seções baseadas em headers (## ou ###)
        sections = self._split_by_headers(text)

        chunks: List[Dict[str, Any]] = []
        chunk_idx = 0

        for header, content in sections:
            if not content.strip():
                continue
            
            # Se o conteúdo da seção couber no chunk_size
            if len(content) <= self.chunk_size:
                full_chunk_text = f"# {doc_title}\n## {header}\n\n{content.strip()}"
                chunks.append({
                    "id": f"{rel_path}:{chunk_idx}",
                    "content": full_chunk_text,
                    "metadata": {
                        "file_path": rel_path,
                        "doc_title": doc_title,
                        "section": header,
                        "category": category,
                        "chunk_index": chunk_idx,
                        **extra
                    }
                })
                chunk_idx += 1
            else:
                # Subdividir seção longa com overlap
                sub_chunks = self._sliding_window_split(content, self.chunk_size, self.overlap)
                for sub in sub_chunks:
                    full_chunk_text = f"# {doc_title}\n## {header}\n\n{sub.strip()}"
                    chunks.append({
                        "id": f"{rel_path}:{chunk_idx}",
                        "content": full_chunk_text,
                        "metadata": {
                            "file_path": rel_path,
                            "doc_title": doc_title,
                            "section": header,
                            "category": category,
                            "chunk_index": chunk_idx,
                            **extra
                        }
                    })
                    chunk_idx += 1

        return chunks

    @staticmethod
    def _split_frontmatter(text: str) -> tuple[str, Dict[str, Any]]:
        """Remove o frontmatter YAML inicial do texto e devolve os campos dele."""
        match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
        if not match:
            return text, {}
        try:
            data = yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            return text, {}
        return text[match.end():], data if isinstance(data, dict) else {}

    def _split_by_headers(self, text: str) -> List[tuple[str, str]]:
        # Regex para identificar ## ou ###
        lines = text.split("\n")
        sections: List[tuple[str, str]] = []
        current_header = "Introdução"
        current_lines: List[str] = []

        for line in lines:
            header_match = re.match(r"^(#{2,3})\s+(.+)$", line)
            if header_match:
                if current_lines:
                    sections.append((current_header, "\n".join(current_lines)))
                    current_lines = []
                current_header = header_match.group(2).strip()
            else:
                current_lines.append(line)

        if current_lines:
            sections.append((current_header, "\n".join(current_lines)))

        return sections

    def _sliding_window_split(self, text: str, size: int, overlap: int) -> List[str]:
        words = text.split()
        chunks: List[str] = []
        start = 0
        while start < len(words):
            end = start + size // 5  # Estimativa aproximada de palavras por caracteres
            chunk_words = words[start:end]
            chunks.append(" ".join(chunk_words))
            if end >= len(words):
                break
            start = end - (overlap // 5)
        return chunks
