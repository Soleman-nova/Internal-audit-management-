import React, { useState, useEffect } from 'react';
import { usersApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import DataTable from '../../components/ui/DataTable';
import Badge from '../../components/ui/Badge';
import { Activity, Search, RefreshCw, Filter, Clock, User, Shield } from 'lucide-react';

function AuditTrailPage() {
  const toast = useToast();
  const { t } = useI18n();
  const [trail, setTrail] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterAction, setFilterAction] = useState('');
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [sortBy, setSortBy] = useState('timestamp');
  const [sortDirection, setSortDirection] = useState('desc');
  const [filters, setFilters] = useState({});
  const PAGE_SIZE = 25;

  const fetchAuditTrail = async () => {
    setLoading(true);
    try {
      const params = { page, page_size: PAGE_SIZE };
      if (filterAction) params.action = filterAction;
      if (searchQuery) params.search = searchQuery;
      if (sortBy) params.ordering = (sortDirection === 'desc' ? '-' : '') + sortBy;
      // Apply column filters
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params[key] = value;
      });
      const res = await usersApi.getAuditTrail(params);
      setTrail(res.results || res || []);
      setTotalCount(res.count || (Array.isArray(res) ? res.length : 0));
    } catch (err) {
      toast.error('Failed to load audit trail');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAuditTrail();
    // eslint-disable-next-line
  }, [page, filterAction, sortBy, sortDirection, filters]);

  const handleSearch = (e) => {
    e.preventDefault();
    setPage(1);
    fetchAuditTrail();
  };

  const handleFilterChange = (e) => {
    setFilterAction(e.target.value);
    setPage(1);
  };

  const handleSortChange = ({ key, direction }) => {
    setSortBy(key);
    setSortDirection(direction);
    setPage(1);
  };

  const handleFilterInput = (nextFilters) => {
    setFilters(nextFilters);
    setPage(1);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
      + ' ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  };

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  const columns = [
    {
      header: t('timestamp'),
      key: 'timestamp',
      sortable: true,
      cell: (row) => <span className="font-mono text-secondary">{formatDate(row.timestamp || row.created_at)}</span>,
    },
    {
      header: t('user'),
      key: 'user_email',
      sortable: true,
      filterable: true,
      cell: (row) => (
        <div>
          <strong className="block text-primary font-medium">{row.user_name || row.user_email || '—'}</strong>
          <span className="text-xs text-muted">{row.user_email}</span>
        </div>
      ),
    },
    {
      header: t('action'),
      key: 'action',
      sortable: true,
      filterable: true,
      cell: (row) => <Badge status={row.action || 'info'}>{row.action || 'system'}</Badge>,
    },
    {
      header: t('targetResource'),
      key: 'object_repr',
      filterable: true,
      cell: (row) => (
        <span className="truncate max-w-xs block text-secondary">
          {row.object_repr || row.target || row.description || '—'}
        </span>
      ),
    },
    {
      header: t('ipAddress'),
      key: 'ip_address',
      cell: (row) => <span className="font-mono text-xs text-muted">{row.ip_address || '127.0.0.1'}</span>,
    },
    {
      header: t('role'),
      key: 'user_role',
      cell: (row) => (
        <Badge variant="neutral">
          {row.user_role || (row.user ? row.user.role || 'user' : 'user')}
        </Badge>
      ),
    },
  ];

  return (
    <div className="audit-trail-view">
      {/* Header Controls */}
      <div className="card">
        <div className="card-header justify-between">
          <div>
            <h3 className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-accent" />
              {t('systemAuditTrail')}
            </h3>
            <p className="card-subtitle mt-1">
              {t('completeChronologicalLog')}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Badge variant="neutral">{t('events', totalCount)}</Badge>
            <button
              className="btn btn-sm btn-outline flex items-center gap-1.5"
              onClick={() => { setPage(1); fetchAuditTrail(); }}
            >
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </button>
          </div>
        </div>

        {/* Search + Filter Bar */}
        <div className="flex gap-3 flex-wrap items-center">
          <form onSubmit={handleSearch} className="flex gap-2 flex-1 min-w-[240px]">
            <div className="relative flex-1">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
              <input
                type="text"
                className="form-control pl-9"
                placeholder={t('searchByUser')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <button type="submit" className="btn btn-primary btn-sm">
              Search
            </button>
          </form>

          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-muted" />
            <select
              className="form-control"
              style={{ width: 'auto' }}
              value={filterAction}
              onChange={handleFilterChange}
            >
              <option value="">{t('allActions')}</option>
              <option value="login">{t('loginAuth')}</option>
              <option value="create">{t('create')}</option>
              <option value="update">{t('updateEdit')}</option>
              <option value="delete">{t('delete')}</option>
              <option value="approve">{t('approveSubmit')}</option>
              <option value="export">{t('exportDownload')}</option>
            </select>
          </div>
        </div>
      </div>

      {/* Trail Table */}
      <DataTable
        columns={columns}
        data={trail}
        loading={loading}
        emptyTitle={t('noAuditTrailEvents')}
        emptyDescription={t('tryAdjusting')}
        page={page}
        pageCount={totalPages}
        onPageChange={setPage}
        sortBy={sortBy}
        sortDirection={sortDirection}
        onSortChange={handleSortChange}
        filters={filters}
        onFilterChange={handleFilterInput}
        totalCount={totalCount}
        showPageSize={false}
        pageSize={PAGE_SIZE}
      />
    </div>
  );
}

export default AuditTrailPage;