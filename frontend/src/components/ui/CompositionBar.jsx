import { useI18n } from '../../context/I18nContext';

/**
 * One proportionally divided bar with a text legend.
 *
 * Extracted from DashboardPage's `LifecycleStrip`: the executive dashboard's
 * plan-completion section needs exactly this shape — a stacked bar per
 * directorate — and a second hand-rolled copy would be two components to keep
 * in step. Plain elements rather than a chart-library stacked bar: they
 * inherit theme tokens and carry real text for screen readers instead of an
 * SVG `title` per slice.
 *
 * @param {object} props
 * @param {{key: string, label: string, count: number, color: string}[]} props.data
 *   Segments in display order. A zero-count segment still renders its legend
 *   row, which is how a reader sees that nothing has completed yet.
 * @param {import('react').ReactNode} [props.footer]  Line under the legend.
 *   Omit for the default "N engagements in scope" summary; pass `null` to
 *   hide it (the executive page labels each row itself).
 */
function CompositionBar({ data, footer }) {
  const { t } = useI18n();
  const total = data.reduce((sum, s) => sum + s.count, 0);
  const summary = data.map(s => `${s.label}: ${s.count}`).join(', ');

  return (
    <div className="lifecycle">
      <div className="lifecycle-bar" role="img" aria-label={summary}>
        {data.map(seg => (
          <span
            key={seg.key}
            className="lifecycle-seg"
            style={{ flexGrow: seg.count, background: seg.color }}
            title={`${seg.label}: ${seg.count}`}
          />
        ))}
      </div>
      <ul className="lifecycle-legend">
        {data.map(seg => (
          <li key={seg.key} className="lifecycle-legend-item">
            <span className="pie-dot" style={{ background: seg.color }} />
            <span className="lifecycle-legend-label">{seg.label}</span>
            <strong className="num">{seg.count}</strong>
            <span className="lifecycle-legend-pct num">
              {total ? Math.round((100 * seg.count) / total) : 0}%
            </span>
          </li>
        ))}
      </ul>
      {footer === undefined ? (
        <p className="lifecycle-total num">{t('engagementsTotal', total)}</p>
      ) : footer}
    </div>
  );
}

export default CompositionBar;