import { useState } from 'react';
import { planningApi } from '../../../api';
import { useToast } from '../../../context/ToastContext';
import { useI18n } from '../../../context/I18nContext';
import { validateForm, validators, hasErrors } from '../../../utils/validation';
import Modal from '../../../components/ui/Modal';
import FormErrorSummary from '../../../components/ui/FormErrorSummary';
import OrgUnitSelect from '../../../components/ui/OrgUnitSelect';
import { Users } from 'lucide-react';
import { emptyEngagement, engagementToForm, scopeValueLabels } from '../planningForms';

/**
 * The schedule/edit form for one Audit Engagement — title, target plan, type,
 * risk, the lead auditor/supervisor/days manager section and the audited
 * entity.
 *
 * `Modal` renders its children only while open, so this component mounts on
 * every open and the `useState` initialiser below replaces the page's old
 * open/close bookkeeping: the form is seeded from `engagement` on the way in
 * and discarded on the way out, and the page holds only the row's id.
 *
 * Props:
 *   isOpen          whether the modal is showing
 *   onClose         close it (Cancel, the X, or after a save)
 *   engagement      the row being edited, or null when scheduling a new one
 *   users           every user, for the lead/supervisor pickers (the endpoint
 *                   pages at 20, so the page walks it once for the whole view)
 *   plansCatalog    the FULL plan list backing the target-plan picker — not the
 *                   paginated slice the tab renders
 *   universeCatalog the FULL universe list backing the entity picker
 *   onSaved         called after a successful create/update, for the page to
 *                   refetch the engagements tab
 */
function EngagementFormModal({
  isOpen,
  onClose,
  engagement,
  users,
  plansCatalog,
  universeCatalog,
  onSaved,
}) {
  const toast = useToast();
  const { t, lang } = useI18n();
  const [newEngagement, setNewEngagement] = useState(() => (engagement ? engagementToForm(engagement) : emptyEngagement));
  const [formErrors, setFormErrors] = useState({});

  const auditors = users.filter(u => u.role === 'auditor' || u.role === 'audit_manager');
  const supervisors = users.filter(u => u.role === 'supervisor' || u.role === 'audit_manager');

  // The three *_name fields are tracked separately from the form payload so
  // the picker can still name a retired unit, which the org tree omits.
  const valueLabels = engagement
    ? scopeValueLabels(engagement, lang)
    : { department: '', region: '', service_center: '' };

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
            return { planned_end: t('endAfterStart') };
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
      if (!payload.region) delete payload.region;
      if (!payload.service_center) delete payload.service_center;
      if (!payload.audit_universe) delete payload.audit_universe;
      if (!payload.lead_auditor) delete payload.lead_auditor;
      if (!payload.supervisor) delete payload.supervisor;
      if (engagement) {
        await planningApi.updateEngagement(engagement.id, payload);
        toast.success(t('engagementUpdatedToast'));
      } else {
        await planningApi.createEngagement(payload);
        toast.success(t('engagementCreatedToast'));
      }
      onSaved();
      onClose();
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : t('engagementSaveFailed');
      toast.error(msg);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={engagement ? t('editEngagement') : t('scheduleEngagementTitle')}
      size="xl"
      footer={(
        <>
          <button type="button" className="btn btn-outline" onClick={onClose}>{t('cancel')}</button>
          <button type="submit" form="engagement-form" className="btn btn-primary">
            {engagement ? t('saveChanges') : t('scheduleEngagement')}
          </button>
        </>
      )}
    >
      <form id="engagement-form" onSubmit={handleSaveEngagement} noValidate>
        <FormErrorSummary errors={formErrors} />
        <div className="form-group">
          <label className="form-label" htmlFor="engagement_title">{t('engagementTitle')}</label>
          <input id="engagement_title" type="text" className="form-control" placeholder={t('engagementTitlePlaceholder')}
            value={newEngagement.title} onChange={(e) => setNewEngagement({ ...newEngagement, title: e.target.value })} required />
        </div>
        <div className="form-group-row">
          <div className="form-group">
            <label className="form-label" htmlFor="engagement_plan">{t('targetAnnualPlan')}</label>
            <select id="engagement_plan" className="form-control" value={newEngagement.plan}
              onChange={(e) => setNewEngagement({ ...newEngagement, plan: e.target.value })} required>
              <option value="">{t('selectPlan')}</option>
              {plansCatalog.map(p => (<option key={p.id} value={p.id}>{p.title}</option>))}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="engagement_type">{t('engagementType')}</label>
            <select id="engagement_type" className="form-control" value={newEngagement.engagement_type}
              onChange={(e) => setNewEngagement({ ...newEngagement, engagement_type: e.target.value })}>
              <option value="operational">{t('engagementTypeOperational')}</option>
              <option value="financial">{t('engagementTypeFinancial')}</option>
              <option value="compliance">{t('engagementTypeCompliance')}</option>
              <option value="it">{t('engagementTypeIt')}</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="engagement_risk_level">{t('riskLevel')}</label>
            <select id="engagement_risk_level" className="form-control" value={newEngagement.risk_level}
              onChange={(e) => setNewEngagement({ ...newEngagement, risk_level: e.target.value })}>
              <option value="low">{t('low')}</option>
              <option value="medium">{t('medium')}</option>
              <option value="high">{t('high')}</option>
              <option value="critical">{t('critical')}</option>
            </select>
          </div>
        </div>

        {/* ★ Manager Section: Lead Auditor, Supervisor & Allocated Days */}
        <div className="form-section-divider">
          <span><Users size={14} /> {t('teamAssignment')}</span>
        </div>
        <div className="form-group-row">
          <div className="form-group">
            <label className="form-label" htmlFor="engagement_lead_auditor">{t('leadAuditor')}</label>
            <select id="engagement_lead_auditor" className="form-control" value={newEngagement.lead_auditor}
              onChange={(e) => setNewEngagement({ ...newEngagement, lead_auditor: e.target.value })}>
              <option value="">{t('selectLeadAuditor')}</option>
              {auditors.map(u => (
                <option key={u.id} value={u.id}>{u.full_name || `${u.first_name} ${u.last_name}`} ({u.employee_id})</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="engagement_supervisor">{t('supervisor')}</label>
            <select id="engagement_supervisor" className="form-control" value={newEngagement.supervisor}
              onChange={(e) => setNewEngagement({ ...newEngagement, supervisor: e.target.value })}>
              <option value="">{t('selectSupervisor')}</option>
              {supervisors.map(u => (
                <option key={u.id} value={u.id}>{u.full_name || `${u.first_name} ${u.last_name}`} ({u.employee_id})</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="engagement_planned_days">{t('allocatedDays')}</label>
            <input id="engagement_planned_days" type="number" min="0" className="form-control"
              placeholder={t('allocatedDaysPlaceholder')}
              value={newEngagement.planned_days}
              onChange={(e) => setNewEngagement({ ...newEngagement, planned_days: parseInt(e.target.value) || 0 })} />
          </div>
        </div>

        <div className="form-group-row">
          <div className="form-group">
            <label className="form-label" htmlFor="engagement_audit_universe">{t('auditUniverseNode')}</label>
            <select id="engagement_audit_universe" className="form-control" value={newEngagement.audit_universe}
              onChange={(e) => setNewEngagement({ ...newEngagement, audit_universe: e.target.value })}>
              <option value="">{t('selectEntity')}</option>
              {universeCatalog.map(u => (<option key={u.id} value={u.id}>{u.code} - {u.name}</option>))}
            </select>
          </div>
          <OrgUnitSelect
            idPrefix="engagement_dept"
            label={t('department')}
            split
            value={newEngagement}
            onFieldChange={(changes) => setNewEngagement(prev => ({ ...prev, ...changes }))}
            valueLabels={valueLabels}
          />
        </div>
        <div className="form-group-row">
          <div className="form-group">
            <label className="form-label" htmlFor="engagement_planned_start">{t('plannedStart')}</label>
            <input id="engagement_planned_start" type="date" className="form-control" value={newEngagement.planned_start}
              onChange={(e) => setNewEngagement({ ...newEngagement, planned_start: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="engagement_planned_end">{t('plannedEnd')}</label>
            <input id="engagement_planned_end" type="date" className="form-control" value={newEngagement.planned_end}
              onChange={(e) => setNewEngagement({ ...newEngagement, planned_end: e.target.value })} />
          </div>
        </div>
      </form>
    </Modal>
  );
}

export default EngagementFormModal;
