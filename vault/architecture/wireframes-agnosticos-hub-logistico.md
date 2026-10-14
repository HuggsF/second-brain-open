---
title: "Modelos Agnósticos de Wireframes — Hub Logístico KIOSK Brands"
date: 2026-10-13
type: specification
tags: [hub-logistico, wireframes, design-system, agnostico, ux-engine-kiosk]
---

# 📐 Modelos Agnósticos de Wireframes — Hub Logístico

> **Guia Arquitetural e Operacional para Refatoração do Front-end do Hub**  
> Adaptado dos padrões visuais do *UserIn CRM* (`crm_hggs`) e do *Second Brain UX Engine* (`ux-engine-kiosk`), totalmente **desacoplado de frameworks** (HTML5 + CSS Puro + JS Vanilla).  
> Pronto para ser utilizado amanhã no trabalho em **PHP puro, Laravel/Blade, Express/EJS, Vue, React ou HTML estático**.

---

## 1. Por que Modelos Agnósticos?

Os wireframes de referência do `crm_hggs` utilizam React + Vite + Tailwind + shadcn/ui. Para aplicar essas melhorias com velocidade no **Hub Logístico** da KIOSK Brands amanhã, transformamos esses componentes em **blocos agnósticos de padrão web**:

* **Zero dependência de bundler**: Funciona com inclusão direta do arquivo CSS [`hub-design-system-agnostico.css`](./hub-design-system-agnostico.css).
* **HTML semântico puro**: `<header>`, `<nav>`, `<main>`, `<section>`, `<table>`, `<dialog>`.
* **CSS com Variáveis Nativas (`:root`)**: Suporte instantâneo a Dark Mode e Light Mode sem pré-processador.
* **Segurança Operacional (UX Engine)**: Ações perigosas (como cancelamento ou reemissão na J&T) possuem confirmação com foco padrão em "Cancelar".

---

## 2. Matriz de Equivalência: UserIn (`crm_hggs`) ➔ Hub Logístico

| Componente no `crm_hggs` | Modelo Agnóstico do Hub | Função no Hub Logístico |
|---|---|---|
| `StatusCard` / `KpiCardsSection` | `.hub-kpi-card` | Semáforo do Token OAuth Bling, Fila Ativa (`pending`, `failed`), Taxa de Sucesso (%) |
| `TableSection` / Data Tables | `.hub-table` | Fila de Pedidos (`orders_queue`), ID ERP, Loja, Rastreio J&T, Ações de Retry |
| `StepperSection` | `.hub-stepper` | Ciclo de vida da Emissão: Webhook ➔ Loja ➔ NF-e ➔ J&T ➔ Bling |
| `Alerts` / `BadgesSection` | `.hub-badge`, `.hub-alert` | Alerta de Rate Limit 429 Bling, Token expirando em < 30min, divergência de etiquetas |
| Dialog / Modal | `.hub-modal-backdrop` | Confirmação de reemissão manual e reprocessamento em lote com trava anti-duplicidade |

---

## 3. Os 5 Modelos Estruturais de Wireframes

---

### 🖥️ Wireframe 1: Layout Master Operacional
Estrutura básica de casca para todas as telas do Hub Logístico.

```html
<div class="hub-layout">
  <!-- Sidebar de Navegação -->
  <aside class="hub-sidebar">
    <div class="hub-sidebar-header">
      <span class="hub-sidebar-brand">
        📦 <span>Hub Logístico</span>
      </span>
    </div>
    <nav class="hub-nav">
      <a href="#cockpit" class="hub-nav-item active">📊 Cockpit de Saúde</a>
      <a href="#fila" class="hub-nav-item">📋 Fila de Pedidos</a>
      <a href="#duplicidades" class="hub-nav-item">🛡️ Auditoria J&T</a>
      <a href="#conectores" class="hub-nav-item">🔌 Conectores & Lojas</a>
      <a href="#logs" class="hub-nav-item">📜 Logs do Sistema</a>
    </nav>
  </aside>

  <!-- Painel Principal -->
  <main class="hub-main">
    <header class="hub-topbar">
      <div style="font-size: 14px; font-weight: 600; color: var(--hub-text-secondary);">
        Ambiente: <span class="hub-badge success">Produção (SRV-API)</span>
      </div>
      <div style="display: flex; gap: 12px; align-items: center;">
        <span style="font-size: 12px; color: var(--hub-text-muted);">Sync: há 12s</span>
        <button class="hub-btn hub-btn-sm" onclick="location.reload()">🔄 Atualizar</button>
      </div>
    </header>

    <div class="hub-content">
      <!-- Injeção dos Módulos/Wireframes aqui -->
    </div>
  </main>
</div>
```

---

### 📊 Wireframe 2: Cockpit de Observabilidade & Semáforo de Tokens
Mostra o status do token OAuth do Bling v3, volume da fila e taxa de sucesso em tempo real.

```html
<section class="hub-card">
  <div class="hub-card-header">
    <h2 class="hub-card-title">Saúde Operacional & Integrações</h2>
    <span class="hub-badge processing">Motor PM2: Ativo</span>
  </div>

  <div class="hub-kpi-grid">
    <!-- Semáforo do Token OAuth Bling -->
    <div class="hub-kpi-card" style="border-left: 4px solid var(--hub-status-success-text);">
      <span class="hub-kpi-label">Token OAuth Bling (v3)</span>
      <div class="hub-kpi-value" style="font-size: 22px; color: var(--hub-status-success-text);">
        4h 18m restantes
      </div>
      <div class="hub-kpi-footer">
        <span class="hub-badge success">Expira às 01:20</span>
        <button class="hub-btn hub-btn-sm" style="margin-left: auto;">Renovar</button>
      </div>
    </div>

    <!-- Pedidos Pendentes -->
    <div class="hub-kpi-card">
      <span class="hub-kpi-label">Fila Pendente</span>
      <div class="hub-kpi-value">14</div>
      <div class="hub-kpi-footer">
        <span class="hub-badge pending">Aguardando motor</span>
      </div>
    </div>

    <!-- Pedidos com Erro/Retry -->
    <div class="hub-kpi-card">
      <span class="hub-kpi-label">Falhas / Revisão</span>
      <div class="hub-kpi-value" style="color: var(--hub-status-failed-text);">3</div>
      <div class="hub-kpi-footer">
        <span class="hub-badge failed">Requer atenção</span>
      </div>
    </div>

    <!-- Taxa de Sucesso Diária -->
    <div class="hub-kpi-card">
      <span class="hub-kpi-label">Taxa de Sucesso (Hoje)</span>
      <div class="hub-kpi-value" style="color: var(--hub-status-success-text);">98.4%</div>
      <div class="hub-kpi-footer">
        <span>528 etiquetas emitidas</span>
      </div>
    </div>
  </div>
</section>
```

---

### 📋 Wireframe 3: Data Table da Fila de Pedidos (`orders_queue`)
A tela de trabalho mais utilizada pelos operadores e desenvolvedores.

```html
<section class="hub-card">
  <div class="hub-card-header">
    <h2 class="hub-card-title">Fila de Processamento de Etiquetas</h2>
    <button class="hub-btn hub-btn-primary">⚡ Processar Pendentes</button>
  </div>

  <!-- Barra de Filtros e Busca -->
  <div class="hub-filter-bar">
    <input type="text" class="hub-input" placeholder="Buscar por ERP ID ou Rastreio..." style="min-width: 280px;" />
    
    <select class="hub-select">
      <option value="">Todos os Status</option>
      <option value="pending">Pendente</option>
      <option value="processing">Processando</option>
      <option value="success">Sucesso</option>
      <option value="failed">Falha (Retry)</option>
      <option value="failed_definitivo">Falha Definitiva</option>
    </select>

    <select class="hub-select">
      <option value="">Todas as Lojas</option>
      <option value="206084387">KIOSK RECIFE (J&T)</option>
      <option value="206085936">KIOSK ESPIRITO SANTO (J&T)</option>
      <option value="206133846">Shopify</option>
    </select>

    <button class="hub-btn">Filtrar</button>
  </div>

  <!-- Tabela de Dados -->
  <div class="hub-table-wrapper">
    <table class="hub-table">
      <thead>
        <tr>
          <th>ID Fila</th>
          <th>ERP ID (Bling)</th>
          <th>Loja / Origem</th>
          <th>Status</th>
          <th>Rastreio (J&T)</th>
          <th>Tentativas</th>
          <th>Data / Hora</th>
          <th style="text-align: right;">Ações</th>
        </tr>
      </thead>
      <tbody>
        <!-- Linha 1: Sucesso -->
        <tr>
          <td class="hub-code">#4128</td>
          <td><strong>27092088358</strong></td>
          <td>KIOSK RECIFE</td>
          <td><span class="hub-badge success"><span class="hub-badge-dot"></span>success</span></td>
          <td><span class="hub-code">899296264686</span></td>
          <td>1</td>
          <td style="color: var(--hub-text-secondary);">13/10 20:45</td>
          <td style="text-align: right;">
            <button class="hub-btn hub-btn-sm">Detalhes</button>
          </td>
        </tr>

        <!-- Linha 2: Falha Recuperável -->
        <tr style="background-color: rgba(248, 81, 73, 0.03);">
          <td class="hub-code">#4129</td>
          <td><strong>27092088359</strong></td>
          <td>KIOSK ESPIRITO SANTO</td>
          <td><span class="hub-badge failed"><span class="hub-badge-dot"></span>failed</span></td>
          <td><span style="color: var(--hub-text-muted);">—</span></td>
          <td><strong style="color: var(--hub-status-failed-text);">3</strong></td>
          <td style="color: var(--hub-text-secondary);">13/10 20:42</td>
          <td style="text-align: right;">
            <button class="hub-btn hub-btn-sm hub-btn-primary">Retentar</button>
            <button class="hub-btn hub-btn-sm">Log</button>
          </td>
        </tr>

        <!-- Linha 3: Pendente -->
        <tr>
          <td class="hub-code">#4130</td>
          <td><strong>27092088360</strong></td>
          <td>KIOSK RECIFE</td>
          <td><span class="hub-badge pending"><span class="hub-badge-dot"></span>pending</span></td>
          <td><span style="color: var(--hub-text-muted);">Aguardando</span></td>
          <td>0</td>
          <td style="color: var(--hub-text-secondary);">13/10 20:50</td>
          <td style="text-align: right;">
            <button class="hub-btn hub-btn-sm">Ver</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</section>
```

---

### 🛡️ Wireframe 4: Painel de Auditoria de Duplicidade & Inconsistências
Mapeado diretamente para resolver os gaps `DEM-17` (Dedup INTEGER vs TEXT) e `DEM-01` (Duplicidade J&T).

```html
<section class="hub-card">
  <div class="hub-card-header">
    <h2 class="hub-card-title">Auditoria Anti-Duplicidade de Etiquetas (J&T vs SQLite)</h2>
    <span class="hub-badge success">Zero Incidentes Ativos</span>
  </div>

  <div class="hub-alert warning">
    <span>⚠️</span>
    <div>
      <strong>Prevenção de Duplicidade Ativa:</strong> Todos os pedidos recebem prefixo único <code>HUB-{erpId}-{timestamp}</code> no <code>txlogisticId</code>. Pedidos marcados como cancelados no Bling são bloqueados de emissão imediata.
    </div>
  </div>

  <div class="hub-table-wrapper">
    <table class="hub-table">
      <thead>
        <tr>
          <th>ERP ID</th>
          <th>txlogisticId (J&T)</th>
          <th>Estado J&T</th>
          <th>billCode Gerado</th>
          <th>Emissão em</th>
          <th>Status de Risco</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>27069630582</strong></td>
          <td class="hub-code">HUB-27069630582-1791581195035</td>
          <td><span class="hub-badge success">confirmed</span></td>
          <td class="hub-code">899296264686</td>
          <td>13/10 18:22:10</td>
          <td><span class="hub-badge success">Sem Duplicidade</span></td>
        </tr>
      </tbody>
    </table>
  </div>
</section>
```

---

### ⚠️ Wireframe 5: Modal de Confirmação Segura (Ação Destrutiva)
Implementa a regra de ouro do `ux-engine-kiosk`: **o foco inicial NUNCA é na ação destrutiva**.

```html
<!-- Exibido condicionalmente via classe ou style -->
<div class="hub-modal-backdrop" id="modal-cancelar-fila" style="display: none;">
  <div class="hub-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
    <h3 class="hub-modal-title" id="modal-title">Cancelar Processamento do Pedido?</h3>
    <p class="hub-modal-desc">
      O pedido Bling <strong>#27092088359</strong> será marcado como <code>cancelado</code> na fila. Nenhuma etiqueta J&T será emitida e o rastreio não será sincronizado.
    </p>

    <div class="hub-modal-actions">
      <!-- Foco padrão sempre no Cancelar -->
      <button class="hub-btn" autofocus onclick="fecharModal()">Manter na Fila</button>
      <button class="hub-btn hub-btn-danger" onclick="confirmarCancelamento()">Sim, Cancelar Pedido</button>
    </div>
  </div>
</div>
```

---

## 4. Os 5 Estados Obrigatórios (State Completeness)

Em conformidade com o princípio de maturidade de UX, qualquer tela do Hub deve renderizar:

```html
<!-- 1. Estado de Carregamento (Loading Skeleton) -->
<div class="hub-card">
  <div class="hub-skeleton" style="width: 40%; height: 24px; margin-bottom: 16px;"></div>
  <div class="hub-skeleton" style="width: 100%; height: 48px; margin-bottom: 8px;"></div>
  <div class="hub-skeleton" style="width: 100%; height: 48px;"></div>
</div>

<!-- 2. Estado Vazio (Empty State) -->
<div class="hub-empty-state">
  <div class="hub-empty-icon">📭</div>
  <h3>Nenhum pedido pendente na fila</h3>
  <p>Todos os webhooks foram processados com sucesso ou filtrados por loja.</p>
</div>

<!-- 3. Estado de Erro com Ação de Retry -->
<div class="hub-alert danger">
  <span>❌</span>
  <div>
    <strong>Falha de conexão com Bling v3:</strong> HTTP 429 (Too Many Requests).
    <button class="hub-btn hub-btn-sm" style="margin-left: 12px;">Tentar Novamente</button>
  </div>
</div>
```

---

## 5. Checklist para Implementação no Trabalho de Amanhã

1. [ ] Baixar ou referenciar [`hub-design-system-agnostico.css`](./hub-design-system-agnostico.css) na tag `<head>` da aplicação do Hub.
2. [ ] Substituir tabelas antigas pelo modelo `.hub-table` com `.hub-badge` semânticas (`success`, `pending`, `failed`).
3. [ ] Inserir os 4 cartões `.hub-kpi-card` no topo da tela inicial (`/admin` ou `/observability`).
4. [ ] Colocar o semáforo de token OAuth com contagem regressiva em destaque no cockpit.
5. [ ] Garantir que ações de reemissão e exclusão usem o dialog modal com botão "Cancelar" focado.
