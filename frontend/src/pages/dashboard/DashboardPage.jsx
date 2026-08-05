import React, { useState, useEffect } from 'react';
import { reportsApi, usersApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area
} from 'recharts';
import { TrendingUp, AlertTriangle, FolderKanban, Clock } from 'lucide-react';

const CHART_TOOLTIP_STYLE = { backgroundColor: '#1a2235', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '8px', color: '#f1f5f9', fontSize: '12px' };

function DashboardPage() {
  const toast = useToast();
  const { t } = useI18n();
  const [stats, setStats] = useState({
    activeAudits: 3,
    openFindings: 12,
    overdueActions: 2,
    complianceScore: 92.4,
  });

  const [findingsData] = useState([
    { name: 'Critical', value: 1, color: '#ef4444' },
    { name: 'High', value: 4, color: '#f59e0b' },
    { name: 'Medium', value: 5, color: '#3b82f6' },
    { name: 'Low', value: 2, color: '#10b981' },
  ]);

  const [monthlyAudits] = useState([
    { month: 'Jan', Completed: 2, InProgress: 1 },
    { month: 'Feb', Completed: 1, InProgress: 2 },
    { month: 'Mar', Completed: 3, InProgress: 1 },
    { month: 'Apr', Completed: 2, InProgress: 2 },
    { month: 'May', Completed: 4, InProgress: 3 },
    { month: 'Jun', Completed: 3, InProgress: 2 },
  ]);

  const [complianceTrend] = useState([
    { name: 'Q1 2025', score: 88 },
    { name: 'Q2 2025', score: 89 },
    { name: 'Q3 2025', score: 91 },
    { name: 'Q4 2025', score: 90 },
    { name: 'Q1 2026', score: 92.4 },
  ]);

  const [activities, setActivities] = useState([
    { id: 1, user: 'Tsion Girma', action: 'Created audit finding', target: 'FIND-001 in ERP Security Audit', time: '2 hours ago' },
    { id: 2, user: 'Martha Hailu', action: 'Approved Annual Plan', target: 'EEU Annual Audit Plan 2026', time: '1 day ago' },
    { id: 3, user: 'Kidus Yosef', action: 'Uploaded working paper', target: 'SoD matrix validation document', time: '2 days ago' },
    { id: 4, user: 'Bekele Dejene', action: 'Completed audit procedure', target: 'PROC-001 (SoD Review)', time: '3 days ago' },
  ]);

  useEffect(() => {
    reportsApi.getAnalytics()
      .then(d => {
        if (d) {
          setStats({
            activeAudits: d.active_engagements ?? 3,
            openFindings: d.open_findings ?? 12,
            overdueActions: d.overdue_actions ?? 2,
            complianceScore: d.compliance_score ?? 92.4,
          });
        }
      })
      .catch(() => {/* fallback defaults */ });

    // Fetch recent activity from the audit trail
    usersApi.getAuditTrail({ page_size: 5 })
      .then(res => {
        const items = res.results || (Array.isArray(res) ? res : []);
        if (items.length > 0) {
          setActivities(items.map((log, idx) => ({
            id: log.id || idx,
            user: log.user_name || log.user_email || 'System',
            action: log.action || 'Event',
            target: log.object_repr || log.description || '—',
            time: log.timestamp ? new Date(log.timestamp).toLocaleString() : '—',
          })));
        }
      })
      .catch(() => {/* keep defaults */ });
  }, []);

  return (
    <div className="dashboard-view">

      {/* ── KPI Cards ── */}
      <div className="kpi-grid">
        <StatCard icon={<FolderKanban size={22} />} label={t('activeAudits')} value={stats.activeAudits} sub={t('ongoingEngagements')} color="blue" />
        <StatCard icon={<AlertTriangle size={22} />} label={t('openFindings')} value={stats.openFindings} sub={t('highSeverityItems')} color="orange" />
        <StatCard icon={<Clock size={22} />} label={t('overdueCapas')} value={stats.overdueActions} sub={t('requireEscalation')} color="red" />
        <StatCard icon={<TrendingUp size={22} />} label={t('overallCompliance')} value={`${stats.complianceScore}%`} sub={t('vsLastQuarter')} color="green" />
      </div>

      {/* ── Main Charts Row ── */}
      <div className="charts-row">

        {/* Bar Chart */}
        <div className="chart-box">
          <div className="chart-box-header">
            <h3>{t('auditExecutionStatus')}</h3>
            <span>{t('monthlyCompletedVsActive')}</span>
          </div>
          <div style={{ width: '100%', height: 280 }}>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={monthlyAudits} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="month" stroke="#64748b" tick={{ fontSize: 12 }} />
                <YAxis stroke="#64748b" tick={{ fontSize: 12 }} />
                <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
                <Bar dataKey="Completed" fill="#10b981" radius={[4, 4, 0, 0]} />
                <Bar dataKey="InProgress" fill="#2563eb" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Donut Chart */}
        <div className="chart-box">
          <div className="chart-box-header">
            <h3>{t('findingsBySeverity')}</h3>
            <span>{t('distributionOfOpenFindings')}</span>
          </div>
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
        </div>
      </div>

      {/* ── Bottom Row ── */}
      <div className="charts-row">

        {/* Area Chart */}
        <div className="chart-box">
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
                <YAxis domain={[80, 100]} stroke="#64748b" tick={{ fontSize: 12 }} />
                <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                <Area type="monotone" dataKey="score" stroke="#2563eb" strokeWidth={2} fill="url(#areaGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Activity Feed */}
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

export default DashboardPage;