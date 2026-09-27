import { useState } from 'react';
import { riskApi, planningApi } from '../../api';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { usePermissions } from '../../hooks/usePermissions';
import useAsyncData from '../../hooks/useAsyncData';
import { useI18n } from '../../context/I18nContext';
import { localizedName, orgScopeLabel } from '../../utils/localizedName';
import { validateForm, validators, hasErrors } from '../../utils/validation';
import Modal from '../../components/ui/Modal';
import FormErrorSummary from '../../components/ui/FormErrorSummary';
import OrgUnitSelect from '../../components/ui/OrgUnitSelect';
import { TrendingUp, Sliders, Plus, RefreshCw, AlertOctagon, ClipboardList, CheckCircle2, Star } from 'lucide-react';

function RiskAssessmentPage() {
  const toast = useToast();
  const auth = useAuth();
  const { t, lang } = useI18n();
  const { canWriteAudit } = usePermissions();
  const [activePageTab, setActivePageTab] = useState('matrix'); // 'matrix' or 'selfAssessment'
  const [formErrors, setFormErrors] = useState({});
  const currentUser = auth.user;

  // Which heat-map cell the detail pane shows, held as its coordinates rather than
  // as the built cell object. `gridCells` below is rebuilt from whatever lists are
  // current on every render — including after a create, a survey submit or a
  // Refresh calls `fetchAll` — so a stored object would keep rendering the cell it
  // was clicked with, stale `items` and all. The coordinates are the identity; the
  // cell itself is derived.
  const [selectedCellKey, setSelectedCellKey] = useState(null);

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

  // One request, six results. The page used to keep each result in its own
  // `useState` and have a hand-rolled `fetchAll` write all six — a shape with no
  // way to discard a response that landed after a newer Refresh, so a slow first
  // load could overwrite the matrix the user had just reloaded. Because the six
  // come from one `Promise.all`, the loader returns them as one object and the
  // hook owns `data`/`loading`/`error`; nothing is copied into a second state.
  //
  // The single toast is unchanged: `fetchAll` only ever had one `catch`, so there
  // was never a per-request message to keep distinguishable.
  const { data, loading, reload: fetchAll, setData } = useAsyncData(
    async () => {
      const [paramRes, assessRes, uniRes, heatRes, sumRes, selfRes] = await Promise.all([
        riskApi.getParameters(),
        riskApi.getAssessments(),
        planningApi.getUniverse(),
        riskApi.getHeatmap(),
        riskApi.getSummary(),
        riskApi.getSelfAssessments(),
      ]);
      return {
        parameters: paramRes || [],
        assessments: assessRes || [],
        universe: uniRes?.items || [],
        heatmap: heatRes || [],
        summary: sumRes || {},
        selfAssessments: selfRes || [],
      };
    },
    [],
    { onError: () => toast.error(t('riskLoadFailed')) },
  );

  // Read straight off `data`, with the same empty defaults the old useState calls
  // seeded. On a failed load `data` stays null and these render exactly as the
  // untouched initial state did.
  const parameters = data?.parameters ?? [];
  const assessments = data?.assessments ?? [];
  const universe = data?.universe ?? [];
  const heatmapData = data?.heatmap ?? [];
  const summary = data?.summary ?? {};
  const selfAssessments = data?.selfAssessments ?? [];

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
      // A blank select holds '', which DRF rejects as a foreign key. Drop the
      // key instead so the field is simply left unset.
      if (!payload.region) delete payload.region;
      if (!payload.service_center) delete payload.service_center;
      const res = await riskApi.createAssessment(payload);
      // Optimistic prepend through the hook's `setData`, then the refresh below
      // reconciles the heat map. Functional form so the prepend lands on whatever
      // list is current rather than on the one this render closed over.
      setData(prev => ({ ...prev, assessments: [res, ...(prev?.assessments ?? [])] }));
      setShowModal(false);
      setNewAssessment({ department: '', region: '', service_center: '', audit_universe: '', year: new Date().getFullYear(), assessment_period: 'Annual', likelihood: 3, impact: 3, control_effectiveness: 3, notes: '' });
      toast.success(t('riskCreateSuccess'));
      fetchAll(); // Refresh heatmap
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error(t('riskCreateFailed', msg));
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
    // The justification textarea carries `required`, so without an app-side
    // validator the browser is the only thing enforcing it — and a form that also
    // carries `noValidate` (needed so a refused submit shows the banner instead of
    // a tooltip) would post a blank one and take a 400. The model makes the field
    // non-blank (`TextField()`, no `blank=True`), so this matches what the server
    // already rejects.
    const errors = validateForm(surveyResponse, {
      justification: { validators: [validators.required] },
    });
    if (hasErrors(errors)) {
      setFormErrors(errors);
      return;
    }
    setFormErrors({});
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

      toast.success(t('riskSurveySubmitted'));
      setShowSurveyModal(false);
      fetchAll();
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error(t('riskSurveyFailed', msg));
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
      toast.success(t('riskReviewSubmitted'));
      setShowReviewModal(false);
      fetchAll();
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error(t('riskReviewFailed', msg));
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

  // Resolved from the freshly built grid rather than stored, so a refetch that
  // changes a cell's `items` shows up in the open detail pane instead of the pane
  // keeping the counts it was opened with.
  const selectedCell = selectedCellKey
    ? gridCells.find(c => c.likelihood === selectedCellKey.likelihood && c.impact === selectedCellKey.impact) ?? null
    : null;

  // Toggles the *coordinates*; clicking the open cell clears the selection.
  const handleCellClick = (cell) => setSelectedCellKey(prev => (
    prev?.likelihood === cell.likelihood && prev?.impact === cell.impact
      ? null
      : { likelihood: cell.likelihood, impact: cell.impact }
  ));

  const getRatingClass = (rating) => {
    switch (rating) {
      case 'critical': return 'badge-danger';
      case 'high': return 'badge-warning';
      case 'medium': return 'badge-info';
      default: return 'badge-success';
    }
  };

  const isAuditee = currentUser && currentUser.role === 'auditee';

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
                  <div className="y-axis-label"><span>{t('impact')}</span></div>
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
                    <div className="x-axis-label"><span>{t('likelihood')}</span></div>
                  </div>
                </div>
              )}

              {/* Legend */}
              <div className="heat-map-legend mt-3">
                {[
                  { cls: 'risk-cell-critical', label: t('criticalScore') },
                  { cls: 'risk-cell-high', label: t('highScore') },
                  { cls: 'risk-cell-medium', label: t('mediumScore') },
                  { cls: 'risk-cell-low', label: t('lowScore') },
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
                    <h3>{t('riskCellHeading', selectedCell.likelihood, selectedCell.impact, selectedCell.likelihood * selectedCell.impact)}</h3>
                    <button className="text-btn" onClick={() => setSelectedCellKey(null)}>{t('riskClearCell')}</button>
                  </div>
                  <div className="selected-cell-items">
                    {selectedCell.items.length === 0 ? (
                      <p className="text-muted py-8 text-center">{t('riskNoAssessmentsMapped')}</p>
                    ) : (
                      selectedCell.items.map((item, i) => (
                        <div key={i} className="risk-item-detail">
                          <div className="flex justify-between items-center mb-1">
                            <h4>{orgScopeLabel(lang, item, t('riskDeptFallback', item.department))}</h4>
                            <span className="risk-score-value">{t('score')} {item.risk_score || (item.likelihood * item.impact)}</span>
                          </div>
                          <p className="text-sm text-secondary">
                            {t('periodLabel')} {item.assessment_period || 'Annual'} — {t('rating')} {item.risk_rating || '—'}
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
                            <h4>{orgScopeLabel(lang, item, t('riskDepartmentFallback', item.department))}</h4>
                            <span className="text-xs text-muted">{item.assessment_period} {item.year}</span>
                          </div>
                          <div className="risk-row-right flex items-center gap-2">
                            <span className={`badge ${getRatingClass(item.risk_rating)}`}>
                              {item.risk_rating?.toUpperCase()}
                            </span>
                            <span className="risk-tag medium">
                              {t('score')} {item.risk_score}
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
                  <RefreshCw size={13} /> {t('refresh')}
                </button>
              </div>

              <div className="table-responsive mt-4">
                <table className="table">
                  <thead>
                    <tr>
                      <th>{t('yearPeriod')}</th>
                      <th>{t('inherentRiskDetails')}</th>
                      <th>{t('selfAssessmentStatus')}</th>
                      <th>{t('action')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {myDepartmentAssessments.length === 0 ? (
                      <tr>
                        <td colSpan="4" className="text-center py-8 text-muted">
                          {t('noPendingAssessments')}
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
                                <span className="text-xs text-muted">{t('riskScoreBreakdown', assess.risk_score, assess.likelihood, assess.impact)}</span>
                              </div>
                            </td>
                            <td>
                              {hasSelf ? (
                                <span className="badge badge-success flex items-center gap-1 w-fit">
                                  <CheckCircle2 size={12} /> {t('submitted')} ({t('status')}: {assess.self_assessment.status?.toUpperCase()})
                                </span>
                              ) : (
                                <span className="badge badge-warning">{t('pendingResponse')}</span>
                              )}
                            </td>
                            <td>
                              {hasSelf ? (
                                <button className="btn btn-outline btn-sm" disabled>{t('submitted')}</button>
                              ) : (
                                <button className="btn btn-primary btn-sm flex items-center gap-1" onClick={() => handleOpenSurvey(assess)}>
                                  <Star size={12} /> {t('respond')}
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
                  <RefreshCw size={13} /> {t('refresh')}
                </button>
              </div>

              <div className="table-responsive mt-4">
                <table className="table">
                  <thead>
                    <tr>
                      <th>{t('department')}</th>
                      <th>{t('riskYearPeriodShort')}</th>
                      <th>{t('auditeeRecommendation')}</th>
                      <th>{t('justificationMitigating')}</th>
                      <th>{t('reviewStatus')}</th>
                      <th>{t('action')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selfAssessments.length === 0 ? (
                      <tr>
                        <td colSpan="6" className="text-center py-8 text-muted">{t('noSelfAssessments')}</td>
                      </tr>
                    ) : (
                      selfAssessments.map(sa => (
                        <tr key={sa.id}>
                          <td><strong>{localizedName(lang, sa.risk_assessment?.department_name, sa.risk_assessment?.department_name_am) || t('riskDeptFallback', sa.risk_assessment?.department)}</strong></td>
                          <td>{sa.risk_assessment?.year} {sa.risk_assessment?.assessment_period}</td>
                          <td>
                            <span className="block text-xs font-semibold">L: {sa.likelihood_self} | I: {sa.impact_self} | C: {sa.control_effectiveness_self}</span>
                          </td>
                          <td>
                            <div className="max-w-md">
                              <span className="block text-xs font-bold text-muted">{t('justificationLabel')}</span>
                              <p className="text-xs truncate">{sa.justification}</p>
                              {sa.mitigating_controls && (
                                <>
                                  <span className="block text-xs font-bold text-muted mt-1">{t('mitigatingLabel')}</span>
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
                              {t('review')}
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
      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title={t('recordRiskAssessment')}
        size="lg"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={() => setShowModal(false)}>{t('cancel')}</button>
            {/* `form=` because Modal renders the footer as a sibling of its
                children, so the submit button sits outside the <form>. */}
            <button type="submit" form="assessment-form" className="btn btn-primary" disabled={saving}>
              {saving ? t('layoutSaving') : t('saveAssessment')}
            </button>
          </>
        )}
      >
        {/* `noValidate` hands validation to the app, as UsersPage's forms do.
            Without it the browser intercepts an empty submit on the required
            department select, React's onSubmit never fires, and `validateForm`
            never runs — so the banner below never appears. That select is the
            only `required` field in this form and `validateForm` covers it with
            `validators.required`, so nothing stops being enforced. */}
        <form id="assessment-form" onSubmit={handleCreateAssessment} noValidate>
          <FormErrorSummary errors={formErrors} />
          <div className="form-group-row">
            <OrgUnitSelect
              idPrefix="assessment_dept"
              label={t('department')}
              split
              value={newAssessment}
              onFieldChange={(changes) => setNewAssessment(prev => ({ ...prev, ...changes }))}
              required
            />
            <div className="form-group">
              <label className="form-label" htmlFor="assessment_universe">{t('auditUniverseEntry')}</label>
              <select
                id="assessment_universe"
                className="form-control"
                value={newAssessment.audit_universe}
                onChange={e => setNewAssessment({ ...newAssessment, audit_universe: e.target.value })}
              >
                <option value="">{t('autoByDepartment')}</option>
                {universe
                  // A universe entry is a candidate when it shares *any* of the
                  // assessment's three scopes — matching on department alone
                  // would hide an entity registered against the region or the
                  // service center. With only a department chosen this behaves
                  // exactly as it did before the scopes were split.
                  .filter(u => {
                    const { department, region, service_center } = newAssessment;
                    if (!department && !region && !service_center) return true;
                    return (
                      (department && String(u.department) === String(department)) ||
                      (region && u.region && String(u.region) === String(region)) ||
                      (service_center && u.service_center && String(u.service_center) === String(service_center))
                    );
                  })
                  .map(u => (
                    <option key={u.id} value={u.id}>{u.code} - {u.name}</option>
                  ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="assessment_period">{t('period')}</label>
              <select
                id="assessment_period"
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
              <label className="form-label" htmlFor="assessment_year">{t('year')}</label>
              <input id="assessment_year" type="number" className="form-control" value={newAssessment.year}
                onChange={e => setNewAssessment({ ...newAssessment, year: parseInt(e.target.value) })} />
            </div>
          </div>

          <div className="form-group-row">
            <div className="form-group">
              <label className="form-label" htmlFor="assessment_likelihood">{t('riskLikelihoodRange')}</label>
              <input id="assessment_likelihood" type="range" min="1" max="5" className="form-control"
                value={newAssessment.likelihood}
                onChange={e => setNewAssessment({ ...newAssessment, likelihood: parseInt(e.target.value) })} />
              <span className="text-center block font-bold">{newAssessment.likelihood}</span>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="assessment_impact">{t('riskImpactRange')}</label>
              <input id="assessment_impact" type="range" min="1" max="5" className="form-control"
                value={newAssessment.impact}
                onChange={e => setNewAssessment({ ...newAssessment, impact: parseInt(e.target.value) })} />
              <span className="text-center block font-bold">{newAssessment.impact}</span>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="assessment_control">{t('controlEffectiveness')}</label>
              <input id="assessment_control" type="range" min="1" max="5" className="form-control"
                value={newAssessment.control_effectiveness}
                onChange={e => setNewAssessment({ ...newAssessment, control_effectiveness: parseInt(e.target.value) })} />
              <span className="text-center block font-bold">{newAssessment.control_effectiveness}</span>
            </div>
          </div>

          <div className="risk-score-preview mb-3 p-3 rounded" style={{ background: 'var(--bg-card-secondary)', textAlign: 'center' }}>
            <span className="text-sm text-muted">{t('calculatedRiskScore')}{' '}</span>
            <strong className="text-lg" style={{ color: newAssessment.likelihood * newAssessment.impact >= 12 ? 'var(--color-danger)' : newAssessment.likelihood * newAssessment.impact >= 6 ? 'var(--color-warning)' : 'var(--color-success)' }}>
              {newAssessment.likelihood * newAssessment.impact} / 25
            </strong>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="assessment_notes">{t('assessmentNotes')}</label>
            <textarea id="assessment_notes" rows="3" className="form-control" placeholder={t('keyObservations')}
              value={newAssessment.notes}
              onChange={e => setNewAssessment({ ...newAssessment, notes: e.target.value })} />
          </div>
        </form>
      </Modal>

      {/* Auditee Survey Response Modal */}
      <Modal
        isOpen={Boolean(showSurveyModal && selectedAssessment)}
        onClose={() => setShowSurveyModal(false)}
        title={t('submitRiskSelfAssessment')}
        size="lg"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={() => setShowSurveyModal(false)}>{t('cancel')}</button>
            <button type="submit" form="survey-form" className="btn btn-primary" disabled={submittingSurvey}>
              {submittingSurvey ? t('riskSubmitting') : t('submitSurvey')}
            </button>
          </>
        )}
      >
        {/* `noValidate` for the same reason as the assessment form: the required
            justification is now enforced by the validator in `handleSubmitSurvey`,
            so letting the browser block the submit would only hide the banner. */}
        {selectedAssessment && (
          <form id="survey-form" onSubmit={handleSubmitSurvey} noValidate>
          <FormErrorSummary errors={formErrors} />
            <div className="mb-4 p-3 rounded" style={{ background: 'var(--bg-card-secondary)' }}>
              <p className="text-sm font-semibold">{t('surveyPeriod')} {selectedAssessment.year} {selectedAssessment.assessment_period}</p>
              <p className="text-xs text-muted">{t('currentInherentRisk')} {selectedAssessment.risk_score} ({selectedAssessment.risk_rating?.toUpperCase()})</p>
            </div>

            <div className="form-group-row">
              <div className="form-group">
                <label className="form-label" htmlFor="survey_likelihood">{t('riskLikelihoodRange')}</label>
                <input id="survey_likelihood" type="range" min="1" max="5" className="form-control"
                  value={surveyResponse.likelihood_self}
                  onChange={e => setSurveyResponse({ ...surveyResponse, likelihood_self: parseInt(e.target.value) })} />
                <span className="text-center block font-bold">{surveyResponse.likelihood_self}</span>
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="survey_impact">{t('riskImpactRange')}</label>
                <input id="survey_impact" type="range" min="1" max="5" className="form-control"
                  value={surveyResponse.impact_self}
                  onChange={e => setSurveyResponse({ ...surveyResponse, impact_self: parseInt(e.target.value) })} />
                <span className="text-center block font-bold">{surveyResponse.impact_self}</span>
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="survey_control">{t('controlEffectiveness')}</label>
                <input id="survey_control" type="range" min="1" max="5" className="form-control"
                  value={surveyResponse.control_effectiveness_self}
                  onChange={e => setSurveyResponse({ ...surveyResponse, control_effectiveness_self: parseInt(e.target.value) })} />
                <span className="text-center block font-bold">{surveyResponse.control_effectiveness_self}</span>
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="survey_justification">{t('justificationSelf')}</label>
              <textarea id="survey_justification" rows="3" className="form-control" placeholder={t('provideBackground')}
                value={surveyResponse.justification}
                onChange={e => setSurveyResponse({ ...surveyResponse, justification: e.target.value })} required />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="survey_mitigating">{t('mitigatingControls')}</label>
              <textarea id="survey_mitigating" rows="2" className="form-control" placeholder={t('describePolicies')}
                value={surveyResponse.mitigating_controls}
                onChange={e => setSurveyResponse({ ...surveyResponse, mitigating_controls: e.target.value })} />
            </div>
          </form>
        )}
      </Modal>

      {/* Manager Review Modal */}
      <Modal
        isOpen={Boolean(showReviewModal && selectedSelfAss)}
        onClose={() => setShowReviewModal(false)}
        title={t('reviewAuditeeSelfAssessment')}
        size="lg"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={() => setShowReviewModal(false)}>{t('cancel')}</button>
            <button type="submit" form="mgr-review-form" className="btn btn-primary" disabled={submittingReview}>
              {submittingReview ? t('riskSubmittingReview') : t('approveMarkReviewed')}
            </button>
          </>
        )}
      >
        {/* Deliberately NOT `noValidate`. The required reviewer-notes textarea has
            no app validator, and the server does not require it either — the
            review action reads `request.data.get('comments', ...)` and keeps the
            existing notes when it is absent (covered by
            test_review_without_comments_keeps_the_existing_notes). Adding
            `noValidate` here would quietly turn "the browser stops you" into
            "the review is approved with no comment", so the browser check stays. */}
        {selectedSelfAss && (
          <form id="mgr-review-form" onSubmit={handleSubmitReview}>
          <FormErrorSummary errors={formErrors} />
            <div className="mb-4 p-3 rounded" style={{ background: 'var(--bg-card-secondary)' }}>
              <p className="text-sm font-semibold">{t('deptLabel')} {localizedName(lang, selectedSelfAss.risk_assessment?.department_name, selectedSelfAss.risk_assessment?.department_name_am) || t('riskDeptFallback', selectedSelfAss.risk_assessment?.department)}</p>
              <p className="text-xs text-muted">{t('auditeeProposedScores')} L={selectedSelfAss.likelihood_self} | I={selectedSelfAss.impact_self} | C={selectedSelfAss.control_effectiveness_self}</p>
              <p className="text-xs text-muted mt-2">{t('justificationLabel')} &quot;{selectedSelfAss.justification}&quot;</p>
              {selectedSelfAss.mitigating_controls && (
                <p className="text-xs text-muted mt-1">{t('mitigatingLabel')} &quot;{selectedSelfAss.mitigating_controls}&quot;</p>
              )}
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="mgr_reviewer_notes">{t('reviewerNotesFeedback')}</label>
              <textarea id="mgr_reviewer_notes" rows="4" className="form-control" placeholder={t('typeFeedback')}
                value={reviewerNotes}
                onChange={e => setReviewerNotes(e.target.value)} required />
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}

export default RiskAssessmentPage;
