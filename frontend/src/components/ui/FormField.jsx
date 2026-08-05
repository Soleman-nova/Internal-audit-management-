import React from 'react';

export const FormField = ({
  label,
  required,
  error,
  helpText,
  children,
  className = '',
  id,
}) => {
  return (
    <div className={`space-y-1 ${className}`}>
      {label && (
        <label htmlFor={id} className="block text-xs font-semibold text-gray-700 dark:text-gray-300">
          {label} {required && <span className="text-rose-500">*</span>}
        </label>
      )}
      {children}
      {error && <p className="text-xs text-rose-600 dark:text-rose-400 mt-1 font-medium">{error}</p>}
      {helpText && !error && <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{helpText}</p>}
    </div>
  );
};

export default FormField;
