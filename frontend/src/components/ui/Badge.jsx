import React from 'react';

const variantStyles = {
  success: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800',
  warning: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800',
  danger: 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/60 dark:text-rose-300 dark:border-rose-800',
  info: 'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/60 dark:text-sky-300 dark:border-sky-800',
  purple: 'bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950/60 dark:text-purple-300 dark:border-purple-800',
  neutral: 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700',
};

const statusVariantMap = {
  approved: 'success',
  completed: 'success',
  resolved: 'success',
  active: 'success',
  verified: 'success',
  closed: 'success',

  in_progress: 'info',
  submitted: 'info',
  under_review: 'info',
  open: 'info',
  pending: 'warning',

  draft: 'neutral',
  inactive: 'neutral',
  archived: 'neutral',

  critical: 'danger',
  high: 'danger',
  rejected: 'danger',
  overdue: 'danger',

  medium: 'warning',
  moderate: 'warning',
  low: 'success',
};

export const Badge = ({ children, variant, status, className = '' }) => {
  let selectedVariant = variant;
  if (!selectedVariant && status) {
    const key = String(status).toLowerCase();
    selectedVariant = statusVariantMap[key] || 'neutral';
  }
  if (!selectedVariant) selectedVariant = 'neutral';

  const styleClass = variantStyles[selectedVariant] || variantStyles.neutral;

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border capitalize ${styleClass} ${className}`}
    >
      {children || status || ''}
    </span>
  );
};

export default Badge;
