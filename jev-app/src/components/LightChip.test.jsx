import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import LightChip from './LightChip.jsx';
import HealthChip from './HealthChip.jsx';

describe('LightChip', () => {
  it.each([
    ['green', 'Verde'],
    ['yellow', 'Amarela'],
    ['red', 'Vermelha'],
    ['grey', 'Cinza'],
  ])('%s mostra texto %s, ícone e o motivo visível', (light, label) => {
    const { container } = render(<LightChip light={light} reason="motivo de teste" />);
    expect(screen.getByText(label)).toBeTruthy();
    expect(screen.getByText('motivo de teste')).toBeTruthy();
    expect(container.querySelector('svg')).not.toBeNull();
    expect(container.querySelector('[title]')).toBeNull();
  });

  it('luz desconhecida cai em Cinza', () => {
    render(<LightChip light="roxa" reason="" />);
    expect(screen.getByText('Cinza')).toBeTruthy();
  });
});

describe('HealthChip', () => {
  it('mostra rótulo e ícone por status', () => {
    const { container } = render(<HealthChip status="red" />);
    expect(screen.getByText('Com falha')).toBeTruthy();
    expect(container.querySelector('svg')).not.toBeNull();
  });
  it('dados obsoletos aparecem em texto', () => {
    render(<HealthChip status="yellow" stale />);
    expect(screen.getByText('Degradada')).toBeTruthy();
    expect(screen.getByText(/desatualizad/i)).toBeTruthy();
  });
});
