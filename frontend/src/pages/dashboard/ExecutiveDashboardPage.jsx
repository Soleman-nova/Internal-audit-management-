import { useEffect, useMemo, useState } from 'react';
import {
  AreaChart, Area, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts';
import { usersApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import useAsyncData from '../../hooks/useAsyncData';
import DirectorateStrip from '../../components/DirectorateStrip';
import CompositionBar from '../../components/ui/CompositionBar';
import ChartTooltip from '../../components/ui/ChartTooltip';
import EmptyState from '../../components/ui/EmptyState';
import Spinner from '../../components/ui/Spinner';
import { useChartTheme, STATUS_META } from '../../utils/chartTheme';
import {
  Activity, AlertTriangle, ClipboardCheck, Clock, FolderKanban,
  RefreshCw, Repeat, Target, TrendingUp,
} from 'lucide-react';

// The directorates the scope strip offers — same list the operational
// dashboard uses. IAEO is the parent office, so scoping to it *is* "every-
// thing", which is what the consolidated option does.
const DIRECTORATE_TYPES = ['FPA', 'TA', 'ITA', 'PP'];

/** How many plan years the year select offers. A plan catalogue is a handful
 * of years deep — a rolling window keeps this page to one request. */
const YEAR_WINDOW = 5;

/** Age buckets, sequential in one amber hue: magnitude over an ordered scale,
 * so light reads "young" and dark reads "old". The count sits beside every bar
 * in ink tokens, so colour is never the only channel. */
const AGING_COLORS = {
  0: '#fef3c7',
  30: '#fde68a',
  60: '#f59e0b',
  90: '#b45309',
};

/** i18n key per bucket start, so the labels translate with the page. */
const AGING_LABEL_KEYS = {
  0: 'execAge0',
  30: 'execAge30',
  60: 'execAge60',
  90: 'execAge90',
};

/** One hue for every engagement-progress meter: they are all the same
 * measure, so a categorical palette would imply differences that are not
 * there. `#f2801f` is STATUS_META's in_progress orange, and the track is the
 * same hue at low alpha — the pattern the auditor-performance meter uses. */
const PROGRESS_HUE = '#f2801f';

const statusColor = (key) => STATUS_META.find((meta) => meta.key === key)?.color || '#64748b';

/** Rate → tone, the same thresholds the operational dashboard's compliance KPI
 * uses, so 90% looks identical on both screens. */
function rateTone(rate) {
  if (rate >= 90) return 'ok';
  if (rate >= 70) return 'warn';
  return 'alert';
}

function ExecutiveDashboardPage() {
  const toast = useToast();
  const { t } = useI18n();
  const chart = useChartTheme();

  const [directorates, setDirectorates] = useState([]);
  const [directoratesLoading, setDirectoratesLoading] = useState(true);
  const [selectedDirectorate, setSelectedDirectorate] = useState('all');
  const [year, setYear] = useState(() => String(new Date().getFullYear()));

  const currentYear = new Date().getFullYear();
  const yearOptions = useMemo(
    () => Array.from({ length: YEAR_WINDOW }, (_, i) => String(currentYear - i)),
    [currentYear],
  );

  // Mount-only: the directorate list for the scope strip. Filtered server-side
  // like the dashboard does — the department table is 600+ units deep.
  useEffect(() => {
    let cancelled = false;
    usersApi.getDepartments({ unit_type: 'AUDIT', parent__directorate_type: 'IAEO' })
      .then((depts) => {
        if (cancelled) return;
        // Keep only the four core directorates (FPA, TA, ITA, PP).
        // region == null excludes regional sub-units (e.g. "Adama Region FPA")
        // that share the same directorate_type as a top-level directorate.
        const list = (Array.isArray(depts) ? depts : (depts?.results || []))
          .filter((d) => DIRECTORATE_TYPES.includes(d.directorate_type) && d.region == null);
        setDirectorates(list);
      })
      .catch(() => {/* strip falls back to the consolidated option only */})
      .finally(() => { if (!cancelled) setDirectoratesLoading(false); });
    return () => { cancelled = true; };
  }, []);

  // Race-safe on filter changes: a slow response for a scope the reader has
  // already left is dropped rather than rendered under the new labels.
  const { data, loading, error, reload } = useAsyncData(
    () => usersApi.getExecutiveStats({
      year,
      ...(selectedDirectorate === 'all' ? {} : { directorate: selectedDirectorate }),
    }),
    [selectedDirectorate, year],
    { onError: () => toast.error(t('dashboardLoadError')) },
  );

  const firstLoad = data === null && loading;
  const refreshing = data !== null && loading ? ' is-refreshing' : '';

  const handleDirectorateSelect = (dept) => {
    if (!dept || dept.directorate_type === 'IAEO') {
      setSelectedDirectorate('all');
      return;
    }
    const target = DIRECTORATE_TYPES.includes(dept.directorate_type)
      ? dept
      : directorates.find((d) => d.id === dept.parent);
    setSelectedDirectorate(target ? target.id : 'all');
  };

  const pc = data?.plan_completion;
  const ep = data?.engagement_progress;
  const aging = data?.findings_aging;
  const trend = data?.compliance_trend ?? [];
  // A zero-count bucket must still be measurable, hence the Math.max(1, …).
  const maxAging = Math.max(1, ...(aging?.buckets ?? []).map((b) => b.count));

  const planSegments = (row) => ([
    { key: 'completed', label: t('legendCompleted'), count: row.completed, color: statusColor('completed') },
    { key: 'in_progress', label: t('legendInProgress'), count: row.in_progress, color: statusColor('in_progress') },
    { key: 'not_started', label: t('legendNotStarted'), count: row.not_started, color: statusColor('planned') },
  ]);

  return (
    <div className="dashboard-view">
      {/* ── Scope strip + plan year — the two filters every section reads ── */}
      <DirectorateStrip
        directorates={directorates}
        selected={selectedDirectorate}
        onSelect={handleDirectorateSelect}
        loading={directoratesLoading}
      />

      <div className="exec-filters">
        <div className="form-group">
          <label className="form-label" htmlFor="exec_year">{t('apPlanYear')}</label>
          <select
            id="exec_year"
            className="form-control"
            value={year}
            onChange={(e) => setYear(e.target.value)}
          >
            {yearOptions.map((y) => <option key={y} value={y}>{y}</option>)}
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

      {error && !data ? (
        <div className="kpi-band kpi-band-error">
          <AlertTriangle size={18} className="kpi-band-error-icon" />
          <div className="kpi-band-error-body">
            <strong>{t('dashboardLoadError')}</strong>
            <span>{t('dashboardLoadErrorSub')}</span>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={reload}>
            <RefreshCw size={13} />{t('retry')}
          </button>
        </div>
      ) : firstLoad || !data ? (
        <div className="flex items-center justify-center min-h-[40vh]">
          <Spinner size="lg" />
        </div>
      ) : (
        <>
          <ExecutiveKpiBand data={data} refreshing={refreshing !== ''} />

          {/* ── Plan completion + engagement progress ── */}
          <div className="charts-row">
            <div className={`chart-box${refreshing}`} aria-busy={loading}>
              <div className="chart-box-header">
                <h3><Target size={15} className="chart-box-header-icon" />{t('execPlanByDirectorate')}</h3>
                <span>{t('execPlanByDirectorateSub')}</span>
              </div>
              {!pc || pc.by_directorate.length === 0 ? (
                <div className="chart-canvas chart-canvas-empty">
                  <EmptyState
                    icon={Target}
                    title={t('execNoPlanData')}
                    description={t('execNoPlanDataSub')}
                  />
                </div>
              ) : (
                <div className="chart-canvas exec-plan-list">
                  {pc.by_directorate.map((row) => (
                    <div key={row.id} className="exec-plan-row">
                      <div className="exec-plan-row-head">
                        <span className="exec-plan-name">{row.name}</span>
                        {/* The rate never stands alone: `2 / 3 · 66.7%` is a
                            weaker claim than `0 / 3 · 0%` only if the reader
                            cannot see the denominator. */}
                        <span className="exec-plan-rate num">
                          {row.completed} / {row.planned} · {row.rate}%
                        </span>
                      </div>
                      <CompositionBar data={planSegments(row)} footer={null} />
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className={`chart-box${refreshing}`} aria-busy={loading}>
              <div className="chart-box-header">
                <h3><FolderKanban size={15} className="chart-box-header-icon" />{t('execEngagementProgress')}</h3>
                <span>{t('execEngagementProgressSub')}</span>
              </div>
              {!ep || !ep.has_program ? (
                <div className="chart-canvas chart-canvas-empty">
                  <EmptyState
                    icon={FolderKanban}
                    title={t('execNoProgram')}
                    description={t('execNoProgramSub')}
                  />
                </div>
              ) : (
                <div className="chart-canvas exec-meter-list">
                  <p className="exec-overall num">
                    <span>{t('execProceduresDone', ep.overall.procedures_done, ep.overall.procedures_total)}</span>
                    <strong>{ep.overall.rate}%</strong>
                  </p>
                  {ep.items.map((item) => (
                    <div key={item.engagement_number} className="exec-meter">
                      <div className="exec-meter-head">
                        <span className="exec-meter-title">{item.title}</span>
                        <span className="num">{item.rate}%</span>
                      </div>
                      <span className="exec-meter-track" style={{ background: `${PROGRESS_HUE}26` }}>
                        <span
                          className="exec-meter-fill"
                          style={{ width: `${item.rate}%`, background: PROGRESS_HUE }}
                        />
                      </span>
                      <div className="exec-meter-meta num">
                        {item.directorate || '—'} · {t('apPlannedEnd')}: {item.planned_end || '—'}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* ── Findings aging + compliance trend ── */}
          <div className="charts-row">
            <div className={`chart-box${refreshing}`} aria-busy={loading}>
              <div className="chart-box-header">
                <h3><Clock size={15} className="chart-box-header-icon" />{t('execAgingTitle')}</h3>
                <span>{t('execAgingSub')}</span>
              </div>
              {!aging || aging.live_findings === 0 ? (
                <div className="chart-canvas chart-canvas-empty">
                  <EmptyState
                    icon={Clock}
                    title={t('execNoLiveFindings')}
                    description={t('execNoLiveFindingsSub')}
                  />
                </div>
              ) : (
                <div className="chart-canvas exec-aging">
                  <p className="exec-aging-summary num">
                    {t('execAgingSummary', aging.overdue_findings, aging.overdue_pct)}
                  </p>
                  {aging.buckets.map((b) => (
                    <div key={b.days} className="exec-aging-row">
                      <span className="exec-aging-label">
                        {t(AGING_LABEL_KEYS[b.days] || 'execAge90')}
                      </span>
                      <span className="exec-aging-track">
                        <span
                          className="exec-aging-fill"
                          style={{
                            width: `${(100 * b.count) / maxAging}%`,
                            background: AGING_COLORS[b.days] || '#f59e0b',
                          }}
                        />
                      </span>
                      <span className="exec-aging-count num">{b.count}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className={`chart-box${refreshing}`} aria-busy={loading}>
              <div className="chart-box-header">
                <h3>{t('complianceRatingTrend')}</h3>
                <span>{t('quarterlyAuditScoreHistory')}</span>
              </div>
              {trend.length === 0 ? (
                <div className="chart-canvas chart-canvas-empty">
                  <EmptyState
                    icon={Activity}
                    title={t('noTrendForScope')}
                    description={t('noTrendForScopeSub')}
                  />
                </div>
              ) : (
                <div className="chart-canvas">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={trend} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                      <defs>
                        {/* Unique gradient id: the operational dashboard renders
                            the same shape under its own id, and two elements
                            sharing one id resolve to whichever came first. */}
                        <linearGradient id="execAreaGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#00a651" stopOpacity={chart.areaFrom} />
                          <stop offset="95%" stopColor="#00a651" stopOpacity={chart.areaTo} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke={chart.grid} vertical={false} />
                      <XAxis dataKey="name" {...chart.axisProps} />
                      {/* Full 0-100 range: a single directorate can sit far
                          below the enterprise average. */}
                      <YAxis domain={[0, 100]} {...chart.axisProps} />
                      <Tooltip content={<ChartTooltip valueFormatter={(v) => `${v}%`} />} />
                      <Area
                        type="monotone"
                        dataKey="score"
                        stroke="#00a651"
                        strokeWidth={2}
                        fill="url(#execAreaGrad)"
                        dot={false}
                        activeDot={{ r: 4, strokeWidth: 0 }}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/**
 * The six leadership tiles on one hairline-divided surface.
 *
 * Same markup and tone rules as the operational dashboard's KPI band — the
 * two screens sit next to each other in the nav, and a tile that changed
 * shape between them would read as a different kind of number. Every rate
 * carries its denominator in the sub-line for the same reason: a bare
 * percentage cannot distinguish `0 / 12` from `0 / 0`.
 */
function ExecutiveKpiBand({ data, refreshing }) {
  const { t } = useI18n();

  const pc = data.plan_completion ?? {};
  const aging = data.findings_aging ?? {};
  const capa = data.capa ?? {};
  const repeat = data.repeat_findings ?? {};

  const cells = [
    {
      key: 'planCompletion',
      icon: Target,
      tone: rateTone(pc.rate ?? 0),
      label: t('planCompletion'),
      value: pc.rate ?? 0,
      suffix: '%',
      sub: t('planCompletionSub', pc.completed ?? 0, pc.total_planned ?? 0),
    },
    {
      key: 'overallCompliance',
      icon: TrendingUp,
      tone: rateTone(data.compliance_score ?? 0),
      label: t('overallCompliance'),
      value: data.compliance_score ?? 0,
      suffix: '%',
      // The denominator, not a delta: the backend computes no previous period.
      sub: t('complianceSub', data.total_findings ?? 0),
    },
    {
      key: 'openFindings',
      icon: AlertTriangle,
      tone: (aging.overdue_findings ?? 0) > 0 ? 'warn' : 'neutral',
      label: t('openFindings'),
      value: data.open_findings ?? 0,
      sub: t('execOpenFindingsSub', aging.overdue_findings ?? 0),
    },
    {
      key: 'overdueFindings',
      icon: Clock,
      // Only flags when there is something to escalate — which is what makes
      // the colour mean anything.
      tone: (aging.overdue_findings ?? 0) > 0 ? 'alert' : 'neutral',
      label: t('overdueFindings'),
      value: aging.overdue_findings ?? 0,
      sub: t('overdueFindingsSub', aging.overdue_pct ?? 0),
    },
    {
      key: 'capaImplementation',
      icon: ClipboardCheck,
      tone: rateTone(capa.rate ?? 0),
      label: t('capaImplementation'),
      value: capa.rate ?? 0,
      suffix: '%',
      sub: t('capaImplementationSub', capa.implemented ?? 0, capa.total ?? 0),
    },
    {
      key: 'repeatRate',
      icon: Repeat,
      tone: (repeat.rate ?? 0) > 0 ? 'warn' : 'neutral',
      label: t('repeatRate'),
      value: repeat.rate ?? 0,
      suffix: '%',
      sub: t('repeatRateSub', repeat.total ?? 0),
    },
  ];

  return (
    <div className={`kpi-band kpi-band-6${refreshing ? ' is-refreshing' : ''}`} aria-busy={refreshing}>
      {cells.map(cell => {
        const Icon = cell.icon;
        return (
          <div key={cell.key} className={`kpi-cell kpi-cell-${cell.tone}`}>
            <span className="kpi-cell-head">
              <Icon size={14} className="kpi-cell-icon" />
              <span className="kpi-label">{cell.label}</span>
            </span>
            <span className="kpi-value num">
              {cell.value}{cell.suffix || ''}
            </span>
            <span className="kpi-sub num">{cell.sub}</span>
          </div>
        );
      })}
    </div>
  );
}

export default ExecutiveDashboardPage;