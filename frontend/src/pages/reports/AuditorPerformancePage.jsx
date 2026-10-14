import { useMemo, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { planningApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import useAsyncData from '../../hooks/useAsyncData';
import ChartTooltip from '../../components/ui/ChartTooltip';
import EmptyState from '../../components/ui/EmptyState';
import Spinner from '../../components/ui/Spinner';
import { useChartTheme, STATUS_META } from '../../utils/chartTheme';
import { ChevronDown, RefreshCw, Users, Award } from 'lucide-react';

/** The one hue every bar in the ranking carries.
 *
 * A ranking is *magnitude*: the bars are all the same measure, so they get one
 * colour. Ramping the hue darker-where-bigger would re-encode bar length as
 * colour — the reader loses nothing and the chart spends its only free channel
 * restating what the bar already shows. `#10b981` is the `completed` green from
 * `STATUS_META`, so the chart and the status vocabulary agree.
 *
 * Validated against both surfaces: it clears 3:1 on the dark surface and lands
 * at 2.47 on the light one, which is a WARN requiring visible relief — the
 * x-axis and the table beside the chart are exactly that, so no value is
 * reachable only through the colour.
 */
const COMPLETED_HUE = '#10b981';

/** Workload is a second single-series mark, so it takes one hue too.
 *
 * The status palette could not be used here. `validate_palette.js` puts
 * `#3b82f6` (fieldwork) and `#8b5cf6` (reporting) at ΔE 1.3 under deuteranopia
 * and 12.0 with normal vision — below the 15 floor that secondary encoding does
 * *not* excuse. A stacked strip was the original plan for this column and it
 * would have been read as one colour. One hue, one meaning instead: in flight.
 */
const IN_FLIGHT_HUE = '#f2801f';

/** How many years the filter offers. The endpoint scopes by the *plan's* year,
 * and a plan catalogue is a handful of years deep — a rolling window keeps this
 * page to one request. A year with no work simply returns an empty roster. */
const YEAR_WINDOW = 5;

const ROLE_LABEL_KEYS = {
  admin: 'apRoleAdmin',
  audit_manager: 'apRoleAuditManager',
  supervisor: 'apRoleSupervisor',
  auditor: 'apRoleAuditor',
  auditee: 'apRoleAuditee',
};

/** A count that renders `—` rather than a misleading `0`.
 *
 * Only for columns where zero means "nothing to say" (days planned, findings
 * raised). `completed` and `in_flight` show a real 0: there, zero is the
 * finding, not the absence of one. */
const orDash = (value) => (value ? value : '—');

/** Axis labels are truncated, not clipped. The table below carries the full
 * name and is the artifact of record, so the chart only has to be scannable. */
const axisLabel = (name) => (name.length > 22 ? `${name.slice(0, 21)}…` : name);

function AuditorPerformancePage() {
  const toast = useToast();
  const { t } = useI18n();
  const chart = useChartTheme();

  const [year, setYear] = useState('all');
  const [expanded, setExpanded] = useState(() => new Set());

  const currentYear = new Date().getFullYear();
  const yearOptions = useMemo(
    () => Array.from({ length: YEAR_WINDOW }, (_, i) => currentYear - i),
    [currentYear],
  );

  const { data, loading, reload } = useAsyncData(
    () => planningApi.getAuditorPerformance(year === 'all' ? {} : { year }),
    [year],
    { onError: () => toast.error(t('apLoadFailed')) },
  );

  const auditors = useMemo(() => data?.auditors ?? [], [data]);
  // Everyone with at least one completed engagement, which is what the chart
  // ranks. The table still lists the rest — a roster that hides the people
  // carrying in-flight work would be a strange thing to call a performance page.
  const ranked = useMemo(
    () => auditors.filter(a => a.completed > 0),
    [auditors],
  );
  // The meter needs a scale, and the busiest person is the honest one.
  const maxInFlight = useMemo(
    () => auditors.reduce((max, a) => Math.max(max, a.in_flight), 0),
    [auditors],
  );

  const toggle = (id) => setExpanded((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });

  // Only the *first* load may blank the page. A filter change or a refresh dims
  // the previous render instead — the same `is-refreshing` treatment the
  // dashboard uses for a scope change — so the layout never jumps under the
  // reader and a slow refetch is visibly slow rather than invisible.
  const firstLoad = data === null && loading;
  const refreshing = data !== null && loading ? ' is-refreshing' : '';

  const statusMeta = (key) => STATUS_META.find(meta => meta.key === key);

  return (
    <div className="planning-view">
      <div className="card-header">
        <div>
          <h2>{t('auditorPerformance')}</h2>
          <p className="text-muted text-sm">{t('auditorPerformanceSub')}</p>
        </div>
      </div>

      {/* One filter row above everything it scopes. There are no filters inside
          the chart card or the table card — both read the same slice. */}
      <div className="ap-filters">
        <div className="form-group">
          <label className="form-label" htmlFor="ap_year">{t('apPlanYear')}</label>
          <select
            id="ap_year"
            className="form-control"
            value={year}
            onChange={(e) => setYear(e.target.value)}
          >
            <option value="all">{t('apAllTime')}</option>
            {yearOptions.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <button
          type="button"
          className="btn btn-outline flex items-center gap-1"
          onClick={reload}
          disabled={loading}
        >
          <RefreshCw size={14} /> {t('refresh')}
        </button>
      </div>

      {firstLoad ? (
        <div className="flex items-center justify-center min-h-[40vh]"><Spinner size="lg" /></div>
      ) : (
        <>
          {/* ── The ranking, as a shape ─────────────────────────────────── */}
          <div className={`chart-box${refreshing}`} aria-busy={refreshing !== ''}>
            <div className="chart-box-header">
              <h3><Award size={15} className="chart-box-header-icon" />{t('apCompletedRanking')}</h3>
              <span>{t('apCompletedRankingSub')}</span>
            </div>
            {ranked.length === 0 ? (
              <div className="chart-canvas chart-canvas-sm chart-canvas-empty">
                <EmptyState
                  icon={Award}
                  title={t('apNothingCompleted')}
                  description={t('apNothingCompletedSub')}
                />
              </div>
            ) : (
              /* The container grows with the roster rather than taking a fixed
                 height — a fixed one would either cram twenty people into a
                 220px plot or clip the axis band off the bottom. */
              <div className="chart-canvas" style={{ height: Math.max(220, ranked.length * 26) }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={ranked}
                    layout="vertical"
                    margin={{ top: 8, right: 16, left: 8, bottom: 0 }}
                  >
                    <CartesianGrid stroke={chart.grid} horizontal={false} />
                    {/* Value on x, people on y — horizontal because the
                        categories are names, which read left-to-right. */}
                    <XAxis type="number" allowDecimals={false} {...chart.axisProps} />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={150}
                      tickFormatter={axisLabel}
                      {...chart.axisProps}
                    />
                    <Tooltip content={<ChartTooltip />} cursor={{ fill: chart.grid }} />
                    {/* One series, so no legend box: the card's title already
                        says what is plotted. The value sits on the axis and in
                        the table, not on every bar. */}
                    <Bar
                      dataKey="completed"
                      name={t('apCompleted')}
                      fill={COMPLETED_HUE}
                      radius={[0, 4, 4, 0]}
                      maxBarSize={24}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* ── The same data, as numbers ───────────────────────────────── */}
          <div className={`card${refreshing}`} aria-busy={refreshing !== ''}>
            <div className="card-header justify-between">
              <h3><Users size={16} /> {t('apRoster')}</h3>
              <span className="text-xs text-muted">{t('apRosterCount', auditors.length)}</span>
            </div>

            {auditors.length === 0 ? (
              <EmptyState
                icon={Users}
                title={t('apNoAuditors')}
                description={t('apNoAuditorsSub')}
              />
            ) : (
              <div className="table-responsive mt-4">
                <table className="table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>{t('apAuditor')}</th>
                      <th>{t('apRole')}</th>
                      <th>{t('apDepartment')}</th>
                      <th title={t('apLedHint')}>{t('apLed')}</th>
                      <th title={t('apWorkedOnHint')}>{t('apWorkedOn')}</th>
                      <th>{t('apCompleted')}</th>
                      <th>{t('apInFlight')}</th>
                      <th title={t('apOnTimeHint')}>{t('apOnTime')}</th>
                      <th>{t('apFindings')}</th>
                      <th>{t('apPlannedDays')}</th>
                      <th aria-label={t('apExpand')} />
                    </tr>
                  </thead>
                  <tbody>
                    {auditors.map((person, index) => {
                      const isOpen = expanded.has(person.id);
                      return [
                        <tr
                          key={person.id}
                          className={isOpen ? 'row-expanded' : undefined}
                        >
                          <td className="num text-muted">{index + 1}</td>
                          <td>
                            <strong>{person.name}</strong>
                          </td>
                          <td className="text-muted">
                            {t(ROLE_LABEL_KEYS[person.role] || 'apRoleAuditor')}
                          </td>
                          <td className="text-muted ap-dept">{orDash(person.department)}</td>
                          {/* Led and worked-on are separate columns on purpose.
                              Seeded data has the directorate head as lead,
                              supervisor *and* team member on every engagement,
                              so a single combined figure would hide the shape of
                              who the work is actually attributed to. */}
                          <td className="num">{person.led}</td>
                          <td className="num">{person.total}</td>
                          <td className="num">{person.completed}</td>
                          <td>
                            <div className="ap-workload">
                              {/* One hue, one meaning. The track is a lighter
                                  step of the same ramp, and the number is
                                  present so the mark is never the only read. */}
                              <span
                                className="ap-workload-track"
                                style={{ background: `${IN_FLIGHT_HUE}26` }}
                              >
                                <span
                                  className="ap-workload-fill"
                                  style={{
                                    width: maxInFlight
                                      ? `${(100 * person.in_flight) / maxInFlight}%`
                                      : 0,
                                    background: IN_FLIGHT_HUE,
                                  }}
                                />
                              </span>
                              <span className="num">{person.in_flight}</span>
                            </div>
                          </td>
                          {/* The rate never stands alone. `3 / 4 · 75%` is a
                              weaker claim than `9 / 9 · 100%`, and a bare
                              percentage cannot tell the two apart. */}
                          <td className="num ap-ontime">
                            {person.on_time.total === 0 ? (
                              <span className="text-muted" title={t('apNoDatedWork')}>—</span>
                            ) : (
                              <>
                                {person.on_time.met} / {person.on_time.total}
                                <span className="text-muted"> · {person.on_time_rate}%</span>
                              </>
                            )}
                          </td>
                          <td className="num">{orDash(person.findings)}</td>
                          <td className="num">{orDash(person.planned_days)}</td>
                          <td>
                            <button
                              type="button"
                              className="btn btn-outline btn-sm"
                              onClick={() => toggle(person.id)}
                              aria-expanded={isOpen}
                              aria-controls={`ap-engagements-${person.id}`}
                              title={t('apExpand')}
                            >
                              <ChevronDown
                                size={14}
                                style={{
                                  transform: isOpen ? 'rotate(180deg)' : undefined,
                                  transition: 'transform 150ms',
                                }}
                              />
                            </button>
                          </td>
                        </tr>,
                        isOpen && (
                          <tr key={`${person.id}-detail`}>
                            <td colSpan={12} id={`ap-engagements-${person.id}`}>
                              {/* The status breakdown belongs here, in a table,
                                  rather than in a stacked strip on the row: six
                                  classes carrying meaning is past the point a
                                  colour stack can be read, and two of those six
                                  hues are indistinguishable anyway. */}
                              <div className="ap-detail">
                                <ul className="ap-status-tally">
                                  {STATUS_META.map(meta => (
                                    <li key={meta.key}>
                                      <span
                                        className="pie-dot"
                                        style={{ background: meta.color }}
                                      />
                                      <span>{t(meta.labelKey)}</span>
                                      <strong className="num">
                                        {person.by_status[meta.key] || 0}
                                      </strong>
                                    </li>
                                  ))}
                                </ul>

                                {person.engagements.length === 0 ? (
                                  <p className="text-muted text-sm">{t('apNoEngagements')}</p>
                                ) : (
                                  <div className="table-responsive">
                                    <table className="table table-sm">
                                      <thead>
                                        <tr>
                                          <th>{t('apEngagementNumber')}</th>
                                          <th>{t('apEngagementTitle')}</th>
                                          <th>{t('status')}</th>
                                          <th>{t('apPlannedEnd')}</th>
                                          <th>{t('apActualEnd')}</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {person.engagements.map(eng => {
                                          const meta = statusMeta(eng.status);
                                          return (
                                            <tr key={eng.id}>
                                              <td className="num">{eng.number}</td>
                                              <td>{eng.title}</td>
                                              <td>
                                                {/* Dot plus label: the status is
                                                    legible without the colour. */}
                                                <span className="ap-status">
                                                  <span
                                                    className="pie-dot"
                                                    style={{ background: meta?.color }}
                                                  />
                                                  {meta ? t(meta.labelKey) : eng.status}
                                                </span>
                                              </td>
                                              <td className="num">{orDash(eng.planned_end)}</td>
                                              <td className="num">{orDash(eng.actual_end)}</td>
                                            </tr>
                                          );
                                        })}
                                      </tbody>
                                    </table>
                                  </div>
                                )}
                              </div>
                            </td>
                          </tr>
                        ),
                      ];
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default AuditorPerformancePage;
