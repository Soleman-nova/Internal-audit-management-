import React, { useState, useEffect } from 'react';
import apiClient from '../../api/apiClient';
import { Activity, Search, RefreshCw, Filter, User, Clock, Shield } from 'lucide-react';

function AuditTrailPage() {
  const [trail, setTrail] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterAction, setFilterAction] = useState('');
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const PAGE_SIZE = 25;

  const fetchAuditTrail = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page });
      if (filterAction) params.append('action', filterAction);
      if (searchQuery) params.append('search', searchQuery);
      const res = await apiClient.get(`/auth/audit-trail/?${params.toString()}`);
      setTrail(res.data.results || res.data || []);
      setTotalCount(res.data.count || 0);
    } catch (err) {
      console.error('Failed to load audit trail:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAuditTrail();
    // eslint-disable-next-line
  }, [page, filterAction]);

  const handleSearch = (e) => {
    e.preventDefault();
    setPage(1);
    // Use timeout to ensure page state updates before fetch
    setTimeout(() => fetchAuditTrail(), 0);
  };

  const handleFilterChange = (e) => {
    setFilterAction(e.target.value);
    setPage(1);
  };

  const getActionBadgeClass = (action) => {
    if (!action) return 'badge-outline';
    const a = action.toLowerCase();
    if (a.includes('create') || a.includes('add')) return 'badge-success';
    if (a.includes('delete') || a.includes('remove')) return 'badge-danger';
    if (a.includes('login') || a.includes('auth')) return 'badge-info';
    if (a.includes('update') || a.includes('edit') || a.includes('change')) return 'badge-warning';
    if (a.includes('approve') || a.includes('submit')) return 'badge-accent';
    if (a.includes('export') || a.includes('download')) return 'badge-primary';
    return 'badge-outline';
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
      + ' ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  };

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  return (
    <div className="audit-trail-view">
      {/* Header Controls */}
      <div className="card mb-4">
        <div className="card-header justify-between flex-wrap gap-3">
          <div>
            <h3><Activity size={18} className="inline mr-2" />System Audit Trail</h3>
            <p className="card-subtitle">Complete chronological log of all user actions and system events</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="badge badge-outline">{totalCount} Total Events</span>
            <button className="btn btn-outline flex items-center gap-1" onClick={() => { setPage(1); fetchAuditTrail(); }}>
              <RefreshCw size={14} /> Refresh
            </button>
          </div>
        </div>

        {/* Search + Filter Bar */}
        <div className="mt-4 flex gap-3 flex-wrap">
          <form onSubmit={handleSearch} className="flex gap-2 flex-1">
            <div className="relative flex-1">
              <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
              <input
                type="text"
                className="form-control pl-9"
                placeholder="Search by user, action, or target..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <button type="submit" className="btn btn-primary">Search</button>
          </form>

          <div className="flex items-center gap-2">
            <Filter size={16} className="text-muted" />
            <select
              className="form-control"
              value={filterAction}
              onChange={handleFilterChange}
            >
              <option value="">All Actions</option>
              <option value="login">Login / Auth</option>
              <option value="create">Create</option>
              <option value="update">Update / Edit</option>
              <option value="delete">Delete</option>
              <option value="approve">Approve / Submit</option>
              <option value="export">Export / Download</option>
            </select>
          </div>
        </div>
      </div>

      {/* Trail Table */}
      <div className="card">
        {loading ? (
          <div className="loading-spinner">Loading audit events...</div>
        ) : (
          <>
            <div className="table-responsive">
              <table className="table">
                <thead>
                  <tr>
                    <th><Clock size={14} className="inline mr-1" />Timestamp</th>
                    <th><User size={14} className="inline mr-1" />User</th>
                    <th>Action</th>
                    <th>Target / Resource</th>
                    <th>IP Address</th>
                    <th><Shield size={14} className="inline mr-1" />Role</th>
                  </tr>
                </thead>
                <tbody>
                  {trail.length === 0 ? (
                    <tr>
                      <td colSpan="6" className="text-center py-12">
                        <Activity size={36} className="mx-auto text-muted mb-3" />
                        <p className="text-muted">No audit trail events found for this filter.</p>
                      </td>
                    </tr>
                  ) : (
                    trail.map((entry, idx) => (
                      <tr key={entry.id || idx}>
                        <td className="text-sm whitespace-nowrap">{formatDate(entry.timestamp || entry.created_at)}</td>
                        <td>
                          <div>
                            <strong className="block">{entry.user_name || entry.user_email || '—'}</strong>
                            <span className="text-xs text-muted">{entry.user_email}</span>
                          </div>
                        </td>
                        <td>
                          <span className={`badge ${getActionBadgeClass(entry.action)}`}>
                            {entry.action || 'system'}
                          </span>
                        </td>
                        <td className="max-w-xs truncate text-sm">
                          {entry.object_repr || entry.target || entry.description || '—'}
                        </td>
                        <td className="text-xs text-muted font-mono">{entry.ip_address || '127.0.0.1'}</td>
                        <td>
                          <span className="badge badge-outline text-xs">
                            {entry.user_role || (entry.user ? entry.user.role || 'user' : 'user')}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4 pt-4 border-t border-border-color">
                <span className="text-sm text-muted">
                  Page {page} of {totalPages} ({totalCount} events)
                </span>
                <div className="flex gap-2">
                  <button
                    className="btn btn-outline btn-sm"
                    disabled={page <= 1}
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                  >
                    Previous
                  </button>
                  <button
                    className="btn btn-outline btn-sm"
                    disabled={page >= totalPages}
                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default AuditTrailPage;