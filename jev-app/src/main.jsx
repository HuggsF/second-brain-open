import { createRoot } from 'react-dom/client';
import './index.css';

function App() {
  return (
    <main className="p-8">
      <h1 className="text-[32px] font-semibold tracking-tight text-text">
        JEV — Evidência e luzes de teste
      </h1>
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
