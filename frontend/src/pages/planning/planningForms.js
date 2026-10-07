import { localizedName } from '../../utils/localizedName';

/**
 * Form templates and row → form mappers for the planning page.
 *
 * They live apart from the page so that the shell — which owns only the *id* of
 * the row a modal is editing — and the modal — which owns the fields — can
 * agree on a form's shape without either keeping a copy of the other's state.
 * Every mapper falls back to exactly what its blank template holds, so an edit
 * form can never come up with a different shape from an add form.
 */

/**
 * Blank "Add Auditable Entity" form.
 *
 * Department, region and service center are three independent fields on the
 * record (see OrgUnitSelect), so every form that picks an audited entity
 * carries all three. Region and service center are optional.
 */
export const emptyUniverse = { name: '', code: '', category: 'system', risk_score: 3.5, audit_frequency: 'Annually', owner: '', department: '', region: '', service_center: '', status: 'active', last_audited: '' };

/** Blank "Create Annual Audit Plan" form. */
export const emptyPlan = { title: '', year: new Date().getFullYear(), plan_scope: 'directorate', directorate: '', total_budget_days: 0, start_date: '', end_date: '', description: '', objectives: '', scope: '', methodology: '' };

/** Blank "Schedule Audit Engagement" form. */
export const emptyEngagement = {
  title: '', plan: '', audit_universe: '', department: '', region: '', service_center: '',
  engagement_type: 'operational', risk_level: 'medium',
  planned_start: '', planned_end: '', planned_days: 0,
  lead_auditor: '', supervisor: '', auditee: '', objectives: '', scope: ''
};

/** Blank "Register a new PPM project" mini-form. */
export const emptyProject = { code: '', name: '' };

/** Blank "Add Team Member" form. */
export const emptyTeamMember = { user: '', role: 'member', allocated_days: 0 };

/** Universe row → the fields the entity form edits. */
export function universeToForm(item) {
  return {
    name: item.name || '', code: item.code || '', category: item.category || 'system',
    risk_score: item.risk_score ?? 3.5, audit_frequency: item.audit_frequency || 'Annually',
    owner: item.owner || '', department: item.department || '', status: item.status || 'active',
    region: item.region || '', service_center: item.service_center || '',
    last_audited: item.last_audited || '',
  };
}

/** Plan row → the fields the plan form edits. */
export function planToForm(plan) {
  return {
    title: plan.title || '', year: plan.year || new Date().getFullYear(),
    plan_scope: plan.plan_scope || 'directorate', directorate: plan.directorate || '',
    total_budget_days: plan.total_budget_days ?? 0, start_date: plan.start_date || '',
    end_date: plan.end_date || '', description: plan.description || '',
    objectives: plan.objectives || '', scope: plan.scope || '',
    methodology: plan.methodology || '',
  };
}

/** Engagement row → the fields the engagement form edits. */
export function engagementToForm(eng) {
  return {
    title: eng.title || '', plan: eng.plan || '', audit_universe: eng.audit_universe || '',
    department: eng.department || '', region: eng.region || '', service_center: eng.service_center || '',
    engagement_type: eng.engagement_type || 'operational',
    risk_level: eng.risk_level || 'medium', planned_start: eng.planned_start || '',
    planned_end: eng.planned_end || '', planned_days: eng.planned_days ?? 0,
    lead_auditor: eng.lead_auditor || '', supervisor: eng.supervisor || '',
    auditee: eng.auditee || '',
    objectives: eng.objectives || '', scope: eng.scope || '',
  };
}

/**
 * A row's department, region and service center as display names, for
 * OrgUnitSelect's `valueLabels`.
 *
 * The three *_name fields are tracked separately from the form payload so
 * the picker can still name a retired unit, which the org tree omits.
 */
export function scopeValueLabels(record, lang) {
  return {
    department: localizedName(lang, record.department_name, record.department_name_am) || '',
    region: localizedName(lang, record.region_name, record.region_name_am) || '',
    service_center: localizedName(lang, record.service_center_name, record.service_center_name_am) || '',
  };
}

/**
 * Best-effort match of a saved registry project to a universe row (there is no
 * FK): code match first, then a case-insensitive name match.
 */
export function matchRegistryProject(projects, name, code) {
  return projects.find(p => p.code && code && p.code === code) ||
    projects.find(p => p.name && name && String(p.name).trim().toLowerCase() === String(name).trim().toLowerCase()) ||
    null;
}
