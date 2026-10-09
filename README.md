# Second Brain - KIOSK Brands (Developer Edition)

Sistema de base de conhecimento técnico local e offline, construído com **Qdrant (Vector DB)**, **Ollama (LLM Local)**, **Model Context Protocol (MCP)** e **Markdown diferencial**.

---

## 🎯 Contexto e Domínio
Desenvolvido para centralizar o conhecimento de engenharia da holding **KIOSK Brands** (marcas Touti, Amavia e Yes! Cosméticos), documentando:
- **ADRs (Architecture Decision Records):** Ex: Migração SULTS e Holmes → Salesforce.
- **Sistemas Legados & ERP:** Arquitetura do SAP, rastreamento de pedidos de quiosques e catálogo de produtos.
- **Model Context Protocol (MCP):** Isolamento de credenciais e exposição de ferramentas inteligentes para IDEs e futuros agentes autônomos.

---

## ⚡ Comandos Rápidos da CLI

Ative o ambiente virtual ou execute via `.venv`:

```powershell
# 1. Verificar saúde dos serviços (Qdrant, Ollama, Vault)
.\.venv\Scripts\python.exe cli.py status

# 2. Sincronizar o Vault Markdown com o Qdrant (Diferencial com hash SHA256)
.\.venv\Scripts\python.exe cli.py sync

# 3. Fazer uma pergunta técnica para o Second Brain (com RAG local)
.\.venv\Scripts\python.exe cli.py ask "Por que estamos migrando do SULTS para o Salesforce?"
.\.venv\Scripts\python.exe cli.py ask "Qual é o problema de tracking de pedidos no SAP?"

# 4. Iniciar monitoramento contínuo em tempo real (Watcher automático)
.\.venv\Scripts\python.exe ingestion/scheduler.py
```

---

## 🔒 Servidor MCP (Model Context Protocol)

O servidor MCP está registrado globalmente no IDE em `C:\Users\HugoMelo\.gemini\config\mcp_config.json`:

```json
{
  "mcpServers": {
    "kiosk-second-brain": {
      "command": "C:\\KIOSK\\second-brain\\.venv\\Scripts\\python.exe",
      "args": ["C:\\KIOSK\\second-brain\\mcp_servers\\brain_mcp.py"]
    }
  }
}
```

### Ferramentas expostas pelo MCP:
- `search_knowledge_base(query, category)`: Busca semântica vetorial no Qdrant.
- `get_adr(adr_identifier)`: Leitura integral de uma ADR por código ou título.
- `get_system_architecture(system_name)`: Detalhamento de arquitetura de um sistema (sap, sults, holmes, salesforce).
- `get_brain_status()`: Métricas de pontos e coleções indexadas.

---

## 📂 Estrutura do Vault Markdown

- `vault/adrs/`: Decisões técnicas formais para alinhamento com a equipe.
- `vault/systems/`: Mapeamento de integrações, APIs e contratos de sistemas.
- `vault/domain/`: Regras de negócio da holding e catálogo das marcas.
- `vault/daily/`: Notas rápidas de reuniões do Teams e onboarding.

 
## Frontend Second Brain: quatro waves locais

O dashboard local inclui biblioteca, grafo, consultas com fontes e editor de planos. Consulte vault/systems/second-brain-frontend-waves.md para decisões, benchmark, testes e limites.

~~~powershell
.\.venv\Scripts\python.exe dashboard\build_graph.py
.\.venv\Scripts\python.exe dashboard\serve.py --port 8847
~~~

Abra http://127.0.0.1:8847/dashboard/. O servidor serve apenas o dashboard e escuta em loopback. É necessário gerar o snapshot e recarregar após alterar o vault. Se a porta estiver ocupada, use outra porta.

Esta UI usa recuperação textual e relações locais; não está conectada a execução de agentes, busca vetorial, respostas de modelo ou observabilidade ao vivo. O backend Qdrant/Ollama/MCP existente é separado. Arquitetura futura: dashboard/analysis/graphrag-multiagent-contract.md.

Os originais foram preservados em .frontend-backups, com manifesto SHA-256. Testes: node --test --test-isolation=none dashboard/tests/*.test.cjs (Node24 usado) e .\.venv\Scripts\python.exe dashboard\tests\test_build_graph.py.

## BFF local e observabilidade (wave 1)

Execute `.venv\Scripts\python.exe -m backend.server` na raiz. Abra o link de uso único em `.runtime/connect.url`. O dashboard autenticado fica em `http://127.0.0.1:8848/dashboard/`. Coletas de produção/homologação por MCP são somente leitura. GraphRAG semântico e execução multiagente permanecem não conectados.

Veja [contrato e operação](vault/systems/second-brain-observability-bff.md) para pin do servidor, testes, segurança, limites e rollback local.
