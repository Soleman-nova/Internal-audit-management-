import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { usersApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area
} from 'recharts';
import {
  TrendingUp, AlertTriangle, FolderKanban, Clock, Building2, Filter,
  Inbox, ShieldAlert, ClipboardCheck, ChevronRight
} from 'lucide-react';
import EEUOrgChart from '../../components/EEUOrgChart';

const CHART_TOOLTIP_STYLE = { backgroundColor: '#1a2235', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '8px', color: '#f1f5f9', fontSize: '12px' };

// Severity buckets, worst first, keyed by the backend's AuditFinding.SEVERITY_CHOICES values.
const SEVERITY_META = [
  { key: 'critical', name: 'Critical', color: '#ef4444' },
  { key: 'high', name: 'High', color: '#f59e0b' },
  { key: 'medium', name: 'Medium', color: '#3b82f6' },
  { key: 'low', name: 'Low', color: '#10b981' },
  { key: 'informational', name: 'Informational', color: '#64748b' },
];

// The four directorates the filter switcher offers. IAEO is the parent office —
// scoping to it means "everything", which is what the consolidated option does.
const DIRECTORATE_TYPES = ['FPA', 'TA', 'ITA', 'PP'];

/** Turn the API's [{severity, count}] rows into the donut's {name, value, color} shape. */
function toSeverityChartData(rows) {
  const counts = new Map((rows || []).map(r => [r.severity, r.count]));
  return SEVERITY_META
    .map(meta => ({ name: meta.name, value: counts.get(meta.key) || 0, color: meta.color }))
    .filter(entry => entry.value > 0);
}

function DashboardPage() {
  const toast = useToast();
  const { t } = useI18n();

  // ── Directorate Filter Switcher ──
  // Drives every fetch below: 'all' means the EEU consolidated view.
  const [directorates, setDirectorates] = useState([]);
  const [selectedDirectorate, setSelectedDirectorate] = useState('all');
  const [directorateStats, setDirectorateStats] = useState(null);

  // One bundle for everything the directorate scopes, tagged with the scope it
  // was fetched for. `scope` doubles as the loading signal — while it disagrees
  // with the current selection, a fetch is in flight — which avoids a
  // synchronous setState in the effect body and makes a late response from a
  // previous directorate impossible to render.
  const [scoped, setScoped] = useState({
    scope: null,
    stats: null,
    findingsData: [],
    monthlyAudits: [],
    complianceTrend: [],
    myWork: null,
  });
  const [activities, setActivities] = useState([]);

  const statsLoading = scoped.scope !== selectedDirectorate;
  const { stats, findingsData, monthlyAudits, complianceTrend, myWork } = scoped;

  // Mount-only: the directorate list for the switcher and the enterprise-wide
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
      .catch(() => {/* switcher falls back to the consolidated option only */ });

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

    return () => { cancelled = true; };
  }, []);

  // Refetch every KPI and chart series whenever the directorate changes.
  useEffect(() => {
    let cancelled = false;
    const scope = selectedDirectorate;

    const params = scope === 'all' ? {} : { directorate: scope };
    usersApi.getDashboardStats(params)
      .then(d => {
        if (cancelled) return;
        setScoped({
          scope,
          stats: {
            activeAudits: d.active_engagements ?? 0,
            openFindings: d.open_findings ?? 0,
            overdueActions: d.overdue_actions ?? 0,
            complianceScore: d.compliance_score ?? 0,
          },
          findingsData: toSeverityChartData(d.open_findings_by_severity),
          monthlyAudits: d.monthly_engagements || [],
          complianceTrend: d.compliance_trend || [],
          myWork: d.my_work || null,
        });
      })
      .catch(() => {
        if (cancelled) return;
        toast.error('Failed to load dashboard statistics');
        // Settle on this scope with nothing in it rather than leaving the
        // previous directorate's numbers on screen under a new label.
        setScoped({
          scope, stats: null, findingsData: [], monthlyAudits: [],
          complianceTrend: [], myWork: null,
        });
      });

    return () => { cancelled = true; };
    // toast is stable for the life of the provider; refetching on it would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDirectorate]);

  // Shared by the switcher and the org chart, which can hand us any node in the
  // tree — the IAEO root, a directorate, or a sub-unit beneath one.
  const handleDirectorateSelect = useCallback((dept) => {
    if (!dept || dept.directorate_type === 'IAEO') {
      // IAEO owns every directorate, so scoping to it *is* the consolidated view.
      setSelectedDirectorate('all');
      setDirectorateStats(null);
      return;
    }

    // A sub-unit has no <option> of its own; roll it up to its parent
    // directorate so the select and the data stay in agreement.
    const target = DIRECTORATE_TYPES.includes(dept.directorate_type)
      ? dept
      : directorates.find(d => d.id === dept.parent);

    if (!target) {
      setSelectedDirectorate('all');
      setDirectorateStats(null);
      return;
    }

    setSelectedDirectorate(target.id);
    setDirectorateStats({
      name: target.name,
      code: target.directorate_type,
      head: target.head,
      staffCount: target.staff_count,
    });
  }, [directorates]);

  const handleFilterChange = (e) => {
    const value = e.target.value;
    if (value === 'all') {
      handleDirectorateSelect(null);
    } else {
      const dept = directorates.find(d => d.id === Number(value));
      if (dept) handleDirectorateSelect(dept);
    }
  };

  // Dash while a fetch is in flight and until the first response lands. Never
  // show the previous directorate's numbers under the new one's label — and
  // never substitute a placeholder for a real 0.
  const kpi = (value, suffix = '') => (statsLoading || !stats ? '—' : `${value}${suffix}`);
  // Appended to the class of every box whose data is directorate-scoped, so a
  // switch visibly reads as "working" rather than as "nothing happened".
  const refreshing = statsLoading ? ' is-refreshing' : '';

  return (
    <div className="dashboard-view">

      {/* ── Directorate Filter Switcher ── */}
      <div className="directorate-filter-bar">
        <div className="directorate-filter-label">
          <Filter size={16} />
          <span>{selectedDirectorate === 'all' ? t('enterpriseConsolidatedView') : t('directorateView')}</span>
        </div>
        <select
          className="directorate-filter-select"
          value={selectedDirectorate}
          onChange={handleFilterChange}
          aria-label="Filter by directorate"
        >
          <option value="all">EEU Consolidated Master View</option>
          {directorates.map(d => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
        {directorateStats && (
          <div className="directorate-filter-info">
            <span className="directorate-filter-head">Head: {directorateStats.head}</span>
            <span className="directorate-filter-staff">Staff: {directorateStats.staffCount}</span>
          </div>
        )}
      </div>

      {/* ── KPI Cards ── */}
      <div className={`kpi-grid${refreshing}`} aria-busy={statsLoading}>
        <StatCard icon={<FolderKanban size={22} />} label={t('activeAudits')} value={kpi(stats?.activeAudits)} sub={t('ongoingEngagements')} color="blue" />
        <StatCard icon={<AlertTriangle size={22} />} label={t('openFindings')} value={kpi(stats?.openFindings)} sub={t('highSeverityItems')} color="orange" />
        <StatCard icon={<Clock size={22} />} label={t('overdueCapas')} value={kpi(stats?.overdueActions)} sub={t('requireEscalation')} color="red" />
        {/* The subtitle is "verified closed", not "vs last quarter": the value is
            a point-in-time verified-closure rate, no delta is computed, and only
            findings a CLOSE_FINDINGS holder has signed off count towards it. */}
        <StatCard icon={<TrendingUp size={22} />} label={t('overallCompliance')} value={kpi(stats?.complianceScore, '%')} sub={t('verifiedClosures')} color="green" />
      </div>

      {/* ── My Work ──
          Personal queue, straight from the dashboard payload. It is the only
          block the directorate switcher does not rescope: an auditee's findings
          may sit outside the selected directorate, and hiding them there would
          leave that role staring at an EEU-wide dashboard with nothing on it
          they can act on. */}
      {myWork && (
        <div className="my-work-section">
          <div className="chart-box-header">
            <h3><Inbox size={16} style={{ verticalAlign: 'middle', marginRight: 6 }} />{t('myWork')}</h3>
            <span>{t('myWorkSub')}</span>
          </div>
          <div className="my-work-grid">
            <MyWorkCard
              icon={<ShieldAlert size={16} />}
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
                  <span className="my-work-meta">
                    {f.target_resolution_date || t('noDueDate')}
                  </span>
                  <ChevronRight size={14} className="my-work-chevron" />
                </Link>
              ))}
            </MyWorkCard>

            <MyWorkCard
              icon={<Clock size={16} />}
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
                  <span className={`badge ${a.is_overdue ? 'badge-danger' : 'badge-outline'}`}>
                    {a.due_date}
                  </span>
                  <ChevronRight size={14} className="my-work-chevron" />
                </Link>
              ))}
            </MyWorkCard>

            <MyWorkCard
              icon={<ClipboardCheck size={16} />}
              title={myWork.assessments_are_for_review
                ? t('assessmentsToReview')
                : t('mySelfAssessments')}
              count={myWork.assessments_count}
              empty={t('nothingAssigned')}
            >
              {myWork.assessments.map(s => (
                <Link key={s.id} to="/risk" className="my-work-row">
                  <span className="my-work-title">{s.department || '—'}</span>
                  <span className="my-work-meta">{s.period} {s.year}</span>
                  <span className="badge badge-outline">{s.status?.toUpperCase()}</span>
                  <ChevronRight size={14} className="my-work-chevron" />
                </Link>
              ))}
            </MyWorkCard>
          </div>
        </div>
      )}

      {/* ── Organizational Structure ── */}
      <div className="chart-box org-chart-box">
        <div className="chart-box-header">
          <h3><Building2 size={16} style={{ verticalAlign: 'middle', marginRight: 6 }} />EEU Internal Audit Organizational Structure</h3>
          <span>Executive Office & Directorate Hierarchy — click a card to filter the dashboard</span>
        </div>
        <EEUOrgChart onSelectDirectorate={handleDirectorateSelect} />
      </div>

      {/* ── Main Charts Row ── */}
      <div className="charts-row">

        {/* Bar Chart */}
        <div className={`chart-box${refreshing}`} aria-busy={statsLoading}>
          <div className="chart-box-header">
            <h3>{t('auditExecutionStatus')}</h3>
            <span>{t('monthlyCompletedVsActive')}</span>
          </div>
          <div style={{ width: '100%', height: 280 }}>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={monthlyAudits} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="month" stroke="#64748b" tick={{ fontSize: 12 }} />
                <YAxis stroke="#64748b" tick={{ fontSize: 12 }} allowDecimals={false} />
                <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
                <Bar dataKey="Completed" fill="#10b981" radius={[4, 4, 0, 0]} />
                <Bar dataKey="InProgress" fill="#2563eb" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Donut Chart */}
        <div className={`chart-box${refreshing}`} aria-busy={statsLoading}>
          <div className="chart-box-header">
            <h3>{t('findingsBySeverity')}</h3>
            <span>{t('distributionOfOpenFindings')}</span>
          </div>
          {findingsData.length === 0 ? (
            <div className="chart-empty">
              {statsLoading ? t('loadingDashboard') : t('noOpenFindingsForScope')}
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 24, height: 280 }}>
              <div style={{ width: 180, height: 180, flexShrink: 0 }}>
                <ResponsiveContainer width={180} height={180}>
                  <PieChart>
                    <Pie data={findingsData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={4} dataKey="value">
                      {findingsData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                    </Pie>
                    <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="pie-legend-list">
                {findingsData.map(e => (
                  <div key={e.name} className="pie-legend-item">
                    <span className="pie-dot" style={{ background: e.color }} />
                    <span>{e.name}</span>
                    <strong>{e.value}</strong>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Bottom Row ── */}
      <div className="charts-row">

        {/* Area Chart */}
        <div className={`chart-box${refreshing}`} aria-busy={statsLoading}>
          <div className="chart-box-header">
            <h3>{t('complianceRatingTrend')}</h3>
            <span>{t('quarterlyAuditScoreHistory')}</span>
          </div>
          <div style={{ width: '100%', height: 240 }}>
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={complianceTrend} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#2563eb" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#2563eb" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="name" stroke="#64748b" tick={{ fontSize: 12 }} />
                {/* Full 0-100 range: a single directorate can legitimately sit far
                    below the enterprise average, and the old [80, 100] domain
                    would push its line off the bottom of the chart. */}
                <YAxis domain={[0, 100]} stroke="#64748b" tick={{ fontSize: 12 }} />
                <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                <Area type="monotone" dataKey="score" stroke="#2563eb" strokeWidth={2} fill="url(#areaGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Activity Feed — enterprise-wide, so it is not dimmed on a directorate switch. */}
        <div className="chart-box">
          <div className="chart-box-header">
            <h3>{t('recentSystemActivity')}</h3>
            <span>{t('realTimeAuditTrail')}</span>
          </div>
          <div className="activity-feed">
            {activities.slice(0, 5).map(act => (
              <div key={act.id} className="activity-row">
                <div className="activity-bullet" />
                <div className="activity-body">
                  <p><strong>{act.user}</strong> {act.action} <em>{act.target}</em></p>
                  <span className="activity-ts">{act.time}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, sub, color }) {
  return (
    <div className={`kpi-card kpi-${color}`}>
      <div className={`kpi-icon kpi-icon-${color}`}>{icon}</div>
      <div className="kpi-body">
        <span className="kpi-label">{label}</span>
        <h2 className="kpi-value">{value}</h2>
        <span className="kpi-sub">{sub}</span>
      </div>
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
        <span className="my-work-count">{count ?? 0}</span>
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