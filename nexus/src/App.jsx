import React from 'react';
import { SimulationProvider } from './context.jsx';
import Workspace from './components/Workspace.jsx';

export default function App() {
  return <SimulationProvider><Workspace /></SimulationProvider>;
}
