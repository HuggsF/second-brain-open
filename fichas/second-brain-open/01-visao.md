---
secao: 1
origem: Pitch do Shape Up
aplica: sim
---
# Visão de negócio

## Problema

Agentes de IA que ajudam em engenharia erram de dois jeitos caros: respondem sem base no que o time já
decidiu, e executam comandos que ninguém autorizou. As soluções prontas costumam resolver um dos dois e
pedem um serviço externo para guardar o conhecimento.

## Apetite

Um motor que uma pessoa mantém sozinha e que roda na máquina dela. Nada que exija uma equipe de plataforma
para ficar de pé.

## Solução

- O conhecimento fica em arquivos Markdown versionados; tudo o mais é derivado e pode ser reconstruído.
- Toda chamada de ferramenta por um agente passa por uma decisão única: aprovar, escalar para um humano ou
  negar.
- Missões passam por portões antes e depois de rodar (vazamento de dado, fundamentação, plano sem ciclo,
  regra de negócio, idempotência).
- Cada regra de negócio aponta os testes que a provam e o resultado da última execução.
- O núcleo não conhece a organização que o usa: o vocabulário dela entra por um perfil.

## Armadilhas

- A busca é por palavras: pergunta com vocabulário diferente do da nota não acha nada.
- O piso de relevância da busca não foi medido neste repositório.
- A resposta do `ask` precisa de um servidor local de modelos; `sync` e `buscar` não precisam de nada.
- O repositório não traz vault nem adaptadores de infraestrutura: quem instala precisa trazer os seus.
- A interface de agentes é um protótipo com dados simulados.

## Fora de escopo

- Serviço hospedado ou multiusuário.
- Execução de comando que altera um servidor sem um humano aprovar.
- Dados de qualquer organização: o repositório é genérico.
