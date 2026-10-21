---
type: system
status: active
date: 2026-10-21
related: [hub-regras-operacionais-codex]
source: hub-logistico/docs/migration-stable-contract.md
source_branch: codex/detailed-integration-logs
---

# Contrato da Versão Estável e Avaliação de Migração

Avaliação técnica da versão estável do Hub Logístico (commit `0d1eab7`, merge `89f16e68`,
implantado em 14/10/2026) com objetivo de preparar regressões E2E antes de migrar JS→TS
ou reorganizar domínio. Documento não autoriza início de migração.

## Conclusão Principal

O prompt de migração original (`prompt-opus.md`) mistura propostas arquiteturais com
funcionalidades reais e precisa de correção. Ele declara artefatos TS, ADRs e
correções como concluídos quando não estão.

## Divergências Factuais do Prompt Original

| Tema | Estado Real | Correção Necessária |
|------|-------------|---------------------|
| Branch/runtime | `fix/webhook-queue-admission`; `node server.js` CommonJS | Não assumir branch TS |
| TypeScript | `src/` vazio; sem `tsconfig.json`, deps ou scripts TS | Não declarar Foundation TS concluída |
| ADRs | `docs/adr/` inexistente; planejamento com 8 seções, não 11 | Tratar como proposta |
| Transportadoras | Sem `CarrierRegistry`, `CarrierPort` ou filtro `ignorado_transporte` | Registry é proposta, não implementação |
| Anti-duplicidade | Motor combina job, `jt_emissions`, histórico e ERP | Não substituir por precedência Bling→Hub→cache |
| NF e retry | NF real obrigatória para nova emissão; sem categoria `nf_pending` | Preservar política vigente |
| Quota Bling | Sliding window local 3 req/s no adapter | Diferenciar de coordenação global proposta |
| Segurança login | SHA-256, seed `admin123`, sem bcrypt/TTL | Não marcar como concluído |
| Webhook | HMAC-SHA256 sobre corpo bruto já existe | Não apresentar como ausente |
| Corpem | Adapter executa `axios.post` real se WMS configurado | Interceptar nos testes |

## Invariantes de Migração (NÃO Negociáveis)

Estas invariantes devem ser preservadas por qualquer refatoração ou tradução TS:

1. **Intenção uncertain + `txlogistic_id`** persistidos ANTES de `addOrder`; confirmação
   durável antes da fila/ERP/WMS; recuperação sem segunda emissão.
2. **REVIEW_REQUIRED** para intenção incerta, conflito ou cancelamento. Não priorizar
   Bling sobre Hub/cache, não apagar intenção, não liberar `processing` abandonado
   sem reconciliação operacional.
3. **NF real obrigatória** para nova emissão; etiqueta existente reutilizável com NF
   indisponível. Atualização pelo objeto logístico e GET de confirmação no Bling.
4. **Reserva SQLite atômica**, exclusividade por ERP, `next_attempt_at` e gravações
   condicionais que não sobrescrevem cancelamento.
5. **Política de retries/cooldown**, flags e overrides de lojas/conectores,
   persistência de token rotativo, reidratação OAuth e assinatura sobre corpo bruto.
6. **HML e worker pausado** bloqueiam emissão; sem bypass operacional.
7. **Migrações preservam** dados/estados/identidades; rollback preserva banco atual.

## Mudanças que Alteram Comportamento (Requerem Escopo Explícito)

Estas funcionalidades NÃO devem ser incluídas em refatoração ou tradução TS:

- `CarrierRegistry` / filtro de carrier
- Nova precedência de fontes (Bling→Hub→cache)
- Retry `nf_pending` / DLQ
- Redis/Kafka
- Segurança de login (bcrypt, TTL)
- Várias remessas por ERP
- Coordenação global de sliding window / backpressure

## Bateria E2E Estável

Reverificação em 14/10/2026 (checkout `0284df6`, runtime idêntico):

| Categoria | Quantidade |
|-----------|------------|
| Testes `node --test` | 62 |
| `suite_duplicidade` | 4 |
| **Total JS** | **66** |
| Testes E2E | 17 |
| Testes Python | 9 |
| Mutações CI detectadas | 3 |

### Lacunas Demonstradas (invariantes sem cobertura E2E)

Cinco invariantes sem nenhum teste e duas com apenas teste unitário foram
identificadas por mutação deliberada:

- Guarda do `success` final durante WMS
- HMAC sobre bytes originais
- Cancelamento por webhook com conector da loja
- NF com chave zerada
- 429 no PUT do Bling
- Limite de 20 ciclos de 429 (só unitário)
- Ambiente desconhecido falhando fechado (só unitário)

A ampliação (`stable_gaps.test.js`, `network_guard.test.js`) acrescentou 14 cenários,
totalizando **31 E2E** e **80 cenários JS**. Cada mutação é detectada por pelo menos
um teste E2E.

### Defeitos Conhecidos na Versão Estável (Não Corrigidos)

- `Authorization: constructor` passa pela autenticação (rotas admin barram, operador não)
- `POST /api/login` sem senha derruba o processo

Estes são comportamento esperado da referência estável. Correção requer escopo e
regressões próprias.

## Limites de Cobertura

A suíte local NÃO comprova:

- UI em navegador
- Contrato externo completo
- Disponibilidade de fornecedores
- Performance de produção
- Segurança absoluta
