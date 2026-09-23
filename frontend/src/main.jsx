import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.jsx';
import { AuthProvider } from './context/AuthContext';
import { ToastProvider } from './context/ToastContext';
import { I18nProvider } from './context/I18nContext';
import MaybeLogtoProvider from './auth/MaybeLogtoProvider';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {/* Outermost, and specifically *outside* AuthProvider: AuthContext ends the
        Logto SSO session on logout via a bridge component that calls useLogto(),
        which throws if no provider is above it — taking the whole app down with
        it, login page included. */}
    <MaybeLogtoProvider>
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
    </MaybeLogtoProvider>
  </StrictMode>
);
