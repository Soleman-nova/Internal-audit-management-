import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { capaApi, findingsApi, usersApi } from '../../api';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { usePermissions } from '../../hooks/usePermissions';
import useAsyncData from '../../hooks/useAsyncData';
import { useI18n } from '../../context/I18nContext';
import { localizedName } from '../../utils/localizedName';
import { validateForm, validators, hasErrors } from '../../utils/validation';
import Modal from '../../components/ui/Modal';
import FormErrorSummary from '../../components/ui/FormErrorSummary';
import Pagination from '../../components/ui/Pagination';
import { CheckCircle2, MessageCircle, RefreshCw, Plus, FileUp } from 'lucide-react';

// Mirrors `AuditFinding.PRE_PUBLICATION_STATUSES`. A finding in one of these is
// the audit team's own work in progress — a supervisor has not endorsed it yet —
// and both the server and the compiled report treat it as not yet existing for
// anyone outside the audit team.
const PRE_PUBLICATION_STATUSES = ['draft', 'open'];

function FollowUpPage() {
  const toast = useToast();
  const auth = useAuth();
  const { t, lang } = useI18n();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // A finding's own page sends the auditor here to raise a plan against it
  // (`/capa?finding=<id>`). Without this the link was a dead end that landed on
  // the follow-up tab with the form closed and the finding still to be found in
  // a dropdown of every finding in the register — the one moment the user knows
  // exactly which record they mean.
  const deepLinkFindingId = searchParams.get('finding');
  const { canWriteAudit, canApprovePlans } = usePermissions();
  const [activeTab, setActiveTab] = useState('all');
  // Server-side pagination: the capas hook below holds only the current page
  // slice. `page` is both what the user asked for and what gets requested — a
  // page past the end is a 404 from DRF, so there is no separate clamped copy to
  // keep in sync.
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [formErrors, setFormErrors] = useState({});
  const currentUser = auth.user;

  // The auditee is the one who formulates the remediation plan for a finding
  // that concerns them (spec Step 11), so raising a CAPA is the single write
  // this page offers them — `CanProposeCorrectiveAction` on the backend allows
  // exactly that. Everything else here stays capability-gated.
  const canProposeCapa = canWriteAudit || currentUser?.role === 'auditee';

  // An auditee's plan is theirs by definition — the server overwrites `owner`
  // with the requester — so the form carries their own id and the picker is
  // not rendered for them. Everyone else picks an auditee from the list.
  const emptyCapa = () => ({
    finding: '',
    title: '',
    description: '',
    recommendation: '',
    owner: canWriteAudit ? '' : String(currentUser?.id ?? ''),
    priority: 'medium',
    due_date: '',
  });

  // Spawning CAPA Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newCapa, setNewCapa] = useState(emptyCapa);
  const [creating, setCreating] = useState(false);
  // Whether a `?finding=` deep link has already been acted on, so a later refetch
  // of the picker list does not put the form back in front of a user who closed it.
  const [deepLinkConsumed, setDeepLinkConsumed] = useState(false);

  // One place that builds a form out of a finding, so a deep link and a dropdown
  // pick produce the same draft rather than one prefilled and one blank.
  const capaFromFinding = (finding) => ({
    ...emptyCapa(),
    finding: finding.id,
    title: `CAPA: ${finding.title}`,
    description: finding.description || '',
    recommendation: finding.recommendation || '',
  });

  const openCreateModal = (findingId = null) => {
    setFormErrors({});
    const selected = findingId
      ? findings.find(f => String(f.id) === String(findingId))
      : null;
    // A finding that is not among the pickable ones leaves the form blank rather
    // than carrying someone else's record: a stale link, or a finding this user
    // may not link an action to (see `linkableFindings`).
    setNewCapa(selected ? capaFromFinding(selected) : emptyCapa());
    setShowCreateModal(true);
  };

  // Auditee Response Modal State
  const [showResponseModal, setShowResponseModal] = useState(false);
  // Which CAPA the response modal acts on, held as an **id** rather than as the
  // row object. Every mutation re-requests the list, so a stored row would go
  // stale; the id is resolved against whatever page is on screen instead.
  const [selectedCapaId, setSelectedCapaId] = useState(null);
  const [responseText, setResponseText] = useState('');
  const [statusUpdate, setStatusUpdate] = useState('in_progress');
  const [evidenceFile, setEvidenceFile] = useState(null);
  const [submittingResponse, setSubmittingResponse] = useState(false);

  // One request per (tab, page, page size), and a response that arrives after a
  // newer run started is discarded — paging or switching tabs faster than the
  // server answers used to let a slow earlier response land last and leave the
  // table showing one tab's rows under another tab's heading.
  const { data: capasData, loading, reload: reloadCapas } = useAsyncData(
    async () => {
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
      // Rows and total come out of the one response, so they are returned
      // together rather than kept as two pieces of state that a superseded
      // request could leave disagreeing.
      return { items: res.items || [], count: res.count || 0 };
    },
    [activeTab, page, pageSize],
    { onError: () => toast.error(t('capaLoadFailed')) },
  );

  const capas = capasData?.items ?? [];
  const totalCount = capasData?.count ?? 0;

  // Role-scoped counts (total/overdue/...) driving the tab badges. Refetched
  // after mutations; a failure just falls back to the loaded page's total, so
  // there is no toast to lose here.
  const { data: summary, reload: reloadSummary } = useAsyncData(
    async () => capaApi.getSummary(),
    [currentUser?.id],
  );

  // Options for the spawn-CAPA pickers. Auditees need the findings list too now
  // — the endpoint scopes it to the findings that concern them, which is
  // exactly the set they may propose a plan for — but not the owner list,
  // which the server overrides for them anyway.
  const { data: pickers } = useAsyncData(
    async () => {
      const [findingsRes, usersRes] = await Promise.all([
        // `page_size` because this is a picker, not a paged list: it must offer
        // every finding that could be linked to a CAPA. Without it the endpoint
        // paginates at 20 and the 21st finding is silently unlinkable — the same
        // reason `planningApi`'s picker endpoints default to 1000.
        findingsApi.getFindings({ page_size: 1000 }),
        canWriteAudit ? usersApi.getAllUsers({ role: 'auditee' }) : Promise.resolve([]),
      ]);
      return {
        findings: Array.isArray(findingsRes) ? findingsRes : [],
        auditees: Array.isArray(usersRes) ? usersRes : [],
      };
    },
    [currentUser?.id, canWriteAudit],
    {
      enabled: Boolean(currentUser),
      onError: () => toast.error(t('capaPickersLoadFailed')),
    },
  );

  const findings = pickers?.findings ?? [];
  const auditees = pickers?.auditees ?? [];

  // Only findings a supervisor has endorsed may be linked, and the server now
  // refuses the rest (CorrectiveActionSerializer.validate_finding) — so listing
  // one here would offer a choice that can only end in a 400. The auditee's copy
  // of this list arrives already filtered by their read scope, so the count below
  // is zero for them and the hint is simply not rendered.
  //
  // Raw `status`, not `status_display`: this is the stored value the server
  // compares against PRE_PUBLICATION_STATUSES, and the label is prose for people.
  const linkableFindings = findings.filter(f => !PRE_PUBLICATION_STATUSES.includes(f.status));
  const unendorsedCount = findings.length - linkableFindings.length;

  // Opening a modal because of a URL is not an effect — it is state derived from a
  // prop that happened to arrive in the URL bar. React's own answer for "adjust
  // state when an input changes" is a render-phase set, which it re-runs the
  // component for immediately, so the user never sees the un-prefilled form. An
  // effect here would be the same work plus a frame of flicker, and would be the
  // kind of effect that re-fires every time the list is reloaded.
  //
  // `deepLinkConsumed` is what makes it once-per-arrival: without it every
  // re-fetch of the findings list would re-open the modal over a user who had
  // deliberately closed it.
  const linkedFinding = deepLinkFindingId && !deepLinkConsumed
    ? linkableFindings.find(f => String(f.id) === String(deepLinkFindingId))
    : null;
  // Only a finding this user may actually link. Anything else opens a blank
  // form, which reads as "the link did not work" rather than "that finding is
  // not eligible" — and for an unendorsed finding it is a refusal the server
  // would make anyway.
  if (linkedFinding) {
    setDeepLinkConsumed(true);
    setFormErrors({});
    setNewCapa(capaFromFinding(linkedFinding));
    setShowCreateModal(true);
  }

  // Resolved from the rows currently on screen rather than stored: a refetch
  // replaces them, and a row that has since left the page resolves to null.
  const selectedCapa = selectedCapaId === null
    ? null
    : capas.find(c => c.id === selectedCapaId) ?? null;

  // Switching the tab re-runs the hook above through `activeTab`; resetting the
  // page in the same handler is what keeps a user on page 3 of "all" from being
  // dropped on a nonexistent page 3 of "overdue". Setting both together *is* the
  // request, so no effect is needed to sync them.
  const handleTabChange = (tab) => {
    if (tab === activeTab) return;
    setActiveTab(tab);
    setPage(1);
  };

  const handleFindingChange = (e) => {
    const findingId = e.target.value;
    const selected = findings.find(f => String(f.id) === String(findingId));
    // Cleared rather than left stale when the pick is emptied: the draft is built
    // from the finding, so keeping a previous one's title under "no finding
    // selected" would put words in the save that belong to no record at all.
    setNewCapa(selected
      ? capaFromFinding(selected)
      : { ...emptyCapa(), owner: newCapa.owner, finding: findingId });
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
            return { due_date: t('capaDueDateFuture') };
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
      setNewCapa(emptyCapa());
      // Reload so counts/ordering stay truthful — the new row's due date
      // decides which page it lands on under due_date ordering, so neither a
      // local prepend nor a page jump would be reliable.
      reloadCapas();
      reloadSummary();
      // An auditee's POST lands as a proposal the auditor has to accept, not as
      // an assigned task, so the confirmation says which of the two happened.
      toast.success(canWriteAudit ? t('capaCreatedToast') : t('capaProposedToast'));
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error(t('capaCreateFailed', msg));
    } finally {
      setCreating(false);
    }
  };

  const handleOpenResponse = (capa) => {
    setSelectedCapaId(capa.id);
    setShowResponseModal(true);
    setFormErrors({});
    setResponseText('');
    setStatusUpdate(capa.status || 'in_progress');
    setEvidenceFile(null);
  };

  const handleSubmitResponse = async (e) => {
    e.preventDefault();
    if (!selectedCapa) return;
    // The notes are the payload of this form — the view's `response_text` is a
    // non-blank TextField — so an empty submit is refused here rather than sent
    // to be rejected by the server. `noValidate` on the form is what lets this
    // run at all.
    const errors = validateForm({ response_notes: responseText }, {
      response_notes: { validators: [validators.required] },
    });
    if (hasErrors(errors)) {
      setFormErrors(errors);
      return;
    }
    setFormErrors({});
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
      toast.success(t('capaResponseRecorded'));
      reloadCapas();
      reloadSummary();
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error(t('capaResponseFailed', msg));
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
  // Anyone else would get a 403, so don't offer them the button. Neither side
  // responds while a plan is awaiting approval: the owner would be walking it out
  // of `pending_approval`, and the auditor's route there is Approve Plan.
  const canRespondTo = (capa) => (
    (canWriteAudit || capa.owner === currentUser?.id)
    && capa.status !== 'pending_approval'
  );

  // Verification is scoped to whoever raised the action, plus APPROVE_PLANS
  // holders who sign off across engagements — the same object check the backend
  // applies to schedule-followup.
  const canVerify = (capa) => canApprovePlans || capa.assigned_by === currentUser?.id;

  return (
    <div className="followup-view">
      <div className="tab-container">
        <button className={`tab-btn ${activeTab === 'all' ? 'active' : ''}`} onClick={() => handleTabChange('all')}>
          {t('allCapas', summary?.total ?? totalCount)}
        </button>
        <button className={`tab-btn ${activeTab === 'open' ? 'active' : ''}`} onClick={() => handleTabChange('open')}>
          {t('openInProgress')}
        </button>
        <button className={`tab-btn ${activeTab === 'resolved' ? 'active' : ''}`} onClick={() => handleTabChange('resolved')}>
          {t('resolvedCapas')}
        </button>
        <button className={`tab-btn ${activeTab === 'overdue' ? 'active' : ''}`} onClick={() => handleTabChange('overdue')}>
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
              <button className="btn btn-outline flex items-center gap-2" onClick={() => reloadCapas()}>
                <RefreshCw size={14} /> {t('refresh')}
              </button>
              {canProposeCapa && (
                <button className="btn btn-accent flex items-center gap-2" onClick={openCreateModal}>
                  <Plus size={16} /> {canWriteAudit ? t('spawnCapaTask') : t('formulateCapa')}
                </button>
              )}
            </div>
          </div>

          <div className="table-responsive">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('actionRef')}</th>
                  <th>{t('actionTitle')}</th>
                  <th>{t('owner')}</th>
                  <th>{t('priority')}</th>
                  <th>{t('dueDate')}</th>
                  <th>{t('status')}</th>
                  <th>{t('action')}</th>
                </tr>
              </thead>
              <tbody>
                {capas.length === 0 ? (
                  <tr>
                    <td colSpan="7" className="text-center py-8">{t('noCapaRecords')}</td>
                  </tr>
                ) : (
                  capas.map(c => (
                    <tr key={c.id} className="cursor-pointer hover:bg-gray-50 dark:hover:bg-slate-800/50" onClick={() => navigate(`/capa/${c.id}`)} title={t('clickForDetails')}>
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
                              <MessageCircle size={14} /> {t('respond')}
                            </button>
                          )}
                          {canVerify(c) && (
                            <button
                              className="btn btn-outline btn-sm flex items-center gap-1"
                              onClick={(e) => { e.stopPropagation(); navigate(`/capa/${c.id}`); }}
                            >
                              <CheckCircle2 size={14} /> {t('verifyAndClose')}
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
        title={canWriteAudit ? t('spawnCapaLinked') : t('formulateCapaTitle')}
        size="xl"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={() => setShowCreateModal(false)}>{t('cancel')}</button>
            {/* `form=` because Modal renders the footer as a sibling of its
                children, so the submit button sits outside the <form>. */}
            <button type="submit" form="capa-form" className="btn btn-accent" disabled={creating}>
              {creating
                ? t('capaSpawning')
                : (canWriteAudit ? t('spawnAssignCapa') : t('submitProposalForApproval'))}
            </button>
          </>
        )}
      >
        {/* `noValidate` hands validation to the app, as UsersPage's forms already
            do. Without it the browser intercepts an empty submit and React's
            onSubmit never fires — so `validateForm` never runs, the banner below
            never renders, and the user gets a browser tooltip instead of the
            named fields. Every one of the six `required` controls here is also
            covered by the schema in handleCreateCapa, so nothing stops being
            enforced. */}
        <form id="capa-form" onSubmit={handleCreateCapa} noValidate>
          <FormErrorSummary errors={formErrors} />
          <div className="form-group">
            <label className="form-label" htmlFor="capa_finding">{t('linkToFinding')}</label>
            <select
              id="capa_finding"
              className="form-control"
              value={newCapa.finding}
              onChange={handleFindingChange}
              required
            >
              <option value="">{t('selectAuditFinding')}</option>
              {linkableFindings.map(f => (
                <option key={f.id} value={f.id}>{f.finding_number} - {f.title}</option>
              ))}
            </select>
            {/* Says what is missing rather than letting the list quietly come up
                short. The findings left out are the ones the auditor raised and
                the supervisor has not signed off, and an auditor who cannot find
                their own finding here needs the reason more than the list. */}
            {unendorsedCount > 0 && (
              <small className="form-hint">{t('unendorsedFindingsHint')}</small>
            )}
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="capa_title">{t('actionCapaTitle')}</label>
            <input
              id="capa_title"
              type="text"
              className="form-control"
              placeholder={t('implementDualAuth')}
              value={newCapa.title}
              onChange={e => setNewCapa({ ...newCapa, title: e.target.value })}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="capa_description">{t('actionDescription')}</label>
            <textarea
              id="capa_description"
              rows="3"
              className="form-control"
              placeholder={t('provideDetailedDescription')}
              value={newCapa.description}
              onChange={e => setNewCapa({ ...newCapa, description: e.target.value })}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="capa_recommendation">{t('auditorRecommendationRef')}</label>
            <textarea
              id="capa_recommendation"
              rows="2"
              className="form-control"
              value={newCapa.recommendation}
              onChange={e => setNewCapa({ ...newCapa, recommendation: e.target.value })}
              placeholder={t('auditorRecommendationDetails')}
              required
            />
          </div>

          <div className="form-group-row">
            <div className="form-group">
              {canWriteAudit ? (
                <>
                  <label className="form-label" htmlFor="capa_owner">{t('assignOwner')}</label>
                  <select
                    id="capa_owner"
                    className="form-control"
                    value={newCapa.owner}
                    onChange={e => setNewCapa({ ...newCapa, owner: e.target.value })}
                    required
                  >
                    <option value="">{t('selectAuditeeOwner')}</option>
                    {auditees.map(a => (
                      <option key={a.id} value={a.id}>{a.first_name} {a.last_name} ({localizedName(lang, a.department_name, a.department_name_am) || t('capaAuditeeFallback')})</option>
                    ))}
                  </select>
                </>
              ) : (
                // No picker: the server assigns the proposal to whoever wrote
                // it, so a choice here would be a control whose value is
                // discarded. Plain text rather than a disabled select — and no
                // `htmlFor`, since a label may only point at a form control.
                <>
                  <span className="form-label">{t('assignOwner')}</span>
                  <p className="form-control-static">
                    {currentUser?.full_name || currentUser?.username}
                  </p>
                </>
              )}
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="capa_priority">{t('priority')}</label>
              <select
                id="capa_priority"
                className="form-control"
                value={newCapa.priority}
                onChange={e => setNewCapa({ ...newCapa, priority: e.target.value })}
              >
                <option value="low">{t('low')}</option>
                <option value="medium">{t('medium')}</option>
                <option value="high">{t('high')}</option>
                <option value="immediate">{t('immediate')}</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="capa_due_date">{t('dueDate')}</label>
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
        title={selectedCapa ? t('submitManagementUpdate', selectedCapa.action_number) : t('capaSubmitUpdatePlain')}
        size="lg"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={() => setShowResponseModal(false)}>{t('cancel')}</button>
            <button type="submit" form="capa-response-form" className="btn btn-primary" disabled={submittingResponse}>
              {submittingResponse ? t('capaSubmittingResponse') : t('submitResponse')}
            </button>
          </>
        )}
      >
        {selectedCapa && (
          // The single `required` control here (the notes) had no app validator
          // to fall back on, so `noValidate` goes on together with one in
          // handleSubmitResponse: the browser's own block would otherwise be
          // traded for a 400 from the view, whose response_text is non-blank.
          <form id="capa-response-form" onSubmit={handleSubmitResponse} noValidate>
          <FormErrorSummary errors={formErrors} />
            <div className="mb-4">
              <span className="text-xs text-muted font-bold block">{t('recommendation')}</span>
              <p className="text-sm font-semibold">{selectedCapa.recommendation}</p>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="response_status">{t('progressStatus')}</label>
              <select
                id="response_status"
                className="form-control"
                value={statusUpdate}
                onChange={(e) => setStatusUpdate(e.target.value)}
              >
                <option value="in_progress">{t('inProgress')}</option>
                <option value="partially_resolved">{t('partiallyResolved')}</option>
                {/* The handoff state: "the work is done, here is the proof". */}
                <option value="evidence_submitted">{t('evidenceSubmitted')}</option>
                {/* Recording the outcome settles the action, so it is the audit
                    side's — an owner posting it is refused server-side, and this
                    form is the one both sides reach. */}
                {canWriteAudit && (
                  <option value="resolved">{t('resolvedActioned')}</option>
                )}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="response_notes">{t('actionUpdateNotes')}</label>
              <textarea
                id="response_notes"
                rows="4"
                className="form-control"
                placeholder={t('provideActionDetails')}
                value={responseText}
                onChange={(e) => setResponseText(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label flex items-center gap-1" htmlFor="response_evidence"><FileUp size={16} /> {t('uploadImplementationDoc')}</label>
              <input
                id="response_evidence"
                type="file"
                className="form-control"
                onChange={(e) => setEvidenceFile(e.target.files[0])}
              />
              {evidenceFile && (
                <span className="text-xs text-success block mt-1">{t('selectedFile', evidenceFile.name)}</span>
              )}
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}

export default FollowUpPage;

