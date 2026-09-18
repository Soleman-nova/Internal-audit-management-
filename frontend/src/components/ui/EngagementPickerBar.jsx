import { useEffect, useId, useMemo, useState } from 'react';
import { planningApi } from '../../api';
import { useI18n } from '../../context/I18nContext';
import { localizedName } from '../../utils/localizedName';
import OrgUnitSelect from './OrgUnitSelect';

/**
 * Scope bar for choosing an audit engagement: department → entity → engagement,
 * with the plan that engagement belongs to read back beneath it.
 *
 * A flat list of every engagement stops working at a few dozen rows — the
 * engagement number is the only thing distinguishing "ENG-0041 — Q1 Payroll
 * Compliance Audit" from "ENG-0042 — Q1 Payroll Compliance Audit". The three
 * steps narrow by the audited unit instead, which is how an auditor thinks
 * about the record they want.
 *
 * Three rules this bar follows, each of which is a way the naive version fails:
 *
 *   Nothing is gated. Every step stays enabled and populated from the start, so
 *   an engagement can be reached in whatever order the user knows it —
 *   department → entity → engagement, or engagement directly. A disabled
 *   downstream <select> forces one order and hides the answer from someone who
 *   already knows it.
 *
 *   Selecting an entity back-fills the scope it carries, but only into steps
 *   that are still empty. Filling a step the user already set would silently
 *   undo a deliberate choice; leaving them empty would make the two directions
 *   inconsistent. An entity's own `department`/`region`/`service_center` is
 *   independent of the others (see OrgUnitSelect), so all three can be filled
 *   from one pick.
 *
 *   The chosen engagement never disappears. A filter that excludes the record
 *   already selected would blank the field, and the next save would write that
 *   blank back over real data — the same trap OrgUnitSelect handles for retired
 *   units. It is appended to the list rather than filtered out.
 *
 * The scope narrows on *any* of the three steps matching, not all of them: an
 * engagement registered against the region alone would otherwise vanish the
 * moment a department was named. With nothing chosen the scope matches
 * everything, so the bar starts as three plain lists.
 *
 * Props:
 *   engagements   every engagement the caller may choose from (the page already
 *                 loads these; this component does not fetch them)
 *   value         selected engagement id
 *   onChange      called with the new engagement id (string)
 *   label         heading for the engagement step; callers pass their own
 *                 wording because Execution says "active" and the rest do not
 *   idPrefix      stable prefix for the four control ids
 *   disabled      disables the engagement step (the scope steps stay live)
 *   className     extra classes on the wrapper
 */

const toId = (v) => (v == null ? '' : String(v));

const EMPTY_SCOPE = { department: '', region: '', service_center: '' };

// One fetch per page load, shared by whichever pages mount the bar. Same
// pattern as the org-tree hook, for the same reason: this is reference data.
let cachedUniversePromise = null;

function fetchUniverse() {
  if (!cachedUniversePromise) {
    cachedUniversePromise = planningApi
      .getUniverse()
      .then((page) => (Array.isArray(page?.items) ? page.items : []))
      .catch((err) => {
        // Don't cache a failure — the next mount should get a fresh attempt.
        cachedUniversePromise = null;
        throw err;
      });
  }
  return cachedUniversePromise;
}

/**
 * True when a record shares any of the chosen scope steps.
 *
 * Each step is only consulted if it was chosen, and an entity or engagement
 * with that field unset simply doesn't match that step — it can still match on
 * the other two. Department, region and service center are independent fields
 * rather than a strict hierarchy, so this is a union, not a drill-down.
 */
function matchesScope(record, scope) {
  if (!scope.department && !scope.region && !scope.service_center) return true;
  return Boolean(
    (scope.department && toId(record.department) === scope.department) ||
    (scope.region && record.region && toId(record.region) === scope.region) ||
    (scope.service_center && record.service_center && toId(record.service_center) === scope.service_center),
  );
}

/**
 * An engagement's scope, falling back to the entity it audits.
 *
 * Engagements created before the scope columns existed have them unset while
 * their entity has them filled, so reading only the engagement's own fields
 * would hide exactly the older records this bar is meant to make findable.
 */
function engagementScope(engagement, entityById) {
  const entity = engagement.audit_universe
    ? entityById.get(toId(engagement.audit_universe))
    : null;
  return {
    department: engagement.department ?? entity?.department ?? null,
    region: engagement.region ?? entity?.region ?? null,
    service_center: engagement.service_center ?? entity?.service_center ?? null,
  };
}

export const EngagementPickerBar = ({
  engagements = [],
  value = '',
  onChange,
  label,
  idPrefix,
  disabled = false,
  className = '',
}) => {
  const { t, lang } = useI18n();

  const [entities, setEntities] = useState([]);
  const [entitiesLoading, setEntitiesLoading] = useState(true);
  const [scope, setScope] = useState(EMPTY_SCOPE);
  const [entityId, setEntityId] = useState('');

  useEffect(() => {
    let cancelled = false;
    fetchUniverse()
      .then((list) => {
        if (!cancelled) setEntities(list);
      })
      .catch(() => {
        // The bar degrades to a plain engagement list — the scope steps just
        // have nothing to narrow. Not worth a toast over a filter aid.
        if (!cancelled) setEntities([]);
      })
      .finally(() => {
        if (!cancelled) setEntitiesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const generatedId = useId();
  const prefix = idPrefix || generatedId;
  const entitySelectId = `${prefix}_entity`;
  const engagementSelectId = `${prefix}_engagement`;

  const entityById = useMemo(
    () => new Map(entities.map((u) => [toId(u.id), u])),
    [entities],
  );

  const visibleEntities = useMemo(
    () => entities.filter((u) => matchesScope(u, scope)),
    [entities, scope],
  );

  const visibleEngagements = useMemo(() => {
    const filtered = engagements.filter((e) => {
      if (entityId && toId(e.audit_universe) !== entityId) return false;
      return matchesScope(engagementScope(e, entityById), scope);
    });
    // Keep the selection in the list even when it falls outside the filter.
    const current = engagements.find((e) => toId(e.id) === toId(value));
    if (current && !filtered.some((e) => toId(e.id) === toId(value))) {
      return [current, ...filtered];
    }
    return filtered;
  }, [engagements, entityById, entityId, scope, value]);

  const selectedEntity = entityId ? entityById.get(entityId) : null;
  const selectedEngagement = engagements.find((e) => toId(e.id) === toId(value)) || null;

  // "2026 — Annual Payroll Plan", or just whichever half the API returned.
  const planLabel = selectedEngagement
    ? [selectedEngagement.plan_year, selectedEngagement.plan_title].filter(Boolean).join(' — ')
    : '';

  // Name the scope steps straight from the selected entity when the org tree
  // doesn't carry them, so a back-filled step never renders as a bare "#id".
  const scopeValueLabels = selectedEntity
    ? {
        department: localizedName(lang, selectedEntity.department_name, selectedEntity.department_name_am) || '',
        region: localizedName(lang, selectedEntity.region_name, selectedEntity.region_name_am) || '',
        service_center:
          localizedName(lang, selectedEntity.service_center_name, selectedEntity.service_center_name_am) || '',
      }
    : {};

  const handleScopeChange = (changes) => {
    const next = { ...scope, ...changes };
    setScope(next);
    // The entity pick narrows a list rather than holding data, so one the new
    // scope excludes is dropped — otherwise the engagement list is empty with
    // nothing on screen explaining which of the two filters caused it.
    const entity = entityId ? entityById.get(entityId) : null;
    if (entity && !matchesScope(entity, next)) setEntityId('');
  };

  const handleEntityChange = (e) => {
    const next = e.target.value;
    setEntityId(next);
    const entity = next ? entityById.get(next) : null;
    if (!entity) return;
    // Back-fill only the steps still unset — see the note on picking order.
    setScope((prev) => ({
      department: prev.department || toId(entity.department),
      region: prev.region || toId(entity.region),
      service_center: prev.service_center || toId(entity.service_center),
    }));
  };

  return (
    <div className={`engagement-picker ${className}`}>
      <OrgUnitSelect
        idPrefix={`${prefix}_scope`}
        label={t('department')}
        split
        value={scope}
        onFieldChange={handleScopeChange}
        valueLabels={scopeValueLabels}
      />

      <div className="form-group">
        <label className="form-label" htmlFor={entitySelectId}>{t('entity')}</label>
        <select
          id={entitySelectId}
          className="form-control"
          value={entityId}
          onChange={handleEntityChange}
          disabled={entitiesLoading}
        >
          <option value="">{t('allEntities')}</option>
          {selectedEntity && !visibleEntities.some((u) => toId(u.id) === entityId) && (
            <option value={entityId}>{selectedEntity.code} - {selectedEntity.name}</option>
          )}
          {visibleEntities.map((u) => (
            <option key={u.id} value={u.id}>{u.code} - {u.name}</option>
          ))}
        </select>
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor={engagementSelectId}>
          {label || t('selectAuditEngagement')}
        </label>
        <select
          id={engagementSelectId}
          className="form-control"
          value={value}
          onChange={(e) => onChange && onChange(e.target.value)}
          disabled={disabled}
        >
          {visibleEngagements.length === 0 && (
            <option value="">{t('noMatchingEngagements')}</option>
          )}
          {visibleEngagements.map((e) => (
            <option key={e.id} value={e.id}>{e.engagement_number} - {e.title}</option>
          ))}
        </select>
        {planLabel && (
          <p className="engagement-picker-plan">
            {t('plan')}: <strong>{planLabel}</strong>
          </p>
        )}
      </div>
    </div>
  );
};

export default EngagementPickerBar;
