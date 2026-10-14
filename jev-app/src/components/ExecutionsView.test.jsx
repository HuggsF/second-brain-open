import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ExecutionsView from './ExecutionsView.jsx';
import { state, EXECUTIONS, PLAYBOOKS } from '../test-utils.jsx';

const view = (executions = EXECUTIONS, onRecord = vi.fn()) =>
  render(<ExecutionsView executions={state(executions)} playbooks={state(PLAYBOOKS)} onRecord={onRecord} />);

describe('ExecutionsView', () => {
  it('ordena da mais nova para a mais antiga', () => {
    view();
    const rows = screen.getAllByRole('row').slice(1);
    expect(rows).toHaveLength(3);
    expect(rows[0].textContent).toContain('Cenário 7 falhou'); // 12/10
    expect(rows[1].textContent).toContain('Emissão bloqueada como esperado'); // 10/10
    expect(rows[2].textContent).toContain('Runner indisponível'); // 01/10
  });

  it('mostra resultado (texto), ambiente, resumo, evidência, commit, run e origem', () => {
    view();
    const row = screen.getAllByRole('row')[2];
    expect(within(row).getByText('Aprovada')).toBeTruthy();
    expect(within(row).getByText('Homologação')).toBeTruthy();
    expect(within(row).getByText('vault/x.md:57')).toBeTruthy();
    expect(within(row).getByText('abc1234')).toBeTruthy();
    expect(within(row).getByText('run-77')).toBeTruthy();
    expect(within(row).getByText('dashboard')).toBeTruthy();
    expect(row.querySelector('time[datetime]')).not.toBeNull();
    expect(row.querySelector('svg')).not.toBeNull(); // ícone do resultado
  });

  it('origem cai em _origin quando não há source', () => {
    view();
    expect(within(screen.getAllByRole('row')[3]).getByText('seed')).toBeTruthy();
  });

  it('linha do tempo só com 2 ou mais execuções, só com atributos SVG', () => {
    const { container, unmount } = view();
    const svg = container.querySelector('svg[role="img"]');
    expect(svg).not.toBeNull();
    expect(svg.getAttribute('aria-label')).toMatch(/linha do tempo/i);
    expect(svg.querySelectorAll('circle')).toHaveLength(3);
    expect(container.querySelectorAll('[style]')).toHaveLength(0);
    unmount();
    const one = view([EXECUTIONS[0]]);
    expect(one.container.querySelector('svg[role="img"]')).toBeNull();
    expect(screen.getByText(/2 ou mais/i)).toBeTruthy();
  });

  it('vazio mostra texto e ainda oferece registrar', async () => {
    const onRecord = vi.fn();
    view([], onRecord);
    expect(screen.getByText(/nenhuma execução/i)).toBeTruthy();
  });

  it('botão Registrar execução chama onRecord sem playbook e com o botão como retorno de foco', async () => {
    const user = userEvent.setup();
    const onRecord = vi.fn();
    view(EXECUTIONS, onRecord);
    await user.click(screen.getByRole('button', { name: /registrar execução/i }));
    expect(onRecord).toHaveBeenCalledWith({}, expect.any(HTMLElement));
  });

  it('erro mostra Tentar novamente', async () => {
    const user = userEvent.setup();
    const ex = state(null, { error: { status: 503, message: 'Banco de evidências indisponível.' } });
    render(<ExecutionsView executions={ex} playbooks={state(PLAYBOOKS)} onRecord={() => {}} />);
    expect(screen.getByText('Banco de evidências indisponível.')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }));
    expect(ex.reload).toHaveBeenCalled();
  });
});
