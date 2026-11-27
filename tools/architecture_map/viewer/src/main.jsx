import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import { readModel } from './model.js';
import './styles.css';

const root = document.getElementById('root');
try {
  createRoot(root).render(<StrictMode><App model={readModel()} /></StrictMode>);
} catch (error) {
  root.textContent = `The map could not start: ${error.message}`;
}
