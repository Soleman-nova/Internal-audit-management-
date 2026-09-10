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

export default localizedName;
