import React, { createContext, useContext, useState, useCallback, useRef } from 'react';
import { CheckCircle2, AlertTriangle, AlertCircle, Info, X } from 'lucide-react';
import { useI18n } from './I18nContext';

const ToastContext = createContext(null);

// Success and info are progress reports — they wait for a pause in speech.
// Errors and warnings are the only channel the app has for a refusal (the
// engagement completion guard, a 403, a validation failure), so they interrupt,
// and they do not disappear on a timer: 4500ms is not enough to read
// "Cannot complete this engagement: 3 finding(s) are not yet resolved…".
const ASSERTIVE_TYPES = new Set(['error', 'warning']);
const AUTO_DISMISS_MS = 4500;
// Beyond this the stack covers the page it is reporting on. Oldest goes first.
const MAX_VISIBLE = 4;

const TYPE_ICONS = {
  success: <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />,
  error: <AlertCircle className="w-5 h-5 text-rose-600 dark:text-rose-400" />,
  warning: <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400" />,
  info: <Info className="w-5 h-5 text-blue-600 dark:text-blue-400" />,
};

const TYPE_STYLES = {
  success: 'bg-emerald-50 text-emerald-900 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-100 dark:border-emerald-800',
  error: 'bg-rose-50 text-rose-900 border-rose-200 dark:bg-rose-950 dark:text-rose-100 dark:border-rose-800',
  warning: 'bg-amber-50 text-amber-900 border-amber-200 dark:bg-amber-950 dark:text-amber-100 dark:border-amber-800',
  info: 'bg-blue-50 text-blue-900 border-blue-200 dark:bg-blue-950 dark:text-blue-100 dark:border-blue-800',
};

export const ToastProvider = ({ children }) => {
  const [toasts, setToasts] = useState([]);
  // A counter rather than Date.now() + Math.random(): two toasts raised in the
  // same tick used to be able to collide on a key, and `substr` is deprecated.
  const nextId = useRef(0);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback((type, message, title = '') => {
    const id = nextId.current++;
    setToasts((prev) => {
      // Suppress an exact repeat that is still on screen. Several handlers
      // re-fetch inside their catch block, so one failure can raise the same
      // message twice in a row.
      if (prev.some((t) => t.type === type && t.title === title && t.message === message)) {
        return prev;
      }
      return [...prev, { id, type, message, title }].slice(-MAX_VISIBLE);
    });

    if (!ASSERTIVE_TYPES.has(type)) {
      setTimeout(() => removeToast(id), AUTO_DISMISS_MS);
    }
  }, [removeToast]);

  const toast = {
    success: (msg, title) => addToast('success', msg, title || 'Success'),
    error: (msg, title) => addToast('error', msg, title || 'Error'),
    warning: (msg, title) => addToast('warning', msg, title || 'Warning'),
    info: (msg, title) => addToast('info', msg, title || 'Info'),
  };

  const polite = toasts.filter((t) => !ASSERTIVE_TYPES.has(t.type));
  const assertive = toasts.filter((t) => ASSERTIVE_TYPES.has(t.type));

  return (
    <ToastContext.Provider value={toast}>
      {children}
      {/* Two regions, not one: a single container cannot be both polite and
          assertive, and both have to be in the tree *before* their content is
          inserted or a screen reader will not announce the change. They render
          unconditionally and stay empty. */}
      <div className="fixed top-5 right-5 z-[9999] flex flex-col gap-3 max-w-sm w-full pointer-events-none">
        <div role="status" aria-live="polite" aria-atomic="true" className="flex flex-col gap-3">
          {polite.map((t) => <Toast key={t.id} toast={t} onDismiss={removeToast} />)}
        </div>
        <div role="alert" aria-live="assertive" aria-atomic="true" className="flex flex-col gap-3">
          {assertive.map((t) => <Toast key={t.id} toast={t} onDismiss={removeToast} />)}
        </div>
      </div>
    </ToastContext.Provider>
  );
};

const Toast = ({ toast, onDismiss }) => {
  const { t: translate } = useI18n();
  return (
    <div
      className={`pointer-events-auto flex items-start p-4 rounded-lg shadow-lg border text-sm transition-all duration-300 transform translate-y-0 opacity-100 ${
        TYPE_STYLES[toast.type] || TYPE_STYLES.info
      }`}
    >
      <div className="mr-3 mt-0.5 flex-shrink-0">{TYPE_ICONS[toast.type]}</div>
      <div className="flex-1 pr-2">
        {toast.title && <h4 className="font-semibold text-sm mb-0.5">{toast.title}</h4>}
        <p className="text-xs opacity-90 leading-snug">{toast.message}</p>
      </div>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        aria-label={translate('dismissNotification')}
        className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 p-0.5 rounded"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
};

export const useToast = () => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
};

export default ToastContext;
