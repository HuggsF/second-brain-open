import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import ContradictionBanner from './ContradictionBanner.jsx';

const c = { rule_id: 'RULE-007', environment: 'hml', light: 'green', health: 'red', reason: 'banco fora do ar' };

describe('ContradictionBanner', () => {
  it('não renderiza nada sem contradições', () => {
    const { container } = render(<ContradictionBanner contradictions={[]} />);
    expect(container.firstChild).toBeNull();
    const again = render(<ContradictionBanner />);
    expect(again.container.firstChild).toBeNull();
  });

  it('cita a regra e o ambiente, com a razão', () => {
    render(<ContradictionBanner contradictions={[c]} />);
    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('RULE-007');
    expect(alert.textContent).toContain('Homologação');
    expect(alert.textContent).toContain('banco fora do ar');
  });

  it('lista cada contradição', () => {
    render(<ContradictionBanner contradictions={[c, { ...c, rule_id: 'RULE-008', environment: 'production' }]} />);
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByRole('alert').textContent).toContain('Produção');
  });
});
