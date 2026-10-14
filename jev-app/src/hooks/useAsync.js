import { useCallback, useEffect, useRef, useState } from 'react';
import { describeFailure } from '../lib/api.js';

// Carrega dados assincronos. `fn` devolve o resultado de lib/api.js ({ok, status, data}) ou um valor
// qualquer. Resultado !ok vira `error` ({status, message}); promessa rejeitada tambem. Dados antigos
// ficam visiveis durante um reload; respostas atrasadas de uma busca anterior sao descartadas.
export function useAsync(fn, deps = []) {
  const [state, setState] = useState({ loading: true, error: null, data: null });
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const seq = useRef(0);

  useEffect(() => {
    const id = ++seq.current;
    setState((prev) => ({ ...prev, loading: true, error: null }));
    Promise.resolve()
      .then(() => fnRef.current())
      .then(
        (res) => {
          if (id !== seq.current) return;
          if (res && typeof res === 'object' && typeof res.ok === 'boolean') {
            if (res.ok) setState({ loading: false, error: null, data: res.data });
            else {
              setState((prev) => ({
                loading: false,
                error: { status: res.status, message: describeFailure(res.status) },
                data: prev.data,
              }));
            }
          } else {
            setState({ loading: false, error: null, data: res });
          }
        },
        (err) => {
          if (id !== seq.current) return;
          setState((prev) => ({
            loading: false,
            error: { status: 0, message: (err && err.message) || 'Falha inesperada.' },
            data: prev.data,
          }));
        },
      );
    return () => {
      seq.current += 1;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}
