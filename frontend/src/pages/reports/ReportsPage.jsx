import { useState, useEffect, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { reportsApi, planningApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import useAsyncData from '../../hooks/useAsyncData';
import { validateForm, validators, hasErrors } from '../../utils/validation';
import Modal from '../../components/ui/Modal';
import FormErrorSummary from '../../components/ui/FormErrorSummary';
import EngagementPickerBar from '../../components/ui/EngagementPickerBar';
import Pagination from '../../components/ui/Pagination';
import { FileText, Download, Plus, RefreshCw } from 'lucide-react';

function ReportsPage() {
  const toast = useToast();
  const { t } = useI18n();
  const [searchParams] = useSearchParams();
  // reports/jobs.py notifies with /reports?id=<id> when a report finishes.
  const focusReportId = searchParams.get('id');

  // The archive's fetch dependencies: a page click, the size selector, the
  // Refresh button and the poll below each re-run its request by changing one of
  // the three, rather than calling a fetcher by hand.
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

  /* ── Reference data: report templates + the engagement picker's list ────
   * One request — the two were already fetched together with `Promise.all` — and
   * the *defaults* ride back with it. The old mount fetch wrote them into five
   * pieces of state (`templates`, `engagements`, `selectedEngId`,
   * `selectedTemplateId` and the report title) from inside its own response, so
   * the fetcher depended on the state it was setting. They are resolved at render
   * time below instead: a value the user has not chosen yet falls back to the
   * default the loader returned, and nothing writes it back into state.
   */
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

  // The user's pick, or the default until they make one. Resolved here rather
  // than stored, because the raw selection is still '' on load while the page is
  // already displaying — and submitting — the first engagement/template.
  const engId = selectedEngId || referenceData?.defaultEngId || '';
  const templateId = selectedTemplateId || referenceData?.defaultTemplateId || '';
  // `reportTitle` stays null until the user types, so the default shows through
  // without an effect copying it into state. Clearing the box yields '' (not
  // null) and therefore keeps the box empty, exactly as before.
  const reportTitleValue = reportTitle ?? referenceData?.defaultTitle ?? '';

  // ── Generated reports archive (server-side paginated) ────────────
  // The page slice and its total were two pieces of state fed by `fetchGenerated`
  // from three different callers (mount, the paged effect, the deep-link scan).
  // The loader now returns both halves of the single response, as AuditTrailPage
  // does, and page/pageSize/genReloadKey *are* the request. Nothing special-cases
  // the mount — the hook runs on mount — so the `generatedLoadedRef` guard that
  // skipped the first paged effect is gone.
  const archiveNeverLoadedRef = useRef(true);

  const { data: archiveData, loading: archiveLoading } = useAsyncData(
    async () => {
      const res = await reportsApi.getGeneratedReports({ page, page_size: pageSize });
      archiveNeverLoadedRef.current = false;
      return { items: res.items ?? [], count: res.count ?? 0 };
    },
    [page, pageSize, genReloadKey],
    {
      onError: () => {
        // The first load used to sit inside `fetchReportsData`'s catch, which
        // toasted; a failed *refetch* was deliberately silent ("the next tick
        // retries"). Same message for both, so the guard is what keeps the poll
        // from repeating it every three seconds. `referenceData` keeps a total
        // outage to the single toast the old combined load produced.
        if (archiveNeverLoadedRef.current && referenceData) {
          toast.error('Failed to load reports data');
        }
      },
    },
  );

  // Memoised so the two effects below can depend on the slice without the `?? []`
  // making a fresh array every render.
  const generated = useMemo(() => archiveData?.items ?? [], [archiveData]);
  const generatedCount = archiveData?.count ?? 0;

  const totalPages = Math.max(1, Math.ceil(generatedCount / pageSize));

  // `fetchGenerated` clamped the page from inside its own response, so that a
  // refresh which shrank the archive could not leave the pointer past the last
  // page. That branch was unreachable: a *successful* page response always proves
  // `page <= last` (DRF's PageNumberPagination 404s an out-of-range page, and
  // `max_page_size` is 1000 against a control that offers at most 100), and the
  // 404 path — the only way the pointer can really end up out of range, e.g. when
  // the page size grows under a later page — never reached the clamp at all. It
  // is not reimplemented here: `page` is left as the user's pointer, and the
  // Pagination control still walks it back with its prev button.

  // Only the *first* archive load blanks the table. A page change or a poll tick
  // must not — the old archive fetch deliberately left `loading` alone so the
  // poll could never flicker the table.
  const loading = referenceLoading || (archiveData === null && archiveLoading);

  // ── Poll while anything is still being generated ─────────────────
  // Generation runs off-thread in reports/jobs.py, so the row lands as
  // `generating` and flips to ready/failed seconds later. Each tick bumps the
  // reload key, which is one of the archive request's dependencies below — so
  // whatever page is visible is what gets refetched. If the generating row is on
  // another page, polling naturally stops until the user returns to that page.
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

  // ── Deep-link lookup ─────────────────────────────────────────────
  const focusLocatedRef = useRef(false);

  // Deep link (?id=N from reports/jobs.py): the report may live beyond page 1.
  // Scan forward once and jump to its page; that page change refetches it and
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
  }, [loading, focusReportId, generated, generatedCount, pageSize]);

  const handleGenerateReport = async (e) => {
    e.preventDefault();
    // Validate form. The resolved ids and title, not the raw selections: on mount
    // those are still '' while the form is showing the first template and
    // engagement, so validating (and then posting) the raw state would look like a
    // 400 from nowhere on the one path a user takes when the defaults are right.
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
      // Newest-first ordering (-generated_at) puts the new generating row on
      // page 1, so jump there and let the page change (or the reload key, if the
      // page is already 1) refetch it; the poll above then keeps refetching until
      // the file is ready.
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
            pageCount={totalPages}
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
        {/* `noValidate` hands validation to the app, as UsersPage's forms already
            do. Without it the browser's own check on the `required` title
            intercepts an empty submit, React's onSubmit never fires — so
            `validateForm` never runs and the FormErrorSummary below never
            renders. The title is covered by validators.required (plus
            minLength), and the engagement/template fields by their own required
            validators, so nothing stops being enforced. */}
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
              required
            />
          </div>

          {/* `value` is the resolved id, not the raw selection: the picker must
              show the engagement whose report will actually be generated, which
              is the loader's default until the user picks another. */}
          <EngagementPickerBar
            idPrefix="report"
            engagements={engagements}
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