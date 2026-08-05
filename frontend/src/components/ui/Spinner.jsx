import React from 'react';
import { Loader2 } from 'lucide-react';

const sizeClasses = {
  sm: 'w-4 h-4',
  md: 'w-6 h-6',
  lg: 'w-10 h-10',
};

export const Spinner = ({ size = 'md', message, className = '' }) => {
  return (
    <div className={`flex flex-col items-center justify-center p-6 text-gray-500 dark:text-gray-400 ${className}`}>
      <Loader2 className={`animate-spin text-emerald-600 dark:text-emerald-400 ${sizeClasses[size] || sizeClasses.md}`} />
      {message && <p className="mt-2 text-xs font-medium">{message}</p>}
    </div>
  );
};

export default Spinner;
