import { Building2, Users, FolderKanban, Activity, ShieldAlert } from 'lucide-react';
import { useI18n } from '../context/I18nContext';
import { localizedName } from '../utils/localizedName';

/**
 * Standard display order for audit directorates in EEU
 */
const DIRECTORATE_ORDER = ['FPA', 'TA', 'ITA', 'PP'];

/**
 * Standard fallback names when backend does not provide full name
 */
const DIRECTORATE_NAMES = {
  FPA: { en: 'Financial & Performance Audit', am: 'የፋይናንስና የአፈጻጸም ኦዲት ዳይሬክቶሬት' },
  TA: { en: 'Technical Audit', am: 'የቴክኒክ ኦዲት ዳይሬክቶሬት' },
  ITA: { en: 'Information Technology Audit', am: 'የኢንፎርሜሽን ቴክኖሎጂ ኦዲት ዳይሬክቶሬት' },
  PP: { en: 'Planning & Performance', am: 'የዕቅድና አፈጻጸም ዳይሬክቶሬት' },
  IAEO: { en: 'EEU Consolidated', am: 'የኢ.ኤ.ዩ ጥምር ዳሽቦርድ' },
};

/**
 * Colour and icon per audit directorate, keyed by `directorate_type`.
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
 * consolidated option, replacing both the old select filter bar and the
 * full organizational tree.
 */
function DirectorateStrip({ directorates = [], selected = 'all', onSelect, loading = false }) {
  const { t, lang } = useI18n();

  const isAll = selected === 'all';

  // Sort directorates according to standard EEU sequence
  const sortedDirectorates = [...directorates].sort((a, b) => {
    const idxA = DIRECTORATE_ORDER.indexOf(a.directorate_type);
    const idxB = DIRECTORATE_ORDER.indexOf(b.directorate_type);
    return (idxA === -1 ? 99 : idxA) - (idxB === -1 ? 99 : idxB);
  });

  return (
    <div className="command-bar" role="group" aria-label={t('scopeSelector') || 'Scope Selector'}>
      <button
        type="button"
        className="command-scope command-scope-consolidated"
        style={{ '--scope-color': DIRECTORATE_COLORS.IAEO }}
        aria-pressed={isAll}
        onClick={() => onSelect(null)}
      >
        <span className="command-scope-head">
          <Building2 size={14} className="command-scope-icon" />
          <span className="command-scope-name">{t('eeuConsolidated') || 'EEU Consolidated'}</span>
        </span>
        <span className="command-scope-meta">{t('allDirectorates') || 'All Directorates'}</span>
      </button>

      {loading && sortedDirectorates.length === 0 && (
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

      {sortedDirectorates.map(dept => {
        const color = DIRECTORATE_COLORS[dept.directorate_type] || '#64748b';
        const Icon = DIRECTORATE_ICONS[dept.directorate_type] || Building2;
        const fallback = DIRECTORATE_NAMES[dept.directorate_type];
        const displayName = localizedName(
          lang,
          dept.name || fallback?.en || dept.directorate_type,
          dept.name_am || fallback?.am || dept.name
        );

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
                {displayName}
              </span>
            </span>
            <span className="command-scope-meta">
              {dept.head || t('noHeadAssigned') || 'No Head Assigned'}
              {dept.staff_count != null && (
                <> · {dept.staff_count} {t('staffLabel') || 'staff'}</>
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export default DirectorateStrip;

