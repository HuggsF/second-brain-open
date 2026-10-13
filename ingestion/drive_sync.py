"""
Google Drive Knowledge Sync Engine for KIOSK Second Brain.
Automates discovery, download, extraction and indexing of product and technical
documents from shared Google Drive folders into the Vault and Knowledge Graph.
"""

import sys
import os
import re
import json
import hashlib
import subprocess
import unicodedata
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Optional Rich console
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    console = Console(force_terminal=True)
except ImportError:
    class DummyConsole:
        def print(self, *args, **kwargs):
            clean = " ".join(str(a) for a in args)
            clean = re.sub(r'\[/?[a-zA-Z0-9_\s#]+\]', '', clean)
            print(clean)
    console = DummyConsole()


def reference_slug(filename: str) -> str:
    """ASCII kebab-case slug for a Drive file name, without extensions or copy suffixes."""
    name = filename
    while True:
        stripped = re.sub(r"\.(pdf|pptx?|docx?|xlsx?|png|jpe?g|txt)$", "", name.strip(), flags=re.IGNORECASE)
        if stripped == name.strip():
            break
        name = stripped
    name = re.sub(r"-\s*Microsoft PowerPoint", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\(\d+\)", "", name)
    name = re.sub(r"\.(pptx?|pdf|docx?)(_\d+_)?", "", name, flags=re.IGNORECASE)
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")


class DriveSyncEngine:
    DEFAULT_FOLDER_ID = "1iHodiTblGvqfGND-HdW3e2FrkbEHYPHr"

    def __init__(
        self,
        folder_id: Optional[str] = None,
        base_dir: Optional[Path] = None,
        chrome_path: Optional[str] = None
    ):
        self.folder_id = folder_id or self.DEFAULT_FOLDER_ID
        self.base_dir = Path(base_dir or Path(__file__).resolve().parent.parent)
        self.downloads_dir = self.base_dir / "downloads_drive"
        self.extracted_dir = self.base_dir / "extracted_drive"
        self.references_dir = self.base_dir / "vault" / "product" / "references"
        self.manifest_file = self.downloads_dir / "manifest.json"

        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.extracted_dir.mkdir(parents=True, exist_ok=True)
        self.references_dir.mkdir(parents=True, exist_ok=True)

        self.chrome_path = chrome_path or self._find_browser()
        self.manifest = self._load_manifest()

    def _find_browser(self) -> str:
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            "chrome",
            "google-chrome",
            "msedge"
        ]
        for c in candidates:
            if os.path.isabs(c) and os.path.exists(c):
                return c
        return candidates[0]

    def _load_manifest(self) -> Dict[str, Any]:
        if self.manifest_file.exists():
            try:
                return json.loads(self.manifest_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_manifest(self):
        self.manifest_file.write_text(json.dumps(self.manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    def discover_files(self) -> List[Dict[str, str]]:
        """Usa headless Chrome para renderizar o DOM do Google Drive e extrair IDs e títulos."""
        folder_url = f"https://drive.google.com/drive/folders/{self.folder_id}"
        console.print(f"[bold cyan]🔍 Varrendo Google Drive:[/bold cyan] {folder_url}")

        cmd = [
            self.chrome_path,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--virtual-time-budget=9000",
            "--dump-dom",
            folder_url
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=30)
            dom_text = res.stdout
        except Exception as e:
            console.print(f"[bold red]Falha ao executar browser headless:[/bold red] {e}")
            return []

        # Extrair arquivos do DOM do Google Drive
        discovered = []
        labels = re.findall(r'aria-label="([^"]+(?:\.pdf|\.png|\.docx?|\.xlsx?|\.pptx?|\.txt|\.md)[^"]*)"', dom_text)
        unique_labels = sorted(set(labels))

        for raw_label in unique_labels:
            # Limpar rótulo (Google Drive adiciona 'PDF Compartilhado' ou 'Imagem Compartilhado')
            clean_name = re.sub(r'\s+(?:PDF|Imagem|Planilha|Documento|Apresentação)?\s*Compartilhado.*$', '', raw_label, flags=re.IGNORECASE).strip()
            
            # Buscar o file ID associado nos arredores do rótulo no HTML
            idx = dom_text.find(raw_label)
            file_id = None
            if idx != -1:
                snippet = dom_text[max(0, idx - 600):min(len(dom_text), idx + 600)]
                ids = re.findall(r'data-id="([1a-zA-Z0-9_-]{25,})"', snippet)
                if not ids:
                    ids = re.findall(r'"([1a-zA-Z0-9_-]{28,35})"', snippet)
                if ids:
                    file_id = ids[0]

            if file_id and clean_name:
                discovered.append({
                    "id": file_id,
                    "filename": clean_name,
                    "raw_label": raw_label
                })

        console.print(f"  [green]✓ {len(discovered)} documentos identificados na pasta.[/green]")
        return discovered

    def download_file(self, file_id: str, filename: str) -> Optional[Path]:
        """Faz o download incremental do arquivo a partir do Google Drive."""
        dest_path = self.downloads_dir / filename
        url = f"https://drive.google.com/uc?export=download&id={file_id}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        # Verificar se já existe e está no manifesto
        if dest_path.exists() and dest_path.stat().st_size > 0:
            if file_id in self.manifest and self.manifest[file_id].get("status") == "downloaded":
                return dest_path

        console.print(f"  [yellow]⬇ Baixando:[/yellow] {filename}...")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp, open(dest_path, "wb") as out:
                data = resp.read()
                out.write(data)

            sha256 = hashlib.sha256(data).hexdigest()
            self.manifest[file_id] = {
                "id": file_id,
                "filename": filename,
                "size_bytes": len(data),
                "sha256": sha256,
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "status": "downloaded"
            }
            self._save_manifest()
            console.print(f"    [green]✓ Concluído ({len(data)} bytes, SHA-256: {sha256[:10]}...)[/green]")
            return dest_path
        except Exception as e:
            console.print(f"    [red]✗ Erro no download:[/red] {e}")
            return None

    def extract_text(self, file_path: Path) -> Optional[str]:
        """Extrai texto de PDF, PPTX/Slides, DOCX, TXT ou MD usando detecção de magic bytes."""
        suffix = file_path.suffix.lower()
        content = ""

        try:
            with open(file_path, "rb") as f:
                header = f.read(8)

            is_pdf = header.startswith(b"%PDF") or suffix == ".pdf"
            is_zip = header.startswith(b"PK\x03\x04")

            if is_pdf:
                from pypdf import PdfReader
                reader = PdfReader(str(file_path))
                pages_text = []
                for i, page in enumerate(reader.pages):
                    t = page.extract_text() or ""
                    pages_text.append(f"--- PÁGINA {i+1} ---\n{t}")
                content = "\n\n".join(pages_text)

            elif suffix in [".txt", ".md"]:
                content = file_path.read_text(encoding="utf-8", errors="ignore")

            elif is_zip and suffix == ".docx":
                with zipfile.ZipFile(file_path) as docx:
                    xml_content = docx.read("word/document.xml")
                    tree = ET.fromstring(xml_content)
                    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                    paragraphs = []
                    for p in tree.iterfind(".//w:p", ns):
                        texts = [node.text for node in p.iterfind(".//w:t", ns) if node.text]
                        if texts:
                            paragraphs.append("".join(texts))
                    content = "\n\n".join(paragraphs)

            elif is_zip and ("pptx" in suffix or "powerpoint" in file_path.name.lower()):
                with zipfile.ZipFile(file_path) as pptx:
                    slide_names = sorted([n for n in pptx.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")])
                    slides_text = []
                    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
                    for idx, sname in enumerate(slide_names):
                        xml_content = pptx.read(sname)
                        tree = ET.fromstring(xml_content)
                        texts = [node.text for node in tree.iterfind(".//a:t", ns) if node.text]
                        if texts:
                            slides_text.append(f"--- SLIDE {idx+1} ---\n" + "\n".join(texts))
                    content = "\n\n".join(slides_text)

            elif suffix in [".png", ".jpg", ".jpeg"]:
                content = f"[Arquivo de Imagem: {file_path.name} - Tamanho: {file_path.stat().st_size} bytes]"

            else:
                content = f"[Formato binário {suffix} registrado sem extração direta de texto]"

            # Salvar no diretório de extraídos
            out_txt = self.extracted_dir / f"{file_path.stem}.txt"
            out_txt.write_text(content, encoding="utf-8")
            return content
        except Exception as e:
            console.print(f"  [red]Erro ao extrair texto de {file_path.name}:[/red] {e}")
            return None

    def generate_vault_reference(self, filename: str, file_id: str, text: str, sha256: str) -> Path:
        """Cria uma nota estruturada no Vault em vault/product/references/ tornando o conhecimento rastreável.

        Uma nota que já cita o mesmo SHA-256 é reaproveitada e nunca sobrescrita (o mesmo arquivo
        pode aparecer no Drive com outro nome ou File ID).
        """
        if re.fullmatch(r"[0-9a-f]{64}", sha256 or ""):
            for existing in sorted(self.references_dir.glob("*.md")):
                if f"source_sha256: {sha256}" in existing.read_text(encoding="utf-8-sig"):
                    return existing
        ref_path = self.references_dir / f"{reference_slug(filename)}.md"
        if ref_path.exists():
            ref_path = self.references_dir / f"{reference_slug(filename)}-{file_id[:8].lower()}.md"

        sample = text[:800].replace("\r", "").strip() if text else "Sem conteúdo textual extraído."

        md_content = f"""---
type: reference
status: reference
date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
source: Google Drive (AI Product Specialist)
drive_file_id: {json.dumps(file_id)}
source_sha256: {sha256}
original_file: {json.dumps(filename, ensure_ascii=False)}
---
# Referência de Produto: {filename}

## 1. Metadados do Documento

- **Nome do Arquivo Original:** `{filename}`
- **Identificador no Drive:** `{file_id}`
- **Tamanho do Texto Extraído:** {len(text)} caracteres
- **Rastreabilidade:** extraído pelo `DriveSyncEngine`; o texto bruto fica fora do repositório.

## 2. Excerto Inicial & Tópicos Principais

```text
{sample}
```

## 3. Conexões de Produto & Squads

- [[product-vision-ai-specialist]] · Alinhamento estratégico com a Visão de Produto da KIOSK Brands.
- [[prd-second-brain-platform-v2]] · Requisitos e critérios de aceitação do sistema autônomo.
- [[product-discovery-rice-radar]] · Matriz RICE e esteira de Discovery contínuo.
"""
        ref_path.write_bytes(md_content.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
        return ref_path

    def run(self, auto_rebuild_graph: bool = True) -> Dict[str, Any]:
        """Executa a sincronização completa: Descoberta ➔ Download ➔ Extração ➔ Vault ➔ Grafo."""
        console.print("\n[bold green]======================================================================[/bold green]")
        console.print("[bold green]   KIOSK SECOND BRAIN · GOOGLE DRIVE KNOWLEDGE SYNC PIPELINE          [/bold green]")
        console.print("[bold green]======================================================================[/bold green]\n")

        files = self.discover_files()
        if not files:
            console.print("[yellow]Nenhum arquivo encontrado ou acesso restrito.[/yellow]")
            return {"discovered": 0, "downloaded": 0, "extracted": 0}

        downloaded_count = 0
        extracted_count = 0

        for f in files:
            path = self.download_file(f["id"], f["filename"])
            if path:
                downloaded_count += 1
                text = self.extract_text(path)
                if text:
                    extracted_count += 1
                    meta = self.manifest.get(f["id"], {})
                    sha = meta.get("sha256", "desconhecido")
                    ref_file = self.generate_vault_reference(f["filename"], f["id"], text, sha)
                    console.print(f"    [cyan]↳ Gerada nota no Vault:[/cyan] vault/{ref_file.relative_to(self.base_dir / 'vault').as_posix()}")

        # Re-indexar o grafo do Second Brain se solicitado
        if auto_rebuild_graph:
            console.print("\n[bold cyan]🔄 Re-indexando Grafo e Snapshot do Second Brain...[/bold cyan]")
            try:
                build_script = self.base_dir / "dashboard" / "build_graph.py"
                res = subprocess.run([sys.executable, str(build_script)], capture_output=True, text=True, encoding="utf-8")
                if res.returncode == 0:
                    console.print(f"  [green]✓ Grafo atualizado com sucesso: {res.stdout.strip()}[/green]")
                else:
                    console.print(f"  [red]Erro ao atualizar grafo:[/red] {res.stderr}")
            except Exception as e:
                console.print(f"  [red]Falha ao chamar build_graph.py:[/red] {e}")

        console.print("\n[bold green]======================================================================[/bold green]")
        console.print(f"[bold green]✓ Sincronização concluída: {downloaded_count} baixados, {extracted_count} notas geradas.[/bold green]")
        console.print("[bold green]======================================================================[/bold green]\n")

        return {
            "discovered": len(files),
            "downloaded": downloaded_count,
            "extracted": extracted_count
        }


if __name__ == "__main__":
    folder_arg = sys.argv[1] if len(sys.argv) > 1 else None
    engine = DriveSyncEngine(folder_id=folder_arg)
    engine.run()
