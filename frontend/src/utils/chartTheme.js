/**
 * Chart colour and axis constants, in one place.
 *
 * Recharts renders `fill` / `stroke` as SVG presentation attributes, where
 * `var(--token)` does not resolve — so the palette has to exist as literal
 * strings here as well as in index.css, and only one of the two can be the
 * source of truth. This module is it; the `--sev-*` / `--st-*` custom
 * properties in index.css mirror these values for the parts of the dashboard
 * that are styled in CSS (the lifecycle strip, the legends).
 *
 * Kept theme-aware via {@link useChartTheme}: the old module-level constants
 * were dark-only, which made the gridlines invisible on white and left a dark
 * tooltip floating over the light theme.
 */
import { useContext } from 'react';
import AuthContext from '../context/AuthContext';

/** Severity buckets for AuditFinding.SEVERITY_CHOICES, worst first.
 *
 * `labelKey` points at the shared status vocabulary in I18nContext rather than
 * carrying an English string, so the donut legend translates with the rest of
 * the page instead of staying English on an Amharic screen. */
export const SEVERITY_META = [
  { key: 'critical', labelKey: 'critical', color: '#ef4444' },
  { key: 'high', labelKey: 'high', color: '#f59e0b' },
  { key: 'medium', labelKey: 'medium', color: '#3b82f6' },
  { key: 'low', labelKey: 'low', color: '#10b981' },
  { key: 'informational', labelKey: 'informational', color: '#64748b' },
];

/** Engagement lifecycle, in progression order for the composition strip. */
export const STATUS_META = [
  { key: 'planned', labelKey: 'planned', color: '#64748b' },
  { key: 'in_progress', labelKey: 'inProgress', color: '#f2801f' },
  { key: 'fieldwork', labelKey: 'fieldwork', color: '#3b82f6' },
  { key: 'reporting', labelKey: 'reporting', color: '#8b5cf6' },
  { key: 'completed', labelKey: 'completed', color: '#10b981' },
  { key: 'cancelled', labelKey: 'cancelled', color: '#475569' },
];

/** Shared axis treatment: no axis line, no tick marks, muted tick labels. */
const axisPropsFor = (axis) => ({
  stroke: axis,
  tick: { fill: axis, fontSize: 11 },
  tickLine: false,
  axisLine: false,
});

const DARK = {
  grid: 'rgba(255, 255, 255, 0.06)',
  axis: '#64748b',
  axisProps: axisPropsFor('#64748b'),
  areaFrom: 0.18,
  areaTo: 0,
};

const LIGHT = {
  grid: 'rgba(15, 23, 42, 0.08)',
  axis: '#94a3b8',
  axisProps: axisPropsFor('#94a3b8'),
  areaFrom: 0.16,
  areaTo: 0,
};

/** Theme-aware chart constants.
 *
 * Reads the raw context rather than calling `useAuth()`, which throws when no
 * provider is mounted — a `useContext` on a missing provider just returns null,
 * so this degrades to the dark palette instead of taking the chart down.
 */
export function useChartTheme() {
  const auth = useContext(AuthContext);
  return auth?.theme === 'light' ? LIGHT : DARK;
}

/** Turn the API's [{severity, count}] rows into the donut's shape.
 *
 * `t` is the i18n translator; the label is resolved here so the chart and its
 * legend read in the active language. */
export function toSeverityChartData(rows, t) {
  const counts = new Map((rows || []).map(r => [r.severity, r.count]));
  return SEVERITY_META
    .map(meta => ({
      key: meta.key,
      name: t(meta.labelKey),
      value: counts.get(meta.key) || 0,
      color: meta.color,
    }))
    .filter(entry => entry.value > 0);
}

/** Turn the API's [{status, count}] rows into ordered lifecycle segments. */
export function toStatusChartData(rows, t) {
  const counts = new Map((rows || []).map(r => [r.status, r.count]));
  return STATUS_META
    .map(meta => ({
      key: meta.key,
      label: t(meta.labelKey),
      count: counts.get(meta.key) || 0,
      color: meta.color,
    }))
    .filter(entry => entry.count > 0);
}
