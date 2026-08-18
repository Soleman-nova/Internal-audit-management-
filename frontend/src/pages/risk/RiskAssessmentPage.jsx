import React, { useState, useEffect } from 'react';
import { riskApi, planningApi } from '../../api';
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
import OrgUnitSelect from '../../components/ui/OrgUnitSelect';
import { TrendingUp, Sliders, Plus, RefreshCw, AlertOctagon, ClipboardList, CheckCircle2, Star, X } from 'lucide-react';

function RiskAssessmentPage() {
  const toast = useToast();
  const auth = useAuth();
  const { t } = useI18n();
  const { canWriteAudit } = usePermissions();
  const [activePageTab, setActivePageTab] = useState('matrix'); // 'matrix' or 'selfAssessment'
  const [formErrors, setFormErrors] = useState({});
  const [parameters, setParameters] = useState([]);
  const [assessments, setAssessments] = useState([]);
  const [universe, setUniverse] = useState([]);
  const [heatmapData, setHeatmapData] = useState([]);
  const [selectedCell, setSelectedCell] = useState(null);
  const [loading, setLoading] = useState(true);
  const currentUser = auth.user;
  const [summary, setSummary] = useState({ total: 0, critical: 0, high: 0, medium: 0, low: 0 });

  // Self Assessments from backend
  const [selfAssessments, setSelfAssessments] = useState([]);

  // New Assessment Modal (For Managers)
  const [showModal, setShowModal] = useState(false);
  const [newAssessment, setNewAssessment] = useState({
    department: '', audit_universe: '', year: new Date().getFullYear(),
    assessment_period: 'Annual', likelihood: 3, impact: 3,
    control_effectiveness: 3, notes: ''
  });
  const [saving, setSaving] = useState(false);

  // Auditee Survey Response Modal
  const [showSurveyModal, setShowSurveyModal] = useState(false);
  const [selectedAssessment, setSelectedAssessment] = useState(null);
  const [surveyResponse, setSurveyResponse] = useState({
    likelihood_self: 3,
    impact_self: 3,
    control_effectiveness_self: 3,
    justification: '',
    mitigating_controls: ''
  });
  const [submittingSurvey, setSubmittingSurvey] = useState(false);

  // Manager Review Survey Modal
  const [showReviewModal, setShowReviewModal] = useState(false);
  const [selectedSelfAss, setSelectedSelfAss] = useState(null);
  const [reviewerNotes, setReviewerNotes] = useState('');
  const [submittingReview, setSubmittingReview] = useState(false);

  useEffect(() => {
    fetchAll();
  }, []);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [paramRes, assessRes, uniRes, heatRes, sumRes, selfRes] = await Promise.all([
        riskApi.getParameters(),
        riskApi.getAssessments(),
        planningApi.getUniverse(),
        riskApi.getHeatmap(),
        riskApi.getSummary(),
        riskApi.getSelfAssessments(),
      ]);
      setParameters(paramRes || []);
      setAssessments(assessRes || []);
      setUniverse(uniRes || []);
      setHeatmapData(heatRes || []);
      setSummary(sumRes || {});
      setSelfAssessments(selfRes || []);
    } catch (err) {
      toast.error('Failed to load risk assessment data');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateAssessment = async (e) => {
    e.preventDefault();
    // Validate form
    const errors = validateForm(newAssessment, {
      department: { validators: [validators.required] },
      year: { validators: [validators.required, validators.integer] },
      likelihood: { validators: [validators.required, validators.min(1), validators.max(5)] },
      impact: { validators: [validators.required, validators.min(1), validators.max(5)] },
      control_effectiveness: { validators: [validators.required, validators.min(1), validators.max(5)] },
    });
    if (hasErrors(errors)) {
      setFormErrors(errors);
      return;
    }
    setFormErrors({});
    setSaving(true);
    try {
      const payload = { ...newAssessment };
      if (!payload.audit_universe) delete payload.audit_universe;
      const res = await riskApi.createAssessment(payload);
      setAssessments([res, ...assessments]);
      setShowModal(false);
      setNewAssessment({ department: '', audit_universe: '', year: new Date().getFullYear(), assessment_period: 'Annual', likelihood: 3, impact: 3, control_effectiveness: 3, notes: '' });
      toast.success('Risk assessment created successfully');
      fetchAll(); // Refresh heatmap
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error('Failed to create assessment: ' + msg);
    } finally {
      setSaving(false);
    }
  };

  const handleOpenSurvey = (assess) => {
    setSelectedAssessment(assess);
    setSurveyResponse({
      likelihood_self: assess.likelihood || 3,
      impact_self: assess.impact || 3,
      control_effectiveness_self: assess.control_effectiveness || 3,
      justification: '',
      mitigating_controls: ''
    });
    setShowSurveyModal(true);
  };

  const handleSubmitSurvey = async (e) => {
    e.preventDefault();
    if (!selectedAssessment) return;
    setSubmittingSurvey(true);
    try {
      const payload = {
        risk_assessment: selectedAssessment.id,
        status: 'submitted',
        ...surveyResponse
      };
      await riskApi.createSelfAssessment(payload);
      // The parent assessment's is_self_assessment flag is set server-side —
      // an auditee has no write access to RiskAssessment, so PATCHing it here
      // used to 403 and report a failure after the survey had already saved.

      toast.success('Self-assessment survey submitted successfully!');
      setShowSurveyModal(false);
      fetchAll();
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error('Failed to submit survey: ' + msg);
    } finally {
      setSubmittingSurvey(false);
    }
  };

  const handleOpenReview = (selfAss) => {
    setSelectedSelfAss(selfAss);
    setReviewerNotes(selfAss.reviewer_notes || '');
    setShowReviewModal(true);
  };

  const handleSubmitReview = async (e) => {
    e.preventDefault();
    if (!selectedSelfAss) return;
    setSubmittingReview(true);
    try {
      // Must go through the review action, not a status PATCH: only that path
      // enforces APPROVE_PLANS, stamps reviewed_by/reviewed_at, writes the
      // audit trail and notifies the submitter. The backend now also refuses
      // to accept status through PATCH at all.
      await riskApi.reviewSelfAssessment(selectedSelfAss.id, reviewerNotes);
      toast.success('Review submitted and status updated!');
      setShowReviewModal(false);
      fetchAll();
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error('Failed to save review: ' + msg);
    } finally {
      setSubmittingReview(false);
    }
  };

  const getCellColorClass = (l, i) => {
    const score = l * i;
    if (score >= 20) return 'risk-cell-critical';
    if (score >= 12) return 'risk-cell-high';
    if (score >= 6) return 'risk-cell-medium';
    return 'risk-cell-low';
  };

  // Build 5x5 grid
  const gridCells = [];
  for (let i = 5; i >= 1; i--) {
    for (let l = 1; l <= 5; l++) {
      const cellItems = heatmapData.filter(a => a.likelihood === l && a.impact === i);
      const fallback = assessments.filter(a => a.likelihood === l && a.impact === i);
      const items = cellItems.length > 0 ? cellItems : fallback;
      gridCells.push({ impact: i, likelihood: l, colorClass: getCellColorClass(l, i), items });
    }
  }

  const handleCellClick = (cell) => setSelectedCell(
    selectedCell?.likelihood === cell.likelihood && selectedCell?.impact === cell.impact ? null : cell
  );

  const getRatingClass = (rating) => {
    switch (rating) {
      case 'critical': return 'badge-danger';
      case 'high': return 'badge-warning';
      case 'medium': return 'badge-info';
      default: return 'badge-success';
    }
  };

  const isAuditee = currentUser && currentUser.role === 'auditee';
  const isManagerOrAuditor = currentUser && currentUser.role !== 'auditee';

  // Filter assessments for Auditee department
  const myDepartmentAssessments = assessments.filter(a => {
    if (!isAuditee) return false;
    if (currentUser?.department && a.department === currentUser.department) return true;
    if (currentUser?.department_name && a.department_name === currentUser.department_name) return true;
    return false;
  });

  return (
    <div className="risk-view">
      {/* Top Level tab navigation */}
      <div className="tab-container mb-4">
        <button className={`tab-btn ${activePageTab === 'matrix' ? 'active' : ''}`} onClick={() => setActivePageTab('matrix')}>
          <TrendingUp size={16} className="inline mr-1" /> {t('riskMatrixHeatMap')}
        </button>
        <button className={`tab-btn ${activePageTab === 'selfAssessment' ? 'active' : ''}`} onClick={() => setActivePageTab('selfAssessment')}>
          <ClipboardList size={16} className="inline mr-1" /> {t('selfAssessmentPortal')}
        </button>
      </div>

      {activePageTab === 'matrix' ? (
        <>
          {/* Summary KPI Strip */}
          <div className="risk-kpi-strip mb-4">
            {[
              { label: t('totalAssessments'), value: summary.total || assessments.length, cls: 'badge-outline' },
              { label: t('critical'), value: summary.critical || 0, cls: 'badge-danger' },
              { label: t('high'), value: summary.high || 0, cls: 'badge-warning' },
              { label: t('medium'), value: summary.medium || 0, cls: 'badge-info' },
              { label: t('low'), value: summary.low || 0, cls: 'badge-success' },
            ].map(k => (
              <div key={k.label} className="risk-kpi-card card">
                <span className={`badge ${k.cls} text-lg font-bold`}>{k.value}</span>
                <span className="text-xs text-muted mt-1">{k.label}</span>
              </div>
            ))}
          </div>

          <div className="risk-dashboard-grid mb-6">
            {/* Left Side: 5x5 Heat Map */}
            <div className="card heat-map-card">
              <div className="card-header justify-between">
                <div>
                  <h3>{t('riskHeatMap')}</h3>
                  <p className="card-subtitle">{t('likelihoodVsImpact')}</p>
                </div>
                <div className="flex gap-2">
                  <button className="btn btn-outline btn-sm flex items-center gap-1" onClick={fetchAll}>
                    <RefreshCw size={13} /> {t('refresh')}
                  </button>
                  {canWriteAudit && (
                    <button className="btn btn-primary btn-sm flex items-center gap-1" onClick={() => setShowModal(true)}>
                      <Plus size={13} /> {t('addAssessment')}
                    </button>
                  )}
                </div>
              </div>

              {loading ? (
                <div className="loading-spinner">{t('loadingRiskMatrix')}</div>
              ) : (
                <div className="heat-map-container mt-4">
                  <div className="y-axis-label"><span>IMPACT (1 — 5)</span></div>
                  <div className="heat-map-wrapper">
                    <div className="heat-map-grid">
                      {gridCells.map((cell, idx) => (
                        <div
                          key={idx}
                          className={`heat-map-cell ${cell.colorClass} ${selectedCell?.likelihood === cell.likelihood && selectedCell?.impact === cell.impact ? 'selected' : ''}`}
                          onClick={() => handleCellClick(cell)}
                        >
                          <span className="cell-coords">L{cell.likelihood}·I{cell.impact}</span>
                          {cell.items.length > 0 && (
                            <span className="cell-bullet-badge">{cell.items.length}</span>
                          )}
                        </div>
                      ))}
                    </div>
                    <div className="x-axis-label"><span>LIKELIHOOD (1 — 5)</span></div>
                  </div>
                </div>
              )}

              {/* Legend */}
              <div className="heat-map-legend mt-3">
                {[
                  { cls: 'risk-cell-critical', label: 'Critical (≥20)' },
                  { cls: 'risk-cell-high', label: 'High (12–19)' },
                  { cls: 'risk-cell-medium', label: 'Medium (6–11)' },
                  { cls: 'risk-cell-low', label: 'Low (1–5)' },
                ].map(l => (
                  <div key={l.label} className="legend-item">
                    <span className={`legend-swatch ${l.cls}`}></span>
                    <span className="text-xs">{l.label}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Right Side: Cell Detail or Full Assessment List */}
            <div className="card risk-details-card">
              {selectedCell ? (
                <div>
                  <div className="flex justify-between items-center mb-4">
                    <h3>Cell L{selectedCell.likelihood} × I{selectedCell.impact} — Score {selectedCell.likelihood * selectedCell.impact}</h3>
                    <button className="text-btn" onClick={() => setSelectedCell(null)}>Clear ×</button>
                  </div>
                  <div className="selected-cell-items">
                    {selectedCell.items.length === 0 ? (
                      <p className="text-muted py-8 text-center">No assessments mapped to this risk level.</p>
                    ) : (
                      selectedCell.items.map((item, i) => (
                        <div key={i} className="risk-item-detail">
                          <div className="flex justify-between items-center mb-1">
                            <h4>{item.department__name || item.department_name || `Dept #${item.department}`}</h4>
                            <span className="risk-score-value">Score: {item.risk_score || (item.likelihood * item.impact)}</span>
                          </div>
                          <p className="text-sm text-secondary">
                            Period: {item.assessment_period || 'Annual'} — Rating: {item.risk_rating || '—'}
                          </p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              ) : (
                <div>
                  <h3>{t('allRiskAssessments')}</h3>
                  <p className="card-subtitle mb-4">{t('scoredRiskRecords')}</p>
                  <div className="risk-full-list">
                    {assessments.length === 0 ? (
                      <div className="text-center py-8">
                        <AlertOctagon size={40} className="mx-auto text-muted mb-3" />
                        <p className="text-muted">{t('noRiskAssessments')}</p>
                        {canWriteAudit && (
                          <button className="btn btn-primary btn-sm mt-3" onClick={() => setShowModal(true)}>
                            <Plus size={14} className="inline mr-1" /> {t('createFirstAssessment')}
                          </button>
                        )}
                      </div>
                    ) : (
                      assessments.map(item => (
                        <div key={item.id} className="risk-list-row-item">
                          <div className="risk-row-left">
                            <h4>{item.department_name || `Department #${item.department}`}</h4>
                            <span className="text-xs text-muted">{item.assessment_period} {item.year}</span>
                          </div>
                          <div className="risk-row-right flex items-center gap-2">
                            <span className={`badge ${getRatingClass(item.risk_rating)}`}>
                              {item.risk_rating?.toUpperCase()}
                            </span>
                            <span className="risk-tag medium">
                              Score: {item.risk_score}
                            </span>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Risk Parameter Weightings */}
          <div className="card">
            <div className="card-header">
              <h3><Sliders size={18} className="inline mr-2" />{t('riskParameterWeightings')}</h3>
              <p className="card-subtitle">{t('configurableFactors')}</p>
            </div>
            <div className="table-responsive mt-3">
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('parameterName')}</th>
                    <th>{t('category')}</th>
                    <th>{t('weight')}</th>
                    <th>{t('description')}</th>
                  </tr>
                </thead>
                <tbody>
                  {parameters.length === 0 ? (
                    <tr><td colSpan="4" className="text-center py-4 text-muted">{t('noRiskParameters')}</td></tr>
                  ) : (
                    parameters.map(param => (
                      <tr key={param.id}>
                        <td><strong>{param.name}</strong></td>
                        <td><span className="badge badge-outline">{param.category?.toUpperCase()}</span></td>
                        <td><strong>{(param.weight * 100).toFixed(0)}%</strong></td>
                        <td className="text-sm text-secondary">{param.description}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : (
        /* Self Assessment Portal */
        <div className="self-assessment-portal">
          {isAuditee ? (
            <div className="card">
              <div className="card-header justify-between">
                <div>
                  <h3>{t('operationalRiskSelfAssessments')}</h3>
                  <p className="card-subtitle">{t('submitSelfAssessmentSurveys')}</p>
                </div>
                <button className="btn btn-outline btn-sm flex items-center gap-1" onClick={fetchAll}>
                  <RefreshCw size={13} /> Refresh
                </button>
              </div>

              <div className="table-responsive mt-4">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Year / Period</th>
                      <th>Inherent Risk Details</th>
                      <th>Self Assessment Status</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {myDepartmentAssessments.length === 0 ? (
                      <tr>
                        <td colSpan="4" className="text-center py-8 text-muted">
                          No pending risk assessments assigned to your department.
                        </td>
                      </tr>
                    ) : (
                      myDepartmentAssessments.map(assess => {
                        const hasSelf = !!assess.self_assessment;
                        return (
                          <tr key={assess.id}>
                            <td><strong>{assess.year} {assess.assessment_period}</strong></td>
                            <td>
                              <div className="flex gap-2 items-center">
                                <span className={`badge ${getRatingClass(assess.risk_rating)}`}>
                                  {assess.risk_rating?.toUpperCase()}
                                </span>
                                <span className="text-xs text-muted">Score: {assess.risk_score} (Likelihood: {assess.likelihood}, Impact: {assess.impact})</span>
                              </div>
                            </td>
                            <td>
                              {hasSelf ? (
                                <span className="badge badge-success flex items-center gap-1 w-fit">
                                  <CheckCircle2 size={12} /> Submitted (Status: {assess.self_assessment.status?.toUpperCase()})
                                </span>
                              ) : (
                                <span className="badge badge-warning">Pending Response</span>
                              )}
                            </td>
                            <td>
                              {hasSelf ? (
                                <button className="btn btn-outline btn-sm" disabled>Submitted</button>
                              ) : (
                                <button className="btn btn-primary btn-sm flex items-center gap-1" onClick={() => handleOpenSurvey(assess)}>
                                  <Star size={12} /> Respond
                                </button>
                              )}
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            /* Manager view of all submitted self assessments */
            <div className="card">
              <div className="card-header justify-between">
                <div>
                  <h3>{t('submittedAuditeeSelfAssessments')}</h3>
                  <p className="card-subtitle">{t('reviewOperationalFeedback')}</p>
                </div>
                <button className="btn btn-outline btn-sm flex items-center gap-1" onClick={fetchAll}>
                  <RefreshCw size={13} /> Refresh
                </button>
              </div>

              <div className="table-responsive mt-4">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Department</th>
                      <th>Year/Period</th>
                      <th>Auditee Recommendation</th>
                      <th>Justification / Mitigating Controls</th>
                      <th>Review Status</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selfAssessments.length === 0 ? (
                      <tr>
                        <td colSpan="6" className="text-center py-8 text-muted">No self assessments submitted yet.</td>
                      </tr>
                    ) : (
                      selfAssessments.map(sa => (
                        <tr key={sa.id}>
                          <td><strong>{sa.risk_assessment?.department_name || `Dept #${sa.risk_assessment?.department}`}</strong></td>
                          <td>{sa.risk_assessment?.year} {sa.risk_assessment?.assessment_period}</td>
                          <td>
                            <span className="block text-xs font-semibold">L: {sa.likelihood_self} | I: {sa.impact_self} | C: {sa.control_effectiveness_self}</span>
                          </td>
                          <td>
                            <div className="max-w-md">
                              <span className="block text-xs font-bold text-muted">Justification:</span>
                              <p className="text-xs truncate">{sa.justification}</p>
                              {sa.mitigating_controls && (
                                <>
                                  <span className="block text-xs font-bold text-muted mt-1">Mitigating:</span>
                                  <p className="text-xs truncate">{sa.mitigating_controls}</p>
                                </>
                              )}
                            </div>
                          </td>
                          <td>
                            <span className={`badge ${sa.status === 'reviewed' ? 'badge-success' : 'badge-warning'}`}>
                              {sa.status?.toUpperCase()}
                            </span>
                          </td>
                          <td>
                            <button className="btn btn-outline btn-sm" onClick={() => handleOpenReview(sa)}>
                              Review
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
        </div>
      )}

      {/* New Assessment Modal (For Managers) */}
      {showModal && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setShowModal(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setShowModal(false); }}
        >
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="assessment-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="assessment-modal-title">{t('recordRiskAssessment')}</h3>
              <button
                type="button"
                className="close-btn"
                onClick={() => setShowModal(false)}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleCreateAssessment}>
              <div className="modal-body">
                <div className="form-group-row">
                  <OrgUnitSelect
                    label="Department"
                    value={newAssessment.department}
                    onChange={(id) => setNewAssessment({ ...newAssessment, department: id })}
                    required
                  />
                  <div className="form-group">
                    <label className="form-label">Audit Universe Entry</label>
                    <select
                      className="form-control"
                      value={newAssessment.audit_universe}
                      onChange={e => setNewAssessment({ ...newAssessment, audit_universe: e.target.value })}
                    >
                      <option value="">Auto (by department)</option>
                      {universe
                        .filter(u => !newAssessment.department || String(u.department) === String(newAssessment.department))
                        .map(u => (
                          <option key={u.id} value={u.id}>{u.code} - {u.name}</option>
                        ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Period</label>
                    <select
                      className="form-control"
                      value={newAssessment.assessment_period}
                      onChange={e => setNewAssessment({ ...newAssessment, assessment_period: e.target.value })}
                    >
                      <option value="Q1">Q1</option>
                      <option value="Q2">Q2</option>
                      <option value="Q3">Q3</option>
                      <option value="Q4">Q4</option>
                      <option value="Annual">Annual</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Year</label>
                    <input type="number" className="form-control" value={newAssessment.year}
                      onChange={e => setNewAssessment({ ...newAssessment, year: parseInt(e.target.value) })} />
                  </div>
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Likelihood (1–5)</label>
                    <input type="range" min="1" max="5" className="form-control"
                      value={newAssessment.likelihood}
                      onChange={e => setNewAssessment({ ...newAssessment, likelihood: parseInt(e.target.value) })} />
                    <span className="text-center block font-bold">{newAssessment.likelihood}</span>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Impact (1–5)</label>
                    <input type="range" min="1" max="5" className="form-control"
                      value={newAssessment.impact}
                      onChange={e => setNewAssessment({ ...newAssessment, impact: parseInt(e.target.value) })} />
                    <span className="text-center block font-bold">{newAssessment.impact}</span>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Control Effectiveness (1–5)</label>
                    <input type="range" min="1" max="5" className="form-control"
                      value={newAssessment.control_effectiveness}
                      onChange={e => setNewAssessment({ ...newAssessment, control_effectiveness: parseInt(e.target.value) })} />
                    <span className="text-center block font-bold">{newAssessment.control_effectiveness}</span>
                  </div>
                </div>

                <div className="risk-score-preview mb-3 p-3 rounded" style={{ background: 'var(--bg-card-secondary)', textAlign: 'center' }}>
                  <span className="text-sm text-muted">Calculated Risk Score: </span>
                  <strong className="text-lg" style={{ color: newAssessment.likelihood * newAssessment.impact >= 12 ? 'var(--color-danger)' : newAssessment.likelihood * newAssessment.impact >= 6 ? 'var(--color-warning)' : 'var(--color-success)' }}>
                    {newAssessment.likelihood * newAssessment.impact} / 25
                  </strong>
                </div>

                <div className="form-group">
                  <label className="form-label">Assessment Notes</label>
                  <textarea rows="3" className="form-control" placeholder="Key observations, context, or control details..."
                    value={newAssessment.notes}
                    onChange={e => setNewAssessment({ ...newAssessment, notes: e.target.value })} />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? 'Saving...' : 'Save Assessment'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Auditee Survey Response Modal */}
      {showSurveyModal && selectedAssessment && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setShowSurveyModal(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setShowSurveyModal(false); }}
        >
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="survey-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="survey-modal-title">{t('submitRiskSelfAssessment')}</h3>
              <button
                type="button"
                className="close-btn"
                onClick={() => setShowSurveyModal(false)}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleSubmitSurvey}>
              <div className="modal-body">
                <div className="mb-4 p-3 rounded" style={{ background: 'var(--bg-card-secondary)' }}>
                  <p className="text-sm font-semibold">Survey Period: {selectedAssessment.year} {selectedAssessment.assessment_period}</p>
                  <p className="text-xs text-muted">Current Inherent Risk Level: {selectedAssessment.risk_score} ({selectedAssessment.risk_rating?.toUpperCase()})</p>
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Likelihood (1–5)</label>
                    <input type="range" min="1" max="5" className="form-control"
                      value={surveyResponse.likelihood_self}
                      onChange={e => setSurveyResponse({ ...surveyResponse, likelihood_self: parseInt(e.target.value) })} />
                    <span className="text-center block font-bold">{surveyResponse.likelihood_self}</span>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Impact (1–5)</label>
                    <input type="range" min="1" max="5" className="form-control"
                      value={surveyResponse.impact_self}
                      onChange={e => setSurveyResponse({ ...surveyResponse, impact_self: parseInt(e.target.value) })} />
                    <span className="text-center block font-bold">{surveyResponse.impact_self}</span>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Control Effectiveness (1–5)</label>
                    <input type="range" min="1" max="5" className="form-control"
                      value={surveyResponse.control_effectiveness_self}
                      onChange={e => setSurveyResponse({ ...surveyResponse, control_effectiveness_self: parseInt(e.target.value) })} />
                    <span className="text-center block font-bold">{surveyResponse.control_effectiveness_self}</span>
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Justification / Self-Assessment Notes</label>
                  <textarea rows="3" className="form-control" placeholder="Provide background on why these scores represent your department..."
                    value={surveyResponse.justification}
                    onChange={e => setSurveyResponse({ ...surveyResponse, justification: e.target.value })} required />
                </div>

                <div className="form-group">
                  <label className="form-label">Mitigating Controls Implemented</label>
                  <textarea rows="2" className="form-control" placeholder="Describe policies, technologies, or manual controls that reduce this risk..."
                    value={surveyResponse.mitigating_controls}
                    onChange={e => setSurveyResponse({ ...surveyResponse, mitigating_controls: e.target.value })} />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowSurveyModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={submittingSurvey}>
                  {submittingSurvey ? 'Submitting...' : 'Submit Survey'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Manager Review Modal */}
      {showReviewModal && selectedSelfAss && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setShowReviewModal(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setShowReviewModal(false); }}
        >
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="review-mgr-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="review-mgr-modal-title">{t('reviewAuditeeSelfAssessment')}</h3>
              <button
                type="button"
                className="close-btn"
                onClick={() => setShowReviewModal(false)}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleSubmitReview}>
              <div className="modal-body">
                <div className="mb-4 p-3 rounded" style={{ background: 'var(--bg-card-secondary)' }}>
                  <p className="text-sm font-semibold">Department: {selectedSelfAss.risk_assessment?.department_name || `Dept #${selectedSelfAss.risk_assessment?.department}`}</p>
                  <p className="text-xs text-muted">Auditee Proposed Scores: L={selectedSelfAss.likelihood_self} | I={selectedSelfAss.impact_self} | C={selectedSelfAss.control_effectiveness_self}</p>
                  <p className="text-xs text-muted mt-2">Justification: "{selectedSelfAss.justification}"</p>
                  {selectedSelfAss.mitigating_controls && (
                    <p className="text-xs text-muted mt-1">Mitigating: "{selectedSelfAss.mitigating_controls}"</p>
                  )}
                </div>

                <div className="form-group">
                  <label className="form-label">Reviewer Notes / Feedback</label>
                  <textarea rows="4" className="form-control" placeholder="Type feedback or adjustment rationale..."
                    value={reviewerNotes}
                    onChange={e => setReviewerNotes(e.target.value)} required />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowReviewModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={submittingReview}>
                  {submittingReview ? 'Submitting Review...' : 'Approve & Mark Reviewed'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default RiskAssessmentPage;
