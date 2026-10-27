# Escritório de agentes — protótipo local

Pedido: código completo React, planta baixa interativa, pelo menos cinco agentes, estados animados, eventos em tempo real, detalhes/memória/histórico/métricas e botão de simulação/tarefa.

Direção: escritório 2D moderno com fundo claro, cores índigo/violeta, estações desenhadas em CSS, cinco agentes identificáveis e painel lateral de atividades. Planta com pesquisa, desenvolvimento, redação, reunião/revisão e mesa do orquestrador. Interface em português. Visualização acompanha a execução local simulada, com tarefas fictícias. Eventos são resumos operacionais; não apresentam pensamentos internos de modelos.

Alternativas: pixel art puro (mais lúdico, menos legível) ou lista/dashboard tradicional (mais denso, perde a metáfora espacial). Escolhida planta moderna por facilitar identificar pessoas, tarefas, estados e relações.

Arquitetura: React/Vite com Lucide React e Tailwind; CSS dedicado à planta e objetos. Motor puro determinístico separado: idle → working/thinking → waitingApproval → done. Pausa congela simulação; aprovação libera revisão; nova missão inicia um ciclo limpo. Sem backend, modelos, telemetria, credenciais, integração de produção ou Git remoto.

Entrega: projeto completo + ZIP e preview compilado. Timer com cleanup, seleção por botão, painel acessível, estados com texto, foco visível, prefers-reduced-motion, responsivo e logs limitados. Testes comportamentais do motor antes de sua implementação; build e QA de desktop/celular; revisor independente.

Escopo arquitetural de protótipo novo.
