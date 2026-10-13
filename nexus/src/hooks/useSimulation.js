import { useSimulationContext } from '../context.jsx';
export function useSimulation() {
  const { workspace, simulation, actions, effectiveReducedMotion } = useSimulationContext();
  return { workspace, simulation, actions, effectiveReducedMotion };
}
