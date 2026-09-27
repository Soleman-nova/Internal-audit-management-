import { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { planningApi, usersApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import useAsyncData from '../../hooks/useAsyncData';
import { useI18n } from '../../context/I18nContext';
import { useOrgUnits } from '../../hooks/useOrgUnits';
import UniverseTab from './tabs/UniverseTab';
import PlansTab from './tabs/PlansTab';
import EngagementsTab from './tabs/EngagementsTab';
import UniverseFormModal from './modals/UniverseFormModal';
import { UniverseExportModal, UniverseImportModal } from './modals/UniverseTransferModals';
import PlanFormModal from './modals/PlanFormModal';
import EngagementFormModal from './modals/EngagementFormModal';
import TeamModal from './modals/TeamModal';

/**
 * The planning page shell: the tab bar, the deep links, and every request the
 * page makes.
 *
 * The three tab loads and the shared reference load live here and are *not*
 * lazy. The "Engagements (N)" label reads a server total even while another tab
 * is showing, and the effects these hooks replaced all ran on mount — so a tab
 * that fetched only when it was opened would blank that label and move the data
 * to a different moment.
 *
 * Rows are never copied into state. A modal is opened with the **id** of the row
 * it acts on and the row itself is resolved against the current list on every
 * render; each form builds its fields from it when it mounts (see
 * `planningForms.js`), and each owns those fields plus the validation and submit
 * that go with them.
 */
function PlanningPage() {
  const toast = useToast();
  const { t } = useI18n();

  // ── Deep links from notifications ────────────────────────────────
  // The backend emits /planning?plan=<id> and /planning?engagement=<id>.
  // The tab that holds the record is derived from the query string, not set
  // from an effect — an effect would render the universe tab first and then
  // replace it, and the scroll-into-view below would chase a moving target.
  const [searchParams] = useSearchParams();
  const focusPlanId = searchParams.get('plan');
  const focusEngagementId = searchParams.get('engagement');
  const deepLinkTab = focusPlanId ? 'plans' : focusEngagementId ? 'engagements' : null;
  const deepLinkKey = focusPlanId
    ? `plan-${focusPlanId}`
    : focusEngagementId ? `engagement-${focusEngagementId}` : '';

  const [activeTab, setActiveTab] = useState(deepLinkTab || 'universe');
  const [lastDeepLink, setLastDeepLink] = useState(deepLinkKey);
  if (deepLinkKey && deepLinkKey !== lastDeepLink) {
    // Clicking a second notification while already on this page changes the
    // query string without remounting, so the initial state above never
    // re-runs. Adjusting during render is React's documented answer.
    setLastDeepLink(deepLinkKey);
    setActiveTab(deepLinkTab);
  }

  // Per-tab pagination controls, the same shape AuditTrailPage uses. The slices
  // themselves — and each tab's server total — come back from the tab's
  // `useAsyncData` loader below rather than from `useState`s written by hand,
  // because a hand-kept copy of a fetched list is exactly what drifts: the
  // response that arrives late overwrites the current one and nothing says so.
  const [universePage, setUniversePage] = useState(1);
  const [universePageSize, setUniversePageSize] = useState(25);
  const [universeNonce, setUniverseNonce] = useState(0);
  const [plansPage, setPlansPage] = useState(1);
  const [plansPageSize, setPlansPageSize] = useState(25);
  const [plansNonce, setPlansNonce] = useState(0);
  const [engagementsPage, setEngagementsPage] = useState(1);
  const [engagementsPageSize, setEngagementsPageSize] = useState(25);
  const [engagementsNonce, setEngagementsNonce] = useState(0);

  // Which row each modal is open on — the id only, never the row (see the note
  // at the top). The modals are rendered unconditionally with an `isOpen` prop;
  // `Modal` renders its children only while open, so a form mounts on open and
  // is thrown away on close.
  const [showUniverseModal, setShowUniverseModal] = useState(false);
  const [editingUniverseId, setEditingUniverseId] = useState(null);

  // Bulk import/export of the Audit Universe (Excel/CSV).
  const [showUniverseImportModal, setShowUniverseImportModal] = useState(false);
  const [showUniverseExportModal, setShowUniverseExportModal] = useState(false);

  const [showPlanModal, setShowPlanModal] = useState(false);
  const [editingPlanId, setEditingPlanId] = useState(null);

  const [showEngagementModal, setShowEngagementModal] = useState(false);
  const [editingEngagementId, setEditingEngagementId] = useState(null);

  // Team Member Assignment State. The engagement the modal acts on is held as
  // an **id**, not as the row object: the engagements tab refetches after every
  // status change, and the row is resolved from whatever the current page holds.
  const [showTeamModal, setShowTeamModal] = useState(false);
  const [selectedEngagementId, setSelectedEngagementId] = useState(null);

  // Every tab keeps its own page state, so switching tabs never loses the
  // user's place.

  // Guard flags so the deep-link page scans below run at most once per link
  // (the resulting setXPage(...) moves a fetch dependency, which would
  // otherwise re-enter the scan forever).
  const plansLocateDone = useRef(false);
  const engagementsLocateDone = useRef(false);

  // PPM project registry feeding the universe form's "PPM Project" dropdown,
  // shown when the entity's category is 'project'. Picking or adding a project
  // auto-fills the entity name/code and, when empty, the department (PPM node).
  const { units: orgUnits } = useOrgUnits();
  // PPM = EEU Projects Portfolio Management, a top-level Department (code PPM).
  const ppmUnit = orgUnits.find(u => String(u.code).toUpperCase() === 'PPM');
  const ppmDepartmentId = ppmUnit ? String(ppmUnit.id) : '';

  // One `useAsyncData` per tab, plus one for the shared reference sets and one
  // for the team list of the engagement whose modal is open. Each loader returns
  // the tab's slice AND its server total as a single object, so the two can no
  // longer disagree about what is on screen — they used to be two `useState`s
  // written from inside the same response, and a response that arrived after a
  // newer one clobbered both.
  //
  // None of the three tabs is lazily loaded: the effects these replace all ran
  // on mount, and these hooks are enabled from mount for the same behaviour.
  // `enabled` is used only where a request is filtered by a selection that
  // starts empty (the team list, which lives in TeamModal).
  const {
    data: universeData,
    loading: universeLoading,
  } = useAsyncData(
    async () => {
      const res = await planningApi.getUniverse({ page: universePage, page_size: universePageSize });
      const items = res.items || [];
      const count = res.count || 0;
      // A deletion can leave the current page past the end of the list; clamp it
      // and let the resulting dependency change fetch the page that exists.
      const last = Math.max(1, Math.ceil(count / universePageSize));
      if (universePage > last) setUniversePage(last);
      return { items, count };
    },
    [universePage, universePageSize, universeNonce],
    { onError: () => toast.error(t('planningLoadFailed')) },
  );

  const {
    data: plansData,
    loading: plansLoading,
  } = useAsyncData(
    async () => {
      const res = await planningApi.getPlans({ page: plansPage, page_size: plansPageSize });
      const items = res.items || [];
      const count = res.count || 0;
      const last = Math.max(1, Math.ceil(count / plansPageSize));
      if (plansPage > last) setPlansPage(last);
      // Deep link (?plan=N): if the target plan is on a later page, jump to it.
      if (focusPlanId
        && !items.some(p => String(p.id) === String(focusPlanId))
        && res.hasMore && !plansLocateDone.current) {
        plansLocateDone.current = true;
        const cap = Math.min(last, 200);
        for (let p = plansPage + 1; p <= cap; p++) {
          const r = await planningApi.getPlans({ page: p, page_size: plansPageSize });
          if (r.items.some(x => String(x.id) === String(focusPlanId))) { setPlansPage(p); break; }
          if (!r.hasMore) break;
        }
      }
      return { items, count };
    },
    [plansPage, plansPageSize, plansNonce],
    { onError: () => toast.error(t('planningLoadFailed')) },
  );

  const {
    data: engagementsData,
    loading: engagementsLoading,
  } = useAsyncData(
    async () => {
      const res = await planningApi.getEngagements({ page: engagementsPage, page_size: engagementsPageSize });
      const items = res.items || [];
      const count = res.count || 0;
      const last = Math.max(1, Math.ceil(count / engagementsPageSize));
      if (engagementsPage > last) setEngagementsPage(last);
      // Deep link (?engagement=N): same one-shot jump as the plans tab.
      if (focusEngagementId
        && !items.some(e => String(e.id) === String(focusEngagementId))
        && res.hasMore && !engagementsLocateDone.current) {
        engagementsLocateDone.current = true;
        const cap = Math.min(last, 200);
        for (let p = engagementsPage + 1; p <= cap; p++) {
          const r = await planningApi.getEngagements({ page: p, page_size: engagementsPageSize });
          if (r.items.some(x => String(x.id) === String(focusEngagementId))) { setEngagementsPage(p); break; }
          if (!r.hasMore) break;
        }
      }
      return { items, count };
    },
    [engagementsPage, engagementsPageSize, engagementsNonce],
    { onError: () => toast.error(t('planningLoadFailed')) },
  );

  // Reference data for the modal dropdowns: every user (lead/supervisor
  // pickers — getAllUsers walks the pages, the endpoint only serves 20 at a
  // time), the PPM project registry, the due-for-re-audit badge, and the FULL
  // universe/plan catalogs that back those dropdowns (the arrays the tabs
  // render are paginated slices, which is why the catalogs are separate calls).
  //
  // It is one hook rather than five, because the five requests are one piece of
  // page furniture: the dropdowns are populated or not, and the mutation paths
  // that invalidate them refetch all five together.
  const {
    data: references,
    setData: setReferences,
    reload: reloadReferences,
  } = useAsyncData(
    async () => {
      const [usersRes, projectsRes, dueRes, univCatRes, plansCatRes] = await Promise.all([
        usersApi.getAllUsers(),
        planningApi.getProjects(),
        planningApi.getDueForReAudit(),
        planningApi.getUniverse(),
        planningApi.getPlans(),
      ]);
      return {
        users: usersRes || [],
        projects: projectsRes || [],
        due: dueRes || { items: [], count: 0, hasMore: false },
        universeCatalog: univCatRes.items || [],
        plansCatalog: plansCatRes.items || [],
      };
    },
    [],
    { onError: () => toast.error(t('planningLoadFailed')) },
  );

  // Derived views of the loads above: the slices with their server totals, the
  // reference sets, and the rows the modals act on. None of these is copied
  // into state — they are recomputed from whatever the current response is, so
  // a refetch can never leave a stale row behind.
  const universe = universeData?.items ?? [];
  const universeCount = universeData?.count ?? 0;
  const plans = plansData?.items ?? [];
  const plansCount = plansData?.count ?? 0;
  const engagements = engagementsData?.items ?? [];
  // Server total, shown in the Engagements tab label — never the slice length.
  const engagementCount = engagementsData?.count ?? 0;
  const allUsers = references?.users ?? [];
  const projects = references?.projects ?? [];
  const dueForAudit = references?.due ?? { items: [], count: 0, hasMore: false };
  const universeCatalog = references?.universeCatalog ?? [];
  const plansCatalog = references?.plansCatalog ?? [];

  // The two ids above, resolved against the lists they came from. An id that is
  // no longer in the current page (or list) resolves to null rather than to a
  // frozen copy of a row.
  const selectedEngagement = engagements.find(e => String(e.id) === String(selectedEngagementId)) || null;

  // The row each form modal was opened on, resolved the same way. The modals
  // mount only while open, so this is what seeds their form state.
  const editingUniverse = universe.find(u => String(u.id) === String(editingUniverseId)) || null;
  const editingPlan = plans.find(p => String(p.id) === String(editingPlanId)) || null;
  const editingEngagement = engagements.find(e => String(e.id) === String(editingEngagementId)) || null;

  // The page-level spinner covers the three tab loads, as the single `loading`
  // flag it replaces did. The references never drove it and still do not.
  const loading = universeLoading || plansLoading || engagementsLoading;

  // Refetch a tab after a mutation even when page/pageSize are unchanged.
  // resetPage restarts at page 1 when a new row's position under the current
  // ordering is unpredictable (create/import).
  const reloadTab = (tab, { resetPage = false } = {}) => {
    if (tab === 'universe') {
      if (resetPage) setUniversePage(1);
      setUniverseNonce(n => n + 1);
    } else if (tab === 'plans') {
      if (resetPage) setPlansPage(1);
      setPlansNonce(n => n + 1);
    } else {
      if (resetPage) setEngagementsPage(1);
      setEngagementsNonce(n => n + 1);
    }
  };

  // Scroll the deep-linked record into view once the fetch has landed —
  // otherwise the notification drops the user on the right tab with no
  // indication of which row they were meant to look at. It reads the derived
  // `loading` above, so it waits for the tab that holds the row.
  useEffect(() => {
    if (loading || !deepLinkKey) return;
    const el = document.getElementById(deepLinkKey);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [loading, activeTab, deepLinkKey]);

  // ── Opening and closing the modals ───────────────────────────────
  // The shell owns which row is being edited and whether a modal is showing;
  // the form itself, its validation and its submit belong to the modal.

  const openAddUniverse = () => {
    setEditingUniverseId(null);
    setShowUniverseModal(true);
  };

  const openEditUniverse = (item) => {
    setEditingUniverseId(item.id);
    setShowUniverseModal(true);
  };

  const closeUniverseModal = () => {
    setShowUniverseModal(false);
    setEditingUniverseId(null);
  };

  // A risk_score/name edit can move the row across page boundaries under
  // -risk_score ordering; the catalog and re-audit badge also need to stay
  // truthful — refetch rather than mutate the slice in place.
  const handleUniverseSaved = () => {
    reloadTab('universe', { resetPage: !editingUniverseId });
    reloadReferences();
  };

  const openImportUniverse = () => {
    setShowUniverseImportModal(true);
  };

  const closeImportUniverse = () => {
    setShowUniverseImportModal(false);
  };

  // Imports shift the due-for-re-audit badge and the modal catalogs too,
  // so refresh the references alongside the universe slice.
  const handleUniverseImported = () => {
    reloadTab('universe', { resetPage: true });
    reloadReferences();
  };

  const openAddPlan = () => {
    setEditingPlanId(null);
    setShowPlanModal(true);
  };

  const openEditPlan = (plan) => {
    setEditingPlanId(plan.id);
    setShowPlanModal(true);
  };

  const closePlanModal = () => {
    setShowPlanModal(false);
    setEditingPlanId(null);
  };

  // Year/status edits can reorder the -year slice; refresh plans and the
  // full plans catalog that backs the engagement modal's plan picker.
  const handlePlanSaved = () => {
    reloadTab('plans', { resetPage: !editingPlanId });
    reloadReferences();
  };

  const openAddEngagement = () => {
    setEditingEngagementId(null);
    setShowEngagementModal(true);
  };

  const openEditEngagement = (eng) => {
    setEditingEngagementId(eng.id);
    setShowEngagementModal(true);
  };

  const closeEngagementModal = () => {
    setShowEngagementModal(false);
    setEditingEngagementId(null);
  };

  const handleEngagementSaved = () => {
    reloadTab('engagements', { resetPage: !editingEngagementId });
  };

  const handleSubmitPlan = async (planId) => {
    try {
      await planningApi.submitPlan(planId);
      toast.success(t('planSubmittedToast'));
      reloadTab('plans');
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : t('planSubmitFailed');
      toast.error(msg);
    }
  };

  const handleApprovePlan = async (planId) => {
    try {
      await planningApi.approvePlan(planId);
      toast.success(t('planApprovedToast'));
      reloadTab('plans');
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : t('planApproveFailed');
      toast.error(msg);
    }
  };

  // The engagement status control on each row. The `completed` branch can be
  // refused by the server (open findings), so the message is surfaced rather
  // than swallowed — and `detail` is read before the page's usual
  // JSON.stringify fallback, or the guard's wording reaches the user as
  // `{"detail":"Cannot complete this engagement: …"}`.
  //
  // No optimistic update: the select is bound to `eng.status`, so a rejected
  // change snaps back on its own once the untouched state re-renders.
  const handleUpdateEngagementStatus = async (engagementId, nextStatus) => {
    try {
      await planningApi.updateEngagementStatus(engagementId, nextStatus);
      toast.success(t('engagementStatusSet', nextStatus.replace('_', ' ')));
      reloadTab('engagements');
    } catch (err) {
      const data = err.response?.data;
      const msg = data?.detail
        || (typeof data === 'object' ? JSON.stringify(data) : t('engagementStatusFailed'));
      toast.error(msg);
      // Re-fetch so the select is repainted from the server's actual value.
      reloadTab('engagements');
    }
  };

  // The modal loads the roster itself, keyed on the id set here; closing clears
  // it so re-opening the same engagement fetches again.
  const openTeamModal = (engagement) => {
    setSelectedEngagementId(engagement.id);
    setShowTeamModal(true);
  };

  const closeTeamModal = () => {
    setShowTeamModal(false);
    setSelectedEngagementId(null);
  };

  return (
    <div className="planning-view">
      <div className="tab-container">
        <button className={`tab-btn ${activeTab === 'universe' ? 'active' : ''}`} onClick={() => setActiveTab('universe')}>
          {t('auditUniverse')}
        </button>
        <button className={`tab-btn ${activeTab === 'plans' ? 'active' : ''}`} onClick={() => setActiveTab('plans')}>
          {t('annualAuditPlans')}
        </button>
        <button className={`tab-btn ${activeTab === 'engagements' ? 'active' : ''}`} onClick={() => setActiveTab('engagements')}>
          {t('engagementsTabLabel', engagementCount)}
        </button>
      </div>

      {loading ? (
        <div className="loading-spinner">{t('loading')}</div>
      ) : (
        <div className="tab-content active mt-4">

          {/* === AUDIT UNIVERSE TAB === */}
          {activeTab === 'universe' && (
            <UniverseTab
              universe={universe}
              count={universeCount}
              page={universePage}
              pageSize={universePageSize}
              onPageChange={setUniversePage}
              onPageSizeChange={setUniversePageSize}
              dueForAudit={dueForAudit}
              onImport={openImportUniverse}
              onExport={() => setShowUniverseExportModal(true)}
              onAdd={openAddUniverse}
              onEdit={openEditUniverse}
            />
          )}

          {/* === ANNUAL PLANS TAB === */}
          {activeTab === 'plans' && (
            <PlansTab
              plans={plans}
              count={plansCount}
              page={plansPage}
              pageSize={plansPageSize}
              onPageChange={setPlansPage}
              onPageSizeChange={setPlansPageSize}
              focusPlanId={focusPlanId}
              onAdd={openAddPlan}
              onEdit={openEditPlan}
              onSubmit={handleSubmitPlan}
              onApprove={handleApprovePlan}
            />
          )}

          {/* === ENGAGEMENTS TAB === */}
          {activeTab === 'engagements' && (
            <EngagementsTab
              engagements={engagements}
              count={engagementCount}
              page={engagementsPage}
              pageSize={engagementsPageSize}
              onPageChange={setEngagementsPage}
              onPageSizeChange={setEngagementsPageSize}
              focusEngagementId={focusEngagementId}
              onAdd={openAddEngagement}
              onEdit={openEditEngagement}
              onManageTeam={openTeamModal}
              onStatusChange={handleUpdateEngagementStatus}
            />
          )}

        </div>
      )}

      {/* ==================== MODALS ==================== */}

      {/* Universe Entity Modal */}
      <UniverseFormModal
        isOpen={showUniverseModal}
        onClose={closeUniverseModal}
        item={editingUniverse}
        projects={projects}
        ppmDepartmentId={ppmDepartmentId}
        setReferences={setReferences}
        onSaved={handleUniverseSaved}
      />

      {/* Universe Export Modal */}
      <UniverseExportModal
        isOpen={showUniverseExportModal}
        onClose={() => setShowUniverseExportModal(false)}
      />

      {/* Universe Import Modal */}
      <UniverseImportModal
        isOpen={showUniverseImportModal}
        onClose={closeImportUniverse}
        onImported={handleUniverseImported}
      />

      {/* Annual Plan Modal */}
      <PlanFormModal
        isOpen={showPlanModal}
        onClose={closePlanModal}
        plan={editingPlan}
        onSaved={handlePlanSaved}
      />

      {/* Engagement Modal — with Lead Auditor, Supervisor & Days */}
      <EngagementFormModal
        isOpen={showEngagementModal}
        onClose={closeEngagementModal}
        engagement={editingEngagement}
        users={allUsers}
        plansCatalog={plansCatalog}
        universeCatalog={universeCatalog}
        onSaved={handleEngagementSaved}
      />

      {/* Team Assignment Modal */}
      <TeamModal
        isOpen={Boolean(showTeamModal && selectedEngagementId)}
        onClose={closeTeamModal}
        engagementId={selectedEngagementId}
        engagement={selectedEngagement}
        users={allUsers}
      />

    </div>
  );
}

export default PlanningPage;
