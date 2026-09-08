import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { reportsApi, planningApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import { validateForm, validators, hasErrors } from '../../utils/validation';
import Modal from '../../components/ui/Modal';
import Badge from '../../components/ui/Badge';
import Spinner from '../../components/ui/Spinner';
import EmptyState from '../../components/ui/EmptyState';
import FormField from '../../components/ui/FormField';
import Pagination from '../../components/ui/Pagination';
import { FileText, Download, Plus, RefreshCw, BarChart2 } from 'lucide-react';

function ReportsPage() {
  const toast = useToast();
  const { t } = useI18n();
  const [searchParams] = useSearchParams();
  // reports/jobs.py notifies with /reports?id=<id> when a report finishes.
  const focusReportId = searchParams.get('id');
  const [templates, setTemplates] = useState([]);
  const [engagements, setEngagements] = useState([]);
  // `generated` holds only the current page slice of the archive; the page,
  // size and reload key drive server-side pagination (reloadKey lets the poll
  // and the generate flow force a refetch even when the page is unchanged).
  const [generated, setGenerated] = useState([]);
  const [generatedCount, setGeneratedCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [genReloadKey, setGenReloadKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [formErrors, setFormErrors] = useState({});
  const [downloadingId, setDownloadingId] = useState(null);

  // Form State
  const [showGenModal, setShowGenModal] = useState(false);
  const [selectedEngId, setSelectedEngId] = useState('');
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [selectedFormat, setSelectedFormat] = useState('pdf');
  const [reportTitle, setReportTitle] = useState('');
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    fetchReportsData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Poll while anything is still being generated ─────────────────
  // Generation runs off-thread in reports/jobs.py, so the row lands as
  // `generating` and flips to ready/failed seconds later. Each tick bumps the
  // reload key, which drives the paged fetch effect below — so whatever page is
  // visible is what gets refetched. If the generating row is on another page,
  // polling naturally stops until the user returns to that page.
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

  // Scroll the deep-linked row into view once it has loaded (deps include
  // `generated` so it retries after a page jump brings the row onto the slice).
  useEffect(() => {
    if (loading || !focusReportId) return;
    const el = document.getElementById(`report-${focusReportId}`);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [loading, focusReportId, generated]);

  // ── Paged archive helpers ────────────────────────────────────────
  const generatedLoadedRef = useRef(false);
  const focusLocatedRef = useRef(false);

  // Fetch one page of generated reports (defaults to the current page/size).
  // Used by the mount load, page navigation and the generate/poll reload path.
  // Does not toggle `loading`, so the poll never blanks the table.
  const fetchGenerated = async (pageNo = page, size = pageSize) => {
    const res = await reportsApi.getGeneratedReports({ page: pageNo, page_size: size });
    setGenerated(res.items || []);
    setGeneratedCount(res.count || 0);
    // Clamp: after a refresh the current page may exceed the new last page.
    const last = Math.max(1, Math.ceil((res.count || 0) / size));
    if (pageNo > last) setPage(last);
    return res;
  };

  // Refetch the visible page whenever the page, page size or reload key change.
  // The very first run is skipped — fetchReportsData loads page 1 on mount.
  useEffect(() => {
    if (!generatedLoadedRef.current) {
      generatedLoadedRef.current = true;
      return undefined;
    }
    fetchGenerated(page, pageSize).catch(() => {
      // A failed refetch is not worth a toast — the next tick retries.
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize, genReloadKey]);

  // Deep link (?id=N from reports/jobs.py): the report may live beyond page 1.
  // Scan forward once and jump to its page; the paged effect refetches it and
  // the scroll effect then centers the ringed row.
  useEffect(() => {
    if (loading || !focusReportId || focusLocatedRef.current) return;
    focusLocatedRef.current = true;
    if (generated.some(g => String(g.id) === String(focusReportId))) return;
    (async () => {
      const last = Math.max(1, Math.ceil(generatedCount / pageSize));
      for (let p = 2; p <= Math.min(last, 200); p++) {
        try {
          const res = await reportsApi.getGeneratedReports({ page: p, page_size: pageSize });
          if (res.items.some(g => String(g.id) === String(focusReportId))) { setPage(p); return; }
          if (!res.hasMore) return;
        } catch {
          return;
        }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, focusReportId, generated, generatedCount, pageSize]);

  const fetchReportsData = async () => {
    setLoading(true);
    try {
      const [tempRes, engRes] = await Promise.all([
        reportsApi.getTemplates(),
        planningApi.getEngagements({ page_size: 1000 }),
      ]);
      const templateList = Array.isArray(tempRes) ? tempRes : [];
      const engList = engRes.items;

      setTemplates(templateList);
      setEngagements(engList);

      if (engList.length > 0) {
        setSelectedEngId(engList[0].id);
        setReportTitle(`Audit Report for ${engList[0].title}`);
      }
      if (templateList.length > 0) {
        setSelectedTemplateId(templateList[0].id);
      }
      await fetchGenerated(1, pageSize);
    } catch (err) {
      toast.error('Failed to load reports data');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateReport = async (e) => {
    e.preventDefault();
    // Validate form
    const errors = validateForm({ title: reportTitle, engagement: selectedEngId, template: selectedTemplateId }, {
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
      title: reportTitle,
      template: selectedTemplateId,
      engagement: selectedEngId,
      format: selectedFormat
    };

    try {
      await reportsApi.generateReport(data);
      setShowGenModal(false);
      toast.success('Report generation triggered. Download available when status is READY.');
      // Newest-first ordering (-generated_at) puts the new generating row on
      // page 1, so jump there and let the paged effect refetch it; the poll
      // above then keeps refetching until the file is ready.
      setPage(1);
      setGenReloadKey(k => k + 1);
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error('Failed to generate report: ' + msg);
    } finally {
      setGenerating(false);
    }
  };

  // Always go through the export endpoint via apiClient: it attaches the JWT,
  // resolves the host from the configured base URL, and honours the
  // Content-Disposition filename. window.open on file_url sends no auth header,
  // and the old localhost:8000 fallback broke every non-local deployment.
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
      <div className="reports-split-layout">
        {/* Left Side: Report templates & quick wizard */}
        <div className="card left-side-card">
          <div className="card-header justify-between">
            <h3>{t('reportTemplates')}</h3>
            <button className="btn btn-accent flex items-center gap-1" onClick={() => setShowGenModal(true)}>
              <Plus size={16} /> {t('compileReport')}
            </button>
          </div>

          <div className="templates-list mt-4">
            {templates.length === 0 ? (
              <p className="text-muted text-center py-4">{t('noReportTemplates')}</p>
            ) : (
              templates.map(temp => (
                <div key={temp.id} className="template-item">
                  <div className="template-icon">
                    <FileText size={20} />
                  </div>
                  <div className="template-info">
                    <h4>{temp.name}</h4>
                    <p className="text-xs text-muted">{temp.description}</p>
                    <span className="badge badge-outline mt-1">{temp.template_type?.toUpperCase()}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Side: Generated reports log */}
        <div className="card right-side-card">
          <div className="card-header justify-between">
            <h3>{t('generatedReportsArchive')}</h3>
            <button className="btn btn-outline flex items-center gap-1" onClick={() => setGenReloadKey(k => k + 1)}>
              <RefreshCw size={14} /> {t('refresh')}
            </button>
          </div>

          {loading ? (
            <div className="loading-spinner">{t('loadingArchive')}</div>
          ) : (
            <div className="table-responsive mt-4">
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('title')}</th>
                    <th>{t('format')}</th>
                    <th>{t('dateGenerated')}</th>
                    <th>{t('status')}</th>
                    <th>{t('actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {generated.length === 0 ? (
                    <tr>
                      <td colSpan="5" className="text-center py-8">{t('noReportsCompiled')}</td>
                    </tr>
                  ) : (
                    generated.map(gen => (
                      <tr
                        key={gen.id}
                        id={`report-${gen.id}`}
                        className={String(gen.id) === focusReportId ? 'ring-2 ring-emerald-500' : undefined}
                      >
                        <td><strong>{gen.title}</strong></td>
                        <td><span className="badge badge-outline">{gen.format?.toUpperCase()}</span></td>
                        <td>{new Date(gen.generated_at).toLocaleDateString()}</td>
                        <td>
                          <span className={`badge ${
                            gen.status === 'ready' ? 'badge-success'
                              : gen.status === 'failed' ? 'badge-danger' : 'badge-warning'
                          }`}>
                            {gen.status?.toUpperCase()}
                          </span>
                          {gen.status === 'failed' && gen.error_message && (
                            <p className="text-xs text-danger mt-1">{gen.error_message}</p>
                          )}
                        </td>
                        <td>
                          <button
                            className="btn btn-outline btn-sm flex items-center gap-1"
                            onClick={() => triggerDownload(gen)}
                            disabled={gen.status !== 'ready' || downloadingId === gen.id}
                          >
                            <Download size={14} /> {downloadingId === gen.id ? t('loading') : t('download')}
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
            pageCount={Math.max(1, Math.ceil(generatedCount / pageSize))}
            totalCount={generatedCount}
            onPageChange={setPage}
            pageSize={pageSize}
            onPageSizeChange={setPageSize}
            showPageSize
          />
        </div>
      </div>

      {/* Generate Report Modal */}
      <Modal
        isOpen={showGenModal}
        onClose={() => setShowGenModal(false)}
        title={t('compileExport')}
        size="lg"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={() => setShowGenModal(false)}>{t('cancel')}</button>
            {/* `form=` because Modal renders the footer as a sibling of its
                children, so the submit button sits outside the <form>. */}
            <button type="submit" form="report-form" className="btn btn-primary" disabled={generating}>
              {generating ? 'Compiling...' : t('generateDocument')}
            </button>
          </>
        )}
      >
        <form id="report-form" onSubmit={handleGenerateReport}>
          <div className="form-group">
            <label className="form-label" htmlFor="report_title">{t('reportDocumentTitle')}</label>
            <input
              id="report_title"
              type="text"
              className="form-control"
              value={reportTitle}
              onChange={(e) => setReportTitle(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="report_engagement">{t('selectAuditEngagement')}</label>
            <select
              id="report_engagement"
              className="form-control"
              value={selectedEngId}
              onChange={(e) => {
                setSelectedEngId(e.target.value);
                const engObj = engagements.find(eng => eng.id.toString() === e.target.value.toString());
                if (engObj) setReportTitle(`Audit Report for ${engObj.title}`);
              }}
            >
              {engagements.map(e => (
                <option key={e.id} value={e.id}>{e.engagement_number} - {e.title}</option>
              ))}
            </select>
          </div>

          <div className="form-group-row">
            <div className="form-group">
              <label className="form-label" htmlFor="report_template">{t('selectTemplateLayout')}</label>
              <select
                id="report_template"
                className="form-control"
                value={selectedTemplateId}
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