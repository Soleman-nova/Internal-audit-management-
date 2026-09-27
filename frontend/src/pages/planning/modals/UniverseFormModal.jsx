import { useState } from 'react';
import { planningApi } from '../../../api';
import { useToast } from '../../../context/ToastContext';
import { usePermissions } from '../../../hooks/usePermissions';
import { useI18n } from '../../../context/I18nContext';
import { validateForm, validators, hasErrors } from '../../../utils/validation';
import Modal from '../../../components/ui/Modal';
import FormErrorSummary from '../../../components/ui/FormErrorSummary';
import OrgUnitSelect from '../../../components/ui/OrgUnitSelect';
import { Plus } from 'lucide-react';
import {
  emptyUniverse, emptyProject, universeToForm, scopeValueLabels, matchRegistryProject,
} from '../planningForms';

/**
 * The add/edit form for one Auditable Entity, and the "register a PPM project"
 * mini-form it opens.
 *
 * The modal is rendered by the page unconditionally with an `isOpen` prop, and
 * `Modal` renders its children only while open — so this component mounts on
 * every open. That is what makes the `useState` initialisers below the whole of
 * the old open/close bookkeeping: the form is seeded from `item` on the way in
 * and simply discarded on the way out, and the page only ever holds the row's
 * id.
 *
 * It owns the form, its validation and its submit; the page owns the request
 * that follows (see `onSaved`) because it is the page that fetched the list.
 *
 * Props:
 *   isOpen           whether the modal is showing
 *   onClose          close it (Cancel, the X, or after a save)
 *   item             the universe row being edited, or null when adding
 *   projects         the PPM project registry backing the dropdown
 *   ppmDepartmentId  id of the PPM chief office, or '' when the tree has not
 *                    loaded; selects the department the mini-form defaults to
 *   setReferences    the references hook's setter, so a project registered here
 *                    is prepended to the registry without a refetch
 *   onSaved          called after a successful create/update, for the page to
 *                    refetch the tab and the reference catalogs
 */
function UniverseFormModal({
  isOpen,
  onClose,
  item,
  projects,
  ppmDepartmentId,
  setReferences,
  onSaved,
}) {
  const toast = useToast();
  const { canWriteAudit } = usePermissions();
  const { t, lang } = useI18n();

  const [newUniverse, setNewUniverse] = useState(() => (item ? universeToForm(item) : emptyUniverse));
  const [formErrors, setFormErrors] = useState({});

  // Which registry project the universe form points at, held as an **id** and
  // resolved against the reference list on every render. The registry is
  // replaced wholesale whenever a project is added or the references are
  // refetched, so a stored row object would be a snapshot of a list that no
  // longer exists. `projects` itself is the registry the page passed in.
  const [selectedProjectId, setSelectedProjectId] = useState(() => {
    // For a project-category row, preselect the registry entry whose code/name
    // matches (there is no FK, so this is a best-effort match); department keeps
    // whatever the row already stores.
    if (!item || item.category !== 'project') return '';
    const match = matchRegistryProject(projects, item.name, item.code);
    return match ? match.id : '';
  });
  const selectedProject = projects.find(p => String(p.id) === String(selectedProjectId)) || null;

  const [showAddProject, setShowAddProject] = useState(false);
  const [newProject, setNewProject] = useState(emptyProject);
  const [projectErrors, setProjectErrors] = useState({});
  const [addingProject, setAddingProject] = useState(false);

  // True once the department picker resolves to the PPM chief office — reveals
  // the "PPM Project" dropdown just like category === 'project' does.
  const ppmDepartmentSelected = !!(ppmDepartmentId && newUniverse.department &&
    String(newUniverse.department) === ppmDepartmentId);

  // The three *_name fields are tracked separately from the form payload so
  // the picker can still name a retired unit, which the org tree omits.
  const valueLabels = item
    ? scopeValueLabels(item, lang)
    : { department: '', region: '', service_center: '' };

  const handleSelectProject = (id) => {
    if (!id) {
      setSelectedProjectId('');
      return;
    }
    const project = projects.find(p => String(p.id) === String(id));
    if (!project) return;
    setSelectedProjectId(String(project.id));
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
      // Optimistic prepend into the reference set rather than a refetch: the
      // created row is already in hand, so `setReferences` (the hook's escape
      // hatch for exactly this) is enough. The catalog is a separate list from
      // the universe tab's slice, so the tab is not disturbed.
      setReferences(prev => ({
        ...(prev || {}),
        projects: [created, ...(prev?.projects ?? [])],
      }));
      setSelectedProjectId(String(created.id));
      setNewUniverse(prev => ({
        ...prev,
        name: created.name,
        code: prev.code || created.code || '',
        department: prev.department || ppmDepartmentId || '',
      }));
      setShowAddProject(false);
      setNewProject(emptyProject);
      toast.success(t('projectAddedToast'));
    } catch (err) {
      const msg = typeof err.response?.data === 'object'
        ? JSON.stringify(err.response.data)
        : t('projectAddFailed');
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
      // A blank select holds '', which DRF rejects as a foreign key. Drop the
      // key instead so the field is simply left unset.
      if (!payload.region) delete payload.region;
      if (!payload.service_center) delete payload.service_center;
      if (!payload.last_audited) delete payload.last_audited;
      if (item) {
        await planningApi.updateUniverse(item.id, payload);
        toast.success(t('universeUpdatedToast'));
      } else {
        await planningApi.createUniverse(payload);
        toast.success(t('universeCreatedToast'));
      }
      onSaved();
      onClose();
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : t('universeSaveFailed');
      toast.error(msg);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={item ? t('editEntity') : t('addEntityTitle')}
      size="lg"
      footer={(
        <>
          <button type="button" className="btn btn-outline" onClick={onClose}>{t('cancel')}</button>
          {/* `form=` because Modal renders the footer as a sibling of its
              children, so the submit button sits outside the <form>. */}
          <button type="submit" form="universe-form" className="btn btn-primary">
            {item ? t('saveChanges') : t('saveEntity')}
          </button>
        </>
      )}
    >
      <form id="universe-form" onSubmit={handleSaveUniverse} noValidate>
        <FormErrorSummary errors={formErrors} />
        <div className="form-group">
          <label className="form-label" htmlFor="universe_name">{t('entityName')}</label>
          <input id="universe_name" type="text" className="form-control" placeholder={t('universeNamePlaceholder')}
            value={newUniverse.name} onChange={(e) => setNewUniverse({ ...newUniverse, name: e.target.value })} required />
        </div>
        <div className="form-group-row">
          <div className="form-group">
            <label className="form-label" htmlFor="universe_code">{t('uniqueCode')}</label>
            <input id="universe_code" type="text" className="form-control" placeholder={t('universeCodePlaceholder')}
              value={newUniverse.code} onChange={(e) => setNewUniverse({ ...newUniverse, code: e.target.value })} required />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="universe_category">{t('category')}</label>
            <select id="universe_category" className="form-control" value={newUniverse.category} onChange={(e) => setNewUniverse({ ...newUniverse, category: e.target.value })}>
              <option value="department">{t('department')}</option>
              <option value="process">{t('categoryBusinessProcess')}</option>
              <option value="system">{t('categoryItSystem')}</option>
              <option value="project">{t('categoryProject')}</option>
              <option value="subsidiary">{t('categorySubsidiary')}</option>
              <option value="regulation">{t('categoryRegulation')}</option>
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
            <label className="form-label" htmlFor="universe_ppm_project">{t('ppmProject')}</label>
            <div className="flex items-center gap-2">
              <select
                id="universe_ppm_project"
                className="form-control flex-1 min-w-0"
                value={selectedProject ? String(selectedProject.id) : ''}
                onChange={(e) => handleSelectProject(e.target.value)}
              >
                <option value="">{t('ppmSelectProject')}</option>
                {projects.map(p => (
                  <option key={p.id} value={p.id}>{p.code} — {p.name}</option>
                ))}
              </select>
              {canWriteAudit && (
                <button
                  type="button"
                  className="btn btn-outline flex items-center gap-1"
                  onClick={() => setShowAddProject(v => !v)}
                  title={t('ppmRegisterHint')}
                  aria-expanded={showAddProject}
                >
                  <Plus size={16} />
                  <span>{t('add')}</span>
                </button>
              )}
            </div>
            {showAddProject && canWriteAudit && (
              <div className="mt-3 border border-border-color rounded-lg p-3">
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                  {t('ppmRegisterBody')}
                </p>
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label" htmlFor="project_code">{t('projectCode')}</label>
                    <input id="project_code" type="text" className="form-control" placeholder={t('projectCodePlaceholder')}
                      value={newProject.code}
                      onChange={(e) => setNewProject({ ...newProject, code: e.target.value })}
                      onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddProject(); } }} />
                    {projectErrors.code && <p className="form-error">{projectErrors.code}</p>}
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="project_name">{t('projectName')}</label>
                    <input id="project_name" type="text" className="form-control" placeholder={t('projectNamePlaceholder')}
                      value={newProject.name}
                      onChange={(e) => setNewProject({ ...newProject, name: e.target.value })}
                      onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddProject(); } }} />
                    {projectErrors.name && <p className="form-error">{projectErrors.name}</p>}
                  </div>
                </div>
                <div className="mt-3 flex gap-2">
                  <button type="button" className="btn btn-primary" onClick={handleAddProject} disabled={addingProject}>
                    {addingProject ? t('addingProject') : t('addProject')}
                  </button>
                  <button type="button" className="btn btn-outline" onClick={() => setShowAddProject(false)}>{t('cancel')}</button>
                </div>
              </div>
            )}
          </div>
        )}
        <div className="form-group-row">
          <OrgUnitSelect
            idPrefix="universe_dept"
            label={t('departmentDirectorate')}
            split
            value={newUniverse}
            onFieldChange={(changes) => setNewUniverse(prev => {
              const next = { ...prev, ...changes };
              // Picking the PPM chief office implies a project-managed entity,
              // so default the category to Project (only when it is unset).
              const isPpm = !!(next.department && ppmDepartmentId && String(next.department) === ppmDepartmentId);
              if (isPpm && next.category !== 'project') next.category = 'project';
              return next;
            })}
            valueLabels={valueLabels}
          />
          <div className="form-group">
            <label className="form-label" htmlFor="universe_risk_score">{t('initialRiskScore')}</label>
            <input id="universe_risk_score" type="number" step="0.05" min="1" max="5" className="form-control"
              value={newUniverse.risk_score} onChange={(e) => setNewUniverse({ ...newUniverse, risk_score: parseFloat(e.target.value) })} required />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="universe_frequency">{t('auditFrequency')}</label>
            <select id="universe_frequency" className="form-control" value={newUniverse.audit_frequency} onChange={(e) => setNewUniverse({ ...newUniverse, audit_frequency: e.target.value })}>
              <option value="Annually">{t('frequencyAnnually')}</option>
              <option value="Bi-annually">{t('frequencyBiAnnually')}</option>
              <option value="Tri-annually">{t('frequencyTriAnnually')}</option>
            </select>
          </div>
        </div>
        <div className="form-group-row">
          <div className="form-group">
            <label className="form-label" htmlFor="universe_last_audited">{t('lastAudited')}</label>
            <input id="universe_last_audited" type="date" className="form-control"
              value={newUniverse.last_audited} onChange={(e) => setNewUniverse({ ...newUniverse, last_audited: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="universe_status">{t('status')}</label>
            <select id="universe_status" className="form-control" value={newUniverse.status} onChange={(e) => setNewUniverse({ ...newUniverse, status: e.target.value })}>
              <option value="active">{t('active')}</option>
              <option value="inactive">{t('inactive')}</option>
              <option value="under_review">{t('statusUnderReview')}</option>
            </select>
          </div>
        </div>
      </form>
    </Modal>
  );
}

export default UniverseFormModal;
