import { Building2, Users, FolderKanban, Activity, ShieldAlert } from 'lucide-react';
import { useI18n } from '../context/I18nContext';
import { localizedName } from '../utils/localizedName';

/**
 * Colour and icon per audit directorate, keyed by `directorate_type`.
 *
 * Moved here from the org chart this component replaced — it is the only
 * remaining consumer.
 */
const DIRECTORATE_COLORS = {
  IAEO: '#f2801f',
  FPA: '#10b981',
  TA: '#f59e0b',
  ITA: '#8b5cf6',
  PP: '#00a651',
};

const DIRECTORATE_ICONS = {
  IAEO: Building2,
  FPA: FolderKanban,
  TA: Activity,
  ITA: ShieldAlert,
  PP: Users,
};

/**
 * The dashboard's scope selector: one pressable card per directorate plus a
 * consolidated option, replacing both the old `<select>` filter bar and the
 * full organizational tree that sat beneath it — two controls that did the
 * same job and between them pushed the charts below the fold.
 *
 * Deliberately shows identity only (name, code, head, staff). The tree it
 * replaced also displayed per-directorate universe/engagement counts, but it
 * derived them by filtering a `page_size: 100` fetch on the client, so every
 * one of those numbers was a floor rather than a total. Restoring them needs
 * a grouped endpoint; until then the strip does not claim to know them.
 *
 * A toggle group of `<button aria-pressed>` rather than a `<select>`: the
 * options are few, always visible, and each carries more than a label.
 */
function DirectorateStrip({ directorates = [], selected = 'all', onSelect, loading = false }) {
  const { t, lang } = useI18n();

  const isAll = selected === 'all';

  return (
    <div className="command-bar" role="group" aria-label={t('scopeSelector')}>
      <button
        type="button"
        className="command-scope command-scope-consolidated"
        style={{ '--scope-color': DIRECTORATE_COLORS.IAEO }}
        aria-pressed={isAll}
        onClick={() => onSelect(null)}
      >
        <span className="command-scope-head">
          <Building2 size={14} className="command-scope-icon" />
          <span className="command-scope-name">{t('eeuConsolidated')}</span>
        </span>
        <span className="command-scope-meta">{t('allDirectorates')}</span>
      </button>

      {loading && directorates.length === 0 && (
        <>
          <div className="command-scope command-scope-skeleton" aria-hidden="true">
            <span className="skeleton skeleton-line" />
            <span className="skeleton skeleton-line skeleton-line-short" />
          </div>
          <div className="command-scope command-scope-skeleton" aria-hidden="true">
            <span className="skeleton skeleton-line" />
            <span className="skeleton skeleton-line skeleton-line-short" />
          </div>
        </>
      )}

      {directorates.map(dept => {
        const color = DIRECTORATE_COLORS[dept.directorate_type] || '#64748b';
        const Icon = DIRECTORATE_ICONS[dept.directorate_type] || Building2;

        return (
          <button
            key={dept.id}
            type="button"
            className="command-scope"
            style={{ '--scope-color': color }}
            aria-pressed={selected === dept.id}
            onClick={() => onSelect(dept)}
          >
            <span className="command-scope-head">
              <Icon size={14} className="command-scope-icon" style={{ color }} />
              <span className="command-scope-name">
                {localizedName(lang, dept.name, dept.name_am)}
              </span>
            </span>
            <span className="command-scope-meta">
              {dept.head || t('noHeadAssigned')}
              {dept.staff_count != null && (
                <> · {dept.staff_count} {t('staffLabel')}</>
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export default DirectorateStrip;
