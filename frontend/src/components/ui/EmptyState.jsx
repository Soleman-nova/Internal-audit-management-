import React from 'react';
import { FolderOpen } from 'lucide-react';

export const EmptyState = ({
  icon: Icon = FolderOpen,
  title = 'No records found',
  description = 'There are no items to display at this time.',
  action,
  className = '',
}) => {
  return (
    <div className={`flex flex-col items-center justify-center p-8 text-center bg-gray-50/50 dark:bg-slate-900/50 rounded-xl border border-dashed border-gray-200 dark:border-slate-800 ${className}`}>
      <div className="p-3 bg-white dark:bg-slate-800 rounded-full shadow-sm mb-3 text-gray-400 dark:text-gray-500">
        <Icon className="w-7 h-7" />
      </div>
      <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-1">{title}</h4>
      <p className="text-xs text-gray-500 dark:text-gray-400 max-w-sm mb-4">{description}</p>
      {action && <div>{action}</div>}
    </div>
  );
};

export default EmptyState;
