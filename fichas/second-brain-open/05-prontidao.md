---
secao: 5
origem: Checklist de lançamento do livro de SRE do Google
aplica: sim
categorias:
  arquitetura:
    evidencia: fichas/second-brain-open/03-arquitetura.md
  maquinas:
    motivo: "Roda na máquina de quem usa; não há servidor nem datacenter."
  volume:
    motivo: "Uso individual; nunca houve medição de volume, capacidade ou desempenho."
  confiabilidade:
    evidencia: core/resilience/circuit_breaker.py
  monitoramento:
    evidencia: core/tracing.py
  seguranca:
    evidencia: core/policy/decide.py
  automacao:
    motivo: "Não há integração contínua; a suíte é rodada à mão, conforme o runbook."
  crescimento:
    motivo: "Não há plano de crescimento: o motor atende uma pessoa ou um time pequeno."
  dependencias:
    evidencia: docker-compose.yml
  lancamento:
    motivo: "Não há versão publicada nem plano de lançamento; o repositório é uma referência."
---
# Prontidão

As dez categorias são as do checklist de lançamento do livro de SRE do Google. Cinco têm evidência no
repositório e cinco não se aplicam a um motor que roda na máquina de uma pessoa; o motivo de cada uma está
nos campos acima.

Ter evidência não quer dizer estar pronto: a categoria de confiabilidade aponta o disjuntor, e parte dos
testes de resiliência falha hoje. O veredito está na auditoria de construção.
