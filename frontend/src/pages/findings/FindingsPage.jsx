import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { findingsApi, planningApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { usePermissions } from '../../hooks/usePermissions';
import { useI18n } from '../../context/I18nContext';
import { validateForm, validators, hasErrors } from '../../utils/validation';
import Modal from '../../components/ui/Modal';
import Badge from '../../components/ui/Badge';
import Spinner from '../../components/ui/Spinner';
import EmptyState from '../../components/ui/EmptyState';
import FormField from '../../components/ui/FormField';
import { ShieldAlert, Plus, Layers, List, MessageCircle, FileText, ChevronRight, X } from 'lucide-react';

function FindingsPage() {
  const toast = useToast();
  const { t } = useI18n();
  const navigate = useNavigate();
  const { canWriteAudit, canCloseFindings } = usePermissions();
  const [engagements, setEngagements] = useState([]);
  const [selectedEngId, setSelectedEngId] = useState('');
  const [findings, setFindings] = useState([]);
  const [viewMode, setViewMode] = useState('list'); // 'list' or 'kanban'
  const [loading, setLoading] = useState(false);
  const [formErrors, setFormErrors] = useState({});

  // Selected Finding Inspection Detail
  const [activeFinding, setActiveFinding] = useState(null);

  // Add Finding Modal State
  const [showAddModal, setShowAddModal] = useState(false);
  const [newFinding, setNewFinding] = useState({
    title: '', severity: 'medium', category: 'control_deficiency',
    description: '', condition: '', criteria: '', cause: '', effect: '', recommendation: ''
  });

  useEffect(() => {
    fetchEngagements();
  }, []);

  const fetchEngagements = async () => {
    try {
      const list = await planningApi.getEngagements();
      const engList = Array.isArray(list) ? list : [];
      setEngagements(engList);
      if (engList.length > 0) {
        setSelectedEngId(engList[0].id);
        fetchFindings(engList[0].id);
      }
    } catch (err) {
      toast.error('Failed to load engagements');
    }
  };

  const fetchFindings = async (engId) => {
    setLoading(true);
    try {
      const list = await findingsApi.getFindings({ engagement: engId });
      const fList = Array.isArray(list) ? list : [];
      setFindings(fList);
      if (fList.length > 0) {
        setActiveFinding(fList[0]);
      } else {
        setActiveFinding(null);
      }
    } catch (err) {
      toast.error('Failed to load findings');
    } finally {
      setLoading(false);
    }
  };

  const handleEngChange = (e) => {
    const val = e.target.value;
    setSelectedEngId(val);
    fetchFindings(val);
  };

  const handleCreateFinding = async (e) => {
    e.preventDefault();
    // Validate form
    const errors = validateForm(newFinding, {
      title: { validators: [validators.required, validators.minLength(5)] },
      description: { validators: [validators.required, validators.minLength(10)] },
      recommendation: { validators: [validators.required, validators.minLength(10)] },
    });
    if (hasErrors(errors)) {
      setFormErrors(errors);
      return;
    }
    setFormErrors({});

    // finding_number is assigned server-side (FND-#####) — sending one here was
    // silently discarded by perform_create, so the client value never applied.
    const data = {
      ...newFinding,
      engagement: selectedEngId,
    };

    try {
      const response = await findingsApi.createFinding(data);
      setFindings([response, ...findings]);
      setActiveFinding(response);
      setShowAddModal(false);
      // Reset
      setNewFinding({
        title: '', severity: 'medium', category: 'control_deficiency',
        description: '', condition: '', criteria: '', cause: '', effect: '', recommendation: ''
      });
      toast.success('Finding logged successfully!');
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error('Failed to create finding: ' + msg);
    }
  };

  // Kanban Columns configuration
  const columns = [
    { id: 'draft', title: 'Draft' },
    { id: 'open', title: 'Open' },
    { id: 'in_progress', title: 'In Progress' },
    { id: 'resolved', title: 'Resolved' },
  ];

  return (
    <div className="findings-view">
      {/* Top selector bar */}
      <div className="card mb-4 flex justify-between items-center flex-wrap gap-4">
        <div className="form-group mb-0 flex-grow max-w-md">
          <label className="form-label font-bold">{t('selectAuditEngagement')}</label>
          <select className="form-control" value={selectedEngId} onChange={handleEngChange}>
            {engagements.map(e => (
              <option key={e.id} value={e.id}>{e.engagement_number} - {e.title}</option>
            ))}
          </select>
        </div>

        <div className="flex gap-2">
          <button
            className={`btn ${viewMode === 'list' ? 'btn-primary' : 'btn-outline'}`}
            onClick={() => setViewMode('list')}
          >
            <List size={16} className="inline mr-1" /> {t('listView')}
          </button>
          <button
            className={`btn ${viewMode === 'kanban' ? 'btn-primary' : 'btn-outline'}`}
            onClick={() => setViewMode('kanban')}
          >
            <Layers size={16} className="inline mr-1" /> {t('kanbanBoard')}
          </button>
          {canWriteAudit && (
            <button className="btn btn-accent" onClick={() => setShowAddModal(true)}>
              <Plus size={16} className="inline mr-1" /> {t('logFinding')}
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="loading-spinner">{t('loadingFindings')}</div>
      ) : (
        <div className="tab-content active">
          {viewMode === 'list' ? (
            <div className="findings-split-layout">
              {/* Left Column: Finding list */}
              <div className="card list-column">
                <h3>{t('findingsRegistered', findings.length)}</h3>
                <div className="findings-list mt-3">
                  {findings.length === 0 ? (
                    <p className="text-muted text-center py-8">{t('noFindings')}</p>
                  ) : (
                    findings.map(f => (
                      <div
                        key={f.id}
                        className={`finding-list-item ${activeFinding?.id === f.id ? 'active' : ''}`}
                        onClick={() => setActiveFinding(f)}
                        onDoubleClick={() => navigate(`/findings/${f.id}`)}
                        title={t('clickForDetails') || 'Click to view details'}
                      >
                        <div className="finding-item-meta">
                          <span className="finding-num">{f.finding_number}</span>
                          <span className={`risk-tag ${f.severity === 'critical' ? 'critical' : f.severity === 'high' ? 'high' : 'medium'}`}>
                            {f.severity?.toUpperCase()}
                          </span>
                        </div>
                        <h4>{f.title}</h4>
                        <span className="badge badge-outline mt-1">{f.status?.toUpperCase()}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Right Column: Finding details */}
              {activeFinding ? (
                <div className="card detail-column">
                  <div className="detail-header mb-4">
                    <span className="badge badge-outline mb-2">{activeFinding.category?.replace('_', ' ').toUpperCase()}</span>
                    <h2>{activeFinding.finding_number}: {activeFinding.title}</h2>
                    <span className={`badge ${activeFinding.status === 'open' ? 'badge-warning' : activeFinding.status === 'resolved' ? 'badge-success' : 'badge-info'} mt-2`}>
                      {activeFinding.status?.toUpperCase()}
                    </span>
                  </div>

                  <div className="detail-body">
                    <div className="detail-section">
                      <h4>Description</h4>
                      <p>{activeFinding.description}</p>
                    </div>

                    <div className="detail-section">
                      <h4>Condition (What was found?)</h4>
                      <p>{activeFinding.condition || 'N/A'}</p>
                    </div>

                    <div className="detail-section">
                      <h4>Criteria (What policies/standards apply?)</h4>
                      <p>{activeFinding.criteria || 'N/A'}</p>
                    </div>

                    <div className="detail-section">
                      <h4>Root Cause Analysis</h4>
                      <p>{activeFinding.cause || 'N/A'}</p>
                    </div>

                    <div className="detail-section">
                      <h4>Effect & Impact (Potential Risk)</h4>
                      <p>{activeFinding.effect || 'N/A'}</p>
                    </div>

                    <div className="detail-section highlight-box">
                      <h4>Auditor Recommendation</h4>
                      <p>{activeFinding.recommendation || 'N/A'}</p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="card text-center py-8">
                  <h3>No Finding Selected</h3>
                  <p className="text-muted">Select a finding from the left panel to inspect details.</p>
                </div>
              )}
            </div>
          ) : (
            /* Kanban view */
            <div className="kanban-board mt-4">
              {columns.map(col => {
                const colFindings = findings.filter(f => f.status === col.id);
                return (
                  <div key={col.id} className="kanban-column">
                    <div className="kanban-column-header">
                      <h3>{col.title}</h3>
                      <span className="count-badge">{colFindings.length}</span>
                    </div>
                    <div className="kanban-cards-container">
                      {colFindings.map(f => (
                        <div key={f.id} className="kanban-card" onClick={() => { setViewMode('list'); setActiveFinding(f); }}>
                          <span className={`risk-tag tag-xs ${f.severity === 'critical' ? 'critical' : f.severity === 'high' ? 'high' : 'medium'}`}>
                            {f.severity?.toUpperCase()}
                          </span>
                          <h4>{f.title}</h4>
                          <span className="kanban-card-ref">{f.finding_number}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Add Finding Modal */}
      {showAddModal && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setShowAddModal(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setShowAddModal(false); }}
        >
          <div
            className="modal-card modal-large"
            role="dialog"
            aria-modal="true"
            aria-labelledby="finding-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="finding-modal-title">Log New Audit Finding</h3>
              <button
                type="button"
                className="close-btn"
                onClick={() => setShowAddModal(false)}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleCreateFinding}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Finding Title</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="e.g. Inadequate data replication verification logs"
                    value={newFinding.title}
                    onChange={(e) => setNewFinding({ ...newFinding, title: e.target.value })}
                    required
                  />
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Severity Level</label>
                    <select
                      className="form-control"
                      value={newFinding.severity}
                      onChange={(e) => setNewFinding({ ...newFinding, severity: e.target.value })}
                    >
                      <option value="critical">Critical</option>
                      <option value="high">High</option>
                      <option value="medium">Medium</option>
                      <option value="low">Low</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Finding Category</label>
                    <select
                      className="form-control"
                      value={newFinding.category}
                      onChange={(e) => setNewFinding({ ...newFinding, category: e.target.value })}
                    >
                      <option value="control_deficiency">Control Deficiency</option>
                      <option value="compliance">Compliance Issue</option>
                      <option value="fraud">Fraud Risk</option>
                      <option value="operational">Operational Weakness</option>
                      <option value="it_security">IT/Security Issue</option>
                    </select>
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Description (Summary)</label>
                  <textarea
                    rows="3"
                    className="form-control"
                    value={newFinding.description}
                    onChange={(e) => setNewFinding({ ...newFinding, description: e.target.value })}
                    required
                  />
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Condition (Actual Situation)</label>
                    <textarea
                      rows="2"
                      className="form-control"
                      value={newFinding.condition}
                      onChange={(e) => setNewFinding({ ...newFinding, condition: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Criteria (Policy / Policy Standard)</label>
                    <textarea
                      rows="2"
                      className="form-control"
                      value={newFinding.criteria}
                      onChange={(e) => setNewFinding({ ...newFinding, criteria: e.target.value })}
                    />
                  </div>
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Root Cause (Why it happened?)</label>
                    <textarea
                      rows="2"
                      className="form-control"
                      value={newFinding.cause}
                      onChange={(e) => setNewFinding({ ...newFinding, cause: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Effect & Risk (Impact)</label>
                    <textarea
                      rows="2"
                      className="form-control"
                      value={newFinding.effect}
                      onChange={(e) => setNewFinding({ ...newFinding, effect: e.target.value })}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Auditor Recommendation</label>
                  <textarea
                    rows="2"
                    className="form-control"
                    placeholder="Provide actionable correction advice..."
                    value={newFinding.recommendation}
                    onChange={(e) => setNewFinding({ ...newFinding, recommendation: e.target.value })}
                    required
                  />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowAddModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-accent">Save & Log Finding</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default FindingsPage;
