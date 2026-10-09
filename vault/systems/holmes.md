# Sistema de Processos: Holmes (KIOSK Brands)

## Visão Geral
O **Holmes** é a plataforma de automação de fluxos de trabalho (*workflow*) e gestão de documentos utilizada na KIOSK Brands para padronizar e auditar operações entre a **matriz** e as unidades franqueadas (**quiosques Touti, Amavia e Yes! Cosméticos**).

## Principais Casos de Uso na Holding
1. **Aprovação de Reformas e Layouts:** Validação arquitetural quando um quiosque é inaugurado ou passa por reforma no shopping.
2. **Homologação e Contratos de Franquia:** Tramitação de circulares de oferta de franquia (COF), contratos de cessão e aditivos.
3. **Solicitações Especiais de Faturamento:** Pedidos de desconto por avaria ou devolução de cosméticos vencidos/danificados.

## Motivação para Migração (Target: Salesforce)
- O Holmes atua de forma isolada, gerando duplicação de dados cadastrais de franqueados em relação ao SULTS e ao SAP.
- Os fluxos de aprovação de documentos serão migrados para as regras de processo (Flows / Approval Processes) nativas do **Salesforce**, permitindo auditoria centralizada.
