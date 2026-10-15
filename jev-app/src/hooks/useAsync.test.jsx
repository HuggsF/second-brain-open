import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useAsync } from './useAsync.js';

const ok = (data) => ({ ok: true, status: 200, data });

describe('useAsync', () => {
  it('começa carregando e entrega os dados', async () => {
    const fn = vi.fn().mockResolvedValue(ok([1, 2]));
    const { result } = renderHook(() => useAsync(fn, []));
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual([1, 2]);
    expect(result.current.error).toBeNull();
  });

  it.each([
    [0, null, /sem conexão/i],
    [401, null, /sessão/i],
    [503, { error: 'DB_UNAVAILABLE' }, /indisponível/i],
    [500, null, /HTTP 500/],
  ])('resultado !ok com status %s vira erro legível', async (status, data, text) => {
    const fn = vi.fn().mockResolvedValue({ ok: false, status, data });
    const { result } = renderHook(() => useAsync(fn, []));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error.status).toBe(status);
    expect(result.current.error.message).toMatch(text);
    expect(result.current.data).toBeNull();
  });

  it('promessa rejeitada também vira erro', async () => {
    const fn = vi.fn().mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useAsync(fn, []));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error.message).toBeTruthy();
  });

  it('reload busca de novo e limpa o erro', async () => {
    const fn = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 0, data: null })
      .mockResolvedValueOnce(ok('depois'));
    const { result } = renderHook(() => useAsync(fn, []));
    await waitFor(() => expect(result.current.error).not.toBeNull());
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.data).toBe('depois'));
    expect(result.current.error).toBeNull();
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it('mudar as dependências refaz a busca e ignora resposta atrasada', async () => {
    let resolveFirst;
    const fn = vi.fn((key) =>
      key === 'a' ? new Promise((r) => (resolveFirst = () => r(ok('A')))) : Promise.resolve(ok('B')),
    );
    const { result, rerender } = renderHook(({ k }) => useAsync(() => fn(k), [k]), { initialProps: { k: 'a' } });
    await waitFor(() => expect(fn).toHaveBeenCalledWith('a'));
    rerender({ k: 'b' });
    await waitFor(() => expect(result.current.data).toBe('B'));
    await act(async () => resolveFirst());
    expect(result.current.data).toBe('B');
  });
});
