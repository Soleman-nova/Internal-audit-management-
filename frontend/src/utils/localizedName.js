/**
 * Pick the Amharic variant of a name when the interface language is Amharic.
 *
 * Department and directorate names arrive from the API as an English `*_name`
 * plus an `*_name_am`. The org-tree hook resolves names for units that are in
 * the picker, but a record can point at a unit the tree omits — a retired one,
 * say — so the localized choice has to happen at the point of display.
 */
export function localizedName(lang, english, amharic) {
  return lang === 'am' && amharic ? amharic : english;
}

/**
 * Render a record's three organisational scopes as one line.
 *
 * Department, region and service center are independent fields — see
 * OrgUnitSelect — so a record can be "Finance, in Adama Region, at Adama CSC
 * No. 1", or just "Finance". Parts that are unset are dropped rather than
 * rendered as an empty gap, and `fallback` covers the case where none are set.
 */
export function orgScopeLabel(lang, record, fallback = '') {
  if (!record) return fallback;
  const parts = [
    [record.department_name, record.department_name_am],
    [record.region_name, record.region_name_am],
    [record.service_center_name, record.service_center_name_am],
  ]
    .map(([english, amharic]) => localizedName(lang, english, amharic))
    .filter(Boolean);
  return parts.length > 0 ? parts.join(' · ') : fallback;
}

export default localizedName;
