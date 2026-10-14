import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PlaybooksView from './PlaybooksView.jsx';
import { state, PLAYBOOKS, EXECUTIONS, mockFetch, json } from '../test-utils.jsx';

afterEach(() => vi.unstubAllGlobals());

const detail = (over = {}) => ({
  id: 'PB-002',
  filename: 'PB-002.md',
  content: '# bruto',
  meta: {
    id: 'PB-002',
    title: 'Emissão bloqueada sem NF real',
    status: 'active',
    kind: 'test',
    environment: 'hml',
    params: [{ name: 'cliente', label: 'Cliente', default: 'ACME' }, { name: 'qtd' }],
    ...over,
  },
});

const routes = (extra = {}) => ({
  'GET /api/playbooks/PB-002': detail(),
  'POST /api/playbooks/PB-002/render': (_url, init) => {
    const { params } = JSON.parse(init.body);
    return { id: 'PB-002', rendered_content: `# Título\n\nOlá ${params.cliente ?? '(vazio)'} **negrito**`, params_used: params };
  },
  ...extra,
});

const view = (onRecord = vi.fn()) =>
  render(<PlaybooksView playbooks={state(PLAYBOOKS)} executions={state(EXECUTIONS)} onRecord={onRecord} />);

describe('PlaybooksView lista', () => {
  it('mostra id, título, status, tipo e ambiente; retired aparece como Aposentado', () => {
    view();
    const table = screen.getByRole('table');
    expect(within(table).getAllByRole('row')).toHaveLength(5);
    const pb4 = within(table).getByRole('row', { name: /PB-004/ });
    expect(within(pb4).getByText('Aposentado')).toBeTruthy();
    expect(within(pb4).getByText('Runbook')).toBeTruthy();
    expect(within(pb4).getByText('Produção')).toBeTruthy();
    const pb1 = within(table).getByRole('row', { name: /PB-001/ });
    expect(within(pb1).getByText('Teste')).toBeTruthy();
    expect(within(pb1).getByText('Ativo')).toBeTruthy();
    expect(screen.queryByText(/deprecated|obsoleto/i)).toBeNull();
  });

  it('última execução por ambiente: resultado e tempo relativo, a mais nova vence', () => {
    view();
    const pb2 = screen.getByRole('row', { name: /PB-002/ });
    // pass (10/10) vence o error de 01/10 em hml
    expect(within(pb2).getByText('Aprovada')).toBeTruthy();
    expect(within(pb2).queryByText('Erro')).toBeNull();
    expect(within(pb2).getByText('Homologação', { selector: '[data-last-env]' })).toBeTruthy();
    const pb3 = screen.getByRole('row', { name: /PB-003/ });
    expect(within(pb3).getByText(/sem execução/i)).toBeTruthy();
  });

  it.each([
    ['Tipo', 'runbook', ['PB-003', 'PB-004'], ['PB-001', 'PB-002']],
    ['Status', 'retired', ['PB-004'], ['PB-001', 'PB-002', 'PB-003']],
    ['Ambiente', 'hml', ['PB-002', 'PB-003'], ['PB-001', 'PB-004']],
  ])('filtro %s=%s estreita a lista', async (label, value, shown, hidden) => {
    const user = userEvent.setup();
    view();
    await user.selectOptions(screen.getByLabelText(label), value);
    const table = screen.getByRole('table');
    for (const id of shown) expect(within(table).getByText(id)).toBeTruthy();
    for (const id of hidden) expect(within(table).queryByText(id)).toBeNull();
  });

  it('filtro sem resultado mostra estado vazio com texto', async () => {
    const user = userEvent.setup();
    view();
    await user.selectOptions(screen.getByLabelText('Tipo'), 'test');
    await user.selectOptions(screen.getByLabelText('Status'), 'retired');
    expect(screen.getByText(/nenhum playbook/i)).toBeTruthy();
  });

  it('lista vazia e carregamento têm texto', () => {
    const { unmount } = render(
      <PlaybooksView playbooks={state([])} executions={state([])} onRecord={() => {}} />,
    );
    expect(screen.getByText(/nenhum playbook/i)).toBeTruthy();
    unmount();
    render(
      <PlaybooksView playbooks={state(null, { loading: true })} executions={state(null, { loading: true })} onRecord={() => {}} />,
    );
    expect(screen.getByRole('status').textContent).toMatch(/carregando playbooks/i);
  });
});

describe('PlaybooksView detalhe', () => {
  it('prévia vem do servidor como texto pré-formatado, sem markdown', async () => {
    const user = userEvent.setup();
    const fetchFn = mockFetch(routes());
    view();
    await user.click(screen.getByRole('button', { name: /PB-002/ }));
    const pre = await screen.findByText(/Olá ACME/);
    expect(pre.tagName).toBe('PRE');
    expect(pre.className).toContain('whitespace-pre-wrap');
    expect(pre.textContent).toContain('# Título'); // markdown intocado
    expect(pre.textContent).toContain('**negrito**');
    expect(pre.querySelector('h1,strong,b')).toBeNull();
    const renderCall = fetchFn.mock.calls.find(([u]) => u === '/api/playbooks/PB-002/render');
    expect(JSON.parse(renderCall[1].body)).toEqual({ params: { cliente: 'ACME' } });
  });

  it('parâmetros declarados viram campos rotulados; Atualizar prévia envia os valores', async () => {
    const user = userEvent.setup();
    const fetchFn = mockFetch(routes());
    view();
    await user.click(screen.getByRole('button', { name: /PB-002/ }));
    const cliente = await screen.findByLabelText('Cliente');
    expect(cliente.value).toBe('ACME');
    const qtd = screen.getByLabelText('qtd');
    expect(qtd.value).toBe('');
    await user.clear(cliente);
    await user.type(cliente, 'Beta');
    await user.type(qtd, '3');
    await user.click(screen.getByRole('button', { name: 'Atualizar prévia' }));
    expect(await screen.findByText(/Olá Beta/)).toBeTruthy();
    const last = fetchFn.mock.calls.filter(([u]) => u.endsWith('/render')).at(-1);
    expect(JSON.parse(last[1].body)).toEqual({ params: { cliente: 'Beta', qtd: '3' } });
  });

  it('lista as execuções do playbook e abre o registro com os parâmetros', async () => {
    const user = userEvent.setup();
    mockFetch(routes());
    const onRecord = vi.fn();
    view(onRecord);
    await user.click(screen.getByRole('button', { name: /PB-002/ }));
    await screen.findByText(/Olá ACME/);
    const panel = screen.getByRole('region', { name: /detalhe do playbook/i });
    expect(within(panel).getByText('Runner indisponível')).toBeTruthy();
    expect(within(panel).getByText('Emissão bloqueada como esperado')).toBeTruthy();
    expect(within(panel).queryByText('Cenário 7 falhou')).toBeNull(); // é do PB-001
    await user.click(within(panel).getByRole('button', { name: /registrar execução/i }));
    expect(onRecord).toHaveBeenCalledTimes(1);
    expect(onRecord.mock.calls[0][0]).toEqual({ playbookId: 'PB-002', params: { cliente: 'ACME' }, environment: 'hml' });
    expect(onRecord.mock.calls[0][1]).toBeInstanceOf(HTMLElement);
  });

  it('falha ao renderizar mostra erro com Tentar novamente', async () => {
    const user = userEvent.setup();
    let calls = 0;
    mockFetch(
      routes({
        'POST /api/playbooks/PB-002/render': () => (++calls === 1 ? json({ error: 'X' }, 500) : { id: 'PB-002', rendered_content: 'Recuperado' }),
      }),
    );
    view();
    await user.click(screen.getByRole('button', { name: /PB-002/ }));
    const retry = await screen.findByRole('button', { name: 'Tentar novamente' });
    await user.click(retry);
    expect(await screen.findByText('Recuperado')).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Tentar novamente' })).toBeNull());
  });

  it('detalhe 404 mostra erro', async () => {
    const user = userEvent.setup();
    mockFetch({});
    view();
    await user.click(screen.getByRole('button', { name: /PB-001/ }));
    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeTruthy();
  });
});
