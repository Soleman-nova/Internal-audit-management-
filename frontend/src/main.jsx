import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.jsx';
import { AuthProvider } from './context/AuthContext';
import { ToastProvider } from './context/ToastContext';
import { I18nProvider } from './context/I18nContext';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      {/* I18n outside Toast: the toast container is a sibling of ToastProvider's
          children, so it is outside its own provider's subtree — it needs `t`
          for the dismiss button's accessible name and can only reach it from
          here. I18nProvider depends only on useAuth, so the swap is free. */}
      <I18nProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </I18nProvider>
    </AuthProvider>
  </StrictMode>
);
