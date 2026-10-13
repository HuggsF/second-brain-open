# Nexus — Escritório virtual de agentes

Protótipo funcional local em React, Tailwind CSS e Lucide React. Sem backend, contas ou modelos de IA conectados. Tarefas, contexto e métricas são dados simulados.

## Abrir sem instalar

Abra **office.html** no navegador. Essa versão contém os scripts e estilos compilados e funciona sem internet. Clique em **Iniciar simulação**.

## Executar o código React

Requer Node.js 22.12+ e npm. Na pasta extraída do projeto:

```sh
npm ci
npm run dev
```

Abra a URL local indicada no terminal (normalmente http://127.0.0.1:5173). Para gerar a versão compilada:

```sh
npm run build
npm run preview
```

## O que experimentar

- Clique em qualquer um dos cinco agentes para abrir tarefa atual, memória, histórico e métricas simuladas.
- Inicie, pause e retome a simulação. O botão **1× / 2×** ajusta a velocidade.
- A pesquisa antecede desenvolvimento/redação; a revisão aguarda **Aprovar entrega** antes de concluir.
- Envie uma nova missão pelo botão **Nova tarefa** ou escolha um exemplo. A missão nova limpa contexto/progresso e recebe seu próprio timer.
- **Reiniciar simulação** volta ao estado inicial. Escape fecha o diálogo de tarefa e restaura o foco.

Os registros são eventos e resumos operacionais, não pensamentos internos de um modelo. Todos os dados permanecem na memória do navegador; recarregar reinicia a demonstração.

## Arquivos

- src/App.jsx: componentes React e ciclo da interface.
- src/office.css: estilos Tailwind, planta, móveis, avatares CSS e animações.
- src/simulation.mjs: motor puro determinístico, perfis e roteiro.
- src/main.jsx: montagem React.
- tests/: 22 testes do motor e da estrutura inicial da interface.
- dist/: build estático gerado.
- office.html: build reunido em um arquivo HTML independente.
- DESIGN.md, PLAN.md e HANDOFF.md: decisões e verificações.

## Verificação

```sh
npm test
```

Verificado em Edge headless isolado: iniciar/pausar/retomar, detalhes do agente, gate de aprovação, conclusão, nova missão, Escape/foco, celular sem overflow horizontal e movimento reduzido. Regressão do timer anterior reproduzida e corrigida.

O build pode emitir avisos de que a diretiva “use client” do Lucide não é preservada. Este protótipo é inteiramente client-side; esses avisos não impedem o build ou a execução.

Referências oficiais: [React](https://react.dev/learn/build-a-react-app-from-scratch), [Vite](https://vite.dev/guide/).
