import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RulesView from './RulesView.jsx';
import { state, assessment, RULES, RED_RULE } from '../test-utils.jsx';

const okAssess = () => state({ production: assessment('production'), hml: assessment('hml') });

describe('RulesView', () => {
  it('mostra 3 regras com chips Verde, Amarela, Cinza e os motivos', () => {
    render(<RulesView rules={state(RULES)} assessments={okAssess()} />);
    expect(screen.getAllByRole('row')).toHaveLength(4); // cabeçalho + 3
    expect(screen.getByText('Verde')).toBeTruthy();
    expect(screen.getByText('Amarela')).toBeTruthy();
    expect(screen.getByText('Cinza')).toBeTruthy();
    expect(screen.getByText('PB-002 passou há pouco')).toBeTruthy();
    expect(screen.getByText('última execução de teste expirou')).toBeTruthy();
    expect(screen.getByText('sem execução de teste registrada')).toBeTruthy();
  });

  it('regra vermelha: texto, ícone e motivo, nunca só cor', () => {
    render(<RulesView rules={state([RED_RULE])} assessments={okAssess()} />);
    const row = screen.getByRole('row', { name: /RULE-R/ });
    expect(within(row).getByText('Vermelha')).toBeTruthy();
    expect(within(row).getByText('PB-001 falhou em hml')).toBeTruthy();
    expect(row.querySelector('svg')).not.toBeNull();
  });

  it('saúde obsoleta mostra chip amarelo sem alterar o chip de teste', () => {
    const stale = state({
      production: assessment('production'),
      hml: assessment('hml', { status: 'yellow', stale: true, reason: 'coleta atrasada' }),
    });
    render(<RulesView rules={state([RULES[0]])} assessments={stale} />);
    const row = screen.getByRole('row', { name: /RULE-G/ });
    expect(within(row).getByText('Verde')).toBeTruthy(); // luz de teste intacta
    expect(within(row).getByText('Degradada')).toBeTruthy();
    expect(within(row).getByText(/desatualizad/i)).toBeTruthy();
    expect(within(row).queryByText('Amarela')).toBeNull();
  });

  it('saúde vem só dos ambientes de teste da regra (production e hml)', () => {
    const a = state({
      production: assessment('production', { status: 'red' }),
      hml: assessment('hml'),
    });
    render(<RulesView rules={state([RULES[0], RULES[1]])} assessments={a} />);
    const onlyHml = screen.getByRole('row', { name: /RULE-G/ });
    expect(within(onlyHml).getByText('Homologação')).toBeTruthy();
    expect(within(onlyHml).queryByText('Produção')).toBeNull();
    const both = screen.getByRole('row', { name: /RULE-Y/ });
    expect(within(both).getByText('Produção')).toBeTruthy();
    expect(within(both).getByText('Com falha')).toBeTruthy();
  });

  it('regra só com ambiente local não tem saúde observada', () => {
    render(
      <RulesView rules={state([{ ...RULES[2], test_environments: ['local'] }])} assessments={okAssess()} />,
    );
    expect(screen.getByText(/sem ambiente observado/i)).toBeTruthy();
  });

  it('avaliação indisponível mostra Saúde indisponível e mantém a luz', () => {
    render(<RulesView rules={state([RULES[0]])} assessments={state({ production: null, hml: null })} />);
    expect(screen.getByText(/saúde indisponível/i)).toBeTruthy();
    expect(screen.getByText('Verde')).toBeTruthy();
  });

  it('banner de contradição só aparece com contradições e cita regra e ambiente', () => {
    const { rerender } = render(<RulesView rules={state(RULES)} assessments={okAssess()} />);
    expect(screen.queryByRole('alert')).toBeNull();
    const withC = state({
      production: assessment('production'),
      hml: assessment('hml', {
        status: 'red',
        contradictions: [{ rule_id: 'RULE-G', environment: 'hml', light: 'green', health: 'red', reason: 'banco fora' }],
      }),
    });
    rerender(<RulesView rules={state(RULES)} assessments={withC} />);
    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('RULE-G');
    expect(alert.textContent).toContain('Homologação');
  });

  it('lista vazia mostra estado vazio com texto', () => {
    render(<RulesView rules={state([])} assessments={okAssess()} />);
    expect(screen.getByText(/nenhuma regra/i)).toBeTruthy();
  });

  it('carregando mostra texto de carregamento', () => {
    render(<RulesView rules={state(null, { loading: true })} assessments={state(null, { loading: true })} />);
    expect(screen.getByRole('status').textContent).toMatch(/carregando regras/i);
  });

  it('erro mostra Tentar novamente e chama reload', async () => {
    const rules = state(null, { error: { status: 0, message: 'Sem conexão com o servidor.' } });
    render(<RulesView rules={rules} assessments={okAssess()} />);
    expect(screen.getByText('Sem conexão com o servidor.')).toBeTruthy();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Tentar novamente' }));
    expect(rules.reload).toHaveBeenCalledTimes(1);
  });
});
