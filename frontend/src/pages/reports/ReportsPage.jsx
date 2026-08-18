import React, { useState, useEffect, useRef, useCallback } from 'react';
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
import { FileText, Download, Plus, RefreshCw, BarChart2, X } from 'lucide-react';

function ReportsPage() {
  const toast = useToast();
  const { t } = useI18n();
  const [searchParams] = useSearchParams();
  // reports/jobs.py notifies with /reports?id=<id> when a report finishes.
  const focusReportId = searchParams.get('id');
  const [templates, setTemplates] = useState([]);
  const [engagements, setEngagements] = useState([]);
  const [generated, setGenerated] = useState([]);
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
  // `generating` and flips to ready/failed seconds later. A single fixed
  // 2 s refetch missed anything slower than that and left the row stuck.
  const pollRef = useRef(null);
  const anyGenerating = generated.some(g => g.status === 'generating');

  const refreshGenerated = useCallback(async () => {
    try {
      const genRes = await reportsApi.getGeneratedReports();
      setGenerated(Array.isArray(genRes) ? genRes : []);
    } catch {
      // A failed poll is not worth a toast — the next tick retries.
    }
  }, []);

  useEffect(() => {
    if (!anyGenerating) {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return undefined;
    }
    pollRef.current = setInterval(refreshGenerated, 3000);
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [anyGenerating, refreshGenerated]);

  // Scroll the deep-linked row into view once the archive has loaded.
  useEffect(() => {
    if (loading || !focusReportId) return;
    const el = document.getElementById(`report-${focusReportId}`);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [loading, focusReportId]);

  const fetchReportsData = async () => {
    setLoading(true);
    try {
      const [tempRes, engRes, genRes] = await Promise.all([
        reportsApi.getTemplates(),
        planningApi.getEngagements(),
        reportsApi.getGeneratedReports(),
      ]);
      const templateList = Array.isArray(tempRes) ? tempRes : [];
      const engList = Array.isArray(engRes) ? engRes : [];
      const genList = Array.isArray(genRes) ? genRes : [];

      setTemplates(templateList);
      setEngagements(engList);
      setGenerated(genList);

      if (engList.length > 0) {
        setSelectedEngId(engList[0].id);
        setReportTitle(`Audit Report for ${engList[0].title}`);
      }
      if (templateList.length > 0) {
        setSelectedTemplateId(templateList[0].id);
      }
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
      const response = await reportsApi.generateReport(data);
      setGenerated([response, ...generated]);
      setShowGenModal(false);
      toast.success('Report generation triggered. Download available when status is READY.');
      // The polling effect above takes over from here — the new row is
      // `generating`, so it refetches every 3 s until the file is ready.
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
            <button className="btn btn-outline flex items-center gap-1" onClick={fetchReportsData}>
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
        </div>
      </div>

      {/* Generate Report Modal */}
      {showGenModal && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setShowGenModal(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setShowGenModal(false); }}
        >
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="report-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="report-modal-title">{t('compileExport')}</h3>
              <button
                type="button"
                className="close-btn"
                onClick={() => setShowGenModal(false)}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleGenerateReport}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">{t('reportDocumentTitle')}</label>
                  <input
                    type="text"
                    className="form-control"
                    value={reportTitle}
                    onChange={(e) => setReportTitle(e.target.value)}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">{t('selectAuditEngagement')}</label>
                  <select
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
                    <label className="form-label">{t('selectTemplateLayout')}</label>
                    <select
                      className="form-control"
                      value={selectedTemplateId}
                      onChange={(e) => setSelectedTemplateId(e.target.value)}
                    >
                      {templates.map(t => (
                        <option key={t.id} value={t.id}>{t.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">{t('format')}</label>
                    <select
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
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowGenModal(false)}>{t('cancel')}</button>
                <button type="submit" className="btn btn-primary" disabled={generating}>
                  {generating ? 'Compiling...' : t('generateDocument')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default ReportsPage;