import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

/**
 * Server-side pagination control (page info + prev/next + optional page-size
 * selector). Pure presentational — the parent owns the page/pageSize state and
 * refetches. Mirrors the DataTable footer so it shares the same theme-aware
 * CSS (.data-table-pagination / .data-table-page-size-select / .data-table-page-btn).
 *
 * Props:
 * - page: 1-based current page
 * - pageCount: total pages (caller passes Math.max(1, Math.ceil(total/pageSize)))
 * - totalCount: optional server total (renders "N total record(s)")
 * - onPageChange: fn(nextPage)
 * - pageSize / onPageSizeChange / showPageSize: optional page-size selector
 */
const Pagination = ({
  page = 1,
  pageCount = 1,
  totalCount,
  onPageChange,
  pageSize = 10,
  onPageSizeChange,
  showPageSize = false,
}) => {
  if (!(pageCount > 1 || showPageSize)) return null;

  return (
    <div className="data-table-pagination">
      <div className="flex items-center gap-3">
        {showPageSize && onPageSizeChange && (
          <div className="flex items-center gap-1.5">
            <span className="text-gray-500 dark:text-gray-400">Rows:</span>
            <select
              className="data-table-page-size-select"
              value={pageSize}
              onChange={(e) => onPageSizeChange(parseInt(e.target.value))}
            >
              {[10, 25, 50, 100].map(size => (
                <option key={size} value={size}>{size}</option>
              ))}
            </select>
          </div>
        )}
        {totalCount !== undefined && (
          <span className="text-gray-500 dark:text-gray-400">
            {totalCount} total record{totalCount !== 1 ? 's' : ''}
          </span>
        )}
      </div>
      {pageCount > 1 && onPageChange && (
        <div className="flex items-center gap-1">
          <span className="text-gray-500 dark:text-gray-400 mr-2">
            Page <span className="font-medium text-gray-800 dark:text-gray-200">{page}</span> of{' '}
            <span className="font-medium text-gray-800 dark:text-gray-200">{pageCount}</span>
          </span>
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className="data-table-page-btn"
            aria-label="Previous page"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button
            onClick={() => onPageChange(page + 1)}
            disabled={page >= pageCount}
            className="data-table-page-btn"
            aria-label="Next page"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
};

export default Pagination;
