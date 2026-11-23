import re
from pathlib import Path, PurePosixPath
import yaml
from typing import Dict, List, Any
from config import settings

class MarkdownChunker:
    def __init__(self, chunk_size: int = settings.chunk_size, overlap: int = settings.chunk_overlap):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_file(self, file_path: Path, vault_dir: Path = settings.vault_dir) -> List[Dict[str, Any]]:
        rel_path = file_path.relative_to(vault_dir).as_posix()
        return self.chunk_bytes(file_path.read_bytes(), rel_path, vault_dir)

    def chunk_bytes(self, raw: bytes, rel_path: str, vault_dir: Path = settings.vault_dir) -> List[Dict[str, Any]]:
        """Gera os chunks a partir dos bytes já lidos (o sync lê cada arquivo uma vez só).

        `rel_path` é relativo ao vault, em formato POSIX; `vault_dir` fica pela simetria com
        `chunk_file`. As quebras de linha são normalizadas como na leitura em modo texto.
        """
        decoded = raw.decode("utf-8").replace("\r\n", "\n")
        text = decoded.replace("\r", "\n")
        # Linha original (1-based, só CRLF -> LF) de cada linha do texto normalizado; um CR isolado
        # vira quebra no texto, mas continua dentro da mesma linha do arquivo original.
        line_map = [number for number, line in enumerate(decoded.split("\n"), start=1) for _ in range(line.count("\r") + 1)]
        rel = PurePosixPath(rel_path)
        text, front, offset = self._split_frontmatter(text)
        extra = {key: str(front[name]) for key, name in (("status", "status"), ("doc_type", "type")) if front.get(name) is not None}
        # Ontology-aware metadata from frontmatter
        for field in ("related", "bounded_context", "entities"):
            val = front.get(field)
            if val is not None:
                if isinstance(val, list):
                    extra[field] = ",".join(str(v) for v in val)
                else:
                    extra[field] = str(val)
        # Pasta-mãe imediata, como antes (file_path.parent.name); arquivo na raiz do vault -> "general".
        category = rel.parent.name or "general"

        # Extrair título principal
        title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        doc_title = title_match.group(1).strip() if title_match else rel.stem.replace("-", " ").title()

        # Quebrar em seções baseadas em headers (## ou ###)
        sections = self._split_by_headers(text, line_map[offset:])

        chunks: List[Dict[str, Any]] = []
        chunk_idx = 0

        for header, section_lines in sections:
            content = "\n".join(line for _, line in section_lines)
            if not content.strip():
                continue

            # Se o conteúdo da seção couber no chunk_size: uma peça só, da primeira à última linha não vazia
            if len(content) <= self.chunk_size:
                filled = [number for number, line in section_lines if line.strip()]
                pieces = [(content, filled[0], filled[-1])]
            else:
                # Subdividir seção longa com overlap
                pieces = self._sliding_window_split(section_lines, self.chunk_size, self.overlap)

            for piece, line_start, line_end in pieces:
                full_chunk_text = f"# {doc_title}\n## {header}\n\n{piece.strip()}"
                chunks.append({
                    "id": f"{rel_path}:{chunk_idx}",
                    "content": full_chunk_text,
                    "metadata": {
                        "file_path": rel_path,
                        "doc_title": doc_title,
                        "section": header,
                        "category": category,
                        "chunk_index": chunk_idx,
                        "line_start": line_start,
                        "line_end": line_end,
                        **extra
                    }
                })
                chunk_idx += 1

        return chunks

    @staticmethod
    def _split_frontmatter(text: str) -> tuple[str, Dict[str, Any], int]:
        """Remove o frontmatter YAML inicial do texto e devolve os campos dele.

        O terceiro valor é quantas linhas do início foram removidas (0 sem frontmatter).
        """
        match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
        if not match:
            return text, {}, 0
        try:
            data = yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            return text, {}, 0
        return text[match.end():], data if isinstance(data, dict) else {}, match.group(0).count("\n")

    def _split_by_headers(self, text: str, line_numbers: List[int]) -> List[tuple[str, List[tuple[int, str]]]]:
        """Quebra o texto em seções (## ou ###), cada uma com `(linha_original, texto)` por linha.

        `line_numbers[i]` é a linha original da i-ésima linha de `text`. A linha do cabeçalho não entra
        na seção; o título `#` fica na seção "Introdução".
        """
        lines = text.split("\n")
        sections: List[tuple[str, List[tuple[int, str]]]] = []
        current_header = "Introdução"
        current_lines: List[tuple[int, str]] = []

        for number, line in zip(line_numbers, lines):
            header_match = re.match(r"^(#{2,3})\s+(.+)$", line)
            if header_match:
                if current_lines:
                    sections.append((current_header, current_lines))
                    current_lines = []
                current_header = header_match.group(2).strip()
            else:
                current_lines.append((number, line))

        if current_lines:
            sections.append((current_header, current_lines))

        return sections

    def _sliding_window_split(self, section_lines: List[tuple[int, str]], size: int, overlap: int) -> List[tuple[str, int, int]]:
        """Janela deslizante sobre as palavras da seção: `(texto, linha_inicial, linha_final)` por peça."""
        words: List[str] = []
        word_lines: List[int] = []
        for number, line in section_lines:
            line_words = line.split()
            words.extend(line_words)
            word_lines.extend([number] * len(line_words))
        chunks: List[tuple[str, int, int]] = []
        start = 0
        while start < len(words):
            end = start + size // 5  # Estimativa aproximada de palavras por caracteres
            chunk_words = words[start:end]
            span = word_lines[start:end] or [section_lines[0][0], section_lines[-1][0]]
            chunks.append((" ".join(chunk_words), span[0], span[-1]))
            if end >= len(words):
                break
            start = end - (overlap // 5)
        return chunks
