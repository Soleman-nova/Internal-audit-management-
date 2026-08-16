import React from 'react';
import { useI18n } from '../../context/I18nContext';
import { useOrgUnits } from '../../hooks/useOrgUnits';

/**
 * Cascading organisational-unit picker: department → region → service center.
 *
 * EEU's corporate structure is three levels deep (chief office → region →
 * customer service center) and 600+ units in total, so a single flat <select>
 * is unusable. This narrows the choice in three steps and reports the id of the
 * deepest unit picked, which is what the `department` foreign keys store.
 * Stopping at step one or two is legitimate — a risk assessment can belong to a
 * whole chief office, a whole region, or one service center.
 *
 * All three steps stay usable at all times. Every region hangs off a single
 * chief office (Region Coordination) in the tree, so gating step two on step
 * one's choice left regions and service centers unreachable for the other
 * eighteen departments. Listing the regions unconditionally is the trade-off
 * that keeps one foreign key: picking a region or a service center supersedes
 * the step-one department rather than being recorded alongside it, and step one
 * then re-displays the branch the stored unit actually sits under.
 *
 * Every step is derived from `value` rather than held in local state, so the
 * component is fully controlled and cannot drift out of sync with the form.
 *
 * Props:
 *   value       department id currently stored on the record ('' when unset)
 *   onChange    called with the new id (string) or '' when cleared
 *   label       field label; defaults to the translated "Department"
 *   required    marks step one required
 *   disabled    disables all three steps
 *   valueLabel  name to show when `value` points at a unit missing from the
 *               tree — a retired one, say — so editing cannot silently drop it
 */

// Step one flattens the non-geographic side of the tree. A literal
// CEO → child → grandchild walk would bury the audit directorates under
// Internal Audit → IAEO and hide them, and most auditors are assigned there.
const TOP_LEVEL_TYPES = ['EXECUTIVE', 'CORPORATE', 'AUDIT'];

// Order of the <optgroup>s in step one, most general first.
const GROUP_ORDER = ['EXECUTIVE', 'AUDIT', 'CORPORATE'];

const GROUP_LABELS = {
  EXECUTIVE: { en: 'Executive Office', am: 'የሥራ አስፈጻሚ ጽሕፈት ቤት' },
  AUDIT: { en: 'Internal Audit', am: 'ውስጣዊ ኦዲት' },
  CORPORATE: { en: 'Chief Offices', am: 'ዋና ጽሕፈት ቤቶች' },
};

export const OrgUnitSelect = ({
  value,
  onChange,
  label,
  required = false,
  disabled = false,
  valueLabel = '',
  className = '',
}) => {
  const { t, lang } = useI18n();
  const { units, byId, childrenOf, ancestorsOf, loading, error } = useOrgUnits();

  const selectedId = value == null ? '' : String(value);
  const known = selectedId !== '' && byId.has(selectedId);

  // `value` resolves to nothing we can show — a retired unit, which the tree
  // endpoint excludes on purpose. Keep it selected instead of blanking the
  // field, so opening and saving an old record doesn't wipe its department.
  const isOrphanValue = selectedId !== '' && !known && !loading;

  // ── Derive the three steps from the stored id ────────────────────────────
  const chain = known ? ancestorsOf(selectedId) : [];
  const departmentUnit = [...chain].reverse().find(u => TOP_LEVEL_TYPES.includes(u.unit_type));
  const regionUnit = chain.find(u => u.unit_type === 'REGION');
  const centerUnit = chain.find(u => u.unit_type === 'SERVICE_CENTER');

  const departmentId = departmentUnit ? String(departmentUnit.id) : '';
  const regionId = regionUnit ? String(regionUnit.id) : '';
  const centerId = centerUnit ? String(centerUnit.id) : '';

  const nameOf = (unit) => (lang === 'am' && unit.name_am ? unit.name_am : unit.name);

  // ── Options per step ────────────────────────────────────────────────────
  const topLevel = units.filter(u => TOP_LEVEL_TYPES.includes(u.unit_type));
  const groups = GROUP_ORDER
    .map(type => ({
      type,
      label: GROUP_LABELS[type][lang] || GROUP_LABELS[type].en,
      options: topLevel
        .filter(u => u.unit_type === type)
        .sort((a, b) => nameOf(a).localeCompare(nameOf(b))),
    }))
    .filter(group => group.options.length > 0);

  // Every region, not just those under the step-one choice: regions all hang
  // off Region Coordination, so filtering by step one hid them everywhere else.
  const regions = units
    .filter(u => u.unit_type === 'REGION')
    .sort((a, b) => nameOf(a).localeCompare(nameOf(b)));

  // Sorted by code, not name: service-center names repeat across regions and a
  // few are placeholders ('CSC'), so the code is the reliable ordering key.
  const centers = childrenOf(regionId, 'SERVICE_CENTER')
    .slice()
    .sort((a, b) => a.code.localeCompare(b.code));

  // ── Change handlers — always emit the deepest unit still selected ────────
  // Picking a region or a center replaces whatever step one held: one foreign
  // key can only point at one unit, and the deeper one is the more specific.
  const handleDepartment = (e) => onChange(e.target.value);
  const handleRegion = (e) => onChange(e.target.value || departmentId);
  const handleCenter = (e) => onChange(e.target.value || regionId);

  if (error) {
    return (
      <div className={`form-group ${className}`}>
        <label className="form-label">{label || t('department')}</label>
        <p className="org-unit-select-error">{t('orgStructureError')}</p>
      </div>
    );
  }

  return (
    <div className={`form-group ${className}`}>
      <label className="form-label">{label || t('department')}</label>

      <div className="org-unit-select">
        {/* Step 1 — chief office, executive office, or audit directorate */}
        <select
          className="form-control"
          value={isOrphanValue ? selectedId : departmentId}
          onChange={handleDepartment}
          required={required}
          disabled={disabled || loading}
          aria-label={label || t('department')}
        >
          <option value="">{loading ? t('loadingStructure') : t('selectDepartment')}</option>
          {isOrphanValue && (
            <option value={selectedId}>
              {valueLabel || `#${selectedId}`} ({t('retiredUnit')})
            </option>
          )}
          {groups.map(group => (
            <optgroup key={group.type} label={group.label}>
              {group.options.map(unit => (
                <option key={unit.id} value={unit.id}>
                  {nameOf(unit)} ({unit.code})
                </option>
              ))}
            </optgroup>
          ))}
        </select>

        {/* Step 2 — region; always live, independent of the step-one choice */}
        <select
          className="form-control"
          value={regionId}
          onChange={handleRegion}
          disabled={disabled || loading || regions.length === 0}
          aria-label={t('region')}
        >
          <option value="">
            {regions.length === 0 ? t('notApplicable') : `${t('selectRegion')} (${t('optional')})`}
          </option>
          {regions.map(unit => (
            <option key={unit.id} value={unit.id}>{nameOf(unit)}</option>
          ))}
        </select>

        {/* Step 3 — customer service center within the chosen region */}
        <select
          className="form-control"
          value={centerId}
          onChange={handleCenter}
          disabled={disabled || loading || !regionId || centers.length === 0}
          aria-label={t('serviceCenter')}
        >
          <option value="">
            {!regionId
              ? t('selectRegionFirst')
              : centers.length === 0
                ? t('notApplicable')
                : `${t('selectServiceCenter')} (${t('allOfRegion')})`}
          </option>
          {centers.map(unit => (
            <option key={unit.id} value={unit.id}>
              {nameOf(unit)} ({unit.code})
            </option>
          ))}
        </select>
      </div>
    </div>
  );
};

export default OrgUnitSelect;
