# ADR-010: DriveSyncEngine — Pipeline Automatizado de Ingestão de Conhecimento via Google Drive

## Status
Aceito

## Data
2026-10-12

## Contexto
O Second Brain precisa de um mecanismo robusto e reutilizável para sincronizar documentos de produto e formação do Google Drive para o Vault local, garantindo rastreabilidade de conteúdo (SHA-256), extração textual automática (PDF, PPTX, DOCX, TXT, imagens) e atualização do grafo de conhecimento. Anteriormente, a ingestão era feita manualmente, copiando arquivos e criando notas no Vault sem integridade verificável.

### Problemas Enfrentados
- Documentos de referência estratégica (formações PM3, PMBOK, materiais de produto) ficavam isolados no Google Drive, fora do alcance do pipeline de busca semântica do Second Brain.
- Não havia checksum (hash) dos arquivos baixados, impossibilitando a detecção de alterações ou re-downloads desnecessários.
- Apresentações PowerPoint exportadas pelo Google Drive como PDF continham extensão `.pptx` mas magic bytes `%PDF`, causando falhas em parsers baseados exclusivamente em extensão de arquivo.
- Apresentações PPTX nativas (formato Open XML/ZIP) não eram suportadas para extração textual, resultando em notas vazias de 87 bytes.
- A atualização do grafo de conhecimento (`dashboard/build_graph.py`) não era acionada automaticamente após ingestão.

## Alternativas Consideradas

### Opção A: Google Drive API com OAuth2 e Service Account
- **Prós:** API oficial, metadados ricos, suporte a streaming.
- **Contras:** Requer configuração de credenciais OAuth2/service account no GCP. Complexidade para um caso de uso de pasta pública compartilhada. Over-engineering para a necessidade atual.

### Opção B: Headless Chrome + Download Direto via URL Pública (Escolhida)
- **Prós:** Zero dependência de credenciais ou GCP. Funciona com pastas públicas ou compartilhadas. Headless Chrome renderiza o DOM do Drive para descobrir IDs e nomes de arquivos. Download via `drive.usercontent.google.com` com streaming de chunks. Compatível com a infraestrutura existente (Chrome já instalado).
- **Contras:** Depende da estrutura do DOM do Google Drive (pode quebrar se Google alterar o HTML). Limitado a pastas compartilhadas publicamente ou com link.

### Opção C: Selenium com Navegação Completa
- **Prós:** Suporte total a interação dinâmica.
- **Contras:** Pesado, lento, frágil. Requer chromedriver separado. Desnecessário para leitura de DOM estático.

## Decisão
Implementar o **DriveSyncEngine** como classe Python reutilizável em `ingestion/drive_sync.py`, acessível tanto via importação direta quanto via CLI (`python cli.py drive-sync [--folder-id]`).

### 1. Arquitetura do Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    DriveSyncEngine Pipeline                     │
├─────────────────────────────────────────────────────────────────┤
│ 1. DISCOVER  │ Headless Chrome (--headless=new --dump-dom)      │
│              │ Regex em aria-label para extrair filenames        │
│              │ Regex em data-id / proximidade para file IDs     │
├──────────────┼──────────────────────────────────────────────────┤
│ 2. DOWNLOAD  │ urllib com streaming de chunks (64KB)            │
│              │ SHA-256 calculado sobre todo o conteúdo binário  │
│              │ Manifest JSON incremental (skip se hash idêntico)│
├──────────────┼──────────────────────────────────────────────────┤
│ 3. EXTRACT   │ Magic bytes detection:                           │
│              │   %PDF → pypdf (extração por página)             │
│              │   PK\x03\x04 + .docx → zipfile + word/document  │
│              │   PK\x03\x04 + .pptx/powerpoint → ppt/slides/*  │
│              │   .txt/.md → leitura direta UTF-8                │
│              │   .png/.jpg → placeholder com metadados          │
│              │ Output: extracted_drive/{stem}.txt                │
├──────────────┼──────────────────────────────────────────────────┤
│ 4. VAULT     │ Slug do filename → vault/product/references/     │
│              │ Nota estruturada com SHA-256, File ID, excerpt   │
│              │ Tags: #status/reference                          │
├──────────────┼──────────────────────────────────────────────────┤
│ 5. RE-INDEX  │ Execução automática de build_graph.py            │
│              │ Atualização do snapshot_id do grafo               │
└──────────────┴──────────────────────────────────────────────────┘
```

### 2. Detecção por Magic Bytes (Resolução do Problema PPTX/PDF)
O Google Drive exporta apresentações PPTX como PDF quando acessadas via download direto. Isso significa que o arquivo salvo como `04_Como_Modelos_de_IA_Aprendem.pptx Microsoft PowerPoint` tem extensão aparente `.pptx` mas começa com `%PDF-1.4`. A solução:
1. Ler os primeiros 8 bytes do arquivo (`header`).
2. Se `header.startswith(b"%PDF")` → tratar como PDF via `pypdf`, independentemente da extensão.
3. Se `header.startswith(b"PK\x03\x04")` e nome contém `pptx`/`powerpoint` → extrair slides XML do ZIP Open XML.
4. Se `header.startswith(b"PK\x03\x04")` e extensão `.docx` → extrair parágrafos do `word/document.xml`.

### 3. Extração de Slides PPTX Nativos
Para apresentações PPTX genuínas (formato Open XML ZIP):
```python
with zipfile.ZipFile(file_path) as pptx:
    slide_names = sorted([n for n in pptx.namelist()
                          if n.startswith("ppt/slides/slide") and n.endswith(".xml")])
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    for idx, sname in enumerate(slide_names):
        tree = ET.fromstring(pptx.read(sname))
        texts = [node.text for node in tree.iterfind(".//a:t", ns) if node.text]
```

### 4. Manifest Incremental
O arquivo `downloads_drive/manifest.json` armazena para cada `file_id`:
- `filename`, `size_bytes`, `sha256`, `downloaded_at`, `status`.
- Em sincronizações subsequentes, arquivos com hash idêntico ao manifest são skippados.

### 5. Comando CLI
```bash
python cli.py drive-sync                                    # Pasta padrão
python cli.py drive-sync --folder-id 1iHodiTblGvqfGND-...   # Pasta específica
```

## Consequências

### Positivas
- **23 documentos** sincronizados da nova pasta com SHA-256 verificável em uma única execução.
- Pipeline 100% reutilizável: basta alterar o `folder_id` para sincronizar qualquer pasta pública do Drive.
- Detecção por magic bytes resolve o problema de extensões incorretas do Google Drive exportando PPTX como PDF.
- Grafo do Second Brain atualizado automaticamente após ingestão (93 fontes ativas).
- Extração textual agora cobre PDFs (14.109 - 734.555 chars), PPTX nativos (22.846 - 28.321 chars) e DOCX.

### Desafios / Riscos
- Se o Google alterar a estrutura do DOM do Drive (atributos `aria-label`, `data-id`), a fase de Discovery pode quebrar — mitigar com fallback para regex mais amplo.
- PDFs com fontes Type1 emitem warnings de `fontTools` via `pypdf`, mas a extração funciona normalmente.
- Arquivos protegidos por permissão (não-públicos) não podem ser baixados via URL direta — necessário compartilhamento com link.
- Apresentações com conteúdo predominantemente visual (gráficos, screenshots) geram textos curtos na extração.

## Times Impactados
- **Engenharia Full-Cycle (Hugo Melo):** Responsável pela manutenção do DriveSyncEngine e pela configuração de novas pastas.
- **Squad de Knowledge & RAG:** Consumidor das notas geradas em `vault/product/references/` para busca semântica.
- **Squad de Avaliação & Evals:** As notas de referência alimentam o Golden Dataset com novos cenários de avaliação.

## Referências
- [[ingestion/drive_sync.py]] — Código-fonte do DriveSyncEngine
- [[product/product-vision-ai-specialist]] — Seção 10 (Relação com Documentos do Vault)
- [[ADR-005-arvore-de-evidencias-regras-playbooks-execucoes]] — Padrão de rastreabilidade SHA-256 no Vault
