import { describe, it, expect, vi, afterEach } from 'vitest';
import { useRef, useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ExecutionDialog from './ExecutionDialog.jsx';
import { PLAYBOOKS, mockFetch, json } from '../test-utils.jsx';

afterEach(() => vi.unstubAllGlobals());

function Harness({ onSaved = () => {}, initial = { playbookId: 'PB-002', environment: 'hml' } }) {
  const [open, setOpen] = useState(false);
  const opener = useRef(null);
  return (
    <>
      <button ref={opener} onClick={() => setOpen(true)}>
        Abrir registro
      </button>
      <ExecutionDialog
        open={open}
        onClose={() => setOpen(false)}
        onSaved={onSaved}
        playbooks={PLAYBOOKS}
        initial={initial}
        returnFocusRef={opener}
      />
    </>
  );
}

const dlg = () => document.querySelector('dialog');
const openIt = async (user) => user.click(screen.getByRole('button', { name: 'Abrir registro' }));

describe('ExecutionDialog', () => {
  it('abre como dialog aberto e move o foco para dentro', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(dlg().open).toBe(false);
    await openIt(user);
    expect(dlg().open).toBe(true);
    expect(screen.getByRole('dialog', { name: /registrar execução/i })).toBeTruthy();
    expect(dlg().contains(document.activeElement)).toBe(true);
  });

  it('campos têm rótulo associado', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await openIt(user);
    for (const name of [/playbook/i, /ambiente/i, /resultado/i, /resumo/i, /referência de evidência/i, /commit/i, /id da execução/i]) {
      expect(screen.getByLabelText(name)).toBeTruthy();
    }
  });

  it('recusa evidence_ref vazio: mensagem no campo e nenhum POST', async () => {
    const user = userEvent.setup();
    const fetchFn = mockFetch({});
    render(<Harness />);
    await openIt(user);
    await user.type(screen.getByLabelText(/resumo/i), 'Resumo qualquer');
    await user.click(screen.getByRole('button', { name: 'Registrar' }));
    const field = screen.getByLabelText(/referência de evidência/i);
    expect(field.getAttribute('aria-invalid')).toBe('true');
    const ids = (field.getAttribute('aria-describedby') || '').split(' ');
    expect(ids.length).toBeGreaterThan(0);
    expect(ids.map((i) => document.getElementById(i)?.textContent).join(' ')).toMatch(/obrigatória/i);
    expect(fetchFn).not.toHaveBeenCalled();
    expect(dlg().open).toBe(true);
  });

  it('envia dados válidos, notifica e fecha', async () => {
    const user = userEvent.setup();
    const fetchFn = mockFetch({ 'POST /api/playbooks/executions': () => json({ id: 5, status: 'recorded' }, 201) });
    const onSaved = vi.fn();
    render(<Harness onSaved={onSaved} />);
    await openIt(user);
    await user.type(screen.getByLabelText(/resumo/i), 'Passou em hml');
    await user.type(screen.getByLabelText(/referência de evidência/i), 'vault/x.md:3');
    await user.type(screen.getByLabelText(/commit/i), 'abc1234');
    await user.type(screen.getByLabelText(/id da execução/i), 'run-9');
    await user.click(screen.getByRole('button', { name: 'Registrar' }));
    await waitFor(() => expect(dlg().open).toBe(false));
    expect(fetchFn).toHaveBeenCalledTimes(1);
    const [url, init] = fetchFn.mock.calls[0];
    expect(url).toBe('/api/playbooks/executions');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toMatchObject({
      playbook_id: 'PB-002',
      result: 'pass',
      environment: 'hml',
      summary: 'Passou em hml',
      evidence_ref: 'vault/x.md:3',
      commit_sha: 'abc1234',
      run_id: 'run-9',
    });
    expect(onSaved).toHaveBeenCalledTimes(1);
  });

  it('commit e run_id vazios não vão no corpo', async () => {
    const user = userEvent.setup();
    const fetchFn = mockFetch({ 'POST /api/playbooks/executions': () => json({ id: 5 }, 201) });
    render(<Harness />);
    await openIt(user);
    await user.type(screen.getByLabelText(/resumo/i), 'ok');
    await user.type(screen.getByLabelText(/referência de evidência/i), 'DEM-1');
    await user.click(screen.getByRole('button', { name: 'Registrar' }));
    await waitFor(() => expect(fetchFn).toHaveBeenCalled());
    const body = JSON.parse(fetchFn.mock.calls[0][1].body);
    expect('commit_sha' in body).toBe(false);
    expect('run_id' in body).toBe(false);
  });

  it('erro 400 VALIDATION_FAILED do servidor aparece e os campos continuam preenchidos', async () => {
    const user = userEvent.setup();
    mockFetch({
      'POST /api/playbooks/executions': () =>
        json({ error: 'VALIDATION_FAILED', detail: 'evidence_ref does not exist in the vault' }, 400),
    });
    render(<Harness />);
    await openIt(user);
    await user.type(screen.getByLabelText(/resumo/i), 'Resumo mantido');
    await user.type(screen.getByLabelText(/referência de evidência/i), 'vault/nada.md:1');
    await user.click(screen.getByRole('button', { name: 'Registrar' }));
    expect(await screen.findByText(/evidence_ref does not exist in the vault/)).toBeTruthy();
    expect(dlg().open).toBe(true);
    expect(screen.getByLabelText(/resumo/i).value).toBe('Resumo mantido');
    expect(screen.getByLabelText(/referência de evidência/i).value).toBe('vault/nada.md:1');
    expect(screen.getByRole('button', { name: 'Registrar' }).disabled).toBe(false);
  });

  it('falha de rede também mantém o formulário', async () => {
    const user = userEvent.setup();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('down')));
    render(<Harness />);
    await openIt(user);
    await user.type(screen.getByLabelText(/resumo/i), 'ok');
    await user.type(screen.getByLabelText(/referência de evidência/i), 'DEM-1');
    await user.click(screen.getByRole('button', { name: 'Registrar' }));
    expect(await screen.findByText(/sem conexão/i)).toBeTruthy();
    expect(screen.getByLabelText(/resumo/i).value).toBe('ok');
  });

  it('Esc fecha e devolve o foco ao botão que abriu', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const opener = screen.getByRole('button', { name: 'Abrir registro' });
    await user.click(opener);
    expect(dlg().open).toBe(true);
    await user.keyboard('{Escape}');
    expect(dlg().open).toBe(false);
    expect(document.activeElement).toBe(opener);
  });

  it('Cancelar fecha e devolve o foco', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const opener = screen.getByRole('button', { name: 'Abrir registro' });
    await user.click(opener);
    await user.click(screen.getByRole('button', { name: 'Cancelar' }));
    expect(dlg().open).toBe(false);
    expect(document.activeElement).toBe(opener);
  });

  it('resumo pré-preenchido com os parâmetros Liquid', async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ playbookId: 'PB-002', environment: 'hml', params: { cliente: 'ACME', qtd: 2 } }} />);
    await openIt(user);
    expect(screen.getByLabelText(/resumo/i).value).toBe('Parâmetros Liquid: {"cliente":"ACME","qtd":2}');
  });

  it('sem parâmetros o resumo começa vazio e o ambiente vem do playbook', async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ playbookId: 'PB-001' }} />);
    await openIt(user);
    expect(screen.getByLabelText(/resumo/i).value).toBe('');
    expect(screen.getByLabelText(/ambiente/i).value).toBe('local');
  });

  it('reabrir limpa o formulário', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await openIt(user);
    await user.type(screen.getByLabelText(/resumo/i), 'rascunho');
    await user.keyboard('{Escape}');
    await openIt(user);
    expect(screen.getByLabelText(/resumo/i).value).toBe('');
  });
});
