---
type: system
status: active
date: 2026-10-21
related: [hub-regras-operacionais-codex, hub-arquitetura-ddd-typescript]
source: hub-logistico/docs/contratos/mensageria.md
source_branch: working-tree
---

# Contrato: Mensageria (Envios, Templates e Jornadas)

Contrato consumido pelo frontend `web/` nas telas **Acompanhamento de Envios**,
**Templates** e **Jornadas**. Sem endpoint (404/405/501), tela mostra "Dados ainda não
disponíveis nesta versão do Hub".

Tipos TS: `web/src/features/mensageria/types.ts`. Autenticação: header `Authorization`
com token cru (sem `Bearer`), perfis `admin` e `operador`.

## Envios

Um envio é uma mensagem disparada por uma etapa de jornada para um destinatário, num canal.

### Ciclo de Vida

```
enfileirado → enviado → entregue → lido
```

Terminais fora do funil: `falhou`, `ignorado`.

Origem: régua de cobrança (títulos SAP) e jornadas logísticas (pedido Bling, rastreio J&T).

### `GET /api/mensageria/envios/resumo`

Query: `dataInicio`, `dataFim` (AAAA-MM-DD, America/Sao_Paulo), `canal?`, `status?`,
`contexto?`, `busca?`.

Resposta:

```json
{
  "periodo": { "dataInicio": "2026-10-21", "dataFim": "2026-10-21" },
  "total": 1284,
  "porStatus": { "enfileirado": 38, "enviado": 112, "entregue": 401, "lido": 642, "falhou": 47, "ignorado": 44 },
  "porCanal": { "whatsapp": 1031, "email": 221, "sms": 32 },
  "falhasHoje": 6,
  "atualizadoEm": "2026-10-21T13:00:00Z"
}
```

`porStatus` é o status **atual** de cada envio. O front acumula o funil
(entregues = entregue + lido; disparados = total − ignorado).

### `GET /api/mensageria/envios`

Mesma query + `pagina` (1+), `porPagina` (25). Ordem: `criadoEm` desc.

Campos relevantes por envio:

| Campo | Tipo | Observação |
|-------|------|------------|
| `canal` | `whatsapp\|email\|sms` | — |
| `status` | ciclo acima | — |
| `destinatario` | string | **Mascarado** pelo backend |
| `contexto` | `logistica\|cobranca` | — |
| `jornada` | `{id, nome}\|null` | `null` para envio avulso |
| `template` | `{id, nome}` | — |
| `referencia` | `{tipo, valor}` | tipo: `pedido\|nf\|titulo` |
| `tentativas` | number | — |
| `erro` | string | ex: "Evolution API: número sem WhatsApp" |
| `eventos` | array | histórico de transições com timestamp |

`busca` procura em referência e destinatário (completo, comparado no servidor).

## Templates

Corpo e assunto em **Liquid** (subconjunto em `web/src/features/mensageria/liquid.ts`).
Variáveis permitidas por contexto em `web/src/features/mensageria/variaveis.ts`.

| Método | Rota | Corpo/Resposta |
|--------|------|----------------|
| GET | `/api/mensageria/templates` | Lista com `id, nome, canal, contexto, ativo, variaveis[], atualizadoEm` |
| GET | `/api/mensageria/templates/:id` | Detalhe com `assunto` e `corpo` |
| POST | `/api/mensageria/templates` | Criar → `{ id }` |
| PUT | `/api/mensageria/templates/:id` | Atualizar → `{ ok: true }` |

### Regras

- `canal`: `whatsapp` | `email` | `sms`
- `contexto`: `logistica` | `cobranca`
- `assunto` só em e-mail (vazio nos demais)
- Limites renderizados: WhatsApp 4.096 chars, SMS 160 chars

**INV-10 (mensageria):** O backend deve renderizar com o mesmo catálogo e recusar envio se
houver variável desconhecida, filtro/tag desconhecidos ou variável vazia sem `default`.

## Jornadas

As jornadas usam a API de workflows existente (`/api/workflows`, `WorkflowRouter`),
renomeada apenas na interface.

O resumo da listagem aceita três campos **opcionais** para a tela de Jornadas:

```json
{ "contexto": "logistica", "canais": ["whatsapp"], "envios24h": 612 }
```

### Blocos Novos no Catálogo

Definidos em `web/src/features/workflows/constants.ts`:

| Bloco | Tipo | Detalhes |
|-------|------|----------|
| `rastreio_atualizado` | Entrada | Evento logístico |
| `titulo_vencido` | Entrada | Fase COBRANCA 0–3, limite diário |
| `enviar_mensagem` | Ação | canal, `template_id`, destinatário Liquid, janela de envio; portas `enviado` e `falhou` |

A simulação do painel de testes não envia nada (`simulado: true`).
