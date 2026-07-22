import React, { useState, useEffect } from 'react';
import apiClient from '../../api/apiClient';
import { FileText, Download, Plus, RefreshCw, BarChart2 } from 'lucide-react';

function ReportsPage() {
  const [templates, setTemplates] = useState([]);
  const [engagements, setEngagements] = useState([]);
  const [generated, setGenerated] = useState([]);
  const [loading, setLoading] = useState(true);

  // Form State
  const [showGenModal, setShowGenModal] = useState(false);
  const [selectedEngId, setSelectedEngId] = useState('');
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [selectedFormat, setSelectedFormat] = useState('pdf');
  const [reportTitle, setReportTitle] = useState('');
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    fetchReportsData();
  }, []);

  const fetchReportsData = async () => {
    setLoading(true);
    try {
      const [tempRes, engRes, genRes] = await Promise.all([
        apiClient.get('/reports/templates/'),
        apiClient.get('/planning/engagements/'),
        apiClient.get('/reports/generated/')
      ]);
      setTemplates(tempRes.data.results || []);
      setEngagements(engRes.data.results || []);
      setGenerated(genRes.data.results || []);

      if (engRes.data.results?.length > 0) {
        setSelectedEngId(engRes.data.results[0].id);
        setReportTitle(`Audit Report for ${engRes.data.results[0].title}`);
      }
      if (tempRes.data.results?.length > 0) {
        setSelectedTemplateId(tempRes.data.results[0].id);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateReport = async (e) => {
    e.preventDefault();
    setGenerating(true);
    const data = {
      title: reportTitle,
      template: selectedTemplateId,
      engagement: selectedEngId,
      format: selectedFormat
    };

    try {
      const response = await apiClient.post('/reports/generated/', data);
      setGenerated([response.data, ...generated]);
      setShowGenModal(false);
      alert('Report generation triggered. You can download once status is READY.');
      // Refresh list after brief delay
      setTimeout(fetchReportsData, 2000);
    } catch (err) {
      alert('Failed: ' + JSON.stringify(err.response?.data || err.message));
    } finally {
      setGenerating(false);
    }
  };

  const triggerDownload = (report) => {
    // Use file_url if available (full absolute URL from serializer)
    if (report.file_url) {
      window.open(report.file_url, '_blank');
    } else if (report.file) {
      window.open(report.file, '_blank');
    } else {
      // Fallback to export endpoint
      const downloadUrl = `http://localhost:8000/api/reports/generated/${report.id}/export/`;
      window.open(downloadUrl, '_blank');
    }
  };

  return (
    <div className="reports-view">
      <div className="reports-split-layout">
        {/* Left Side: Report templates & quick wizard */}
        <div className="card left-side-card">
          <div className="card-header justify-between">
            <h3>Report Templates</h3>
            <button className="btn btn-accent flex items-center gap-1" onClick={() => setShowGenModal(true)}>
              <Plus size={16} /> Compile Report
            </button>
          </div>

          <div className="templates-list mt-4">
            {templates.length === 0 ? (
              <p className="text-muted text-center py-4">No report templates defined.</p>
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
            <h3>Generated Reports Archive</h3>
            <button className="btn btn-outline flex items-center gap-1" onClick={fetchReportsData}>
              <RefreshCw size={14} /> Refresh
            </button>
          </div>

          {loading ? (
            <div className="loading-spinner">Loading archive...</div>
          ) : (
            <div className="table-responsive mt-4">
              <table className="table">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Format</th>
                    <th>Date Generated</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {generated.length === 0 ? (
                    <tr>
                      <td colSpan="5" className="text-center py-8">No reports compiled yet. Click 'Compile Report' to generate.</td>
                    </tr>
                  ) : (
                    generated.map(gen => (
                      <tr key={gen.id}>
                        <td><strong>{gen.title}</strong></td>
                        <td><span className="badge badge-outline">{gen.format?.toUpperCase()}</span></td>
                        <td>{new Date(gen.generated_at).toLocaleDateString()}</td>
                        <td>
                          <span className={`badge ${gen.status === 'ready' ? 'badge-success' : 'badge-warning'}`}>
                            {gen.status?.toUpperCase()}
                          </span>
                        </td>
                        <td>
                          <button
                            className="btn btn-outline btn-sm flex items-center gap-1"
                            onClick={() => triggerDownload(gen)}
                            disabled={gen.status !== 'ready' && !gen.file}
                          >
                            <Download size={14} /> Download
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
        <div className="modal-backdrop">
          <div className="modal-card">
            <div className="modal-header">
              <h3>Compile & Export Audit Report</h3>
              <button className="close-btn" onClick={() => setShowGenModal(false)}>×</button>
            </div>
            <form onSubmit={handleGenerateReport}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Report Document Title</label>
                  <input
                    type="text"
                    className="form-control"
                    value={reportTitle}
                    onChange={(e) => setReportTitle(e.target.value)}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Select Audit Engagement</label>
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
                    <label className="form-label">Select Template Layout</label>
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
                    <label className="form-label">Format</label>
                    <select
                      className="form-control"
                      value={selectedFormat}
                      onChange={(e) => setSelectedFormat(e.target.value)}
                    >
                      <option value="pdf">PDF Document</option>
                      <option value="excel">Excel Sheet</option>
                      <option value="word">Word (docx)</option>
                    </select>
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowGenModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={generating}>
                  {generating ? 'Compiling...' : 'Generate Document'}
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