import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { planningApi, usersApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { usePermissions } from '../../hooks/usePermissions';
import { useI18n } from '../../context/I18nContext';
import { localizedName } from '../../utils/localizedName';
import { validateForm, validators, hasErrors } from '../../utils/validation';
import Modal from '../../components/ui/Modal';
import Badge from '../../components/ui/Badge';
import Spinner from '../../components/ui/Spinner';
import EmptyState from '../../components/ui/EmptyState';
import FormField from '../../components/ui/FormField';
import Pagination from '../../components/ui/Pagination';
import OrgUnitSelect from '../../components/ui/OrgUnitSelect';
import { useOrgUnits } from '../../hooks/useOrgUnits';
import { Calendar, Plus, Users, Shield, Clock, Pencil, Upload, Download } from 'lucide-react';

// Mirrors AuditEngagement.STATUS_CHOICES. The server rejects anything else, and
// refuses `completed` outright while the engagement still holds a finding that
// is not resolved or closed — see BLOCKS_COMPLETION in audit_planning/views.py.
const ENGAGEMENT_STATUSES = [
  'planned', 'in_progress', 'fieldwork', 'reporting', 'completed', 'cancelled',
];

function PlanningPage() {
  const toast = useToast();
  const { t, lang } = useI18n();
  const { canWriteAudit, canApprovePlans } = usePermissions();

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

  const [formErrors, setFormErrors] = useState({});
  // The three arrays below hold ONLY the current page slice of each tab. The
  // per-tab count/page/pageSize/nonce drive server-side pagination (same pattern
  // as AuditTrailPage). The modal dropdowns must NOT read these slices — they use
  // the full universeCatalog/plansCatalog reference sets loaded at page_size 1000.
  const [universe, setUniverse] = useState([]);
  const [plans, setPlans] = useState([]);
  const [engagements, setEngagements] = useState([]);
  const [universeCount, setUniverseCount] = useState(0);
  const [plansCount, setPlansCount] = useState(0);
  // Server total shown in the Engagements tab label (never the slice length).
  const [engagementCount, setEngagementCount] = useState(0);
  const [universePage, setUniversePage] = useState(1);
  const [universePageSize, setUniversePageSize] = useState(25);
  const [universeNonce, setUniverseNonce] = useState(0);
  const [plansPage, setPlansPage] = useState(1);
  const [plansPageSize, setPlansPageSize] = useState(25);
  const [plansNonce, setPlansNonce] = useState(0);
  const [engagementsPage, setEngagementsPage] = useState(1);
  const [engagementsPageSize, setEngagementsPageSize] = useState(25);
  const [engagementsNonce, setEngagementsNonce] = useState(0);
  const [universeCatalog, setUniverseCatalog] = useState([]);
  const [plansCatalog, setPlansCatalog] = useState([]);
  const [loading, setLoading] = useState(true);
  const [allUsers, setAllUsers] = useState([]);
  const [dueForAudit, setDueForAudit] = useState({ items: [], count: 0, hasMore: false });

  // Form State
  const emptyUniverse = { name: '', code: '', category: 'system', risk_score: 3.5, audit_frequency: 'Annually', owner: '', department: '', status: 'active', last_audited: '' };
  const emptyPlan = { title: '', year: new Date().getFullYear(), plan_scope: 'directorate', directorate: '', total_budget_days: 0, start_date: '', end_date: '', description: '', objectives: '', scope: '', methodology: '' };
  const emptyEngagement = {
    title: '', plan: '', audit_universe: '', department: '',
    engagement_type: 'operational', risk_level: 'medium',
    planned_start: '', planned_end: '', planned_days: 0,
    lead_auditor: '', supervisor: ''
  };

  const [showUniverseModal, setShowUniverseModal] = useState(false);
  const [editingUniverseId, setEditingUniverseId] = useState(null);
  const [editingUniverseDeptName, setEditingUniverseDeptName] = useState('');
  const [newUniverse, setNewUniverse] = useState(emptyUniverse);

  // PPM project registry feeding the universe form's "PPM Project" dropdown,
  // shown when the entity's category is 'project'. Picking or adding a project
  // auto-fills the entity name/code and, when empty, the department (PPM node).
  const { units: orgUnits } = useOrgUnits();
  // PPM = EEU Projects Portfolio Management, a top-level Department (code PPM).
  const ppmUnit = orgUnits.find(u => String(u.code).toUpperCase() === 'PPM');
  const ppmDepartmentId = ppmUnit ? String(ppmUnit.id) : '';
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [showAddProject, setShowAddProject] = useState(false);
  const [newProject, setNewProject] = useState({ code: '', name: '' });
  const [projectErrors, setProjectErrors] = useState({});
  const [addingProject, setAddingProject] = useState(false);

  // Bulk import/export of the Audit Universe (Excel/CSV).
  const [showUniverseImportModal, setShowUniverseImportModal] = useState(false);
  const [showUniverseExportModal, setShowUniverseExportModal] = useState(false);
  const [importBusy, setImportBusy] = useState(false);
  const [importFile, setImportFile] = useState(null);
  const [importResult, setImportResult] = useState(null);

  const [showPlanModal, setShowPlanModal] = useState(false);
  const [editingPlanId, setEditingPlanId] = useState(null);
  const [newPlan, setNewPlan] = useState(emptyPlan);

  const [showEngagementModal, setShowEngagementModal] = useState(false);
  const [editingEngagementId, setEditingEngagementId] = useState(null);
  const [editingEngagementDeptName, setEditingEngagementDeptName] = useState('');
  const [newEngagement, setNewEngagement] = useState(emptyEngagement);

  // Team Member Assignment State
  const [showTeamModal, setShowTeamModal] = useState(false);
  const [selectedEngagement, setSelectedEngagement] = useState(null);
  const [teamMember, setTeamMember] = useState({ user: '', role: 'member', allocated_days: 0 });
  const [engagementTeam, setEngagementTeam] = useState([]);

  // Tab slices and reference data are loaded by the per-tab effects defined
  // below their loaders. Each tab keeps its own page state, so switching tabs
  // never loses the user's place.

  // Scroll the deep-linked record into view once the fetch has landed —
  // otherwise the notification drops the user on the right tab with no
  // indication of which row they were meant to look at.
  useEffect(() => {
    if (loading || !deepLinkKey) return;
    const el = document.getElementById(deepLinkKey);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [loading, activeTab, deepLinkKey]);

  // Guard flags so the deep-link page scans below run at most once per link
  // (the resulting setXPage(...) refetches through the effect, which would
  // otherwise re-enter the scan forever).
  const plansLocateDone = useRef(false);
  const engagementsLocateDone = useRef(false);

  // Per-tab server-paginated loaders. Each mirrors AuditTrailPage: fetch the
  // page, store the slice + the server total, and clamp the page if a mutation
  // shrank the list. Bumping the tab's nonce forces a refetch even when the
  // page/pageSize are unchanged.
  const fetchUniverseTab = async () => {
    setLoading(true);
    try {
      const res = await planningApi.getUniverse({ page: universePage, page_size: universePageSize });
      setUniverse(res.items || []);
      setUniverseCount(res.count || 0);
      const last = Math.max(1, Math.ceil((res.count || 0) / universePageSize));
      if (universePage > last) setUniversePage(last);
    } catch (err) {
      toast.error('Failed to load planning data');
    } finally {
      setLoading(false);
    }
  };

  const fetchPlansTab = async () => {
    setLoading(true);
    try {
      const res = await planningApi.getPlans({ page: plansPage, page_size: plansPageSize });
      setPlans(res.items || []);
      setPlansCount(res.count || 0);
      const last = Math.max(1, Math.ceil((res.count || 0) / plansPageSize));
      if (plansPage > last) setPlansPage(last);
      // Deep link (?plan=N): if the target plan is on a later page, jump to it.
      if (focusPlanId
        && !res.items.some(p => String(p.id) === String(focusPlanId))
        && res.hasMore && !plansLocateDone.current) {
        plansLocateDone.current = true;
        const cap = Math.min(last, 200);
        for (let p = plansPage + 1; p <= cap; p++) {
          const r = await planningApi.getPlans({ page: p, page_size: plansPageSize });
          if (r.items.some(p => String(p.id) === String(focusPlanId))) { setPlansPage(p); break; }
          if (!r.hasMore) break;
        }
      }
    } catch (err) {
      toast.error('Failed to load planning data');
    } finally {
      setLoading(false);
    }
  };

  const fetchEngagementsTab = async () => {
    setLoading(true);
    try {
      const res = await planningApi.getEngagements({ page: engagementsPage, page_size: engagementsPageSize });
      setEngagements(res.items || []);
      setEngagementCount(res.count || 0);
      const last = Math.max(1, Math.ceil((res.count || 0) / engagementsPageSize));
      if (engagementsPage > last) setEngagementsPage(last);
      // Deep link (?engagement=N): same one-shot jump as the plans tab.
      if (focusEngagementId
        && !res.items.some(e => String(e.id) === String(focusEngagementId))
        && res.hasMore && !engagementsLocateDone.current) {
        engagementsLocateDone.current = true;
        const cap = Math.min(last, 200);
        for (let p = engagementsPage + 1; p <= cap; p++) {
          const r = await planningApi.getEngagements({ page: p, page_size: engagementsPageSize });
          if (r.items.some(e => String(e.id) === String(focusEngagementId))) { setEngagementsPage(p); break; }
          if (!r.hasMore) break;
        }
      }
    } catch (err) {
      toast.error('Failed to load planning data');
    } finally {
      setLoading(false);
    }
  };

  // Reference data that never paginates: users (lead/supervisor pickers), the
  // PPM project registry, the due-for-re-audit badge, and the FULL universe/plan
  // catalogs that back the modal dropdowns (the arrays in state are slices).
  const fetchReferences = async () => {
    try {
      const [usersRes, projectsRes, dueRes, univCatRes, plansCatRes] = await Promise.all([
        usersApi.getUsers(),
        planningApi.getProjects(),
        planningApi.getDueForReAudit(),
        planningApi.getUniverse(),
        planningApi.getPlans(),
      ]);
      setAllUsers(usersRes || []);
      setProjects(projectsRes || []);
      setDueForAudit(dueRes || { items: [], count: 0, hasMore: false });
      setUniverseCatalog(univCatRes.items || []);
      setPlansCatalog(plansCatRes.items || []);
    } catch (err) {
      toast.error('Failed to load planning data');
    }
  };

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

  useEffect(() => {
    fetchUniverseTab();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [universePage, universePageSize, universeNonce]);

  useEffect(() => {
    fetchPlansTab();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plansPage, plansPageSize, plansNonce]);

  useEffect(() => {
    fetchEngagementsTab();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engagementsPage, engagementsPageSize, engagementsNonce]);

  useEffect(() => {
    fetchReferences();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const auditors = allUsers.filter(u => u.role === 'auditor' || u.role === 'audit_manager');
  const supervisors = allUsers.filter(u => u.role === 'supervisor' || u.role === 'audit_manager');

  // True once the department picker resolves to the PPM chief office — reveals
  // the "PPM Project" dropdown just like category === 'project' does.
  const ppmDepartmentSelected = !!(ppmDepartmentId && newUniverse.department &&
    String(newUniverse.department) === ppmDepartmentId);

  const openAddUniverse = () => {
    setEditingUniverseId(null);
    setNewUniverse(emptyUniverse);
    setSelectedProject(null);
    setShowAddProject(false);
    setNewProject({ code: '', name: '' });
    setProjectErrors({});
    setShowUniverseModal(true);
  };

  const openEditUniverse = (item) => {
    setEditingUniverseId(item.id);
    // department_name is tracked separately from the form payload so the picker
    // can still name a retired unit, which the org tree omits.
    setEditingUniverseDeptName(localizedName(lang, item.department_name, item.department_name_am) || '');
    setNewUniverse({
      name: item.name || '', code: item.code || '', category: item.category || 'system',
      risk_score: item.risk_score ?? 3.5, audit_frequency: item.audit_frequency || 'Annually',
      owner: item.owner || '', department: item.department || '', status: item.status || 'active',
      last_audited: item.last_audited || '',
    });
    // For a project-category row, preselect the registry entry whose code/name
    // matches (there is no FK, so this is a best-effort match); department keeps
    // whatever the row already stores.
    if (item.category === 'project') {
      const match = matchRegistryProject(item.name, item.code);
      setSelectedProject(match || null);
    } else {
      setSelectedProject(null);
    }
    setShowAddProject(false);
    setNewProject({ code: '', name: '' });
    setProjectErrors({});
    setShowUniverseModal(true);
  };

  const closeUniverseModal = () => {
    setShowUniverseModal(false);
    setEditingUniverseId(null);
    setEditingUniverseDeptName('');
    setNewUniverse(emptyUniverse);
    setSelectedProject(null);
    setShowAddProject(false);
    setNewProject({ code: '', name: '' });
    setProjectErrors({});
  };

  // Best-effort match of a saved registry project to a universe row (there is no
  // FK): code match first, then a case-insensitive name match.
  const matchRegistryProject = (name, code) =>
    projects.find(p => p.code && code && p.code === code) ||
    projects.find(p => p.name && name && String(p.name).trim().toLowerCase() === String(name).trim().toLowerCase()) ||
    null;

  const handleSelectProject = (id) => {
    if (!id) {
      setSelectedProject(null);
      return;
    }
    const project = projects.find(p => String(p.id) === String(id));
    if (!project) return;
    setSelectedProject(project);
    setNewUniverse(prev => ({
      ...prev,
      name: project.name,
      // Fill the Unique Code only when it is still blank: registry codes and
      // universe codes are separate namespaces, and a reused code would 400 on
      // the universe table's unique constraint.
      code: prev.code || project.code || '',
      department: prev.department || ppmDepartmentId || '',
    }));
  };

  const handleAddProject = async () => {
    if (!canWriteAudit) return;
    const errors = validateForm(newProject, {
      code: { validators: [validators.required, validators.code] },
      name: { validators: [validators.required, validators.minLength(3)] },
    });
    if (hasErrors(errors)) {
      setProjectErrors(errors);
      return;
    }
    setProjectErrors({});
    setAddingProject(true);
    try {
      const created = await planningApi.createProject({
        code: newProject.code.trim(),
        name: newProject.name.trim(),
      });
      setProjects(prev => [created, ...prev]);
      setSelectedProject(created);
      setNewUniverse(prev => ({
        ...prev,
        name: created.name,
        code: prev.code || created.code || '',
        department: prev.department || ppmDepartmentId || '',
      }));
      setShowAddProject(false);
      setNewProject({ code: '', name: '' });
      toast.success('Project added to the registry');
    } catch (err) {
      const msg = typeof err.response?.data === 'object'
        ? JSON.stringify(err.response.data)
        : 'Failed to add project';
      toast.error(msg);
    } finally {
      setAddingProject(false);
    }
  };

  const handleSaveUniverse = async (e) => {
    e.preventDefault();
    // Validate form
    const errors = validateForm(newUniverse, {
      name: { validators: [validators.required, validators.minLength(3)] },
      code: { validators: [validators.required, validators.code] },
      risk_score: { validators: [validators.required, validators.min(1), validators.max(5)] },
    });
    if (hasErrors(errors)) {
      setFormErrors(errors);
      return;
    }
    setFormErrors({});
    try {
      const payload = { ...newUniverse };
      if (!payload.department) delete payload.department;
      if (!payload.last_audited) delete payload.last_audited;
      if (editingUniverseId) {
        await planningApi.updateUniverse(editingUniverseId, payload);
        toast.success('Audit universe item updated successfully');
      } else {
        await planningApi.createUniverse(payload);
        toast.success('Audit universe item created successfully');
      }
      // A risk_score/name edit can move the row across page boundaries under
      // -risk_score ordering; the catalog and re-audit badge also need to stay
      // truthful — refetch rather than mutate the slice in place.
      reloadTab('universe', { resetPage: !editingUniverseId });
      fetchReferences();
      closeUniverseModal();
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : 'Failed to save universe item';
      toast.error(msg);
    }
  };

  const openImportUniverse = () => {
    setImportFile(null);
    setImportResult(null);
    setShowUniverseImportModal(true);
  };

  const closeImportUniverse = () => {
    setShowUniverseImportModal(false);
    setImportFile(null);
    setImportResult(null);
    setImportBusy(false);
  };

  const handleExportUniverse = async (format) => {
    try {
      await planningApi.exportUniverse(format);
      toast.success(format === 'csv' ? 'Audit universe exported as CSV' : 'Audit universe exported as Excel');
      setShowUniverseExportModal(false);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail
        : 'Failed to export audit universe';
      toast.error(msg);
    }
  };

  const handleImportUniverse = async (e) => {
    e.preventDefault();
    if (!importFile) {
      toast.warning('Choose an .xlsx or .csv file to import');
      return;
    }
    setImportBusy(true);
    setImportResult(null);
    try {
      const result = await planningApi.importUniverse(importFile);
      setImportResult(result);
      if (result.created || result.updated) {
        toast.success(`Import complete: ${result.created} created, ${result.updated} updated`);
      } else {
        toast.info('No rows were added or changed by the import');
      }
      if (result.errors?.length) {
        toast.error(`${result.errors.length} row(s) could not be imported`);
      }
      // Imports shift the due-for-re-audit badge and the modal catalogs too,
      // so refresh the references alongside the universe slice.
      reloadTab('universe', { resetPage: true });
      fetchReferences();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : 'Failed to import audit universe';
      toast.error(msg);
      setImportResult({ created: 0, updated: 0, errors: [{ row: null, message: msg }] });
    } finally {
      setImportBusy(false);
    }
  };

  const openAddPlan = () => {
    setEditingPlanId(null);
    setNewPlan(emptyPlan);
    setShowPlanModal(true);
  };

  const openEditPlan = (plan) => {
    setEditingPlanId(plan.id);
    setNewPlan({
      title: plan.title || '', year: plan.year || new Date().getFullYear(),
      plan_scope: plan.plan_scope || 'directorate', directorate: plan.directorate || '',
      total_budget_days: plan.total_budget_days ?? 0, start_date: plan.start_date || '',
      end_date: plan.end_date || '', description: plan.description || '',
      objectives: plan.objectives || '', scope: plan.scope || '',
      methodology: plan.methodology || '',
    });
    setShowPlanModal(true);
  };

  const closePlanModal = () => {
    setShowPlanModal(false);
    setEditingPlanId(null);
    setNewPlan(emptyPlan);
  };

  const handleSavePlan = async (e) => {
    e.preventDefault();
    // Validate form
    const errors = validateForm(newPlan, {
      title: { validators: [validators.required, validators.minLength(5)] },
      year: { validators: [validators.required, validators.integer] },
      plan_scope: { validators: [validators.required] },
      total_budget_days: { validators: [validators.required, validators.integer, validators.min(0)] },
      start_date: { validators: [validators.required, validators.date] },
      end_date: {
        validators: [validators.required, validators.date],
        crossField: (values) => {
          if (!values.start_date || !values.end_date) return {};
          if (new Date(values.end_date) < new Date(values.start_date)) {
            return { end_date: 'End date must be after start date.' };
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
    try {
      const payload = { ...newPlan };
      if (!payload.directorate) delete payload.directorate;
      if (editingPlanId) {
        await planningApi.updatePlan(editingPlanId, payload);
        toast.success('Annual plan updated successfully');
      } else {
        await planningApi.createPlan(payload);
        toast.success('Annual plan created successfully');
      }
      // Year/status edits can reorder the -year slice; refresh plans and the
      // full plans catalog that backs the engagement modal's plan picker.
      reloadTab('plans', { resetPage: !editingPlanId });
      fetchReferences();
      closePlanModal();
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : 'Failed to save plan';
      toast.error(msg);
    }
  };

  const openAddEngagement = () => {
    setEditingEngagementId(null);
    setNewEngagement(emptyEngagement);
    setShowEngagementModal(true);
  };

  const openEditEngagement = (eng) => {
    setEditingEngagementId(eng.id);
    setEditingEngagementDeptName(localizedName(lang, eng.department_name, eng.department_name_am) || '');
    setNewEngagement({
      title: eng.title || '', plan: eng.plan || '', audit_universe: eng.audit_universe || '',
      department: eng.department || '', engagement_type: eng.engagement_type || 'operational',
      risk_level: eng.risk_level || 'medium', planned_start: eng.planned_start || '',
      planned_end: eng.planned_end || '', planned_days: eng.planned_days ?? 0,
      lead_auditor: eng.lead_auditor || '', supervisor: eng.supervisor || '',
    });
    setShowEngagementModal(true);
  };

  const closeEngagementModal = () => {
    setShowEngagementModal(false);
    setEditingEngagementId(null);
    setEditingEngagementDeptName('');
    setNewEngagement(emptyEngagement);
  };

  const handleSaveEngagement = async (e) => {
    e.preventDefault();
    // Validate form
    const errors = validateForm(newEngagement, {
      title: { validators: [validators.required, validators.minLength(5)] },
      plan: { validators: [validators.required] },
      planned_days: { validators: [validators.integer, validators.min(0)] },
      planned_start: { validators: [validators.required, validators.date] },
      planned_end: {
        validators: [validators.required, validators.date],
        crossField: (values) => {
          if (!values.planned_start || !values.planned_end) return {};
          if (new Date(values.planned_end) < new Date(values.planned_start)) {
            return { planned_end: 'End date must be after start date.' };
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
    try {
      const payload = { ...newEngagement };
      if (!payload.department) delete payload.department;
      if (!payload.audit_universe) delete payload.audit_universe;
      if (!payload.lead_auditor) delete payload.lead_auditor;
      if (!payload.supervisor) delete payload.supervisor;
      if (editingEngagementId) {
        await planningApi.updateEngagement(editingEngagementId, payload);
        toast.success('Audit engagement updated successfully');
      } else {
        await planningApi.createEngagement(payload);
        toast.success('Audit engagement created successfully');
      }
      reloadTab('engagements', { resetPage: !editingEngagementId });
      closeEngagementModal();
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : 'Failed to save engagement';
      toast.error(msg);
    }
  };

  const handleSubmitPlan = async (planId) => {
    try {
      await planningApi.submitPlan(planId);
      toast.success('Plan submitted for approval successfully!');
      reloadTab('plans');
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : 'Failed to submit plan';
      toast.error(msg);
    }
  };

  const handleApprovePlan = async (planId) => {
    try {
      await planningApi.approvePlan(planId);
      toast.success('Plan approved successfully!');
      reloadTab('plans');
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : 'Failed to approve plan';
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
      toast.success(`Engagement status set to ${nextStatus.replace('_', ' ')}`);
      reloadTab('engagements');
    } catch (err) {
      const data = err.response?.data;
      const msg = data?.detail
        || (typeof data === 'object' ? JSON.stringify(data) : 'Failed to update engagement status');
      toast.error(msg);
      // Re-fetch so the select is repainted from the server's actual value.
      reloadTab('engagements');
    }
  };

  const openTeamModal = async (engagement) => {
    setSelectedEngagement(engagement);
    setShowTeamModal(true);
    setTeamMember({ user: '', role: 'member', allocated_days: 0 });
    // Fetch current team for this engagement
    try {
      const res = await planningApi.getEngagement(engagement.id);
      setEngagementTeam(res.team_members || []);
    } catch (err) {
      toast.error('Failed to load engagement team members');
    }
  };

  const handleAddTeamMember = async (e) => {
    e.preventDefault();
    try {
      await planningApi.addTeamMember(selectedEngagement.id, teamMember);
      toast.success('Team member assigned successfully!');
      // Refresh team
      const res = await planningApi.getEngagement(selectedEngagement.id);
      setEngagementTeam(res.team_members || []);
      setTeamMember({ user: '', role: 'member', allocated_days: 0 });
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : 'Failed to assign team member';
      toast.error(msg);
    }
  };

  return (
    <div className="planning-view">
      <div className="tab-container">
        <button className={`tab-btn ${activeTab === 'universe' ? 'active' : ''}`} onClick={() => setActiveTab('universe')}>
          Audit Universe
        </button>
        <button className={`tab-btn ${activeTab === 'plans' ? 'active' : ''}`} onClick={() => setActiveTab('plans')}>
          Annual Audit Plans
        </button>
        <button className={`tab-btn ${activeTab === 'engagements' ? 'active' : ''}`} onClick={() => setActiveTab('engagements')}>
          Engagements ({engagementCount})
        </button>
      </div>

      {loading ? (
        <div className="loading-spinner">{t('loading')}</div>
      ) : (
        <div className="tab-content active mt-4">

          {/* === AUDIT UNIVERSE TAB === */}
          {activeTab === 'universe' && (
            <div className="card">
              <div className="card-header justify-between">
                <div>
                  <h3>EEU Risk-Weighted Audit Universe</h3>
                  <p className="card-subtitle">Complete directory of all auditable operational nodes and systems</p>
                </div>
                <div className="flex gap-2">
                  {dueForAudit.count > 0 && (
                    <span className="badge badge-danger flex items-center gap-1">
                      <Clock size={13} /> {dueForAudit.count} due for re-audit
                    </span>
                  )}
                  {canWriteAudit && (
                    <>
                      <button
                        className="btn btn-outline flex items-center gap-2"
                        onClick={openImportUniverse}
                        title="Bulk-import the audit universe from an Excel or CSV file"
                      >
                        <Upload size={16} /> Import
                      </button>
                      <button
                        className="btn btn-outline flex items-center gap-2"
                        onClick={() => setShowUniverseExportModal(true)}
                        title="Download the audit universe as Excel or CSV"
                      >
                        <Download size={16} /> Export
                      </button>
                      <button className="btn btn-primary flex items-center gap-2" onClick={openAddUniverse}>
                        <Plus size={16} /> Add Entity
                      </button>
                    </>
                  )}
                </div>
              </div>
              <div className="table-responsive">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Code</th>
                      <th>Entity Name</th>
                      <th>Category</th>
                      <th>Department</th>
                      <th>Risk Score</th>
                      <th>Frequency</th>
                      <th>Last Audited</th>
                      <th>Re-Audit</th>
                      <th>Status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {universe.map(item => (
                      <tr key={item.id}>
                        <td><strong>{item.code}</strong></td>
                        <td>{item.name}</td>
                        <td><span className="badge badge-outline">{item.category?.toUpperCase()}</span></td>
                        <td>{localizedName(lang, item.department_name, item.department_name_am) || 'N/A'}</td>
                        <td>
                          <span className={`risk-tag ${item.risk_score >= 4 ? 'critical' : item.risk_score >= 3 ? 'high' : 'medium'}`}>
                            {item.risk_score}
                          </span>
                        </td>
                        <td>{item.audit_frequency}</td>
                        <td>{item.last_audited || 'Never'}</td>
                        <td>
                          {item.due_for_re_audit ? (
                            <span className="badge badge-danger">Due</span>
                          ) : (
                            <span className="badge badge-success">OK</span>
                          )}
                        </td>
                        <td>
                          <span className={`badge ${item.status === 'active' ? 'badge-success' : 'badge-warning'}`}>
                            {item.status}
                          </span>
                        </td>
                        <td>
                          {canWriteAudit && (
                            <button className="btn btn-sm btn-outline flex items-center gap-1" onClick={() => openEditUniverse(item)}>
                              <Pencil size={13} /> Edit
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <Pagination
                page={universePage}
                pageCount={Math.max(1, Math.ceil(universeCount / universePageSize))}
                totalCount={universeCount}
                onPageChange={setUniversePage}
                pageSize={universePageSize}
                onPageSizeChange={setUniversePageSize}
                showPageSize
              />
            </div>
          )}

          {/* === ANNUAL PLANS TAB === */}
          {activeTab === 'plans' && (
            <div className="card">
              <div className="card-header justify-between">
                <div>
                  <h3>Annual Audit Plans</h3>
                  <p className="card-subtitle">Active and historical approved annual audit schedules</p>
                </div>
                {canWriteAudit && (
                  <button className="btn btn-primary flex items-center gap-2" onClick={openAddPlan}>
                    <Plus size={16} /> Create Plan
                  </button>
                )}
              </div>
              <div className="plans-grid mt-4">
                {plans.map(plan => (
                  <div
                    key={plan.id}
                    id={`plan-${plan.id}`}
                    className={`plan-card${String(plan.id) === focusPlanId ? ' ring-2 ring-emerald-500' : ''}`}
                  >
                    <div className="plan-card-header">
                      <h4>{plan.title}</h4>
                      <span className={`badge ${plan.status === 'approved' || plan.status === 'active' ? 'badge-success' : 'badge-info'}`}>
                        {plan.status.toUpperCase()}
                      </span>
                    </div>
                    <div className="plan-card-body">
                      <p>{plan.description}</p>
                      <div className="plan-meta-row">
                        <div><span>Year:</span><strong>{plan.year}</strong></div>
                        <div><span>Scope:</span><strong>{plan.plan_scope_display || plan.plan_scope}</strong></div>
                        <div><span>Directorate:</span><strong>{localizedName(lang, plan.directorate_name, plan.directorate_name_am) || '—'}</strong></div>
                        <div><span>Budget Days:</span><strong>{plan.total_budget_days} Days</strong></div>
                      </div>
                      <div className="plan-dates text-sm">
                        <span>Timeline:</span>
                        <strong>{plan.start_date} to {plan.end_date}</strong>
                      </div>
                      <div className="mt-4 flex gap-2 border-t pt-3 border-border-color">
                        {canWriteAudit && (
                          <button className="btn btn-sm btn-outline flex items-center gap-1" onClick={() => openEditPlan(plan)}>
                            <Pencil size={13} /> Edit
                          </button>
                        )}
                        {plan.status === 'draft' && canWriteAudit && (
                          <button className="btn btn-sm btn-outline flex-1" onClick={() => handleSubmitPlan(plan.id)}>
                            Submit for Approval
                          </button>
                        )}
                        {plan.status === 'submitted' && canApprovePlans && (
                          <button className="btn btn-sm btn-primary flex-1" onClick={() => handleApprovePlan(plan.id)}>
                            Approve Plan
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <Pagination
                page={plansPage}
                pageCount={Math.max(1, Math.ceil(plansCount / plansPageSize))}
                totalCount={plansCount}
                onPageChange={setPlansPage}
                pageSize={plansPageSize}
                onPageSizeChange={setPlansPageSize}
                showPageSize
              />
            </div>
          )}

          {/* === ENGAGEMENTS TAB === */}
          {activeTab === 'engagements' && (
            <div className="card">
              <div className="card-header justify-between">
                <div>
                  <h3>Audit Engagements</h3>
                  <p className="card-subtitle">Individual operational audits configured under current plans</p>
                </div>
                {canWriteAudit && (
                  <button className="btn btn-primary flex items-center gap-2" onClick={openAddEngagement}>
                    <Plus size={16} /> Schedule Engagement
                  </button>
                )}
              </div>
              <div className="table-responsive">
                <table className="table engagements-table">
                  <thead>
                    <tr>
                      <th>Ref Number</th>
                      <th>Audit Title</th>
                      <th>Type</th>
                      <th>Lead Auditor</th>
                      <th>Supervisor</th>
                      <th>Days</th>
                      <th>Timeline</th>
                      <th>Risk Level</th>
                      <th>Status</th>
                      <th>Team</th>
                    </tr>
                  </thead>
                  <tbody>
                    {engagements.map(eng => (
                      <tr
                        key={eng.id}
                        id={`engagement-${eng.id}`}
                        className={String(eng.id) === focusEngagementId ? 'ring-2 ring-emerald-500' : undefined}
                      >
                        <td><strong>{eng.engagement_number}</strong></td>
                        <td>{eng.title}</td>
                        <td><span className="badge badge-outline">{eng.engagement_type?.toUpperCase()}</span></td>
                        <td>
                          {eng.lead_auditor_name ? (
                            <span className="flex items-center gap-1">
                              <Users size={13} className="text-primary" />
                              {eng.lead_auditor_name}
                            </span>
                          ) : <span className="text-muted">—</span>}
                        </td>
                        <td>
                          {eng.supervisor_name ? (
                            <span className="flex items-center gap-1">
                              <Shield size={13} className="text-warning" />
                              {eng.supervisor_name}
                            </span>
                          ) : <span className="text-muted">—</span>}
                        </td>
                        <td>
                          <span className="flex items-center gap-1">
                            <Clock size={13} />
                            {eng.planned_days || 0}d
                          </span>
                        </td>
                        <td>{eng.planned_start} – {eng.planned_end}</td>
                        <td>
                          <span className={`risk-tag ${eng.risk_level === 'critical' ? 'critical' : eng.risk_level === 'high' ? 'high' : 'medium'}`}>
                            {eng.risk_level?.toUpperCase()}
                          </span>
                        </td>
                        <td>
                          <span className={`badge ${eng.status === 'in_progress' ? 'badge-info' : eng.status === 'fieldwork' ? 'badge-warning' : 'badge-success'}`}>
                            {eng.status?.replace('_', ' ')}
                          </span>
                        </td>
                        <td>
                          <div className="flex gap-1">
                            <button className="btn btn-sm btn-outline flex items-center gap-1" onClick={() => openEditEngagement(eng)}>
                              <Pencil size={13} /> Edit
                            </button>
                            <button className="btn btn-sm btn-outline" onClick={() => openTeamModal(eng)}>
                              Assign
                            </button>
                            {canWriteAudit && (
                              <select
                                className="form-input"
                                aria-label={`Status for ${eng.engagement_number || eng.title}`}
                                value={eng.status || 'planned'}
                                onChange={(e) => handleUpdateEngagementStatus(eng.id, e.target.value)}
                              >
                                {ENGAGEMENT_STATUSES.map((s) => (
                                  <option key={s} value={s}>{s.replace('_', ' ')}</option>
                                ))}
                              </select>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <Pagination
                page={engagementsPage}
                pageCount={Math.max(1, Math.ceil(engagementCount / engagementsPageSize))}
                totalCount={engagementCount}
                onPageChange={setEngagementsPage}
                pageSize={engagementsPageSize}
                onPageSizeChange={setEngagementsPageSize}
                showPageSize
              />
            </div>
          )}

        </div>
      )}

      {/* ==================== MODALS ==================== */}

      {/* Universe Entity Modal */}
      <Modal
        isOpen={showUniverseModal}
        onClose={closeUniverseModal}
        title={editingUniverseId ? 'Edit Auditable Entity' : 'Add Auditable Entity'}
        size="lg"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={closeUniverseModal}>Cancel</button>
            {/* `form=` because Modal renders the footer as a sibling of its
                children, so the submit button sits outside the <form>. */}
            <button type="submit" form="universe-form" className="btn btn-primary">
              {editingUniverseId ? 'Save Changes' : 'Save Entity'}
            </button>
          </>
        )}
      >
        <form id="universe-form" onSubmit={handleSaveUniverse}>
          <div className="form-group">
            <label className="form-label" htmlFor="universe_name">Entity Name</label>
            <input id="universe_name" type="text" className="form-control" placeholder="e.g. Substation Asset Management"
              value={newUniverse.name} onChange={(e) => setNewUniverse({ ...newUniverse, name: e.target.value })} required />
          </div>
          <div className="form-group-row">
            <div className="form-group">
              <label className="form-label" htmlFor="universe_code">Unique Code</label>
              <input id="universe_code" type="text" className="form-control" placeholder="e.g. UNIV-DIST-06"
                value={newUniverse.code} onChange={(e) => setNewUniverse({ ...newUniverse, code: e.target.value })} required />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="universe_category">Category</label>
              <select id="universe_category" className="form-control" value={newUniverse.category} onChange={(e) => setNewUniverse({ ...newUniverse, category: e.target.value })}>
                <option value="department">Department</option>
                <option value="process">Business Process</option>
                <option value="system">IT System</option>
                <option value="project">Project</option>
                <option value="subsidiary">Subsidiary</option>
                <option value="regulation">Regulatory Area</option>
              </select>
            </div>
          </div>
          {/* PPM project registry — shown for project-category entities and for
              entities whose department is the PPM chief office. Picking or adding
              a project fills the entity name/code and, when blank, the department
              (EEU Projects Portfolio Management). The mini-form is an inline panel
              (Modal is not nest-safe) inside universe-form; all its buttons are
              type="button" so it never submits the entity form. */}
          {(newUniverse.category === 'project' || ppmDepartmentSelected) && (
            <div className="form-group">
              <label className="form-label" htmlFor="universe_ppm_project">PPM Project</label>
              <div className="flex items-center gap-2">
                <select
                  id="universe_ppm_project"
                  className="form-control flex-1 min-w-0"
                  value={selectedProject ? String(selectedProject.id) : ''}
                  onChange={(e) => handleSelectProject(e.target.value)}
                >
                  <option value="">Select a saved project…</option>
                  {projects.map(p => (
                    <option key={p.id} value={p.id}>{p.code} — {p.name}</option>
                  ))}
                </select>
                {canWriteAudit && (
                  <button
                    type="button"
                    className="btn btn-outline flex items-center gap-1"
                    onClick={() => setShowAddProject(v => !v)}
                    title="Register a new PPM project"
                    aria-expanded={showAddProject}
                  >
                    <Plus size={16} />
                    <span>Add</span>
                  </button>
                )}
              </div>
              {showAddProject && canWriteAudit && (
                <div className="mt-3 border border-border-color rounded-lg p-3">
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                    Register a new project — it is saved and offered in the dropdown next time.
                  </p>
                  <div className="form-group-row">
                    <div className="form-group">
                      <label className="form-label" htmlFor="project_code">Project Code</label>
                      <input id="project_code" type="text" className="form-control" placeholder="e.g. PRJ-SCADA-01"
                        value={newProject.code}
                        onChange={(e) => setNewProject({ ...newProject, code: e.target.value })}
                        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddProject(); } }} />
                      {projectErrors.code && <p className="form-error">{projectErrors.code}</p>}
                    </div>
                    <div className="form-group">
                      <label className="form-label" htmlFor="project_name">Project Name</label>
                      <input id="project_name" type="text" className="form-control" placeholder="e.g. SCADA Expansion"
                        value={newProject.name}
                        onChange={(e) => setNewProject({ ...newProject, name: e.target.value })}
                        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddProject(); } }} />
                      {projectErrors.name && <p className="form-error">{projectErrors.name}</p>}
                    </div>
                  </div>
                  <div className="mt-3 flex gap-2">
                    <button type="button" className="btn btn-primary" onClick={handleAddProject} disabled={addingProject}>
                      {addingProject ? 'Adding…' : 'Add Project'}
                    </button>
                    <button type="button" className="btn btn-outline" onClick={() => setShowAddProject(false)}>Cancel</button>
                  </div>
                </div>
              )}
            </div>
          )}
          <div className="form-group-row">
            <OrgUnitSelect
              idPrefix="universe_dept"
              label="Department / Directorate"
              value={newUniverse.department}
              onChange={(id) => setNewUniverse(prev => {
                // Picking the PPM chief office implies a project-managed entity,
                // so default the category to Project (only when it is unset).
                const isPpm = !!(id && ppmDepartmentId && String(id) === ppmDepartmentId);
                return {
                  ...prev,
                  department: id,
                  category: isPpm && prev.category !== 'project' ? 'project' : prev.category,
                };
              })}
              valueLabel={editingUniverseDeptName}
            />
            <div className="form-group">
              <label className="form-label" htmlFor="universe_risk_score">Initial Risk Score (1-5)</label>
              <input id="universe_risk_score" type="number" step="0.05" min="1" max="5" className="form-control"
                value={newUniverse.risk_score} onChange={(e) => setNewUniverse({ ...newUniverse, risk_score: parseFloat(e.target.value) })} required />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="universe_frequency">Audit Frequency</label>
              <select id="universe_frequency" className="form-control" value={newUniverse.audit_frequency} onChange={(e) => setNewUniverse({ ...newUniverse, audit_frequency: e.target.value })}>
                <option value="Annually">Annually</option>
                <option value="Bi-annually">Bi-annually</option>
                <option value="Tri-annually">Tri-annually</option>
              </select>
            </div>
          </div>
          <div className="form-group-row">
            <div className="form-group">
              <label className="form-label" htmlFor="universe_last_audited">Last Audited</label>
              <input id="universe_last_audited" type="date" className="form-control"
                value={newUniverse.last_audited} onChange={(e) => setNewUniverse({ ...newUniverse, last_audited: e.target.value })} />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="universe_status">Status</label>
              <select id="universe_status" className="form-control" value={newUniverse.status} onChange={(e) => setNewUniverse({ ...newUniverse, status: e.target.value })}>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
                <option value="under_review">Under Review</option>
              </select>
            </div>
          </div>
        </form>
      </Modal>

      {/* Universe Export Modal */}
      <Modal
        isOpen={showUniverseExportModal}
        onClose={() => setShowUniverseExportModal(false)}
        title="Export Audit Universe"
        subtitle="Download the full directory as a spreadsheet"
      >
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
          The exported file uses the same columns the import accepts, so you can
          edit it offline and re-import the changes later.
        </p>
        <div className="flex flex-col gap-2">
          <button className="btn btn-outline flex items-center gap-2" onClick={() => handleExportUniverse('xlsx')}>
            <Download size={16} /> Excel (.xlsx)
          </button>
          <button className="btn btn-outline flex items-center gap-2" onClick={() => handleExportUniverse('csv')}>
            <Download size={16} /> CSV
          </button>
        </div>
      </Modal>

      {/* Universe Import Modal */}
      <Modal
        isOpen={showUniverseImportModal}
        onClose={closeImportUniverse}
        title="Import Audit Universe"
        subtitle="Bulk-create or update universe entries from an Excel (.xlsx) or CSV file"
        footer={
          importResult ? (
            <button type="button" className="btn btn-primary" onClick={closeImportUniverse}>
              Close
            </button>
          ) : (
            <>
              <button type="button" className="btn btn-outline" onClick={closeImportUniverse}>
                Cancel
              </button>
              <button
                type="submit"
                form="universe-import-form"
                className="btn btn-primary flex items-center gap-2"
                disabled={importBusy}
              >
                {importBusy ? 'Importing…' : 'Import'}
              </button>
            </>
          )
        }
      >
        <form id="universe-import-form" onSubmit={handleImportUniverse}>
          {importResult ? (
            <div className="space-y-3">
              <div className="flex gap-2">
                <span className="badge badge-success">{importResult.created ?? 0} created</span>
                <span className="badge badge-info">{importResult.updated ?? 0} updated</span>
                <span className="badge badge-warning">{importResult.errors?.length ?? 0} errors</span>
              </div>
              {importResult.errors?.length > 0 && (
                <div className="max-h-64 overflow-auto border border-rose-200 dark:border-rose-900 rounded-lg p-3 text-xs">
                  <p className="font-semibold mb-2 text-rose-700 dark:text-rose-400">
                    Rows that could not be imported:
                  </p>
                  {importResult.errors.slice(0, 20).map((err, i) => (
                    <p key={i} className="mb-1 text-gray-700 dark:text-gray-300">
                      {err.row != null ? <span className="font-semibold">Row {err.row}: </span> : null}
                      {err.message}
                    </p>
                  ))}
                  {importResult.errors.length > 20 && (
                    <p className="text-gray-500 dark:text-gray-400">
                      …and {importResult.errors.length - 20} more
                    </p>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div>
              <p className="mb-3 text-sm text-gray-600 dark:text-gray-400">
                Rows are matched by their unique <strong>Code</strong>: an existing code
                updates that entry (blank cells keep the current value), and a new code
                creates one. Use <strong>Export</strong> to download a ready-made template,
                or create columns: code, name, category, department_code, directorate_code,
                description, owner, risk_score, audit_frequency, last_audited, status.
              </p>
              <label className="form-label" htmlFor="universe_import_file">Spreadsheet File</label>
              <input
                id="universe_import_file"
                type="file"
                accept=".xlsx,.csv"
                className="form-control"
                onChange={(e) => setImportFile(e.target.files?.[0] || null)}
              />
              {importBusy && <div className="loading-spinner mt-4" />}
            </div>
          )}
        </form>
      </Modal>

      {/* Annual Plan Modal */}
      <Modal
        isOpen={showPlanModal}
        onClose={closePlanModal}
        title={editingPlanId ? 'Edit Annual Audit Plan' : 'Create Annual Audit Plan'}
        size="lg"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={closePlanModal}>Cancel</button>
            <button type="submit" form="plan-form" className="btn btn-primary">
              {editingPlanId ? 'Save Changes' : 'Create Plan'}
            </button>
          </>
        )}
      >
        <form id="plan-form" onSubmit={handleSavePlan}>
          <div className="form-group">
            <label className="form-label" htmlFor="plan_title">Plan Title</label>
            <input id="plan_title" type="text" className="form-control" placeholder="e.g. FY 2026 Comprehensive Audit Plan"
              value={newPlan.title} onChange={(e) => setNewPlan({ ...newPlan, title: e.target.value })} required />
          </div>
          <div className="form-group-row">
            <div className="form-group">
              <label className="form-label" htmlFor="plan_year">Year</label>
              <input id="plan_year" type="number" className="form-control" value={newPlan.year}
                onChange={(e) => setNewPlan({ ...newPlan, year: parseInt(e.target.value) })} required />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="plan_scope">Plan Scope</label>
              <select id="plan_scope" className="form-control" value={newPlan.plan_scope}
                onChange={(e) => setNewPlan({ ...newPlan, plan_scope: e.target.value })} required>
                <option value="directorate">Directorate Plan</option>
                <option value="consolidated">EEU Consolidated Master Plan</option>
              </select>
            </div>
          </div>
          <OrgUnitSelect
            idPrefix="plan_directorate"
            label="Directorate"
            value={newPlan.directorate}
            onChange={(id) => setNewPlan({ ...newPlan, directorate: id })}
          />
          <div className="form-group-row">
            <div className="form-group">
              <label className="form-label" htmlFor="plan_budget_days">Budget Days</label>
              <input id="plan_budget_days" type="number" className="form-control" value={newPlan.total_budget_days}
                onChange={(e) => setNewPlan({ ...newPlan, total_budget_days: parseInt(e.target.value) })} />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="plan_start_date">Start Date</label>
              <input id="plan_start_date" type="date" className="form-control" value={newPlan.start_date}
                onChange={(e) => setNewPlan({ ...newPlan, start_date: e.target.value })} />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="plan_end_date">End Date</label>
              <input id="plan_end_date" type="date" className="form-control" value={newPlan.end_date}
                onChange={(e) => setNewPlan({ ...newPlan, end_date: e.target.value })} />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="plan_description">Description</label>
            <textarea id="plan_description" rows="2" className="form-control" value={newPlan.description}
              onChange={(e) => setNewPlan({ ...newPlan, description: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="plan_objectives">Objectives</label>
            <textarea id="plan_objectives" rows="2" className="form-control" placeholder="Overall goals of the audit plan"
              value={newPlan.objectives} onChange={(e) => setNewPlan({ ...newPlan, objectives: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="plan_scope_text">Scope</label>
            <textarea id="plan_scope_text" rows="2" className="form-control" placeholder="Entities, processes and systems covered"
              value={newPlan.scope} onChange={(e) => setNewPlan({ ...newPlan, scope: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="plan_methodology">Methodology</label>
            <textarea id="plan_methodology" rows="2" className="form-control" placeholder="Risk-based approach, sampling and techniques"
              value={newPlan.methodology} onChange={(e) => setNewPlan({ ...newPlan, methodology: e.target.value })} />
          </div>
        </form>
      </Modal>

      {/* Engagement Modal — with Lead Auditor, Supervisor & Days */}
      <Modal
        isOpen={showEngagementModal}
        onClose={closeEngagementModal}
        title={editingEngagementId ? 'Edit Audit Engagement' : 'Schedule Audit Engagement'}
        size="xl"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={closeEngagementModal}>Cancel</button>
            <button type="submit" form="engagement-form" className="btn btn-primary">
              {editingEngagementId ? 'Save Changes' : 'Schedule Engagement'}
            </button>
          </>
        )}
      >
        <form id="engagement-form" onSubmit={handleSaveEngagement}>
          <div className="form-group">
            <label className="form-label" htmlFor="engagement_title">Engagement Title</label>
            <input id="engagement_title" type="text" className="form-control" placeholder="e.g. Q1 Payroll Compliance Audit"
              value={newEngagement.title} onChange={(e) => setNewEngagement({ ...newEngagement, title: e.target.value })} required />
          </div>
          <div className="form-group-row">
            <div className="form-group">
              <label className="form-label" htmlFor="engagement_plan">Target Annual Plan</label>
              <select id="engagement_plan" className="form-control" value={newEngagement.plan}
                onChange={(e) => setNewEngagement({ ...newEngagement, plan: e.target.value })} required>
                <option value="">Select Plan...</option>
                {plansCatalog.map(p => (<option key={p.id} value={p.id}>{p.title}</option>))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="engagement_type">Engagement Type</label>
              <select id="engagement_type" className="form-control" value={newEngagement.engagement_type}
                onChange={(e) => setNewEngagement({ ...newEngagement, engagement_type: e.target.value })}>
                <option value="operational">Operational</option>
                <option value="financial">Financial</option>
                <option value="compliance">Compliance</option>
                <option value="it">IT Audit</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="engagement_risk_level">Risk Level</label>
              <select id="engagement_risk_level" className="form-control" value={newEngagement.risk_level}
                onChange={(e) => setNewEngagement({ ...newEngagement, risk_level: e.target.value })}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
          </div>

          {/* ★ Manager Section: Lead Auditor, Supervisor & Allocated Days */}
          <div className="form-section-divider">
            <span><Users size={14} /> Team Assignment</span>
          </div>
          <div className="form-group-row">
            <div className="form-group">
              <label className="form-label" htmlFor="engagement_lead_auditor">Lead Auditor</label>
              <select id="engagement_lead_auditor" className="form-control" value={newEngagement.lead_auditor}
                onChange={(e) => setNewEngagement({ ...newEngagement, lead_auditor: e.target.value })}>
                <option value="">Select Lead Auditor...</option>
                {auditors.map(u => (
                  <option key={u.id} value={u.id}>{u.full_name || `${u.first_name} ${u.last_name}`} ({u.employee_id})</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="engagement_supervisor">Supervisor</label>
              <select id="engagement_supervisor" className="form-control" value={newEngagement.supervisor}
                onChange={(e) => setNewEngagement({ ...newEngagement, supervisor: e.target.value })}>
                <option value="">Select Supervisor...</option>
                {supervisors.map(u => (
                  <option key={u.id} value={u.id}>{u.full_name || `${u.first_name} ${u.last_name}`} ({u.employee_id})</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="engagement_planned_days">Allocated Days</label>
              <input id="engagement_planned_days" type="number" min="0" className="form-control"
                placeholder="e.g. 10"
                value={newEngagement.planned_days}
                onChange={(e) => setNewEngagement({ ...newEngagement, planned_days: parseInt(e.target.value) || 0 })} />
            </div>
          </div>

          <div className="form-group-row">
            <div className="form-group">
              <label className="form-label" htmlFor="engagement_audit_universe">Audit Universe Node (Optional)</label>
              <select id="engagement_audit_universe" className="form-control" value={newEngagement.audit_universe}
                onChange={(e) => setNewEngagement({ ...newEngagement, audit_universe: e.target.value })}>
                <option value="">Select Entity...</option>
                {universeCatalog.map(u => (<option key={u.id} value={u.id}>{u.code} - {u.name}</option>))}
              </select>
            </div>
            <OrgUnitSelect
              idPrefix="engagement_dept"
              label="Department"
              value={newEngagement.department}
              onChange={(id) => setNewEngagement({ ...newEngagement, department: id })}
              valueLabel={editingEngagementDeptName}
            />
          </div>
          <div className="form-group-row">
            <div className="form-group">
              <label className="form-label" htmlFor="engagement_planned_start">Planned Start</label>
              <input id="engagement_planned_start" type="date" className="form-control" value={newEngagement.planned_start}
                onChange={(e) => setNewEngagement({ ...newEngagement, planned_start: e.target.value })} />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="engagement_planned_end">Planned End</label>
              <input id="engagement_planned_end" type="date" className="form-control" value={newEngagement.planned_end}
                onChange={(e) => setNewEngagement({ ...newEngagement, planned_end: e.target.value })} />
            </div>
          </div>
        </form>
      </Modal>

      {/* Team Assignment Modal */}
      <Modal
        isOpen={Boolean(showTeamModal && selectedEngagement)}
        onClose={() => setShowTeamModal(false)}
        title={selectedEngagement ? `Manage Team — ${selectedEngagement.title}` : 'Manage Team'}
        size="xl"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={() => setShowTeamModal(false)}>Close</button>
            <button type="submit" form="team-member-form" className="btn btn-primary">Add Member</button>
          </>
        )}
      >
        {/* Existing team */}
        {engagementTeam.length > 0 && (
          <div className="mb-4">
            <h4 className="mb-2">Current Team Members</h4>
            {/* .table has no min-width of its own, so without this wrapper the
                columns compress instead of scrolling on a narrow screen. */}
            <div className="table-responsive">
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Role</th>
                    <th>Allocated Days</th>
                  </tr>
                </thead>
                <tbody>
                  {engagementTeam.map(tm => (
                    <tr key={tm.id}>
                      <td>{tm.user_details?.full_name || tm.user_details?.employee_id}</td>
                      <td><span className="badge badge-outline">{tm.role?.toUpperCase()}</span></td>
                      <td>{tm.allocated_days} days</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Add new member form */}
        <form id="team-member-form" onSubmit={handleAddTeamMember}>
          <div className="form-section-divider"><span>Add Team Member</span></div>
          <div className="form-group-row">
            <div className="form-group">
              <label className="form-label" htmlFor="team_user">User</label>
              <select id="team_user" className="form-control" value={teamMember.user}
                onChange={(e) => setTeamMember({ ...teamMember, user: e.target.value })} required>
                <option value="">Select User...</option>
                {allUsers.map(u => (
                  <option key={u.id} value={u.id}>{u.full_name || `${u.first_name} ${u.last_name}`} ({u.role})</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="team_role">Role in Engagement</label>
              <select id="team_role" className="form-control" value={teamMember.role}
                onChange={(e) => setTeamMember({ ...teamMember, role: e.target.value })}>
                <option value="lead">Lead Auditor</option>
                <option value="member">Team Member</option>
                <option value="supervisor">Supervisor</option>
                <option value="specialist">Subject Matter Expert</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="team_allocated_days">Allocated Days</label>
              <input id="team_allocated_days" type="number" min="0" className="form-control"
                value={teamMember.allocated_days}
                onChange={(e) => setTeamMember({ ...teamMember, allocated_days: parseInt(e.target.value) || 0 })} />
            </div>
          </div>
        </form>
      </Modal>

    </div>
  );
}

export default PlanningPage;
