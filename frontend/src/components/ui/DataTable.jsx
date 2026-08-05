import React, { useState, useEffect, useMemo } from 'react';
import Spinner from './Spinner';
import EmptyState from './EmptyState';
import { ChevronLeft, ChevronRight, ChevronUp, ChevronDown, ChevronsUpDown, Search, X } from 'lucide-react';

/**
 * Enhanced DataTable with server-side pagination, sorting, and filtering.
 *
 * Props:
 * - columns: [{ key, header, accessorKey (string|fn), cell (fn), sortable (bool), filterable (bool), headerClassName, className }]
 * - data: array of row objects
 * - loading: bool
 * - keyExtractor: fn
 * - emptyTitle / emptyDescription / emptyAction
 * - page / pageCount / onPageChange: server-side pagination
 * - onSortChange: fn({ key, direction }) — server-side sorting
 * - onFilterChange: fn(filters) — server-side filtering
 * - sortBy / sortDirection: controlled sort state
 * - filters: controlled filter state
 * - onRowClick: fn(row)
 * - pageSize / onPageSizeChange: optional page size selector
 * - totalCount: optional total record count
 */
export const DataTable = ({
  columns = [],
  data = [],
  loading = false,
  keyExtractor = (item, index) => item.id || index,
  emptyTitle = 'No records found',
  emptyDescription = 'There are no items to display.',
  emptyAction,
  page = 1,
  pageCount = 1,
  onPageChange,
  onSortChange,
  onFilterChange,
  sortBy,
  sortDirection,
  filters = {},
  onRowClick,
  className = '',
  pageSize = 10,
  onPageSizeChange,
  totalCount,
  showPageSize = false,
}) => {
  const [localFilters, setLocalFilters] = useState(filters);
  const [localSort, setLocalSort] = useState({ key: sortBy, direction: sortDirection });

  // Sync local state with controlled props
  useEffect(() => {
    setLocalFilters(filters);
  }, [filters]);

  useEffect(() => {
    setLocalSort({ key: sortBy, direction: sortDirection });
  }, [sortBy, sortDirection]);

  const handleSort = (col) => {
    if (!col.sortable) return;
    const nextDirection = localSort.key === col.key && localSort.direction === 'asc' ? 'desc' : 'asc';
    const nextSort = { key: col.key, direction: nextDirection };
    setLocalSort(nextSort);
    if (onSortChange) {
      onSortChange(nextSort);
    }
  };

  const handleFilterInput = (colKey, value) => {
    const next = { ...localFilters, [colKey]: value };
    setLocalFilters(next);
    if (onFilterChange) {
      onFilterChange(next);
    }
  };

  const clearFilter = (colKey) => {
    const next = { ...localFilters };
    delete next[colKey];
    setLocalFilters(next);
    if (onFilterChange) {
      onFilterChange(next);
    }
  };

  const SortIcon = ({ col }) => {
    if (!col.sortable) return null;
    if (localSort.key === col.key) {
      return localSort.direction === 'asc'
        ? <ChevronUp className="w-3.5 h-3.5 inline ml-1 text-emerald-500" />
        : <ChevronDown className="w-3.5 h-3.5 inline ml-1 text-emerald-500" />;
    }
    return <ChevronsUpDown className="w-3.5 h-3.5 inline ml-1 text-gray-300 dark:text-slate-600" />;
  };

  const hasFilters = columns.some(c => c.filterable);

  return (
    <div className={`data-table-container ${className}`}>
      <div className="data-table-scroll">
        <table className="data-table">
          <thead>
            <tr className="data-table-header-row">
              {columns.map((col, idx) => (
                <th
                  key={col.key || idx}
                  className={`data-table-th ${col.headerClassName || ''} ${col.sortable ? 'data-table-sortable' : ''}`}
                  onClick={() => handleSort(col)}
                >
                  <span className="inline-flex items-center">
                    {col.header}
                    <SortIcon col={col} />
                  </span>
                </th>
              ))}
            </tr>
            {hasFilters && (
              <tr className="data-table-filter-row">
                {columns.map((col, idx) => (
                  <th key={`filter-${col.key || idx}`} className="data-table-filter-th">
                    {col.filterable ? (
                      <div className="relative">
                        <Search className="w-3 h-3 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
                        <input
                          type="text"
                          className="data-table-filter-input"
                          placeholder={`Filter ${col.header}...`}
                          value={localFilters[col.key] || ''}
                          onChange={(e) => handleFilterInput(col.key, e.target.value)}
                        />
                        {localFilters[col.key] && (
                          <button
                            className="absolute right-1.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                            onClick={() => clearFilter(col.key)}
                            aria-label={`Clear ${col.header} filter`}
                          >
                            <X className="w-3 h-3" />
                          </button>
                        )}
                      </div>
                    ) : null}
                  </th>
                ))}
              </tr>
            )}
          </thead>
          <tbody className="data-table-body">
            {loading ? (
              <tr>
                <td colSpan={columns.length} className="py-12">
                  <Spinner message="Loading records..." />
                </td>
              </tr>
            ) : data.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="py-8">
                  <EmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} />
                </td>
              </tr>
            ) : (
              data.map((row, rowIndex) => (
                <tr
                  key={keyExtractor(row, rowIndex)}
                  onClick={() => onRowClick && onRowClick(row)}
                  className={`data-table-row ${onRowClick ? 'data-table-row-clickable' : ''}`}
                >
                  {columns.map((col, colIndex) => {
                    let cellContent;
                    if (col.cell) {
                      cellContent = col.cell(row, rowIndex);
                    } else if (typeof col.accessorKey === 'function') {
                      cellContent = col.accessorKey(row);
                    } else if (col.accessorKey) {
                      cellContent = row[col.accessorKey];
                    } else {
                      cellContent = null;
                    }
                    return (
                      <td key={col.key || colIndex} className={`data-table-td ${col.className || ''}`}>
                        {cellContent ?? '-'}
                      </td>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls */}
      {(pageCount > 1 || showPageSize) && (
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
      )}
    </div>
  );
};

export default DataTable;