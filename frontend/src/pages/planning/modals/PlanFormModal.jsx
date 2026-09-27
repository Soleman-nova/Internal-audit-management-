import { useState } from 'react';
import { planningApi } from '../../../api';
import { useToast } from '../../../context/ToastContext';
import { useI18n } from '../../../context/I18nContext';
import { validateForm, validators, hasErrors } from '../../../utils/validation';
import Modal from '../../../components/ui/Modal';
import FormErrorSummary from '../../../components/ui/FormErrorSummary';
import OrgUnitSelect from '../../../components/ui/OrgUnitSelect';
import { emptyPlan, planToForm } from '../planningForms';

/**
 * The create/edit form for one Annual Audit Plan.
 *
 * `Modal` renders its children only while open, so this component mounts on
 * every open and the `useState` initialiser below replaces the page's old
 * open/close bookkeeping: the form is seeded from `plan` on the way in and
 * discarded on the way out, and the page holds only the row's id.
 *
 * Props:
 *   isOpen   whether the modal is showing
 *   onClose  close it (Cancel, the X, or after a save)
 *   plan     the plan being edited, or null when creating one
 *   onSaved  called after a successful create/update, for the page to refetch
 *            the plans tab and the catalogs the other modals pick from
 */
function PlanFormModal({ isOpen, onClose, plan, onSaved }) {
  const toast = useToast();
  const { t } = useI18n();
  const [newPlan, setNewPlan] = useState(() => (plan ? planToForm(plan) : emptyPlan));
  const [formErrors, setFormErrors] = useState({});

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
            return { end_date: t('endAfterStart') };
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
      if (plan) {
        await planningApi.updatePlan(plan.id, payload);
        toast.success(t('planUpdatedToast'));
      } else {
        await planningApi.createPlan(payload);
        toast.success(t('planCreatedToast'));
      }
      onSaved();
      onClose();
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : t('planSaveFailed');
      toast.error(msg);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={plan ? t('editPlan') : t('createPlanTitle')}
      size="lg"
      footer={(
        <>
          <button type="button" className="btn btn-outline" onClick={onClose}>{t('cancel')}</button>
          <button type="submit" form="plan-form" className="btn btn-primary">
            {plan ? t('saveChanges') : t('createPlan')}
          </button>
        </>
      )}
    >
      <form id="plan-form" onSubmit={handleSavePlan} noValidate>
        <FormErrorSummary errors={formErrors} />
        <div className="form-group">
          <label className="form-label" htmlFor="plan_title">{t('planTitle')}</label>
          <input id="plan_title" type="text" className="form-control" placeholder={t('planTitlePlaceholder')}
            value={newPlan.title} onChange={(e) => setNewPlan({ ...newPlan, title: e.target.value })} required />
        </div>
        <div className="form-group-row">
          <div className="form-group">
            <label className="form-label" htmlFor="plan_year">{t('year')}</label>
            <input id="plan_year" type="number" className="form-control" value={newPlan.year}
              onChange={(e) => setNewPlan({ ...newPlan, year: parseInt(e.target.value) })} required />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="plan_scope">{t('planScope')}</label>
            <select id="plan_scope" className="form-control" value={newPlan.plan_scope}
              onChange={(e) => setNewPlan({ ...newPlan, plan_scope: e.target.value })} required>
              <option value="directorate">{t('planScopeDirectorate')}</option>
              <option value="consolidated">{t('planScopeConsolidated')}</option>
            </select>
          </div>
        </div>
        <OrgUnitSelect
          idPrefix="plan_directorate"
          label={t('directorate')}
          value={newPlan.directorate}
          onChange={(id) => setNewPlan({ ...newPlan, directorate: id })}
        />
        <div className="form-group-row">
          <div className="form-group">
            <label className="form-label" htmlFor="plan_budget_days">{t('budgetDays')}</label>
            <input id="plan_budget_days" type="number" className="form-control" value={newPlan.total_budget_days}
              onChange={(e) => setNewPlan({ ...newPlan, total_budget_days: parseInt(e.target.value) })} />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="plan_start_date">{t('startDate')}</label>
            <input id="plan_start_date" type="date" className="form-control" value={newPlan.start_date}
              onChange={(e) => setNewPlan({ ...newPlan, start_date: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="plan_end_date">{t('endDate')}</label>
            <input id="plan_end_date" type="date" className="form-control" value={newPlan.end_date}
              onChange={(e) => setNewPlan({ ...newPlan, end_date: e.target.value })} />
          </div>
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor="plan_description">{t('description')}</label>
          <textarea id="plan_description" rows="2" className="form-control" value={newPlan.description}
            onChange={(e) => setNewPlan({ ...newPlan, description: e.target.value })} />
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor="plan_objectives">{t('objectives')}</label>
          <textarea id="plan_objectives" rows="2" className="form-control" placeholder={t('planObjectivesPlaceholder')}
            value={newPlan.objectives} onChange={(e) => setNewPlan({ ...newPlan, objectives: e.target.value })} />
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor="plan_scope_text">{t('scope')}</label>
          <textarea id="plan_scope_text" rows="2" className="form-control" placeholder={t('planScopePlaceholder')}
            value={newPlan.scope} onChange={(e) => setNewPlan({ ...newPlan, scope: e.target.value })} />
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor="plan_methodology">{t('methodology')}</label>
          <textarea id="plan_methodology" rows="2" className="form-control" placeholder={t('planMethodologyPlaceholder')}
            value={newPlan.methodology} onChange={(e) => setNewPlan({ ...newPlan, methodology: e.target.value })} />
        </div>
      </form>
    </Modal>
  );
}

export default PlanFormModal;
