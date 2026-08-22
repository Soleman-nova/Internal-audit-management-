import React, { useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';

const sizeClasses = {
  sm: 'max-w-md',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
  xl: 'max-w-4xl',
  full: 'max-w-6xl',
};

// Everything the browser will focus, minus the elements that are focusable but
// not tabbable. `tabindex="-1"` is deliberately excluded — the dialog itself
// carries it as a fallback target and must not become a tab stop.
const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export const Modal = ({
  isOpen,
  onClose,
  title,
  subtitle,
  children,
  footer,
  size = 'md',
  closeOnBackdrop = true,
}) => {
  const dialogRef = useRef(null);
  // Where focus was before the dialog opened, so it can be handed back on
  // close. Without this, dismissing a modal drops the caret at the top of the
  // document and a keyboard user has to tab all the way back to the button
  // they just pressed.
  const previouslyFocused = useRef(null);
  const headingId = useId();
  const descriptionId = useId();

  useEffect(() => {
    if (!isOpen) return undefined;

    previouslyFocused.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;

    const focusable = () => Array.from(dialogRef.current?.querySelectorAll(FOCUSABLE) || []);

    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && onClose) {
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;

      // Trap: a dialog that lets Tab reach the page behind it is unusable with
      // a keyboard or a screen reader, which announce the background content as
      // though it were available. Wrap at both ends instead.
      const items = focusable();
      if (items.length === 0) {
        // Nothing to cycle through — keep focus on the dialog rather than
        // letting it escape to the document.
        e.preventDefault();
        dialogRef.current?.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || !dialogRef.current?.contains(active))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (active === last || !dialogRef.current?.contains(active))) {
        e.preventDefault();
        first.focus();
      }
    };

    document.body.style.overflow = 'hidden';
    // Listen in the capture phase so the trap sees Tab before any field inside
    // the dialog can act on it.
    document.addEventListener('keydown', handleKeyDown, true);

    // Focus the dialog itself rather than its first control: that is what makes
    // a screen reader announce the title and subtitle on open. Focusing the
    // close button instead — it is first in DOM order — would announce "Close
    // modal, button" with no indication of what had opened. Tab moves inward
    // from here, and the trap above keeps it inside.
    dialogRef.current?.focus();

    return () => {
      document.body.style.overflow = 'unset';
      document.removeEventListener('keydown', handleKeyDown, true);
      previouslyFocused.current?.focus?.();
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-fadeIn">
      {/* Backdrop — aria-hidden because it is decoration plus a click target;
          Escape and the close button are the accessible ways out. */}
      <div
        aria-hidden="true"
        className="fixed inset-0"
        onClick={() => closeOnBackdrop && onClose && onClose()}
      />

      {/* Dialog container */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        // Point the accessible name at the visible heading when there is one;
        // fall back to the literal string so the dialog is never anonymous.
        {...(title ? { 'aria-labelledby': headingId } : { 'aria-label': 'Dialog' })}
        {...(subtitle ? { 'aria-describedby': descriptionId } : {})}
        tabIndex={-1}
        className={`relative bg-white dark:bg-slate-900 rounded-xl shadow-2xl w-full ${sizeClasses[size] || sizeClasses.md} z-10 overflow-hidden border border-gray-200 dark:border-slate-800 flex flex-col max-h-[90vh] focus:outline-none`}
      >
        {/* Header */}
        {(title || onClose) && (
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 dark:border-slate-800 bg-gray-50/50 dark:bg-slate-900/50">
            <div>
              {title && (
                <h3 id={headingId} className="text-lg font-semibold text-gray-900 dark:text-white">
                  {title}
                </h3>
              )}
              {subtitle && (
                <p id={descriptionId} className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                  {subtitle}
                </p>
              )}
            </div>
            {onClose && (
              <button
                type="button"
                onClick={onClose}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors"
                aria-label="Close modal"
              >
                <X className="w-5 h-5" />
              </button>
            )}
          </div>
        )}

        {/* Content Body */}
        <div className="p-6 overflow-y-auto flex-1">{children}</div>

        {/* Footer */}
        {footer && (
          <div className="px-6 py-4 border-t border-gray-100 dark:border-slate-800 bg-gray-50/50 dark:bg-slate-900/50 flex justify-end gap-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
};

export default Modal;
