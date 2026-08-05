import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { capaApi, findingsApi, usersApi } from '../../api';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { usePermissions } from '../../hooks/usePermissions';
import { useI18n } from '../../context/I18nContext';
import { validateForm, validators, hasErrors } from '../../utils/validation';
import Modal from '../../components/ui/Modal';
import Badge from '../../components/ui/Badge';
import Spinner from '../../components/ui/Spinner';
import EmptyState from '../../components/ui/EmptyState';
import FormField from '../../components/ui/FormField';
import { CheckCircle2, Clock, ShieldAlert, MessageCircle, RefreshCw, Plus, FileUp, X } from 'lucide-react';

function FollowUpPage() {
  const toast = useToast();
  const auth = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const { canWriteAudit } = usePermissions();
  const [capas, setCapas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('all');
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
    fetchCapas();
    if (currentUser && currentUser.role !== 'auditee') {
      fetchFindingsAndAuditees();
    }
  }, [currentUser]);

  const fetchCapas = async () => {
    setLoading(true);
    try {
      const res = await capaApi.getActions();
      setCapas(Array.isArray(res) ? res : []);
    } catch (err) {
      toast.error('Failed to load CAPA actions');
    } finally {
      setLoading(false);
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
      const res = await capaApi.createAction(newCapa);
      setCapas([res, ...capas]);
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

      // Update local state
      setCapas(capas.map(c => c.id === selectedCapa.id ? { ...c, status: statusUpdate } : c));
      setShowResponseModal(false);
      toast.success('Response recorded and CAPA status updated!');
      fetchCapas(); // Refresh list to get files or related fields updated
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

  const filteredCapas = capas.filter(c => {
    if (activeTab === 'all') return true;
    if (activeTab === 'open') return c.status === 'open' || c.status === 'in_progress';
    if (activeTab === 'resolved') return c.status === 'resolved' || c.status === 'closed';
    if (activeTab === 'overdue') return c.status === 'overdue';
    return true;
  });

  const isAuditorOrManager = currentUser && currentUser.role !== 'auditee';

  return (
    <div className="followup-view">
      <div className="tab-container">
        <button className={`tab-btn ${activeTab === 'all' ? 'active' : ''}`} onClick={() => setActiveTab('all')}>
          {t('allCapas', capas.length)}
        </button>
        <button className={`tab-btn ${activeTab === 'open' ? 'active' : ''}`} onClick={() => setActiveTab('open')}>
          {t('openInProgress')}
        </button>
        <button className={`tab-btn ${activeTab === 'resolved' ? 'active' : ''}`} onClick={() => setActiveTab('resolved')}>
          {t('resolvedCapas')}
        </button>
        <button className={`tab-btn ${activeTab === 'overdue' ? 'active' : ''}`} onClick={() => setActiveTab('overdue')}>
          {t('overdueCapas')}
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
                {filteredCapas.length === 0 ? (
                  <tr>
                    <td colSpan="7" className="text-center py-8">No corrective action records found for this filter.</td>
                  </tr>
                ) : (
                  filteredCapas.map(c => (
                    <tr key={c.id} className="cursor-pointer hover:bg-gray-50 dark:hover:bg-slate-800/50" onClick={() => navigate(`/capa/${c.id}`)} title={t('clickForDetails') || 'Click to view details'}>
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
                      <td>{c.due_date}</td>
                      <td>
                        <span className={`badge ${getStatusBadge(c.status)}`}>
                          {c.status?.replace('_', ' ').toUpperCase()}
                        </span>
                      </td>
                      <td>
                        <button className="btn btn-outline btn-sm flex items-center gap-1" onClick={() => handleOpenResponse(c)}>
                          <MessageCircle size={14} /> Respond
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Spawn CAPA Modal */}
      {showCreateModal && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setShowCreateModal(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setShowCreateModal(false); }}
        >
          <div
            className="modal-card modal-large"
            role="dialog"
            aria-modal="true"
            aria-labelledby="capa-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="capa-modal-title">{t('spawnCapaLinked')}</h3>
              <button
                type="button"
                className="close-btn"
                onClick={() => setShowCreateModal(false)}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleCreateCapa}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Link to Audit Finding</label>
                  <select
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
                  <label className="form-label">Action / CAPA Title</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="e.g. Implement dual-authorization controls"
                    value={newCapa.title}
                    onChange={e => setNewCapa({ ...newCapa, title: e.target.value })}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Action Description</label>
                  <textarea
                    rows="3"
                    className="form-control"
                    placeholder="Provide detailed description of corrective action..."
                    value={newCapa.description}
                    onChange={e => setNewCapa({ ...newCapa, description: e.target.value })}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Auditor Recommendation Reference</label>
                  <textarea
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
                    <label className="form-label">Assign Owner (Auditee)</label>
                    <select
                      className="form-control"
                      value={newCapa.owner}
                      onChange={e => setNewCapa({ ...newCapa, owner: e.target.value })}
                      required
                    >
                      <option value="">Select Auditee Owner...</option>
                      {auditees.map(a => (
                        <option key={a.id} value={a.id}>{a.first_name} {a.last_name} ({a.department_name || 'Auditee'})</option>
                      ))}
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Priority</label>
                    <select
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
                    <label className="form-label">Due Date</label>
                    <input
                      type="date"
                      className="form-control"
                      value={newCapa.due_date}
                      onChange={e => setNewCapa({ ...newCapa, due_date: e.target.value })}
                      required
                    />
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowCreateModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-accent" disabled={creating}>
                  {creating ? 'Spawning...' : 'Spawn & Assign CAPA'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Auditee Response Modal */}
      {showResponseModal && selectedCapa && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setShowResponseModal(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setShowResponseModal(false); }}
        >
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="response-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="response-modal-title">Submit Management Update for {selectedCapa.action_number}</h3>
              <button
                type="button"
                className="close-btn"
                onClick={() => setShowResponseModal(false)}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleSubmitResponse}>
              <div className="modal-body">
                <div className="mb-4">
                  <span className="text-xs text-muted font-bold block">Recommendation:</span>
                  <p className="text-sm font-semibold">{selectedCapa.recommendation}</p>
                </div>

                <div className="form-group">
                  <label className="form-label">Progress Status</label>
                  <select
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
                  <label className="form-label">Action / Update Notes</label>
                  <textarea
                    rows="4"
                    className="form-control"
                    placeholder="Provide details on action taken, systems modified, or policies published..."
                    value={responseText}
                    onChange={(e) => setResponseText(e.target.value)}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label flex items-center gap-1"><FileUp size={16} /> Upload Implementation Document</label>
                  <input
                    type="file"
                    className="form-control"
                    onChange={(e) => setEvidenceFile(e.target.files[0])}
                  />
                  {evidenceFile && (
                    <span className="text-xs text-success block mt-1">Selected file: {evidenceFile.name}</span>
                  )}
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowResponseModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={submittingResponse}>
                  {submittingResponse ? 'Submitting...' : 'Submit Response'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default FollowUpPage;

