/**
 * Shared recharts tooltip.
 *
 * Replaces the per-page `contentStyle` objects the dashboard used to pass
 * inline, which hardcoded `backgroundColor: '#1a2235'` — a dark box floating
 * over the light theme. Styling this with Tailwind utilities means it follows
 * the app's theme for free: index.css binds Tailwind's `dark:` variant to
 * `[data-theme="dark"]`, so no theme prop or JS branch is needed here.
 *
 * Recharts injects `active`, `payload` and `label`; everything else is ours.
 */
export const ChartTooltip = ({ active, payload, label, valueFormatter }) => {
  if (!active || !payload?.length) return null;

  return (
    <div className="rounded-lg border border-gray-200 bg-white/95 px-3 py-2 text-xs shadow-lg backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/95 dark:shadow-black/40">
      {label != null && label !== '' && (
        <p className="mb-1.5 font-semibold text-gray-700 dark:text-gray-200">{label}</p>
      )}
      <ul className="flex flex-col gap-1">
        {payload.map(entry => (
          <li key={entry.dataKey ?? entry.name} className="flex items-center gap-2">
            {/* A donut slice carries its colour on the datum, a bar/area series
                on the entry itself; one of the two is always present. */}
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ background: entry.color ?? entry.payload?.color }}
            />
            <span className="text-gray-500 dark:text-gray-400">{entry.name}</span>
            <span className="ml-auto font-semibold tabular-nums text-gray-900 dark:text-gray-100">
              {valueFormatter ? valueFormatter(entry.value, entry) : entry.value}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default ChartTooltip;
