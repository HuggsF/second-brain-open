import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.jsx';
import { syncParentTheme } from './lib/theme.js';

syncParentTheme();
createRoot(document.getElementById('root')).render(<App />);
