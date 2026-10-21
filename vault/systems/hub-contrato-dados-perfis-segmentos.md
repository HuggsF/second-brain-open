---
type: system
status: active
date: 2026-10-21
related: [hub-regras-operacionais-codex, hub-ontologia-ddd-proposta]
source: hub-logistico/docs/contratos/dados.md
source_branch: working-tree
---

# Contrato: Dados (Perfis, Segmentos e Assistente de Jornada)

Endpoints consumidos pelas telas de **Perfis**, **Segmentos** e **Assistente de Jornada**
do frontend `web/`. A tela de **Ontologia** não chama API: lê o registro em
`web/src/features/dados/registro.ts` (espelho do futuro `ontologia/kiosk.yaml`).

Sem endpoint (404/405/501) cada tela mostra aviso "dados ainda não disponíveis".
Tipos em `web/src/features/dados/types.ts`. Perfis de acesso: `admin` e `operador`.

## API de Perfis

| Método | Rota | Resposta |
|--------|------|----------|
| GET | `/api/dados/perfis?sujeito=cliente\|franqueado&busca=` | `PerfilResumo[]` |
| GET | `/api/dados/perfis/:sujeito/:id` | `Perfil` (completo) |

Busca requer ≥3 caracteres.

### Estrutura de `Perfil`

```json
{
  "sujeito": "cliente",
  "id": "1",
  "nome": "Mariana Souza",
  "contatos": { "celular": "+55 81 9****-1234", "email": "ma***@exemplo.com", "documento": "CPF ***.***.***-21" },
  "selos": ["YAMPI-ESSENCIA-MARIANA", "2 lojas"],
  "camadas": {
    "fato":    [{ "caminho": "cliente.uf_origem", "rotulo": "UF de origem", "valor": "PE" }],
    "metrica": [{ "caminho": "cliente.uf_atual", "rotulo": "UF atual", "valor": "ES" }],
    "insight": [{ "rotulo": "1 entrega atrasada", "tipo": "risco" }],
    "ia":      { "valor": 78, "descricao": "Chance de recompra em 30 dias", "proximaAcao": "WhatsApp com reposição" }
  },
  "eventos": [{ "id": "e1", "nome": "envio.atrasou", "em": "2026-10-20T03:00:00Z", "resumo": "...", "tipo": "problema" }]
}
```

### Regras de Dados

- Contatos saem **mascarados** do backend (telefone, e-mail, documento).
- `valor` já formatado em pt-BR; `null` = sem dado.
- Todo `caminho` precisa existir no registro da ontologia.
- `ia` é `null` sem histórico suficiente.
- `uf_origem` = UF entrega do primeiro pedido (imutável); `uf_atual` = mais recente.

## API de Segmentos

| Método | Rota | Corpo/Resposta |
|--------|------|----------------|
| GET | `/api/dados/segmentos` | Lista resumida com `id, nome, sujeito, total, jornada, atualizadoEm` |
| GET | `/api/dados/segmentos/:id` | Detalhe com `condições` |
| POST | `/api/dados/segmentos/contagem` | `{ sujeito, condicoes }` → `{ total }` |
| POST | `/api/dados/segmentos` | Criar → `{ id }` |
| PUT | `/api/dados/segmentos/:id` | Atualizar |

### Condições

`condicoes`: `[{ campo, operador, valor }]`, todas ligadas por "E".

Operadores: `igual`, `diferente`, `maior`, `menor`, `em`, `contem`, `ultimos_dias`,
`antes`, `depois` (por tipo em `OPERADORES_POR_TIPO`).

O backend repete `validarCondicao`: campo do sujeito no registro, nunca dado pessoal,
valor do tipo correto. `segmento.entrou` só dispara para quem entra **depois** de salvo.

## Assistente de Jornada

`POST /api/jornadas/assistente/rascunho`

Entrada: `pedido` (texto livre) + `ajuste` (rascunho anterior + erros).

Resposta: `{ workflow: Workflow, explicacao: ["frase por etapa"] }` com `isActive: false`.

### Restrições de Segurança

- O modelo recebe **apenas** registro da ontologia, catálogo de blocos e templates ativos.
  **Nenhum dado pessoal** é enviado ao modelo.
- O front valida com `validarRascunho` (5 verificações):
  1. Blocos e portas → campos da ontologia
  2. Template compatível
  3. Limite e janela
  4. Simulação estrutural
- Backend deve repetir validação ao ativar.
- Só `admin` aprova; aprovar = `POST /api/workflows` com `isActive: true`.
