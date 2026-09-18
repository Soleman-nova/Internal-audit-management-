import React, { useId } from 'react';
import { useI18n } from '../../context/I18nContext';
import { useOrgUnits } from '../../hooks/useOrgUnits';

/**
 * Organisational-unit picker: department, region, service center.
 *
 * EEU's corporate structure is three levels deep (chief office → region →
 * customer service center) and 600+ units in total, so a single flat <select>
 * is unusable. This narrows the choice in three steps.
 *
 * Two modes:
 *
 *   Single value (the default) — ``value`` is one department id and the three
 *   steps are a cascade over that single foreign key. Region and service center
 *   are reachable at any time, and picking one *supersedes* the step-one
 *   department rather than being recorded alongside it, because one key can
 *   only point at one unit. Used where the answer genuinely is one unit — an
 *   audit plan's owning directorate, say.
 *
 *   Split (``split``) — ``value`` is ``{ department, region, service_center }``
 *   and the three steps are independent fields. Nothing is superseded: Finance
 *   can sit alongside Adama Region and Adama CSC No. 1, which is the whole
 *   point, and picking a region leaves the department alone.
 *
 * In both modes every step is derived from ``value`` rather than held in local
 * state, so the component is fully controlled and cannot drift out of sync
 * with the form.
 *
 * Props:
 *   value          one department id (default), or ``{ department, region,
 *                  service_center }`` when ``split`` is set
 *   onChange       single mode: called with the new id (string) or '' when cleared
 *   split          switches to three independent fields
 *   onFieldChange  split mode: called with an object of the fields that changed,
 *                  e.g. ``{ region: '5', service_center: '' }``. Always spread
 *                  it into the previous state — a region change can carry the
 *                  service center with it.
 *   label          field label; defaults to the translated "Department"
 *   required       marks step one required
 *   disabled       disables all three steps
 *   valueLabel     single mode: name to show when ``value`` points at a unit
 *                  missing from the tree — a retired one, say — so editing
 *                  cannot silently drop it
 *   valueLabels    split mode: the same, keyed by field name
 *   idPrefix       optional stable prefix for the three selects' ids; a
 *                  ``useId()`` value is generated when omitted. Callers pass one
 *                  so the ids match the rest of their form's ``<field>_<name>``
 *                  convention.
 */

// Step one flattens the non-geographic side of the tree. A literal
// CEO → child → grandchild walk would bury the audit directorates under
// Internal Audit → IAEO and hide them, and most auditors are assigned there.
const TOP_LEVEL_TYPES = ['EXECUTIVE', 'CORPORATE', 'AUDIT'];

// Order of the flat <optgroup>s in step one, most general first. The CORPORATE
// units are not a single flat group — each chief office becomes its own optgroup
// (built below) and follows these two in the list.
const GROUP_ORDER = ['EXECUTIVE', 'AUDIT', 'CORPORATE'];

const GROUP_LABELS = {
  EXECUTIVE: { en: 'Executive Office', am: 'የሥራ አስፈጻሚ ጽሕፈት ቤት' },
  AUDIT: { en: 'Internal Audit', am: 'ውስጣዊ ኦዲት' },
  CORPORATE: { en: 'Chief Offices', am: 'ዋና ጽሕፈት ቤቶች' },
};

const toId = (v) => (v == null ? '' : String(v));

export const OrgUnitSelect = ({
  value,
  onChange,
  split = false,
  onFieldChange,
  label,
  required = false,
  disabled = false,
  valueLabel = '',
  valueLabels = {},
  className = '',
  idPrefix,
}) => {
  const { t, lang } = useI18n();
  const { units, byId, childrenOf, ancestorsOf, loading, error } = useOrgUnits();

  // One visible label above three controls, so it is bound to step one and the
  // three are wrapped in a named group; steps two and three keep their own
  // aria-label. Without an id here the label was decorative — clicking it did
  // nothing and no control had an accessible name from it.
  const generatedId = useId();
  const prefix = idPrefix || generatedId;
  const departmentSelectId = `${prefix}_department`;

  // ── Current values, per mode ─────────────────────────────────────────────
  // Single mode resolves all three from the one stored id; split mode reads
  // them straight off the object it was handed.
  const scope = split && value && typeof value === 'object' ? value : null;
  const selectedId = split ? toId(scope?.department) : toId(value);

  const singleKnown = !split && selectedId !== '' && byId.has(selectedId);

  // `value` resolves to nothing we can show — a retired unit, which the tree
  // endpoint excludes on purpose. Keep it selected instead of blanking the
  // field, so opening and saving an old record doesn't wipe it.
  const isOrphan = (id) => id !== '' && !byId.has(id) && !loading;

  let departmentId = split ? toId(scope?.department) : '';
  let regionId = split ? toId(scope?.region) : '';
  let centerId = split ? toId(scope?.service_center) : '';

  if (!split) {
    const chain = singleKnown ? ancestorsOf(selectedId) : [];
    const departmentUnit = [...chain].reverse().find(u => TOP_LEVEL_TYPES.includes(u.unit_type));
    const regionUnit = chain.find(u => u.unit_type === 'REGION');
    const centerUnit = chain.find(u => u.unit_type === 'SERVICE_CENTER');
    departmentId = departmentUnit ? String(departmentUnit.id) : '';
    regionId = regionUnit ? String(regionUnit.id) : '';
    centerId = centerUnit ? String(centerUnit.id) : '';
  }

  const singleOrphan = !split && selectedId !== '' && !singleKnown && !loading;

  const labelFor = (field) =>
    (split ? valueLabels[field] : '') || (field === 'department' ? valueLabel : '') || `#${toId(scope?.[field])}`;

  const nameOf = (unit) => (lang === 'am' && unit.name_am ? unit.name_am : unit.name);

  // ── Options per step ────────────────────────────────────────────────────
  const topLevel = units.filter(u => TOP_LEVEL_TYPES.includes(u.unit_type));

  // Step one flat groups cover the handful of executive and audit units; the
  // CORPORATE group is built separately because it is now hundreds deep once
  // the detailed head-office chart is seeded.
  const flatGroups = GROUP_ORDER
    .filter(type => type !== 'CORPORATE')
    .map(type => ({
      key: type,
      type,
      label: GROUP_LABELS[type][lang] || GROUP_LABELS[type].en,
      options: topLevel
        .filter(u => u.unit_type === type)
        .sort((a, b) => nameOf(a).localeCompare(nameOf(b))),
    }))
    .filter(group => group.options.length > 0);

  // The top-level chief office a CORPORATE unit sits under: the highest unit in
  // its chain whose parent is the executive root (or is unset). Finance is its
  // own group heading; CO Treasury, CO Budget Control, ... group beneath it.
  const topOfficeOf = (unit) => {
    let current = unit;
    while (current) {
      const parent = current.parent == null ? null : byId.get(String(current.parent));
      if (!parent || parent.unit_type === 'EXECUTIVE') return current;
      current = parent;
    }
    return unit;
  };

  // Group every CORPORATE unit under its top-level office so the head-office
  // dropdown stays navigable instead of one flat ~150-row list. Each optgroup
  // holds that office plus its CORPORATE descendants at any depth.
  const corporateGroups = Array.from(
    units
      .filter(u => u.unit_type === 'CORPORATE')
      .reduce((groupMap, unit) => {
        const top = topOfficeOf(unit);
        const key = top ? String(top.id) : '__root__';
        if (!groupMap.has(key)) groupMap.set(key, { top, members: [] });
        groupMap.get(key).members.push(unit);
        return groupMap;
      }, new Map()).values(),
  )
    .map(group => ({
      key: group.top ? `corporate-${group.top.id}` : 'corporate-root',
      type: 'CORPORATE',
      label: group.top ? nameOf(group.top) : (GROUP_LABELS.CORPORATE[lang] || GROUP_LABELS.CORPORATE.en),
      options: group.members
        .slice()
        .sort((a, b) => nameOf(a).localeCompare(nameOf(b))),
    }))
    .filter(group => group.options.length > 0)
    .sort((a, b) => a.label.localeCompare(b.label));

  const groups = [...flatGroups, ...corporateGroups];

  // Every region, independent of the step-one choice. Regions are never filtered
  // by department: they all hang off Region Coordination, so gating them on step
  // one hid every region from the other eighteen chief offices.
  const regions = units
    .filter(u => u.unit_type === 'REGION')
    .sort((a, b) => nameOf(a).localeCompare(nameOf(b)));

  // Sorted by code, not name: service-center names repeat across regions and a
  // few are placeholders ('CSC'), so the code is the reliable ordering key.
  const centers = childrenOf(regionId, 'SERVICE_CENTER')
    .slice()
    .sort((a, b) => a.code.localeCompare(b.code));

  // ── Change handlers ─────────────────────────────────────────────────────
  // Single mode: picking a region or a center replaces whatever step one held:
  // one foreign key can only point at one unit, and the deeper one is the more
  // specific.
  const handleDepartment = (e) => onChange(e.target.value);
  const handleRegion = (e) => onChange(e.target.value || departmentId);
  const handleCenter = (e) => onChange(e.target.value || regionId);

  // Split mode: each step writes its own field and nothing else, except that a
  // service center belongs to exactly one region — changing the region clears a
  // center that no longer sits under it, rather than storing a contradictory pair.
  const handleDepartmentSplit = (e) => onFieldChange({ department: e.target.value });

  const handleRegionSplit = (e) => {
    const nextRegion = e.target.value;
    const stillUnder = nextRegion !== '' && centerId !== '' &&
      childrenOf(nextRegion, 'SERVICE_CENTER').some(c => String(c.id) === centerId);
    onFieldChange({ region: nextRegion, service_center: stillUnder ? centerId : '' });
  };

  const handleCenterSplit = (e) => onFieldChange({ service_center: e.target.value });

  if (error) {
    return (
      <div className={`form-group ${className}`}>
        <label className="form-label" htmlFor={departmentSelectId}>{label || t('department')}</label>
        <p className="org-unit-select-error">{t('orgStructureError')}</p>
      </div>
    );
  }

  const departmentValue = split ? departmentId : (singleOrphan ? selectedId : departmentId);
  const departmentOrphan = split ? isOrphan(departmentId) : singleOrphan;
  const regionOrphan = split && isOrphan(regionId);
  const centerOrphan = split && isOrphan(centerId);

  return (
    <div className={`form-group ${className}`}>
      <label className="form-label" htmlFor={departmentSelectId}>{label || t('department')}</label>

      <div className="org-unit-select" role="group" aria-label={label || t('department')}>
        {/* Step 1 — chief office, executive office, or audit directorate. In
            split mode this is the record's own department and is never touched
            by steps two and three. */}
        <select
          id={departmentSelectId}
          className="form-control"
          value={departmentValue}
          onChange={split ? handleDepartmentSplit : handleDepartment}
          required={required}
          disabled={disabled || loading}
        >
          <option value="">{loading ? t('loadingStructure') : t('selectDepartment')}</option>
          {departmentOrphan && (
            <option value={departmentId}>
              {labelFor('department')} ({t('retiredUnit')})
            </option>
          )}
          {groups.map(group => (
            <optgroup key={group.key} label={group.label}>
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
          id={`${prefix}_region`}
          className="form-control"
          value={regionId}
          onChange={split ? handleRegionSplit : handleRegion}
          disabled={disabled || loading || regions.length === 0}
          aria-label={t('region')}
        >
          <option value="">
            {regions.length === 0 ? t('notApplicable') : `${t('selectRegion')} (${t('optional')})`}
          </option>
          {regionOrphan && (
            <option value={regionId}>{labelFor('region')} ({t('retiredUnit')})</option>
          )}
          {regions.map(unit => (
            <option key={unit.id} value={unit.id}>{nameOf(unit)}</option>
          ))}
        </select>

        {/* Step 3 — customer service center within the chosen region */}
        <select
          id={`${prefix}_service_center`}
          className="form-control"
          value={centerId}
          onChange={split ? handleCenterSplit : handleCenter}
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
          {centerOrphan && (
            <option value={centerId}>{labelFor('service_center')} ({t('retiredUnit')})</option>
          )}
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
