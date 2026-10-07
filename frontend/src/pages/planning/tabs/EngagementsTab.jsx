import { usePermissions } from '../../../hooks/usePermissions';
import { useI18n } from '../../../context/I18nContext';
import { orgScopeLabel } from '../../../utils/localizedName';
import Pagination from '../../../components/ui/Pagination';
import { Plus, Users, Shield, Clock, Pencil, UserCheck } from 'lucide-react';

// Mirrors AuditEngagement.STATUS_CHOICES. The server rejects anything else, and
// refuses `completed` outright while the engagement still holds a finding that
// is not resolved or closed — see BLOCKS_COMPLETION in audit_planning/views.py.
const ENGAGEMENT_STATUSES = [
  'planned', 'in_progress', 'fieldwork', 'reporting', 'completed', 'cancelled',
];

/**
 * Audit Engagements tab: the engagement table and its per-row actions.
 *
 * Purely presentational — the page owns the slice, its total and the paging
 * state, and the status change as well, since it is a mutation of data the page
 * fetched and has to refetch.
 *
 * Props:
 *   engagements     rows for the current page
 *   count           the server's total
 *   page/pageSize   paging state, owned by the page
 *   onPageChange / onPageSizeChange
 *   focusEngagementId   id from the `?engagement=` deep link; the matching row
 *                       is ringed and carries the DOM id the page scrolls to
 *   onAdd           open the engagement form empty
 *   onEdit(eng)     open the engagement form on an existing row
 *   onManageTeam(eng)   open the team modal for that engagement
 *   onStatusChange(engagementId, nextStatus)   the inline status control
 */
function EngagementsTab({
  engagements,
  count,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
  focusEngagementId,
  onAdd,
  onEdit,
  onManageTeam,
  onStatusChange,
}) {
  const { canWriteAudit } = usePermissions();
  const { t, lang } = useI18n();

  return (
    <div className="card">
      <div className="card-header justify-between">
        <div>
          <h3>{t('auditEngagements')}</h3>
          <p className="card-subtitle">{t('individualOperationalAudits')}</p>
        </div>
        {canWriteAudit && (
          <button className="btn btn-primary flex items-center gap-2" onClick={onAdd}>
            <Plus size={16} /> {t('scheduleEngagement')}
          </button>
        )}
      </div>
      <div className="table-responsive">
        <table className="table engagements-table">
          <thead>
            <tr>
              <th>{t('refNumber')}</th>
              <th>{t('auditTitle')}</th>
              <th>{t('type')}</th>
              <th>{t('orgUnit')}</th>
              <th>{t('leadAuditor')}</th>
              <th>{t('supervisor')}</th>
              <th>{t('auditeeRepresentative')}</th>
              <th>{t('days')}</th>
              <th>{t('timeline')}</th>
              <th>{t('riskLevel')}</th>
              <th>{t('status')}</th>
              <th>{t('team')}</th>
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
                <td>{orgScopeLabel(lang, eng, '—')}</td>
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
                  {/* Deliberately `—` rather than "Unassigned": a blank here is
                      not a staffing gap on the audit side, it is the reason this
                      engagement's findings will reach the department and answer
                      to no one. The warning tone is the point. */}
                  {eng.auditee_name ? (
                    <span className="flex items-center gap-1">
                      <UserCheck size={13} className="text-success" />
                      {eng.auditee_name}
                    </span>
                  ) : <span className="text-muted" title={t('auditeeRepresentativeHint')}>—</span>}
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
                    <button className="btn btn-sm btn-outline flex items-center gap-1" onClick={() => onEdit(eng)}>
                      <Pencil size={13} /> {t('edit')}
                    </button>
                    <button className="btn btn-sm btn-outline" onClick={() => onManageTeam(eng)}>
                      {t('assign')}
                    </button>
                    {canWriteAudit && (
                      <select
                        className="form-input"
                        aria-label={t('engagementStatusAria', eng.engagement_number || eng.title)}
                        value={eng.status || 'planned'}
                        onChange={(e) => onStatusChange(eng.id, e.target.value)}
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

export default EngagementsTab;
