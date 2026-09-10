import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { capaApi, findingsApi, usersApi } from '../../api';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { usePermissions } from '../../hooks/usePermissions';
import { useI18n } from '../../context/I18nContext';
import { localizedName } from '../../utils/localizedName';
import { validateForm, validators, hasErrors } from '../../utils/validation';
import Modal from '../../components/ui/Modal';
import Badge from '../../components/ui/Badge';
import Spinner from '../../components/ui/Spinner';
import EmptyState from '../../components/ui/EmptyState';
import Pagination from '../../components/ui/Pagination';
import FormField from '../../components/ui/FormField';
import { CheckCircle2, Clock, ShieldAlert, MessageCircle, RefreshCw, Plus, FileUp } from 'lucide-react';

function FollowUpPage() {
  const toast = useToast();
  const auth = useAuth();
  const { t, lang } = useI18n();
  const navigate = useNavigate();
  const { canWriteAudit, canApprovePlans } = usePermissions();
  const [capas, setCapas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('all');
  // Server-side pagination: capas holds only the current page slice. reloadKey
  // lets mutations force a refetch even when page/pageSize are unchanged.
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [reloadKey, setReloadKey] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  // Role-scoped counts (total/overdue/...) driving the tab badges.
  const [summary, setSummary] = useState(null);
  const [formErrors, setFormErrors] = useState({});
  const currentUser = auth.user;

  // Spawning CAPA Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [findings, setFindings] = useState([]);
  const [auditees, setAuditees] = useState([]);
  const [newCapa, setNewCapa] = useState({
    finding: '',
    title: '',
    description: '',
    recommendation: '',
    owner: '',
    priority: 'medium',
    due_date: ''
  });
  const [creating, setCreating] = useState(false);

  // Auditee Response Modal State
  const [showResponseModal, setShowResponseModal] = useState(false);
  const [selectedCapa, setSelectedCapa] = useState(null);
  const [responseText, setResponseText] = useState('');
  const [statusUpdate, setStatusUpdate] = useState('in_progress');
  const [evidenceFile, setEvidenceFile] = useState(null);
  const [submittingResponse, setSubmittingResponse] = useState(false);

  useEffect(() => {
    // Reset to page 1 whenever the active tab changes so a user on page 3 of
    // "all" isn't dropped on a nonexistent page 3 of "overdue".
    setPage(1);
  }, [activeTab]);

  useEffect(() => {
    fetchCapas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, page, pageSize, reloadKey]);

  useEffect(() => {
    fetchSummary();
    if (currentUser && currentUser.role !== 'auditee') {
      fetchFindingsAndAuditees();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentUser]);

  const fetchCapas = async () => {
    setLoading(true);
    try {
      // Each tab is its own paginated server query so the visible rows and the
      // totals both reflect the real set — filtering one loaded page in memory
      // used to stop silently at DRF's PAGE_SIZE. The overdue set comes from a
      // dedicated endpoint so it is correct even before flag_overdue_actions
      // has stamped status='overdue' — it derives the set from due_date.
      const params = { page, page_size: pageSize };
      let res;
      if (activeTab === 'overdue') {
        res = await capaApi.getOverdue(params);
      } else if (activeTab === 'open') {
        res = await capaApi.getActions({ ...params, status__in: 'open,in_progress' });
      } else if (activeTab === 'resolved') {
        res = await capaApi.getActions({ ...params, status__in: 'resolved,closed' });
      } else {
        res = await capaApi.getActions(params);
      }
      setCapas(res.items || []);
      setTotalCount(res.count || 0);
      // Clamp: after a mutation shrank the list, the current page may not exist.
      const last = Math.max(1, Math.ceil((res.count || 0) / pageSize));
      if (page > last) setPage(last);
    } catch (err) {
      toast.error('Failed to load CAPA actions');
    } finally {
      setLoading(false);
    }
  };

  // Role-scoped counts driving the tab badges. Refetched after mutations; a
  // failure just falls back to the loaded page's total.
  const fetchSummary = async () => {
    try {
      const s = await capaApi.getSummary();
      setSummary(s);
    } catch (err) {
      /* non-fatal */
    }
  };

  const fetchFindingsAndAuditees = async () => {
    try {
      const [findingsRes, usersRes] = await Promise.all([
        findingsApi.getFindings(),
        usersApi.getUsers({ role: 'auditee' })
      ]);
      setFindings(Array.isArray(findingsRes) ? findingsRes : []);
      setAuditees(Array.isArray(usersRes) ? usersRes : []);
    } catch (err) {
      toast.error('Failed to fetch findings and auditees list');
    }
  };

  const handleFindingChange = (e) => {
    const findingId = e.target.value;
    const selectedFinding = findings.find(f => f.id.toString() === findingId.toString());
    if (selectedFinding) {
      setNewCapa({
        ...newCapa,
        finding: findingId,
        title: `CAPA: ${selectedFinding.title}`,
        description: selectedFinding.description || '',
        recommendation: selectedFinding.recommendation || ''
      });
    } else {
      setNewCapa({
        ...newCapa,
        finding: findingId,
        title: '',
        description: '',
        recommendation: ''
      });
    }
  };

  const handleCreateCapa = async (e) => {
    e.preventDefault();
    // Validate form
    const errors = validateForm(newCapa, {
      finding: { validators: [validators.required] },
      title: { validators: [validators.required, validators.minLength(5)] },
      description: { validators: [validators.required, validators.minLength(10)] },
      recommendation: { validators: [validators.required, validators.minLength(10)] },
      owner: { validators: [validators.required] },
      due_date: {
        validators: [validators.required, validators.date],
        crossField: (values) => {
          if (!values.due_date) return {};
          const today = new Date().toISOString().split('T')[0];
          if (values.due_date < today) {
            return { due_date: 'Due date must be in the future.' };
          }
          return {};
        },
      },
    });
    if (hasErrors(errors)) {
      setFormErrors(errors);
      return;
    }
    setFormErrors({});
    setCreating(true);
    try {
      await capaApi.createAction(newCapa);
      setShowCreateModal(false);
      setNewCapa({
        finding: '',
        title: '',
        description: '',
        recommendation: '',
        owner: '',
        priority: 'medium',
        due_date: ''
      });
      // Reload so counts/ordering stay truthful — the new row's due date
      // decides which page it lands on under due_date ordering, so neither a
      // local prepend nor a page jump would be reliable.
      setReloadKey(k => k + 1);
      fetchSummary();
      toast.success('CAPA task successfully created and assigned!');
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error('Failed to create CAPA: ' + msg);
    } finally {
      setCreating(false);
    }
  };

  const handleOpenResponse = (capa) => {
    setSelectedCapa(capa);
    setShowResponseModal(true);
    setResponseText('');
    setStatusUpdate(capa.status || 'in_progress');
    setEvidenceFile(null);
  };

  const handleSubmitResponse = async (e) => {
    e.preventDefault();
    if (!selectedCapa) return;
    setSubmittingResponse(true);

    try {
      const formData = new FormData();
      formData.append('response_text', responseText);
      formData.append('status_update', statusUpdate);
      if (evidenceFile) {
        formData.append('evidence_file', evidenceFile);
      }

      await capaApi.addResponse(selectedCapa.id, formData);

      // A status change can move the row off the current tab/filter, so trust
      // the server: refetch the current page and the badge counts.
      setShowResponseModal(false);
      toast.success('Response recorded and CAPA status updated!');
      setReloadKey(k => k + 1);
      fetchSummary();
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error('Failed to submit response: ' + msg);
    } finally {
      setSubmittingResponse(false);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'resolved':
      case 'closed':
        return 'badge-success';
      case 'in_progress':
        return 'badge-info';
      case 'overdue':
        return 'badge-danger';
      default:
        return 'badge-warning';
    }
  };

  // Rows are already server-filtered per active tab. isOverdue only drives the
  // extra OVERDUE overlay on visible rows: the serializer's `is_overdue` covers
  // due-date-derived rows, and flag_overdue_actions may also have stamped
  // status='overdue'.
  const isOverdue = (c) => c.status === 'overdue' || !!c.is_overdue;

  // The named owner may respond without holding WRITE_AUDIT — that mirrors the
  // backend's InvolvedPartyOrCapability.for_('owner') gate on add-response.
  // Anyone else would get a 403, so don't offer them the button.
  const canRespondTo = (capa) => canWriteAudit || capa.owner === currentUser?.id;

  // Verification is scoped to whoever raised the action, plus APPROVE_PLANS
  // holders who sign off across engagements — the same object check the backend
  // applies to schedule-followup.
  const canVerify = (capa) => canApprovePlans || capa.assigned_by === currentUser?.id;

  const isAuditorOrManager = currentUser && currentUser.role !== 'auditee';

  return (
    <div className="followup-view">
      <div className="tab-container">
        <button className={`tab-btn ${activeTab === 'all' ? 'active' : ''}`} onClick={() => setActiveTab('all')}>
          {t('allCapas', summary?.total ?? totalCount)}
        </button>
        <button className={`tab-btn ${activeTab === 'open' ? 'active' : ''}`} onClick={() => setActiveTab('open')}>
          {t('openInProgress')}
        </button>
        <button className={`tab-btn ${activeTab === 'resolved' ? 'active' : ''}`} onClick={() => setActiveTab('resolved')}>
          {t('resolvedCapas')}
        </button>
        <button className={`tab-btn ${activeTab === 'overdue' ? 'active' : ''}`} onClick={() => setActiveTab('overdue')}>
          {t('overdue')}{summary?.overdue > 0 ? ` (${summary.overdue})` : ''}
        </button>
      </div>

      {loading ? (
        <div className="loading-spinner">{t('loadingCapas')}</div>
      ) : (
        <div className="card mt-4">
          <div className="card-header justify-between flex-wrap gap-4">
            <div>
              <h3>{t('capaTitle')}</h3>
              <p className="card-subtitle">{t('followUpTracking')}</p>
            </div>
            <div className="flex gap-2">
              <button className="btn btn-outline flex items-center gap-2" onClick={fetchCapas}>
                <RefreshCw size={14} /> {t('refresh')}
              </button>
              {canWriteAudit && (
                <button className="btn btn-accent flex items-center gap-2" onClick={() => setShowCreateModal(true)}>
                  <Plus size={16} /> {t('spawnCapaTask')}
                </button>
              )}
            </div>
          </div>

          <div className="table-responsive">
            <table className="table">
              <thead>
                <tr>
                  <th>Action Ref</th>
                  <th>Action Title</th>
                  <th>Owner</th>
                  <th>Priority</th>
                  <th>Due Date</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {capas.length === 0 ? (
                  <tr>
                    <td colSpan="7" className="text-center py-8">No corrective action records found for this filter.</td>
                  </tr>
                ) : (
                  capas.map(c => (
                    <tr key={c.id} className="cursor-pointer hover:bg-gray-50 dark:hover:bg-slate-800/50" onClick={() => navigate(`/capa/${c.id}`)} title="Click to view details">
                      <td><strong>{c.action_number}</strong></td>
                      <td>
                        <div className="capa-title-container">
                          <strong>{c.title}</strong>
                          <span className="text-xs text-muted block max-w-md truncate">{c.description}</span>
                        </div>
                      </td>
                      <td>{c.owner_name || 'N/A'}</td>
                      <td>
                        <span className={`badge ${c.priority === 'high' || c.priority === 'immediate' ? 'badge-danger' : 'badge-outline'}`}>
                          {c.priority?.toUpperCase()}
                        </span>
                      </td>
                      <td>{c.extended_due_date || c.due_date}</td>
                      <td>
                        <span className={`badge ${getStatusBadge(c.status)}`}>
                          {c.status?.replace('_', ' ').toUpperCase()}
                        </span>
                        {/* Due-date-derived, so it shows before the nightly command runs */}
                        {isOverdue(c) && c.status !== 'overdue' && (
                          <span className="badge badge-danger ml-1">{t('overdue').toUpperCase()}</span>
                        )}
                      </td>
                      <td>
                        <div className="flex gap-1">
                          {canRespondTo(c) && (
                            <button className="btn btn-outline btn-sm flex items-center gap-1" onClick={(e) => { e.stopPropagation(); handleOpenResponse(c); }}>
                              <MessageCircle size={14} /> Respond
                            </button>
                          )}
                          {canVerify(c) && (
                            <button
                              className="btn btn-outline btn-sm flex items-center gap-1"
                              onClick={(e) => { e.stopPropagation(); navigate(`/capa/${c.id}`); }}
                            >
                              <CheckCircle2 size={14} /> {t('verifyAndSchedule')}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <Pagination
            page={page}
            pageCount={Math.max(1, Math.ceil(totalCount / pageSize))}
            totalCount={totalCount}
            onPageChange={setPage}
            pageSize={pageSize}
            onPageSizeChange={setPageSize}
            showPageSize
          />
        </div>
      )}

      {/* Spawn CAPA Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title={t('spawnCapaLinked')}
        size="xl"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={() => setShowCreateModal(false)}>Cancel</button>
            {/* `form=` because Modal renders the footer as a sibling of its
                children, so the submit button sits outside the <form>. */}
            <button type="submit" form="capa-form" className="btn btn-accent" disabled={creating}>
              {creating ? 'Spawning...' : 'Spawn & Assign CAPA'}
            </button>
          </>
        )}
      >
        <form id="capa-form" onSubmit={handleCreateCapa}>
          <div className="form-group">
            <label className="form-label" htmlFor="capa_finding">Link to Audit Finding</label>
            <select
              id="capa_finding"
              className="form-control"
              value={newCapa.finding}
              onChange={handleFindingChange}
              required
            >
              <option value="">Select Audit Finding...</option>
              {findings.map(f => (
                <option key={f.id} value={f.id}>{f.finding_number} - {f.title}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="capa_title">Action / CAPA Title</label>
            <input
              id="capa_title"
              type="text"
              className="form-control"
              placeholder="e.g. Implement dual-authorization controls"
              value={newCapa.title}
              onChange={e => setNewCapa({ ...newCapa, title: e.target.value })}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="capa_description">Action Description</label>
            <textarea
              id="capa_description"
              rows="3"
              className="form-control"
              placeholder="Provide detailed description of corrective action..."
              value={newCapa.description}
              onChange={e => setNewCapa({ ...newCapa, description: e.target.value })}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="capa_recommendation">Auditor Recommendation Reference</label>
            <textarea
              id="capa_recommendation"
              rows="2"
              className="form-control"
              value={newCapa.recommendation}
              onChange={e => setNewCapa({ ...newCapa, recommendation: e.target.value })}
              placeholder="Auditor recommendation details..."
              required
            />
          </div>

          <div className="form-group-row">
            <div className="form-group">
              <label className="form-label" htmlFor="capa_owner">Assign Owner (Auditee)</label>
              <select
                id="capa_owner"
                className="form-control"
                value={newCapa.owner}
                onChange={e => setNewCapa({ ...newCapa, owner: e.target.value })}
                required
              >
                <option value="">Select Auditee Owner...</option>
                {auditees.map(a => (
                  <option key={a.id} value={a.id}>{a.first_name} {a.last_name} ({localizedName(lang, a.department_name, a.department_name_am) || 'Auditee'})</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="capa_priority">Priority</label>
              <select
                id="capa_priority"
                className="form-control"
                value={newCapa.priority}
                onChange={e => setNewCapa({ ...newCapa, priority: e.target.value })}
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="immediate">Immediate</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="capa_due_date">Due Date</label>
              <input
                id="capa_due_date"
                type="date"
                className="form-control"
                value={newCapa.due_date}
                onChange={e => setNewCapa({ ...newCapa, due_date: e.target.value })}
                required
              />
            </div>
          </div>
        </form>
      </Modal>

      {/* Auditee Response Modal */}
      <Modal
        isOpen={Boolean(showResponseModal && selectedCapa)}
        onClose={() => setShowResponseModal(false)}
        title={selectedCapa ? `Submit Management Update for ${selectedCapa.action_number}` : 'Submit Management Update'}
        size="lg"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={() => setShowResponseModal(false)}>Cancel</button>
            <button type="submit" form="capa-response-form" className="btn btn-primary" disabled={submittingResponse}>
              {submittingResponse ? 'Submitting...' : 'Submit Response'}
            </button>
          </>
        )}
      >
        {selectedCapa && (
          <form id="capa-response-form" onSubmit={handleSubmitResponse}>
            <div className="mb-4">
              <span className="text-xs text-muted font-bold block">Recommendation:</span>
              <p className="text-sm font-semibold">{selectedCapa.recommendation}</p>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="response_status">Progress Status</label>
              <select
                id="response_status"
                className="form-control"
                value={statusUpdate}
                onChange={(e) => setStatusUpdate(e.target.value)}
              >
                <option value="in_progress">In Progress</option>
                <option value="partially_resolved">Partially Resolved</option>
                <option value="resolved">Resolved / Actioned</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="response_notes">Action / Update Notes</label>
              <textarea
                id="response_notes"
                rows="4"
                className="form-control"
                placeholder="Provide details on action taken, systems modified, or policies published..."
                value={responseText}
                onChange={(e) => setResponseText(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label flex items-center gap-1" htmlFor="response_evidence"><FileUp size={16} /> Upload Implementation Document</label>
              <input
                id="response_evidence"
                type="file"
                className="form-control"
                onChange={(e) => setEvidenceFile(e.target.files[0])}
              />
              {evidenceFile && (
                <span className="text-xs text-success block mt-1">Selected file: {evidenceFile.name}</span>
              )}
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}

export default FollowUpPage;

