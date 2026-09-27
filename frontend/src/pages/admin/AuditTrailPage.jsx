import { useState } from 'react';
import { usersApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import useAsyncData from '../../hooks/useAsyncData';
import DataTable from '../../components/ui/DataTable';
import Badge from '../../components/ui/Badge';
import { Activity, Search, RefreshCw, Filter } from 'lucide-react';

const changeValue = (value) => {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
};

/** A compact "from → to" rendering of an audit entry's change diff.
 *
 * This is what makes the trail worth reading: "an UPDATE happened" is not an audit
 * finding, but "status went draft → approved" is. The diff has been recorded
 * (`AuditTrail.changes`, a JSONField) and returned by the API all along — the
 * server populates it at a dozen call sites — it was simply never displayed.
 *
 * Two shapes arrive here. Most entries store `{field: [old, new]}`; the bulk
 * commands log a plain dict of facts typed by hand (e.g. `{demo_case: true}`), so
 * anything that is not a two-item list is rendered as a value, not a transition.
 */
function ChangeSummary({ changes }) {
  const entries =
    changes && typeof changes === 'object' && !Array.isArray(changes)
      ? Object.entries(changes)
      : [];

  if (entries.length === 0) return <span className="text-muted">—</span>;

  // Capped at three: a status change plus a couple of edited fields is the
  // readable case, and a long field list would set the row height for the page.
  const shown = entries.slice(0, 3);

  return (
    <div className="flex flex-col gap-0.5">
      {shown.map(([field, value]) => (
        <span key={field} className="text-xs font-mono text-secondary">
          <span className="text-muted">{field}:</span>{' '}
          {Array.isArray(value)
            ? `${changeValue(value[0])} → ${changeValue(value[1])}`
            : changeValue(value)}
        </span>
      ))}
      {entries.length > shown.length && (
        <span className="text-xs text-muted">+{entries.length - shown.length}</span>
      )}
    </div>
  );
}

function AuditTrailPage() {
  const toast = useToast();
  const { t } = useI18n();
  const [searchQuery, setSearchQuery] = useState('');
  // What the *server* is filtered by, as distinct from what is typed in the box.
  // Search is submit-driven, so the input itself is not a fetch dependency — but
  // giving the applied term its own state is what lets the fetch below be a pure
  // function of its dependencies rather than a manual call, which is where the
  // race lived.
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [filterAction, setFilterAction] = useState('');
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState('timestamp');
  const [sortDirection, setSortDirection] = useState('desc');
  const [filters, setFilters] = useState({});
  const PAGE_SIZE = 25;

  // One request per distinct query, and a superseded one is discarded — so
  // clicking a sortable column twice, or paging faster than the server answers,
  // can no longer let an earlier response land last and render the wrong page
  // under the current filters with no error to hint at it.
  const { data, loading, reload: fetchAuditTrail } = useAsyncData(
    async () => {
      const params = { page, page_size: PAGE_SIZE };
      if (filterAction) params.action = filterAction;
      if (submittedQuery) params.search = submittedQuery;
      if (sortBy) params.ordering = (sortDirection === 'desc' ? '-' : '') + sortBy;
      // Apply column filters
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params[key] = value;
      });
      const res = await usersApi.getAuditTrail(params);
      // One request yields two pieces of state, so the loader returns both rather
      // than the page keeping a second copy in sync by hand.
      return {
        items: res.results || res || [],
        count: res.count || (Array.isArray(res) ? res.length : 0),
      };
    },
    [page, submittedQuery, filterAction, sortBy, sortDirection, filters],
    { onError: () => toast.error(t('auditTrailLoadFailed')) },
  );

  const trail = data?.items ?? [];
  const totalCount = data?.count ?? 0;

  const handleSearch = (e) => {
    e.preventDefault();
    // Both are fetch dependencies now, so setting them *is* the request. Repeating
    // an identical search therefore no longer refetches, which is the correct
    // reading of "nothing changed" rather than a regression.
    setSubmittedQuery(searchQuery);
    setPage(1);
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
      header: t('changes'),
      key: 'changes',
      cell: (row) => <ChangeSummary changes={row.changes} />,
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
              <RefreshCw className="w-3.5 h-3.5" /> {t('refresh')}
            </button>
          </div>
        </div>

        {/* Search + Filter Bar */}
        <div className="trail-toolbar">
          <form onSubmit={handleSearch} className="trail-search">
            <div className="input-group">
              <span className="input-icon">
                <Search size={16} />
              </span>
              <input
                type="text"
                className="form-control"
                placeholder={t('searchByUser')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <button type="submit" className="btn btn-primary">
              {t('search')}
            </button>
          </form>

          <div className="trail-filter">
            <Filter className="w-4 h-4 text-muted" />
            <select
              className="form-control"
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