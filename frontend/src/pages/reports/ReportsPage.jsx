import { useState, useEffect, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { reportsApi, planningApi, usersApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import useAsyncData from '../../hooks/useAsyncData';
import { validateForm, validators, hasErrors } from '../../utils/validation';
import Modal from '../../components/ui/Modal';
import FormErrorSummary from '../../components/ui/FormErrorSummary';
import EngagementPickerBar from '../../components/ui/EngagementPickerBar';
import Pagination from '../../components/ui/Pagination';
import ReportFilterBar from '../../components/ui/ReportFilterBar';
import ReportAnalyticsSection from './ReportAnalyticsSection';
import {
  FileText, Download, Plus, RefreshCw, BarChart2,
  FileSpreadsheet, ShieldAlert, Sparkles, Filter
} from 'lucide-react';

const INITIAL_FILTERS = {
  search: '',
  date_from: '',
  date_to: '',
  directorate: '',
  auditor: '',
  status: '',
  format: '',
  template: '',
};

function ReportsPage() {
  const toast = useToast();
  const { t } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();
  // reports/jobs.py notifies with /reports?id=<id> when a report finishes.
  const focusReportId = searchParams.get('id');

  // Filters State
  const [filters, setFilters] = useState(() => ({
    search: searchParams.get('search') || '',
    date_from: searchParams.get('date_from') || '',
    date_to: searchParams.get('date_to') || '',
    directorate: searchParams.get('directorate') || '',
    auditor: searchParams.get('auditor') || '',
    status: searchParams.get('status') || '',
    format: searchParams.get('format') || '',
    template: searchParams.get('template') || '',
  }));

  const [showAnalytics, setShowAnalytics] = useState(true);
  const [auditors, setAuditors] = useState([]);
  const [exportingCsv, setExportingCsv] = useState(false);

  // Pagination & Reload Keys
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [genReloadKey, setGenReloadKey] = useState(0);
  const [formErrors, setFormErrors] = useState({});
  const [downloadingId, setDownloadingId] = useState(null);

  // Form State
  const [showGenModal, setShowGenModal] = useState(false);
  const [selectedEngId, setSelectedEngId] = useState('');
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [selectedFormat, setSelectedFormat] = useState('pdf');
  const [reportTitle, setReportTitle] = useState(null);
  const [generating, setGenerating] = useState(false);

  // Fetch auditor user list for the filter bar
  useEffect(() => {
    let cancelled = false;
    usersApi.getUsers({ is_active: true, page_size: 100 })
      .then((res) => {
        if (cancelled) return;
        const items = res.results || (Array.isArray(res) ? res : []);
        setAuditors(items);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  /* ── Reference data: report templates + the engagement picker's list ──── */
  const { data: referenceData, loading: referenceLoading } = useAsyncData(
    async () => {
      const [tempRes, engRes] = await Promise.all([
        reportsApi.getTemplates(),
        planningApi.getEngagements({ page_size: 1000 }),
      ]);
      const templates = Array.isArray(tempRes) ? tempRes : [];
      const engagements = engRes.items ?? [];
      return {
        templates,
        engagements,
        defaultEngId: engagements[0]?.id ?? '',
        defaultTemplateId: templates[0]?.id ?? '',
        defaultTitle: engagements[0] ? `Audit Report for ${engagements[0].title}` : '',
      };
    },
    [],
    { onError: () => toast.error('Failed to load reports data') },
  );

  const templates = referenceData?.templates ?? [];
  const engagements = referenceData?.engagements ?? [];

  // Filter engagements list in the wizard if a directorate filter is active
  const filteredEngagements = useMemo(() => {
    if (!filters.directorate || filters.directorate === 'all') return engagements;
    return engagements.filter(e => {
      if (filters.directorate.match(/^\d+$/)) {
        return e.directorate_id === Number(filters.directorate);
      }
      return e.directorate_type === filters.directorate ||
        e.directorate_name?.toLowerCase().includes(filters.directorate.toLowerCase());
    });
  }, [engagements, filters.directorate]);

  // The user's pick, or default
  const engId = selectedEngId || filteredEngagements[0]?.id || referenceData?.defaultEngId || '';
  const templateId = selectedTemplateId || filters.template || referenceData?.defaultTemplateId || '';
  const reportTitleValue = reportTitle ?? (engId ? `Audit Report for ${engagements.find(e => String(e.id) === String(engId))?.title || ''}` : referenceData?.defaultTitle ?? '');

  // ── Generated reports archive (server-side paginated & filtered) ────────────
  const archiveNeverLoadedRef = useRef(true);

  const { data: archiveData, loading: archiveLoading } = useAsyncData(
    async () => {
      const queryParams = {
        page,
        page_size: pageSize,
        ...Object.fromEntries(
          Object.entries(filters).filter(([_, v]) => v !== '' && v !== null && v !== undefined)
        ),
      };
      const res = await reportsApi.getGeneratedReports(queryParams);
      archiveNeverLoadedRef.current = false;
      return { items: res.items ?? [], count: res.count ?? 0 };
    },
    [page, pageSize, genReloadKey, filters],
    {
      onError: () => {
        if (archiveNeverLoadedRef.current && referenceData) {
          toast.error('Failed to load reports data');
        }
      },
    },
  );

  // ── Reports Analytics data ─────────────────────────────────────────
  const { data: analyticsData, loading: analyticsLoading, reload: reloadAnalytics } = useAsyncData(
    async () => {
      const queryParams = Object.fromEntries(
        Object.entries(filters).filter(([_, v]) => v !== '' && v !== null && v !== undefined)
      );
      return await reportsApi.getAnalytics(queryParams);
    },
    [filters, genReloadKey],
  );

  const generated = useMemo(() => archiveData?.items ?? [], [archiveData]);
  const generatedCount = archiveData?.count ?? 0;
  const totalPages = Math.max(1, Math.ceil(generatedCount / pageSize));

  const loading = referenceLoading || (archiveData === null && archiveLoading);

  // ── Poll while anything is still being generated ─────────────────
  const pollRef = useRef(null);
  const anyGenerating = generated.some(g => g.status === 'generating');

  useEffect(() => {
    if (!anyGenerating) {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return undefined;
    }
    pollRef.current = setInterval(() => {
      setGenReloadKey(k => k + 1);
    }, 3000);
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [anyGenerating]);

  // Scroll the deep-linked row into view once it has loaded
  useEffect(() => {
    if (loading || !focusReportId) return;
    const el = document.getElementById(`report-${focusReportId}`);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [loading, focusReportId, generated]);

  const handleFilterChange = (newFilters) => {
    setFilters(newFilters);
    setPage(1); // Reset to page 1 on filter change
  };

  const handleFilterReset = () => {
    setFilters(INITIAL_FILTERS);
    setPage(1);
  };

  const handleExportArchiveCsv = async () => {
    setExportingCsv(true);
    try {
      const queryParams = Object.fromEntries(
        Object.entries(filters).filter(([_, v]) => v !== '' && v !== null && v !== undefined)
      );
      await reportsApi.exportArchive(queryParams);
      toast.success('Reports archive exported to CSV');
    } catch (err) {
      toast.error('Failed to export reports archive');
    } finally {
      setExportingCsv(false);
    }
  };

  const handleGenerateReport = async (e) => {
    e.preventDefault();
    const errors = validateForm({ title: reportTitleValue, engagement: engId, template: templateId }, {
      title: { validators: [validators.required, validators.minLength(5)] },
      engagement: { validators: [validators.required] },
      template: { validators: [validators.required] },
    });
    if (hasErrors(errors)) {
      setFormErrors(errors);
      return;
    }
    setFormErrors({});
    setGenerating(true);
    const data = {
      title: reportTitleValue,
      template: templateId,
      engagement: engId,
      format: selectedFormat
    };

    try {
      await reportsApi.generateReport(data);
      setShowGenModal(false);
      toast.success('Report generation triggered. Download available when status is READY.');
      setPage(1);
      setGenReloadKey(k => k + 1);
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error('Failed to generate report: ' + msg);
    } finally {
      setGenerating(false);
    }
  };

  const triggerDownload = async (report) => {
    setDownloadingId(report.id);
    try {
      await reportsApi.downloadReport(report.id, `${report.title}.${report.format}`);
    } catch (err) {
      const msg = err.response?.status === 400
        ? 'This report has no file attached yet.'
        : 'Failed to download report';
      toast.error(msg);
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <div className="reports-view">
      {/* ── Page Header & Quick Actions ── */}
      <div className="reports-header flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <FileText className="text-primary" size={22} />
            {t('reportsAndAnalytics') || 'Audit Reports & Analytics'}
          </h2>
          <p className="text-xs text-muted">
            {t('reportsSubtitle') || 'Generate, filter, customize and export official EEU Internal Audit documents.'}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            className={`btn btn-sm ${showAnalytics ? 'btn-primary' : 'btn-outline'} flex items-center gap-1.5`}
            onClick={() => setShowAnalytics(!showAnalytics)}
          >
            <BarChart2 size={14} />
            <span>{showAnalytics ? (t('hideAnalytics') || 'Hide Analytics') : (t('showAnalytics') || 'Analytics Overview')}</span>
          </button>

          <button
            type="button"
            className="btn btn-outline btn-sm flex items-center gap-1.5"
            onClick={handleExportArchiveCsv}
            disabled={exportingCsv || generated.length === 0}
            title={t('exportCsv') || 'Export filtered list as CSV'}
          >
            <FileSpreadsheet size={14} />
            <span>{exportingCsv ? (t('exporting') || 'Exporting...') : (t('exportCsv') || 'Export List (CSV)')}</span>
          </button>

          <button
            type="button"
            className="btn btn-accent btn-sm flex items-center gap-1.5 shadow-sm"
            onClick={() => setShowGenModal(true)}
          >
            <Plus size={15} />
            <span>{t('compileReport') || 'Compile Report'}</span>
          </button>
        </div>
      </div>

      {/* ── Customizable Filter Bar ── */}
      <ReportFilterBar
        filters={filters}
        onChange={handleFilterChange}
        onReset={handleFilterReset}
        templates={templates}
        auditors={auditors}
      />

      {/* ── Analytics Overview Section (Collapsible) ── */}
      {showAnalytics && (
        <ReportAnalyticsSection
          analytics={analyticsData}
          loading={analyticsLoading}
        />
      )}

      {/* ── Split Layout: Templates List + Generated Reports Archive ── */}
      <div className="reports-split-layout">
        {/* Left Side: Report templates */}
        <div className="card left-side-card">
          <div className="card-header justify-between">
            <h3>{t('reportTemplates')}</h3>
            <span className="badge badge-outline text-xs num">{templates.length} {t('templates') || 'templates'}</span>
          </div>

          <div className="templates-list mt-3">
            {templates.length === 0 ? (
              <p className="text-muted text-center py-4">{t('noReportTemplates')}</p>
            ) : (
              templates.map(temp => (
                <div
                  key={temp.id}
                  className="template-item cursor-pointer"
                  onClick={() => {
                    setSelectedTemplateId(temp.id);
                    setShowGenModal(true);
                  }}
                  title="Click to generate using this template"
                >
                  <div className="template-icon">
                    <FileText size={20} />
                  </div>
                  <div className="template-info">
                    <h4>{temp.name}</h4>
                    <p className="text-xs text-muted line-clamp-2">{temp.description || 'Standard audit reporting layout'}</p>
                    <span className="badge badge-outline mt-1 text-xs">{temp.template_type?.toUpperCase()}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Side: Generated reports log */}
        <div className="card right-side-card">
          <div className="card-header justify-between">
            <div className="flex items-center gap-2">
              <h3>{t('generatedReportsArchive')}</h3>
              <span className="badge badge-secondary text-xs num">{generatedCount}</span>
            </div>
            <button
              className="btn btn-outline btn-sm flex items-center gap-1"
              onClick={() => {
                setGenReloadKey(k => k + 1);
                reloadAnalytics();
              }}
              title={t('refresh') || 'Refresh Archive'}
            >
              <RefreshCw size={13} /> {t('refresh')}
            </button>
          </div>

          {loading ? (
            <div className="loading-spinner py-12">{t('loadingArchive')}</div>
          ) : (
            <div className="table-responsive mt-3">
              <table className="table table-hover">
                <thead>
                  <tr>
                    <th>{t('title')}</th>
                    <th>{t('directorate') || 'Directorate'}</th>
                    <th>{t('format')}</th>
                    <th>{t('dateGenerated')}</th>
                    <th>{t('status')}</th>
                    <th className="text-right">{t('actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {generated.length === 0 ? (
                    <tr>
                      <td colSpan="6" className="text-center py-10 text-muted">
                        <FileText size={32} className="mx-auto mb-2 opacity-40" />
                        <p>{t('noReportsCompiled')}</p>
                        <button
                          type="button"
                          className="btn btn-accent btn-sm mt-3"
                          onClick={() => setShowGenModal(true)}
                        >
                          <Plus size={14} /> {t('compileReport')}
                        </button>
                      </td>
                    </tr>
                  ) : (
                    generated.map(gen => (
                      <tr
                        key={gen.id}
                        id={`report-${gen.id}`}
                        className={String(gen.id) === focusReportId ? 'ring-2 ring-emerald-500 bg-emerald-500/5' : undefined}
                      >
                        <td>
                          <div className="flex flex-col">
                            <strong>{gen.title}</strong>
                            {gen.engagement_title && (
                              <span className="text-xs text-muted">
                                {gen.engagement_number ? `${gen.engagement_number} · ` : ''}{gen.engagement_title}
                              </span>
                            )}
                            {gen.template_name && (
                              <span className="text-xs text-muted italic">
                                {t('template') || 'Template'}: {gen.template_name}
                              </span>
                            )}
                          </div>
                        </td>
                        <td>
                          {gen.directorate_name ? (
                            <span className="badge badge-outline text-xs">
                              {gen.directorate_name}
                            </span>
                          ) : (
                            <span className="text-xs text-muted">—</span>
                          )}
                        </td>
                        <td>
                          <span className={`badge ${
                            gen.format === 'pdf' ? 'badge-primary' : gen.format === 'excel' ? 'badge-success' : 'badge-outline'
                          } text-xs font-semibold`}>
                            {gen.format?.toUpperCase()}
                          </span>
                        </td>
                        <td>
                          <div className="flex flex-col text-xs">
                            <span className="num font-medium">{new Date(gen.generated_at).toLocaleDateString()}</span>
                            <span className="text-muted">{gen.generated_by_name || 'System'}</span>
                          </div>
                        </td>
                        <td>
                          <span className={`badge ${
                            gen.status === 'ready' ? 'badge-success'
                              : gen.status === 'failed' ? 'badge-danger' : 'badge-warning'
                          }`}>
                            {gen.status?.toUpperCase()}
                          </span>
                          {gen.status === 'failed' && gen.error_message && (
                            <p className="text-xs text-danger mt-1 max-w-[200px] truncate" title={gen.error_message}>
                              {gen.error_message}
                            </p>
                          )}
                        </td>
                        <td className="text-right">
                          <button
                            className="btn btn-outline btn-sm inline-flex items-center gap-1"
                            onClick={() => triggerDownload(gen)}
                            disabled={gen.status !== 'ready' || downloadingId === gen.id}
                            title={gen.status === 'ready' ? t('download') : 'Report compiling...'}
                          >
                            <Download size={13} />
                            <span>{downloadingId === gen.id ? t('loading') : t('download')}</span>
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          <Pagination
            page={page}
            pageCount={totalPages}
            totalCount={generatedCount}
            onPageChange={setPage}
            pageSize={pageSize}
            onPageSizeChange={setPageSize}
            showPageSize
          />
        </div>
      </div>

      {/* ── Generate Report Modal ── */}
      <Modal
        isOpen={showGenModal}
        onClose={() => setShowGenModal(false)}
        title={t('compileExport')}
        size="lg"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={() => setShowGenModal(false)}>{t('cancel')}</button>
            <button type="submit" form="report-form" className="btn btn-primary" disabled={generating}>
              {generating ? (t('compiling') || 'Compiling...') : t('generateDocument')}
            </button>
          </>
        )}
      >
        <form id="report-form" onSubmit={handleGenerateReport} noValidate>
          <FormErrorSummary errors={formErrors} />
          <div className="form-group">
            <label className="form-label" htmlFor="report_title">{t('reportDocumentTitle')}</label>
            <input
              id="report_title"
              type="text"
              className="form-control"
              value={reportTitleValue}
              onChange={(e) => setReportTitle(e.target.value)}
              placeholder="e.g. Annual Technical Audit Report 2026"
              required
            />
          </div>

          <EngagementPickerBar
            idPrefix="report"
            engagements={filteredEngagements.length > 0 ? filteredEngagements : engagements}
            value={engId}
            onChange={(id) => {
              setSelectedEngId(id);
              const engObj = engagements.find(eng => String(eng.id) === String(id));
              if (engObj) setReportTitle(`Audit Report for ${engObj.title}`);
            }}
            label={t('selectAuditEngagement')}
          />

          <div className="form-group-row">
            <div className="form-group">
              <label className="form-label" htmlFor="report_template">{t('selectTemplateLayout')}</label>
              <select
                id="report_template"
                className="form-control"
                value={templateId}
                onChange={(e) => setSelectedTemplateId(e.target.value)}
              >
                {templates.map(tpl => (
                  <option key={tpl.id} value={tpl.id}>{tpl.name}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="report_format">{t('format')}</label>
              <select
                id="report_format"
                className="form-control"
                value={selectedFormat}
                onChange={(e) => setSelectedFormat(e.target.value)}
              >
                <option value="pdf">{t('pdfDocument')}</option>
                <option value="excel">{t('excelSheet')}</option>
                <option value="word">{t('wordDocx')}</option>
              </select>
            </div>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default ReportsPage;