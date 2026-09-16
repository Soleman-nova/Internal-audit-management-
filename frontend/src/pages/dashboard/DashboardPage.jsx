import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { usersApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import { hasCapability, getCurrentUser, CAPABILITIES } from '../../hooks/usePermissions';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area,
} from 'recharts';
import {
  TrendingUp, AlertTriangle, FolderKanban, Clock, Inbox, ShieldAlert,
  ClipboardCheck, ChevronRight, RefreshCw, Activity,
} from 'lucide-react';
import DirectorateStrip from '../../components/DirectorateStrip';
import ChartTooltip from '../../components/ui/ChartTooltip';
import EmptyState from '../../components/ui/EmptyState';
import { useChartTheme, toSeverityChartData, toStatusChartData } from '../../utils/chartTheme';

// The four directorates the scope strip offers. IAEO is the parent office —
// scoping to it means "everything", which is what the consolidated option does.
const DIRECTORATE_TYPES = ['FPA', 'TA', 'ITA', 'PP'];

/** Colour a KPI by whether its value needs attention, not by decoration. */
function complianceTone(score) {
  if (score == null) return 'neutral';
  if (score >= 90) return 'ok';
  if (score >= 70) return 'warn';
  return 'alert';
}

function DashboardPage() {
  const toast = useToast();
  const { t } = useI18n();
  const chart = useChartTheme();

  // ── Directorate Scope ──
  // Drives every fetch below: 'all' means the EEU consolidated view.
  const [directorates, setDirectorates] = useState([]);
  const [directoratesLoading, setDirectoratesLoading] = useState(true);
  const [selectedDirectorate, setSelectedDirectorate] = useState('all');

  // One bundle for everything the directorate scopes, tagged with the scope it
  // was fetched for. `scope` doubles as the loading signal — while it disagrees
  // with the current selection, a fetch is in flight — which avoids a
  // synchronous setState in the effect body and makes a late response from a
  // previous directorate impossible to render.
  const [scoped, setScoped] = useState({
    scope: null,
    stats: null,
    statusData: [],
    findingsData: [],
    monthlyAudits: [],
    complianceTrend: [],
    myWork: null,
    error: false,
  });
  const [activities, setActivities] = useState([]);

  const statsLoading = scoped.scope !== selectedDirectorate;
  const { stats, statusData, findingsData, monthlyAudits, complianceTrend, myWork, error } = scoped;

  // The audit trail is gated behind VIEW_AUDIT_TRAIL even for reads, and
  // auditors and auditees hold no such capability — so the feed is neither
  // fetched nor rendered for them, rather than producing a guaranteed 403 on
  // every dashboard load and an empty card on screen.
  const canViewTrail = hasCapability(getCurrentUser(), CAPABILITIES.VIEW_AUDIT_TRAIL);

  // Mount-only: the directorate list for the scope strip and the enterprise-wide
  // activity feed. Neither depends on the selected directorate — the audit trail
  // carries no directorate link, so the feed stays EEU-wide.
  useEffect(() => {
    let cancelled = false;

    // Filtered server-side: the department table is 600+ units deep, so the
    // default first page would not reach the audit directorates.
    usersApi.getDepartments({ unit_type: 'AUDIT' })
      .then(depts => {
        if (cancelled) return;
        const list = (Array.isArray(depts) ? depts : (depts?.results || []))
          .filter(d => DIRECTORATE_TYPES.includes(d.directorate_type));
        setDirectorates(list);
      })
      .catch(() => {/* strip falls back to the consolidated option only */ })
      .finally(() => { if (!cancelled) setDirectoratesLoading(false); });

    if (canViewTrail) {
      usersApi.getAuditTrail({ page_size: 5 })
        .then(res => {
          if (cancelled) return;
          const items = res.results || (Array.isArray(res) ? res : []);
          setActivities(items.map((log, idx) => ({
            id: log.id || idx,
            user: log.user_name || log.user_email || 'System',
            action: log.action || 'Event',
            target: log.object_repr || log.description || '—',
            time: log.timestamp ? new Date(log.timestamp).toLocaleString() : '—',
          })));
        })
        .catch(() => {/* feed stays empty */ });
    }

    return () => { cancelled = true; };
  }, [canViewTrail]);

  // Refetch every KPI and chart series whenever the scope changes.
  const applyScope = useCallback((scope) => {
    const params = scope === 'all' ? {} : { directorate: scope };
    usersApi.getDashboardStats(params)
      .then(d => {
        setScoped({
          scope,
          stats: {
            activeAudits: d.active_engagements ?? 0,
            totalEngagements: d.total_engagements ?? 0,
            openFindings: d.open_findings ?? 0,
            criticalFindings: d.critical_findings ?? 0,
            highFindings: d.high_findings ?? 0,
            overdueActions: d.overdue_actions ?? 0,
            openActions: d.open_actions ?? 0,
            complianceScore: d.compliance_score ?? 0,
            totalFindings: d.total_findings ?? 0,
          },
          statusData: toStatusChartData(d.engagements_by_status, t),
          findingsData: toSeverityChartData(d.open_findings_by_severity, t),
          monthlyAudits: d.monthly_engagements || [],
          complianceTrend: d.compliance_trend || [],
          myWork: d.my_work || null,
          error: false,
        });
      })
      .catch(() => {
        toast.error(t('dashboardLoadError'));
        // Settle on this scope with nothing in it rather than leaving the
        // previous directorate's numbers on screen under a new label.
        setScoped({
          scope, stats: null, statusData: [], findingsData: [], monthlyAudits: [],
          complianceTrend: [], myWork: null, error: true,
        });
      });
  }, [toast, t]);

  useEffect(() => {
    applyScope(selectedDirectorate);
  }, [selectedDirectorate, applyScope]);

  // Shared by the scope strip. It only ever hands us a top-level directorate or
  // null, but the roll-up is kept so any future caller passing a sub-unit still
  // resolves to the directorate that actually owns the data.
  const handleDirectorateSelect = useCallback((dept) => {
    if (!dept || dept.directorate_type === 'IAEO') {
      // IAEO owns every directorate, so scoping to it *is* the consolidated view.
      setSelectedDirectorate('all');
      return;
    }

    const target = DIRECTORATE_TYPES.includes(dept.directorate_type)
      ? dept
      : directorates.find(d => d.id === dept.parent);

    setSelectedDirectorate(target ? target.id : 'all');
  }, [directorates]);

  const refreshing = statsLoading && stats ? ' is-refreshing' : '';

  return (
    <div className="dashboard-view">

      {/* ── A. Scope command bar ── */}
      <DirectorateStrip
        directorates={directorates}
        selected={selectedDirectorate}
        onSelect={handleDirectorateSelect}
        loading={directoratesLoading}
      />

      {/* ── B. KPI band ── */}
      <KpiBand
        stats={stats}
        refreshing={!!refreshing}
        error={error}
        onRetry={() => applyScope(selectedDirectorate)}
      />

      {/* ── C. My Work ──
          Personal queue, straight from the dashboard payload. It is the only
          block the scope strip does not rescope: an auditee's findings may sit
          outside the selected directorate, and hiding them there would leave
          that role staring at an EEU-wide dashboard with nothing on it they can
          act on. */}
      {myWork && (
        <div className="my-work-section">
          <div className="chart-box-header chart-box-header-row">
            <div>
              <h3><Inbox size={15} className="chart-box-header-icon" />{t('myWork')}</h3>
              <span>{t('myWorkSub')}</span>
            </div>
          </div>
          <div className="my-work-grid">
            <MyWorkCard
              icon={<ShieldAlert size={14} />}
              title={t('myFindings')}
              count={myWork.findings_count}
              empty={t('nothingAssigned')}
            >
              {myWork.findings.map(f => (
                <Link key={f.id} to={`/findings/${f.id}`} className="my-work-row">
                  <span className="my-work-ref">{f.finding_number}</span>
                  <span className="my-work-title">{f.title}</span>
                  <span className={`risk-tag tag-xs ${f.severity === 'critical' ? 'critical' : f.severity === 'high' ? 'high' : 'medium'}`}>
                    {f.severity?.toUpperCase()}
                  </span>
                  <span className="my-work-meta num">
                    {f.target_resolution_date || t('noDueDate')}
                  </span>
                  <ChevronRight size={14} className="my-work-chevron" />
                </Link>
              ))}
            </MyWorkCard>

            <MyWorkCard
              icon={<Clock size={14} />}
              title={t('myCapas')}
              count={myWork.actions_count}
              badge={myWork.overdue_actions_count > 0
                ? `${myWork.overdue_actions_count} ${t('overdueLabel')}`
                : null}
              empty={t('nothingAssigned')}
            >
              {myWork.actions.map(a => (
                <Link key={a.id} to={`/capa/${a.id}`} className="my-work-row">
                  <span className="my-work-ref">{a.action_number}</span>
                  <span className="my-work-title">{a.title}</span>
                  <span className={`badge ${a.is_overdue ? 'badge-danger' : 'badge-outline'} num`}>
                    {a.due_date}
                  </span>
                  <ChevronRight size={14} className="my-work-chevron" />
                </Link>
              ))}
            </MyWorkCard>

            <MyWorkCard
              icon={<ClipboardCheck size={14} />}
              title={myWork.assessments_are_for_review
                ? t('assessmentsToReview')
                : t('mySelfAssessments')}
              count={myWork.assessments_count}
              empty={t('nothingAssigned')}
            >
              {myWork.assessments.map(s => (
                <Link key={s.id} to="/risk" className="my-work-row">
                  <span className="my-work-title">{s.department || '—'}</span>
                  <span className="my-work-meta num">{s.period} {s.year}</span>
                  <span className="badge badge-outline">{s.status?.toUpperCase()}</span>
                  <ChevronRight size={14} className="my-work-chevron" />
                </Link>
              ))}
            </MyWorkCard>
          </div>
        </div>
      )}

      {/* ── D. Trend + severity composition ── */}
      <div className="charts-row charts-row-wide">
        <div className={`chart-box${refreshing}`} aria-busy={statsLoading}>
          <div className="chart-box-header">
            <h3>{t('complianceRatingTrend')}</h3>
            <span>{t('quarterlyAuditScoreHistory')}</span>
          </div>
          {complianceTrend.length === 0 ? (
            <div className="chart-canvas chart-canvas-empty">
              <EmptyState
                icon={TrendingUp}
                title={statsLoading ? t('loadingDashboard') : t('noTrendForScope')}
                description={t('noTrendForScopeSub')}
              />
            </div>
          ) : (
            <div className="chart-canvas">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={complianceTrend} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                  <defs>
                    <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#00a651" stopOpacity={chart.areaFrom} />
                      <stop offset="95%" stopColor="#00a651" stopOpacity={chart.areaTo} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={chart.grid} vertical={false} />
                  <XAxis dataKey="name" {...chart.axisProps} />
                  {/* Full 0-100 range: a single directorate can legitimately sit far
                      below the enterprise average, and an [80, 100] domain would
                      push its line off the bottom of the chart. */}
                  <YAxis domain={[0, 100]} {...chart.axisProps} />
                  <Tooltip content={<ChartTooltip valueFormatter={v => `${v}%`} />} />
                  <Area
                    type="monotone"
                    dataKey="score"
                    stroke="#00a651"
                    strokeWidth={2}
                    fill="url(#areaGrad)"
                    dot={false}
                    activeDot={{ r: 4, strokeWidth: 0 }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        <div className={`chart-box${refreshing}`} aria-busy={statsLoading}>
          <div className="chart-box-header">
            <h3>{t('findingsBySeverity')}</h3>
            <span>{t('distributionOfOpenFindings')}</span>
          </div>
          {findingsData.length === 0 ? (
            <div className="chart-canvas chart-canvas-empty">
              <EmptyState
                icon={ShieldAlert}
                title={statsLoading ? t('loadingDashboard') : t('noOpenFindingsForScope')}
                description={t('noOpenFindingsForScopeSub')}
              />
            </div>
          ) : (
            <div className="donut-wrap">
              <div className="donut-canvas">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={findingsData}
                      cx="50%"
                      cy="50%"
                      innerRadius="64%"
                      outerRadius="92%"
                      paddingAngle={2}
                      dataKey="value"
                      stroke="none"
                    >
                      {findingsData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                    </Pie>
                    <Tooltip content={<ChartTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="donut-center">
                  <span className="donut-total num">
                    {findingsData.reduce((sum, e) => sum + e.value, 0)}
                  </span>
                  <span className="donut-total-label">{t('open')}</span>
                </div>
              </div>
              <ul className="pie-legend-list">
                {findingsData.map(e => (
                  <li key={e.name} className="pie-legend-item">
                    <span className="pie-dot" style={{ background: e.color }} />
                    <span>{e.name}</span>
                    <strong className="num">{e.value}</strong>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* ── E. Execution over time + lifecycle composition ── */}
      <div className="charts-row">
        <div className={`chart-box${refreshing}`} aria-busy={statsLoading}>
          <div className="chart-box-header">
            <h3>{t('auditExecutionStatus')}</h3>
            <span>{t('monthlyCompletedVsActive')}</span>
          </div>
          {monthlyAudits.length === 0 ? (
            <div className="chart-canvas chart-canvas-sm chart-canvas-empty">
              <EmptyState
                icon={FolderKanban}
                title={statsLoading ? t('loadingDashboard') : t('noEngagementsForScope')}
                description={t('noEngagementsForScopeSub')}
              />
            </div>
          ) : (
            <>
              <div className="chart-canvas chart-canvas-sm">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={monthlyAudits} margin={{ top: 8, right: 8, left: -18, bottom: 0 }} barGap={2}>
                    <CartesianGrid stroke={chart.grid} vertical={false} />
                    <XAxis dataKey="month" {...chart.axisProps} />
                    <YAxis {...chart.axisProps} allowDecimals={false} />
                    <Tooltip content={<ChartTooltip />} cursor={{ fill: chart.grid }} />
                    {/* `name` is what the tooltip prints — without it recharts
                        falls back to the raw dataKey ("InProgress"). */}
                    <Bar dataKey="Completed" name={t('legendCompleted')} fill="#10b981" radius={[3, 3, 0, 0]} maxBarSize={26} />
                    <Bar dataKey="InProgress" name={t('legendInProgress')} fill="#f2801f" radius={[3, 3, 0, 0]} maxBarSize={26} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <ul className="chart-legend">
                <li><span className="chart-legend-dot" style={{ background: '#10b981' }} />{t('legendCompleted')}</li>
                <li><span className="chart-legend-dot" style={{ background: '#f2801f' }} />{t('legendInProgress')}</li>
              </ul>
            </>
          )}
        </div>

        <div className={`chart-box${refreshing}`} aria-busy={statsLoading}>
          <div className="chart-box-header">
            <h3><Activity size={15} className="chart-box-header-icon" />{t('engagementLifecycle')}</h3>
            <span>{t('engagementLifecycleSub')}</span>
          </div>
          {statusData.length === 0 ? (
            <div className="chart-canvas chart-canvas-sm chart-canvas-empty">
              <EmptyState
                icon={FolderKanban}
                title={statsLoading ? t('loadingDashboard') : t('noEngagementsForScope')}
                description={t('noEngagementsForScopeSub')}
              />
            </div>
          ) : (
            <LifecycleStrip data={statusData} />
          )}
        </div>
      </div>

      {/* ── F. Activity feed — enterprise-wide, so it is not dimmed on a scope change. ── */}
      {canViewTrail && (
        <div className="chart-box">
          <div className="chart-box-header">
            <h3>{t('recentSystemActivity')}</h3>
            <span>{t('realTimeAuditTrail')}</span>
          </div>
          {activities.length === 0 ? (
            <EmptyState
              icon={Inbox}
              title={t('noActivityTitle')}
              description={t('noActivityData')}
            />
          ) : (
            <ul className="timeline timeline-scroll">
              {activities.slice(0, 5).map(act => (
                <li key={act.id} className="timeline-item">
                  <span className="timeline-time num">{act.time}</span>
                  <span className="timeline-title">{act.user}</span>
                  <span className="timeline-desc">
                    {act.action} <em>{act.target}</em>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * The four headline metrics on a single hairline-divided surface.
 *
 * Three states, deliberately distinct: a first load with no data yet shows
 * skeletons, a scope change over existing data dims it, and a failed fetch
 * shows a persistent retry block — the old version rendered `—` for all three,
 * so a dead backend was indistinguishable from a slow one and the toast was
 * the only signal, long after it had faded.
 */
function KpiBand({ stats, refreshing, error, onRetry }) {
  const { t } = useI18n();

  if (!stats) {
    return error ? (
      <div className="kpi-band kpi-band-error">
        <AlertTriangle size={18} className="kpi-band-error-icon" />
        <div className="kpi-band-error-body">
          <strong>{t('dashboardLoadError')}</strong>
          <span>{t('dashboardLoadErrorSub')}</span>
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>
          <RefreshCw size={13} />{t('retry')}
        </button>
      </div>
    ) : (
      <div className="kpi-band" aria-busy="true">
        {[0, 1, 2, 3].map(i => (
          <div key={i} className="kpi-cell">
            <span className="skeleton skeleton-line skeleton-line-short" />
            <span className="skeleton skeleton-num" />
            <span className="skeleton skeleton-line" />
          </div>
        ))}
      </div>
    );
  }

  const openFindingsTone = stats.criticalFindings > 0
    ? 'alert'
    : stats.highFindings > 0 ? 'warn' : 'neutral';

  const cells = [
    {
      key: 'activeAudits',
      icon: FolderKanban,
      tone: 'neutral',
      label: t('activeAudits'),
      value: stats.activeAudits,
      sub: t('ofTotalEngagements', stats.totalEngagements),
    },
    {
      key: 'openFindings',
      icon: AlertTriangle,
      tone: openFindingsTone,
      label: t('openFindings'),
      value: stats.openFindings,
      sub: t('openFindingsSub', stats.criticalFindings, stats.highFindings),
    },
    {
      key: 'overdueCapas',
      icon: Clock,
      // Only flags when there is something to escalate — which is what makes
      // the colour mean anything.
      tone: stats.overdueActions > 0 ? 'alert' : 'neutral',
      label: t('overdueCapas'),
      value: stats.overdueActions,
      sub: t('overdueActionsSub', stats.openActions),
    },
    {
      key: 'overallCompliance',
      icon: TrendingUp,
      tone: complianceTone(stats.complianceScore),
      label: t('overallCompliance'),
      value: stats.complianceScore,
      suffix: '%',
      // The denominator, not a delta: the value is a point-in-time
      // verified-closure rate and the backend computes no previous period, so
      // any "vs last quarter" here would be invented.
      sub: t('complianceSub', stats.totalFindings),
    },
  ];

  return (
    <div className={`kpi-band${refreshing ? ' is-refreshing' : ''}`} aria-busy={refreshing}>
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

/**
 * Engagement lifecycle as one proportionally divided bar.
 *
 * Hand-rolled rather than a second donut chart: it is compact enough to share a
 * row, and plain elements mean the segments inherit theme tokens and carry real
 * text labels for screen readers instead of an SVG `title` per slice.
 */
function LifecycleStrip({ data }) {
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
      <p className="lifecycle-total num">{t('engagementsTotal', total)}</p>
    </div>
  );
}

/** One column of the My Work panel: a heading with a count, then up to five rows.
 *
 * `count` is the full total from the server while `children` is the capped list,
 * so "12" above five rows is expected rather than a bug — the count and the
 * overdue badge are what tell the user there is more behind the linked page.
 */
function MyWorkCard({ icon, title, count, badge, empty, children }) {
  const rows = React.Children.toArray(children);
  return (
    <div className="my-work-card">
      <div className="my-work-card-header">
        <h4>{icon} {title}</h4>
        <span className="my-work-count num">{count ?? 0}</span>
        {badge && <span className="badge badge-danger">{badge}</span>}
      </div>
      {rows.length === 0 ? (
        <p className="my-work-empty">
          <Inbox size={14} /> {empty}
        </p>
      ) : (
        <div className="my-work-rows">{rows}</div>
      )}
    </div>
  );
}

export default DashboardPage;
