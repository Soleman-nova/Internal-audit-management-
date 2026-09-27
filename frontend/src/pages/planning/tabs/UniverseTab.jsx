import { usePermissions } from '../../../hooks/usePermissions';
import { useI18n } from '../../../context/I18nContext';
import { orgScopeLabel } from '../../../utils/localizedName';
import Pagination from '../../../components/ui/Pagination';
import { Plus, Clock, Pencil, Upload, Download } from 'lucide-react';

/**
 * Audit Universe tab: the paginated directory of auditable entities, with the
 * re-audit badge and the import/export/add toolbar.
 *
 * Purely presentational — the page owns the slice, its server total and the
 * paging state, and re-renders this with new ones. `onEdit` is handed the whole
 * row because the page turns it back into the id its entity form opens with;
 * nothing here keeps a copy of a row in state.
 *
 * Props:
 *   universe        rows for the current page
 *   count           the server's total, for the page count and the pager label
 *   page/pageSize   paging state, owned by the page
 *   onPageChange / onPageSizeChange
 *   dueForAudit     `{ count }` behind the "due for re-audit" badge
 *   onImport / onExport / onAdd   toolbar actions
 *   onEdit(item)    open the entity form on an existing row
 */
function UniverseTab({
  universe,
  count,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
  dueForAudit,
  onImport,
  onExport,
  onAdd,
  onEdit,
}) {
  const { canWriteAudit } = usePermissions();
  const { t, lang } = useI18n();

  return (
    <div className="card">
      <div className="card-header justify-between">
        <div>
          <h3>{t('eeuRiskWeightedUniverse')}</h3>
          <p className="card-subtitle">{t('completeDirectory')}</p>
        </div>
        <div className="flex gap-2">
          {dueForAudit.count > 0 && (
            <span className="badge badge-danger flex items-center gap-1">
              <Clock size={13} /> {dueForAudit.count} {t('dueForReAudit')}
            </span>
          )}
          {canWriteAudit && (
            <>
              <button
                className="btn btn-outline flex items-center gap-2"
                onClick={onImport}
                title={t('universeImportHint')}
              >
                <Upload size={16} /> {t('import')}
              </button>
              <button
                className="btn btn-outline flex items-center gap-2"
                onClick={onExport}
                title={t('universeExportHint')}
              >
                <Download size={16} /> {t('export')}
              </button>
              <button className="btn btn-primary flex items-center gap-2" onClick={onAdd}>
                <Plus size={16} /> {t('addEntity')}
              </button>
            </>
          )}
        </div>
      </div>
      <div className="table-responsive">
        <table className="table">
          <thead>
            <tr>
              <th>{t('code')}</th>
              <th>{t('entityName')}</th>
              <th>{t('category')}</th>
              <th>{t('department')}</th>
              <th>{t('riskScore')}</th>
              <th>{t('frequency')}</th>
              <th>{t('lastAudited')}</th>
              <th>{t('reAudit')}</th>
              <th>{t('status')}</th>
              <th>{t('actions')}</th>
            </tr>
          </thead>
          <tbody>
            {universe.map(item => (
              <tr key={item.id}>
                <td><strong>{item.code}</strong></td>
                <td>{item.name}</td>
                <td><span className="badge badge-outline">{item.category?.toUpperCase()}</span></td>
                <td>{orgScopeLabel(lang, item, 'N/A')}</td>
                <td>
                  <span className={`risk-tag ${item.risk_score >= 4 ? 'critical' : item.risk_score >= 3 ? 'high' : 'medium'}`}>
                    {item.risk_score}
                  </span>
                </td>
                <td>{item.audit_frequency}</td>
                <td>{item.last_audited || t('never')}</td>
                <td>
                  {item.due_for_re_audit ? (
                    <span className="badge badge-danger">{t('due')}</span>
                  ) : (
                    <span className="badge badge-success">{t('ok')}</span>
                  )}
                </td>
                <td>
                  <span className={`badge ${item.status === 'active' ? 'badge-success' : 'badge-warning'}`}>
                    {item.status}
                  </span>
                </td>
                <td>
                  {canWriteAudit && (
                    <button className="btn btn-sm btn-outline flex items-center gap-1" onClick={() => onEdit(item)}>
                      <Pencil size={13} /> {t('edit')}
                    </button>
                  )}
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

export default UniverseTab;
