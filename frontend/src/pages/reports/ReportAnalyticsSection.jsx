import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';
import {
  FileText, CheckCircle2, Clock, AlertTriangle,
  TrendingUp, BarChart2, PieChart as PieIcon,
} from 'lucide-react';
import { useI18n } from '../../context/I18nContext';
import { useChartTheme } from '../../utils/chartTheme';
import ChartTooltip from '../../components/ui/ChartTooltip';
import EmptyState from '../../components/ui/EmptyState';

const STATUS_COLORS = {
  ready: '#10b981',
  generating: '#f59e0b',
  failed: '#ef4444',
};

const DIRECTORATE_COLORS = {
  FPA: '#10b981',
  TA: '#f59e0b',
  ITA: '#8b5cf6',
  PP: '#00a651',
  OTHER: '#64748b',
};

export function ReportAnalyticsSection({ analytics, loading }) {
  const { t } = useI18n();
  const chart = useChartTheme();

  if (loading && !analytics) {
    return (
      <div className="report-analytics-section">
        <div className="kpi-band" aria-busy="true">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="kpi-cell">
              <span className="skeleton skeleton-line skeleton-line-short" />
              <span className="skeleton skeleton-num" />
              <span className="skeleton skeleton-line" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!analytics) return null;

  const totalReports = analytics.total_reports ?? 0;
  const statusCounts = (analytics.reports_by_status || []).reduce((acc, curr) => {
    acc[curr.status] = curr.count;
    return acc;
  }, {});

  const readyCount = statusCounts['ready'] || 0;
  const generatingCount = statusCounts['generating'] || 0;
  const failedCount = statusCounts['failed'] || 0;

  const monthlyReports = analytics.monthly_reports || [];

  const directorateData = (analytics.reports_by_directorate || []).map((d) => ({
    name: d['engagement__directorate__name'] || d['engagement__directorate__directorate_type'] || 'Other',
    code: d['engagement__directorate__directorate_type'] || 'OTHER',
    count: d.count,
    color: DIRECTORATE_COLORS[d['engagement__directorate__directorate_type']] || '#64748b',
  }));

  const statusPieData = [
    { name: t('ready') || 'Ready', value: readyCount, color: STATUS_COLORS.ready },
    { name: t('generating') || 'Generating', value: generatingCount, color: STATUS_COLORS.generating },
    { name: t('failed') || 'Failed', value: failedCount, color: STATUS_COLORS.failed },
  ].filter((item) => item.value > 0);

  const kpis = [
    {
      key: 'total',
      icon: FileText,
      label: t('totalReportsCompiled') || 'Total Reports',
      value: totalReports,
      tone: 'neutral',
      sub: t('allTimeOrFiltered') || 'In current view',
    },
    {
      key: 'ready',
      icon: CheckCircle2,
      label: t('readyForDownload') || 'Ready to Download',
      value: readyCount,
      tone: 'ok',
      sub: `${totalReports > 0 ? Math.round((readyCount / totalReports) * 100) : 0}% ${t('ofTotal') || 'of total'}`,
    },
    {
      key: 'generating',
      icon: Clock,
      label: t('compiling') || 'Compiling in Background',
      value: generatingCount,
      tone: generatingCount > 0 ? 'warn' : 'neutral',
      sub: t('processingQueue') || 'Active generation jobs',
    },
    {
      key: 'failed',
      icon: AlertTriangle,
      label: t('generationFailed') || 'Compilation Failed',
      value: failedCount,
      tone: failedCount > 0 ? 'alert' : 'neutral',
      sub: t('needsRetry') || 'Check error details',
    },
  ];

  return (
    <div className="report-analytics-section">
      {/* ── KPI Band ── */}
      <div className="kpi-band mb-4">
        {kpis.map((kpi) => {
          const Icon = kpi.icon;
          return (
            <div key={kpi.key} className={`kpi-cell kpi-cell-${kpi.tone}`}>
              <span className="kpi-cell-head">
                <Icon size={14} className="kpi-cell-icon" />
                <span className="kpi-label">{kpi.label}</span>
              </span>
              <span className="kpi-value num">{kpi.value}</span>
              <span className="kpi-sub num">{kpi.sub}</span>
            </div>
          );
        })}
      </div>

      {/* ── Visual Analytics Charts ── */}
      <div className="charts-row">
        {/* Monthly Reports Trend */}
        <div className="chart-box">
          <div className="chart-box-header">
            <h3><TrendingUp size={15} className="chart-box-header-icon" />{t('reportsCompiledTrend') || 'Reports Compiled Over Time'}</h3>
            <span>{t('monthlyReportVolume') || 'Monthly production volume (last 6 months)'}</span>
          </div>
          {monthlyReports.length === 0 ? (
            <div className="chart-canvas chart-canvas-sm chart-canvas-empty">
              <EmptyState
                icon={BarChart2}
                title={t('noReportsHistory') || 'No compilation history'}
                description={t('reportsAppearWhenCompiled') || 'Compiled reports will appear here.'}
              />
            </div>
          ) : (
            <div className="chart-canvas chart-canvas-sm">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={monthlyReports} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                  <CartesianGrid stroke={chart.grid} vertical={false} />
                  <XAxis dataKey="month" {...chart.axisProps} />
                  <YAxis {...chart.axisProps} allowDecimals={false} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: chart.grid }} />
                  <Bar
                    dataKey="count"
                    name={t('reportsLabel') || 'Reports'}
                    fill="#00a651"
                    radius={[4, 4, 0, 0]}
                    maxBarSize={32}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* Directorate Distribution or Status Split */}
        <div className="chart-box">
          <div className="chart-box-header">
            <h3><PieIcon size={15} className="chart-box-header-icon" />{t('reportsByDirectorate') || 'Reports by Directorate'}</h3>
            <span>{t('distributionAcrossUnits') || 'Audit directorate volume'}</span>
          </div>
          {directorateData.length === 0 && statusPieData.length === 0 ? (
            <div className="chart-canvas chart-canvas-sm chart-canvas-empty">
              <EmptyState
                icon={PieIcon}
                title={t('noDistributionData') || 'No distribution data'}
                description={t('compileReportsToSeeDistribution') || 'Reports distribution will display here.'}
              />
            </div>
          ) : (
            <div className="donut-wrap">
              <div className="donut-canvas">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={directorateData.length > 0 ? directorateData : statusPieData}
                      cx="50%"
                      cy="50%"
                      innerRadius="60%"
                      outerRadius="90%"
                      paddingAngle={2}
                      dataKey={directorateData.length > 0 ? 'count' : 'value'}
                      stroke="none"
                    >
                      {(directorateData.length > 0 ? directorateData : statusPieData).map((entry, i) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip content={<ChartTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="donut-center">
                  <span className="donut-total num">{totalReports}</span>
                  <span className="donut-total-label">{t('reports') || 'Reports'}</span>
                </div>
              </div>
              <ul className="pie-legend-list">
                {(directorateData.length > 0 ? directorateData : statusPieData).map((e) => (
                  <li key={e.name} className="pie-legend-item">
                    <span className="pie-dot" style={{ background: e.color }} />
                    <span className="text-xs truncate max-w-[140px]">{e.name}</span>
                    <strong className="num text-xs">{e.count ?? e.value}</strong>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default ReportAnalyticsSection;
