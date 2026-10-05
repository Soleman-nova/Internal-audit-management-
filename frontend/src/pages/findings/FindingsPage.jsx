import { useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { executionApi, findingsApi, planningApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { usePermissions } from '../../hooks/usePermissions';
import useAsyncData from '../../hooks/useAsyncData';
import { useI18n } from '../../context/I18nContext';
import { validateForm, validators, hasErrors } from '../../utils/validation';
import Modal from '../../components/ui/Modal';
import FormErrorSummary from '../../components/ui/FormErrorSummary';
import EngagementPickerBar from '../../components/ui/EngagementPickerBar';
import { Plus, Layers, List } from 'lucide-react';

function FindingsPage() {
  const toast = useToast();
  const { t } = useI18n();
  const navigate = useNavigate();
  const { canWriteAudit, role } = usePermissions();
  // An auditee never sees a finding before a supervisor publishes it, so the
  // pre-publication columns can never hold anything for them and the board would
  // just be three empty boxes of noise.
  const isAuditee = role === 'auditee';
  const [searchParams] = useSearchParams();

  // The execution page sends `?engagement=<id>&procedure=<id>` when a procedure
  // is marked failed, so the form opens already pointed at the engagement and the
  // step the finding came from rather than making the auditor re-find both.
  const deepLinkEngId = searchParams.get('engagement') || '';
  const deepLinkProcedureId = searchParams.get('procedure') || '';

  const [selectedEngId, setSelectedEngId] = useState('');
  const [viewMode, setViewMode] = useState('list'); // 'list' or 'kanban'
  const [formErrors, setFormErrors] = useState({});

  // Which finding the detail pane shows, held as an **id** rather than as the row
  // object. The list is re-fetched whenever the engagement changes, so a stored
  // object goes stale the moment that happens — the id cannot, because the row is
  // derived from whatever list is current.
  const [selectedFindingId, setSelectedFindingId] = useState(null);

  // Add Finding Modal State. A deep link that names a procedure opens the form
  // straight away — arriving from "Log Finding" on a failed step and having to
  // press the button again would be a dead end.
  const [showAddModal, setShowAddModal] = useState(Boolean(deepLinkProcedureId));
  const [newFinding, setNewFinding] = useState({
    title: '', severity: 'medium', category: 'control_deficiency',
    description: '', condition: '', criteria: '', cause: '', effect: '',
    recommendation: '', procedure: deepLinkProcedureId
  });

  // The two loads are independent hooks rather than one fetch chained onto
  // another. Previously the engagements load ended by calling `fetchFindings` and
  // the findings load ended by choosing an `activeFinding` — three pieces of state
  // mutated from the inside of each other's responses, none of them cancellable.
  // Here the chain is plain derived state: `activeEngId` becomes non-empty, and the
  // findings hook below re-runs on that dependency; the selected row is picked from
  // the list on every render instead of being copied out of one.
  const { data: engagementsData, loading: engagementsLoading } = useAsyncData(
    async () => {
      const { items } = await planningApi.getEngagements();
      // The first engagement rides along as the initial selection, so the page
      // opens on something without an effect writing state back into a dependency.
      return { items, defaultId: items.length > 0 ? items[0].id : '' };
    },
    [],
    { onError: () => toast.error(t('engagementsLoadFailed')) },
  );

  const engagements = engagementsData?.items ?? [];
  // The deep-linked engagement wins over the default: it is what the user just
  // asked for. The user's own pick still wins over both.
  const activeEngId = selectedEngId || deepLinkEngId || engagementsData?.defaultId || '';

  // A finding is raised from the procedure that failed, so the form's picker
  // offers the failed steps of this engagement and nothing else — offering a
  // pending or completed procedure would only produce a 400 on submit.
  const { data: failedProcedures } = useAsyncData(
    async () => {
      const { items } = await executionApi.getProcedures({
        'program__engagement': activeEngId, status: 'failed', page_size: 200,
      });
      return items;
    },
    [activeEngId],
    { enabled: Boolean(activeEngId) },
  );

  const { data: findingsData, loading: findingsLoading, setData: setFindingsData } = useAsyncData(
    async () => {
      const list = await findingsApi.getFindings({ engagement: activeEngId });
      return Array.isArray(list) ? list : [];
    },
    [activeEngId],
    // `enabled` is load-bearing, not a nicety: before the engagements arrive
    // `activeEngId` is '' and the request would be an unfiltered one, returning
    // every finding in the system.
    { enabled: Boolean(activeEngId), onError: () => toast.error(t('findingsLoadFailed')) },
  );

  const findings = findingsData ?? [];
  const loading = engagementsLoading || findingsLoading;

  // Selecting an id that is not in the current list — it belonged to the engagement
  // the user has just left — falls back to the first row rather than rendering an
  // empty pane.
  const activeFinding = findings.length === 0
    ? null
    : findings.find(f => f.id === selectedFindingId) ?? findings[0];

  const handleEngChange = (val) => {
    // Setting the selection *is* the request now; re-picking the same engagement is
    // correctly a no-op rather than a redundant refetch.
    setSelectedEngId(val);
  };

  const handleCreateFinding = async (e) => {
    e.preventDefault();
    // Validate form
    const errors = validateForm(newFinding, {
      title: { validators: [validators.required, validators.minLength(5)] },
      description: { validators: [validators.required, validators.minLength(10)] },
      recommendation: { validators: [validators.required, validators.minLength(10)] },
      // Matches the server rule: a finding must name the procedure that failed.
      procedure: { validators: [validators.required] },
    });
    if (hasErrors(errors)) {
      setFormErrors(errors);
      return;
    }
    setFormErrors({});

    // finding_number is assigned server-side (FND-#####) — sending one here was
    // silently discarded by perform_create, so the client value never applied.
    //
    // `activeEngId`, not `selectedEngId`: the selection only leaves the picker once
    // the user has touched it, so the raw state is '' while the page is displaying
    // the first engagement. Posting that would file the finding against no
    // engagement at all — a 400 that looks like the button is broken.
    const data = {
      ...newFinding,
      engagement: activeEngId,
    };

    try {
      const response = await findingsApi.createFinding(data);
      // Optimistic prepend: the created row is already in hand, so a refetch would
      // only be to receive data we just sent. `setData` is the hook's escape hatch
      // for exactly this, and the new id makes it the visible selection.
      setFindingsData([response, ...findings]);
      setSelectedFindingId(response.id);
      setShowAddModal(false);
      // Reset
      setNewFinding({
        title: '', severity: 'medium', category: 'control_deficiency',
        description: '', condition: '', criteria: '', cause: '', effect: '',
        recommendation: '', procedure: ''
      });
      toast.success(t('findingsCreatedToast'));
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error(t('findingsCreateFailed', msg));
    }
  };

  // Kanban Columns configuration. `draft` and `open` are pre-publication — an
  // auditee is served neither, so the columns are dropped rather than shown
  // permanently empty. The `draft` column is labelled for the queue it holds
  // rather than for the stored value: a finding sits there from the moment a
  // lead auditor raises it until an approver publishes it, which is the
  // supervisor's work, not the raiser's.
  const columns = [
    { id: 'draft', title: t('pendingSupervisorReview') },
    { id: 'open', title: t('open') },
    { id: 'awaiting_auditee_response', title: t('awaitingAuditeeResponse') },
    { id: 'in_progress', title: t('inProgress') },
    { id: 'resolved', title: t('resolved') },
  ].filter(col => !isAuditee || (col.id !== 'draft' && col.id !== 'open'));

  return (
    <div className="findings-view">
      {/* Top selector bar */}
      <div className="card mb-4">
        <EngagementPickerBar
          idPrefix="findings"
          engagements={engagements}
          // The resolved id, not the raw selection: the picker must show the
          // engagement whose findings are actually on screen, and that is the
          // default one until the user picks otherwise.
          value={activeEngId}
          onChange={handleEngChange}
          label={t('selectAuditEngagement')}
        />

        <div className="flex gap-2 justify-end">
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
                    <p className="text-muted text-center py-8">
                      {isAuditee ? t('noPublishedFindings') : t('noFindings')}
                    </p>
                  ) : (
                    findings.map(f => (
                      <div
                        key={f.id}
                        className={`finding-list-item ${activeFinding?.id === f.id ? 'active' : ''}`}
                        onClick={() => setSelectedFindingId(f.id)}
                        onDoubleClick={() => navigate(`/findings/${f.id}`)}
                        title={t('clickForDetails')}
                      >
                        <div className="finding-item-meta">
                          <span className="finding-num">{f.finding_number}</span>
                          <span className={`risk-tag ${f.severity === 'critical' ? 'critical' : f.severity === 'high' ? 'high' : 'medium'}`}>
                            {f.severity?.toUpperCase()}
                          </span>
                          {/* Derived server-side from target_resolution_date, so the
                              flag is right on first paint rather than appearing
                              whenever a scheduled job last happened to run. */}
                          {f.is_overdue && (
                            <span className="badge badge-danger">{t('overdue').toUpperCase()}</span>
                          )}
                        </div>
                        <h4>{f.title}</h4>
                        {/* `status_display`, not the raw value: the stored
                            `draft` is labelled for the queue it holds — the
                            supervisor's — and uppercasing the value showed
                            "DRAFT" instead. */}
                        <span className="badge badge-outline mt-1">{f.status_display?.toUpperCase()}</span>
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
                      {activeFinding.status_display?.toUpperCase()}
                    </span>
                    {activeFinding.is_overdue && (
                      <span className="badge badge-danger mt-2">{t('overdue').toUpperCase()}</span>
                    )}
                    {/* The split pane holds a summary; the full record — evidence,
                        comments, the remediation section — lives on its own page.
                        Previously the only way there was a double-click nobody
                        discovers, on a row whose tooltip already said "click for
                        details" for the *selection* it actually did. */}
                    <button
                      type="button"
                      className="btn btn-outline btn-sm mt-3"
                      onClick={() => navigate(`/findings/${activeFinding.id}`)}
                    >
                      {t('openFullRecord')}
                    </button>
                  </div>

                  <div className="detail-body">
                    {/* Where the finding came from, and what is being done about
                        it — both answers the split pane could have given and did
                        not: the register listed what had been found with no
                        trace of the test behind it and no trace of the
                        remediation in front of it. */}
                    <div className="detail-section">
                      <h4>{t('sourceProcedure')}</h4>
                      {activeFinding.procedure_label ? (
                        <Link
                          to={`/execution?engagement=${activeFinding.engagement}&procedure=${activeFinding.procedure}`}
                          className="text-accent hover:underline"
                        >
                          {activeFinding.procedure_label}
                        </Link>
                      ) : (
                        <p className="text-muted">—</p>
                      )}
                    </div>

                    <div className="detail-section">
                      <h4>{t('correctiveActions')}</h4>
                      {activeFinding.corrective_actions_count > 0 ? (
                        <Link to={`/capa?finding=${activeFinding.id}`} className="text-accent hover:underline">
                          {t('capasRaised', activeFinding.corrective_actions_count)}
                        </Link>
                      ) : (
                        <p className="text-muted">{t('noCapaForFinding')}</p>
                      )}
                    </div>
                    <div className="detail-section">
                      <h4>{t('description')}</h4>
                      <p>{activeFinding.description}</p>
                    </div>

                    <div className="detail-section">
                      <h4>{t('condition')}</h4>
                      <p>{activeFinding.condition || 'N/A'}</p>
                    </div>

                    <div className="detail-section">
                      <h4>{t('criteria')}</h4>
                      <p>{activeFinding.criteria || 'N/A'}</p>
                    </div>

                    <div className="detail-section">
                      <h4>{t('rootCause')}</h4>
                      <p>{activeFinding.cause || 'N/A'}</p>
                    </div>

                    <div className="detail-section">
                      <h4>{t('effectImpact')}</h4>
                      <p>{activeFinding.effect || 'N/A'}</p>
                    </div>

                    <div className="detail-section highlight-box">
                      <h4>{t('auditorRecommendation')}</h4>
                      <p>{activeFinding.recommendation || 'N/A'}</p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="card text-center py-8">
                  <h3>{t('noFindingSelected')}</h3>
                  <p className="text-muted">{t('selectFinding')}</p>
                </div>
              )}
            </div>
          ) : (
            /* Kanban view */
            <div className="kanban-board mt-4">
              {findings.length === 0 && isAuditee && (
                <div className="card text-center py-8 w-full">
                  <h3>{t('noPublishedFindings')}</h3>
                  <p className="text-muted">{t('noPublishedFindingsHint')}</p>
                </div>
              )}
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
                        <div key={f.id} className="kanban-card" onClick={() => { setViewMode('list'); setSelectedFindingId(f.id); }}>
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
      <Modal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        title={t('logNewFinding')}
        size="xl"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={() => setShowAddModal(false)}>{t('cancel')}</button>
            {/* `form=` because Modal renders the footer as a sibling of its
                children, so the submit button sits outside the <form>. */}
            <button type="submit" form="finding-form" className="btn btn-accent">{t('saveLogFinding')}</button>
          </>
        )}
      >
        {/* `noValidate` hands validation to the app, as UsersPage's forms already
            do. Without it the browser's own check intercepts an empty submit and
            React's onSubmit never fires — so `validateForm` never runs, the banner
            below never renders, and the user gets a browser tooltip instead of the
            named fields. The three `required` inputs here are all also covered by
            the app's validators, so nothing stops being enforced. */}
        <form id="finding-form" onSubmit={handleCreateFinding} noValidate>
          <FormErrorSummary errors={formErrors} />
          {/* The parent link comes first: a finding only exists because a test
              failed, so which test is the first thing to say about it. */}
          <div className="form-group">
            <label className="form-label" htmlFor="finding_procedure">{t('failedProcedure')}</label>
            <select
              id="finding_procedure"
              className="form-control"
              value={newFinding.procedure}
              onChange={(e) => setNewFinding({ ...newFinding, procedure: e.target.value })}
              required
            >
              <option value="">{t('selectFailedProcedure')}</option>
              {(failedProcedures ?? []).map(p => (
                <option key={p.id} value={p.id}>{p.step_number}. {p.title}</option>
              ))}
            </select>
            {(failedProcedures ?? []).length === 0 && (
              <p className="text-xs text-muted mt-1">{t('noFailedProcedures')}</p>
            )}
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="finding_title">{t('findingTitle')}</label>
            <input
              id="finding_title"
              type="text"
              className="form-control"
              placeholder={t('findingsTitlePlaceholder')}
              value={newFinding.title}
              onChange={(e) => setNewFinding({ ...newFinding, title: e.target.value })}
              required
            />
          </div>

          <div className="form-group-row">
            <div className="form-group">
              <label className="form-label" htmlFor="finding_severity">{t('severityLevel')}</label>
              <select
                id="finding_severity"
                className="form-control"
                value={newFinding.severity}
                onChange={(e) => setNewFinding({ ...newFinding, severity: e.target.value })}
              >
                <option value="critical">{t('critical')}</option>
                <option value="high">{t('high')}</option>
                <option value="medium">{t('medium')}</option>
                <option value="low">{t('low')}</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="finding_category">{t('findingCategory')}</label>
              <select
                id="finding_category"
                className="form-control"
                value={newFinding.category}
                onChange={(e) => setNewFinding({ ...newFinding, category: e.target.value })}
              >
                <option value="control_deficiency">{t('controlDeficiency')}</option>
                <option value="compliance">{t('complianceIssue')}</option>
                <option value="fraud">{t('fraudRisk')}</option>
                <option value="operational">{t('operationalWeakness')}</option>
                <option value="it_security">{t('itSecurityIssue')}</option>
              </select>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="finding_description">{t('descriptionSummary')}</label>
            <textarea
              id="finding_description"
              rows="3"
              className="form-control"
              value={newFinding.description}
              onChange={(e) => setNewFinding({ ...newFinding, description: e.target.value })}
              required
            />
          </div>

          <div className="form-group-row">
            <div className="form-group">
              <label className="form-label" htmlFor="finding_condition">{t('conditionActual')}</label>
              <textarea
                id="finding_condition"
                rows="2"
                className="form-control"
                value={newFinding.condition}
                onChange={(e) => setNewFinding({ ...newFinding, condition: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="finding_criteria">{t('criteriaPolicy')}</label>
              <textarea
                id="finding_criteria"
                rows="2"
                className="form-control"
                value={newFinding.criteria}
                onChange={(e) => setNewFinding({ ...newFinding, criteria: e.target.value })}
              />
            </div>
          </div>

          <div className="form-group-row">
            <div className="form-group">
              <label className="form-label" htmlFor="finding_cause">{t('rootCauseWhy')}</label>
              <textarea
                id="finding_cause"
                rows="2"
                className="form-control"
                value={newFinding.cause}
                onChange={(e) => setNewFinding({ ...newFinding, cause: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="finding_effect">{t('effectRisk')}</label>
              <textarea
                id="finding_effect"
                rows="2"
                className="form-control"
                value={newFinding.effect}
                onChange={(e) => setNewFinding({ ...newFinding, effect: e.target.value })}
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="finding_recommendation">{t('auditorRecommendation')}</label>
            <textarea
              id="finding_recommendation"
              rows="2"
              className="form-control"
              placeholder={t('findingsRecommendationPlaceholder')}
              value={newFinding.recommendation}
              onChange={(e) => setNewFinding({ ...newFinding, recommendation: e.target.value })}
              required
            />
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default FindingsPage;
