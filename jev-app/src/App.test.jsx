import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App.jsx';
import EnvToggle from './components/EnvToggle.jsx';
import { mockFetch, baseRoutes, urls, json } from './test-utils.jsx';

afterEach(() => vi.unstubAllGlobals());

describe('EnvToggle', () => {
  it('dois rádios rotulados; marca o atual e avisa a troca', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<EnvToggle value="production" onChange={onChange} />);
    expect(screen.getByRole('radio', { name: 'Produção' }).checked).toBe(true);
    await user.click(screen.getByRole('radio', { name: 'Homologação' }));
    expect(onChange).toHaveBeenCalledWith('hml');
  });
});

describe('App', () => {
  it('mostra texto de carregamento e depois as regras com os dois sinais', async () => {
    mockFetch(baseRoutes());
    render(<App />);
    expect(screen.getAllByRole('status').some((n) => /carregando regras/i.test(n.textContent))).toBe(true);
    expect(await screen.findByText('Regra verde')).toBeTruthy();
    expect(screen.getByText('Verde')).toBeTruthy();
    expect(screen.getByText('Vermelha')).toBeTruthy();
  });

  it('erro de rede em getRules mostra estado de erro e Tentar novamente recarrega', async () => {
    const user = userEvent.setup();
    let fail = true;
    const routes = baseRoutes();
    const fetchFn = vi.fn(async (url, init) => {
      if (url === '/api/rules' && fail) throw new TypeError('down');
      const method = (init && init.method) || 'GET';
      const hit = routes[`${method} ${url}`];
      return hit === undefined ? json({}, 404) : json(hit);
    });
    vi.stubGlobal('fetch', fetchFn);
    render(<App />);
    expect(await screen.findByText(/sem conexão com o servidor/i)).toBeTruthy();
    fail = false;
    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }));
    expect(await screen.findByText('Regra verde')).toBeTruthy();
    expect(screen.queryByText(/sem conexão com o servidor/i)).toBeNull();
  });

  it('alternar para homologação pede o assessment de hml e mostra o painel dele', async () => {
    const user = userEvent.setup();
    const fetchFn = mockFetch(baseRoutes());
    render(<App />);
    const panel = await screen.findByRole('region', { name: /saúde do ambiente/i });
    await within(panel).findByText('Ambiente production responde normalmente.');
    await user.click(screen.getByRole('radio', { name: 'Homologação' }));
    expect(await within(panel).findByText('Homologação com aviso de coleta.')).toBeTruthy();
    expect(urls(fetchFn)).toContain('/v1/observability/assessment?environment=hml');
    expect(urls(fetchFn)).toContain('/v1/observability/assessment?environment=production');
  });

  it('painel lista os 4 nós com status e motivo, e sinaliza obsoleto em texto', async () => {
    const routes = baseRoutes({
      'GET /v1/observability/assessment?environment=production': {
        ...JSON.parse('{}'),
        environment: 'production',
        status: 'yellow',
        reason: 'Observação antiga.',
        stale: true,
        nodes: [
          { id: 'process', status: 'green', reason: 'Processo no ar' },
          { id: 'internal', status: 'yellow', reason: 'Fila lenta' },
          { id: 'external', status: 'unknown', reason: 'Sem dados' },
          { id: 'database', status: 'red', reason: 'Banco fora' },
        ],
        contradictions: [],
        rules_available: true,
      },
    });
    mockFetch(routes);
    render(<App />);
    const panel = await screen.findByRole('region', { name: /saúde do ambiente/i });
    await within(panel).findByText('Observação antiga.');
    expect(within(panel).getAllByRole('listitem')).toHaveLength(4);
    for (const t of ['Processo', 'Interno', 'Externo', 'Banco de dados', 'Fila lenta', 'Banco fora']) {
      expect(within(panel).getByText(t)).toBeTruthy();
    }
    expect(within(panel).getAllByText(/desatualizad/i).length).toBeGreaterThan(0);
  });

  it('Atualizar refaz todas as chamadas', async () => {
    const user = userEvent.setup();
    const fetchFn = mockFetch(baseRoutes());
    render(<App />);
    await screen.findByText('Regra verde');
    const before = urls(fetchFn).filter((u) => u === '/api/rules').length;
    await user.click(screen.getByRole('button', { name: /atualizar/i }));
    await waitFor(() => expect(urls(fetchFn).filter((u) => u === '/api/rules').length).toBe(before + 1));
  });

  it('abas: Regras, Playbooks, Execuções com semântica de tabs e setas', async () => {
    const user = userEvent.setup();
    mockFetch(baseRoutes());
    render(<App />);
    await screen.findByText('Regra verde');
    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((t) => t.textContent)).toEqual(['Regras', 'Playbooks', 'Execuções']);
    expect(tabs[0].getAttribute('aria-selected')).toBe('true');
    await user.click(tabs[1]);
    expect(await screen.findByText('Procedimento antigo de deploy')).toBeTruthy();
    expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe(tabs[1].id);
    tabs[1].focus();
    await user.keyboard('{ArrowRight}');
    expect(tabs[2].getAttribute('aria-selected')).toBe('true');
    expect(await screen.findByText('Cenário 7 falhou')).toBeTruthy();
  });

  it('fluxo: abrir playbook, registrar execução e atualizar a lista', async () => {
    const user = userEvent.setup();
    const routes = baseRoutes({
      'GET /api/playbooks/PB-002': {
        id: 'PB-002',
        content: 'x',
        meta: { id: 'PB-002', title: 'Emissão bloqueada sem NF real', status: 'active', kind: 'test', environment: 'hml', params: [] },
      },
      'POST /api/playbooks/PB-002/render': { id: 'PB-002', rendered_content: 'Prévia do servidor', params_used: {} },
      'POST /api/playbooks/executions': () => json({ id: 9, status: 'recorded' }, 201),
    });
    const fetchFn = mockFetch(routes);
    render(<App />);
    await user.click(await screen.findByRole('tab', { name: 'Playbooks' }));
    await user.click(await screen.findByRole('button', { name: /PB-002/ }));
    await screen.findByText('Prévia do servidor');
    const opener = screen.getByRole('button', { name: /registrar execução/i });
    await user.click(opener);
    const dialog = screen.getByRole('dialog', { name: /registrar execução/i });
    expect(within(dialog).getByLabelText(/playbook/i).value).toBe('PB-002');
    await user.type(within(dialog).getByLabelText(/resumo/i), 'ok');
    await user.type(within(dialog).getByLabelText(/referência de evidência/i), 'DEM-1');
    await user.click(within(dialog).getByRole('button', { name: 'Registrar' }));
    await waitFor(() => expect(document.querySelector('dialog').open).toBe(false));
    expect(document.activeElement).toBe(opener);
    expect(screen.getByText(/execução registrada/i)).toBeTruthy();
    await waitFor(() =>
      expect(urls(fetchFn).filter((u) => u === '/api/playbooks/executions').length).toBeGreaterThanOrEqual(3),
    ); // 1 GET inicial + 1 POST + 1 GET de atualização
  });

  it('nenhum atributo style em nenhuma aba (CSP style-src self)', async () => {
    const user = userEvent.setup();
    mockFetch(baseRoutes());
    const { container } = render(<App />);
    await screen.findByText('Regra verde');
    expect(container.querySelectorAll('[style]')).toHaveLength(0);
    await user.click(screen.getByRole('tab', { name: 'Playbooks' }));
    await screen.findByText('Procedimento antigo de deploy');
    expect(container.querySelectorAll('[style]')).toHaveLength(0);
    await user.click(screen.getByRole('tab', { name: 'Execuções' }));
    await screen.findByText('Cenário 7 falhou');
    expect(container.querySelectorAll('[style]')).toHaveLength(0);
  });
});
