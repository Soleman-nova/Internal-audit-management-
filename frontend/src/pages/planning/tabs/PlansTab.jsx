import { usePermissions } from '../../../hooks/usePermissions';
import { useI18n } from '../../../context/I18nContext';
import { localizedName } from '../../../utils/localizedName';
import Pagination from '../../../components/ui/Pagination';
import { Plus, Pencil } from 'lucide-react';

/**
 * Annual Audit Plans tab: the plan cards, their submit/approve actions and the
 * pager.
 *
 * Purely presentational — the page owns the slice, its total and the paging
 * state, and owns the two approval calls as well, because both are mutations of
 * data it fetched.
 *
 * Props:
 *   plans           plan cards for the current page
 *   count           the server's total
 *   page/pageSize   paging state, owned by the page
 *   onPageChange / onPageSizeChange
 *   focusPlanId     id from the `?plan=` deep link; the matching card is ringed
 *                   and carries the DOM id the page scrolls to
 *   onAdd           open the plan form empty
 *   onEdit(plan)    open the plan form on an existing row
 *   onSubmit(planId) / onApprove(planId)   row actions
 */
function PlansTab({
  plans,
  count,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
  focusPlanId,
  onAdd,
  onEdit,
  onSubmit,
  onApprove,
}) {
  const { canWriteAudit, canApprovePlans } = usePermissions();
  const { t, lang } = useI18n();

  return (
    <div className="card">
      <div className="card-header justify-between">
        <div>
          <h3>{t('annualAuditPlans')}</h3>
          <p className="card-subtitle">{t('activeAndHistorical')}</p>
        </div>
        {canWriteAudit && (
          <button className="btn btn-primary flex items-center gap-2" onClick={onAdd}>
            <Plus size={16} /> {t('createPlan')}
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
                <div><span>{t('year')}:</span><strong>{plan.year}</strong></div>
                <div><span>{t('scope')}:</span><strong>{plan.plan_scope_display || plan.plan_scope}</strong></div>
                <div><span>{t('directorate')}:</span><strong>{localizedName(lang, plan.directorate_name, plan.directorate_name_am) || '—'}</strong></div>
                <div><span>{t('budgetDays')}:</span><strong>{plan.total_budget_days} {t('days')}</strong></div>
              </div>
              <div className="plan-dates text-sm">
                <span>{t('timeline')}:</span>
                <strong>{plan.start_date} to {plan.end_date}</strong>
              </div>
              <div className="mt-4 flex gap-2 border-t pt-3 border-border-color">
                {canWriteAudit && (
                  <button className="btn btn-sm btn-outline flex items-center gap-1" onClick={() => onEdit(plan)}>
                    <Pencil size={13} /> {t('edit')}
                  </button>
                )}
                {plan.status === 'draft' && canWriteAudit && (
                  <button className="btn btn-sm btn-outline flex-1" onClick={() => onSubmit(plan.id)}>
                    {t('submitForApproval')}
                  </button>
                )}
                {plan.status === 'submitted' && canApprovePlans && (
                  <button className="btn btn-sm btn-primary flex-1" onClick={() => onApprove(plan.id)}>
                    {t('approvePlan')}
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      <Pagination
        page={page}
        pageCount={Math.max(1, Math.ceil(count / pageSize))}
        totalCount={count}
        onPageChange={onPageChange}
        pageSize={pageSize}
        onPageSizeChange={onPageSizeChange}
        showPageSize
      />
    </div>
  );
}

export default PlansTab;
