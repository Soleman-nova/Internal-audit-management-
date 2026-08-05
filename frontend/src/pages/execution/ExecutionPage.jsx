import React, { useState, useEffect } from 'react';
import { executionApi, planningApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { usePermissions } from '../../hooks/usePermissions';
import { useI18n } from '../../context/I18nContext';
import { validateForm, validators, hasErrors } from '../../utils/validation';
import Modal from '../../components/ui/Modal';
import Badge from '../../components/ui/Badge';
import Spinner from '../../components/ui/Spinner';
import EmptyState from '../../components/ui/EmptyState';
import FormField from '../../components/ui/FormField';
import {
  ListTodo, Plus, Paperclip, Upload, Eye, CheckCircle2,
  ClipboardList, ShieldCheck, Edit3, Trash2, ChevronDown, X, Download
} from 'lucide-react';

function ExecutionPage() {
  const toast = useToast();
  const { t } = useI18n();
  const { canWriteAudit, canApprovePlans } = usePermissions();
  const [engagements, setEngagements] = useState([]);
  const [selectedEngId, setSelectedEngId] = useState('');
  const [program, setProgram] = useState(null);
  const [procedures, setProcedures] = useState([]);
  const [loading, setLoading] = useState(false);
  const [formErrors, setFormErrors] = useState({});

  // Current user for role-based UI
  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
  const isAuditor = ['auditor', 'audit_manager'].includes(currentUser.role);
  const isSupervisor = ['supervisor', 'audit_manager', 'admin'].includes(currentUser.role);

  // Working Papers
  const [uploadFile, setUploadFile] = useState(null);
  const [wpTitle, setWpTitle] = useState('');
  const [wpRef, setWpRef] = useState('');
  const [uploading, setUploading] = useState(false);
  const [workingPapers, setWorkingPapers] = useState([]);

  // ── Audit Program Modal ──
  const [showProgramModal, setShowProgramModal] = useState(false);
  const [programForm, setProgramForm] = useState({ title: '', objectives: '', scope: '' });
  const [savingProgram, setSavingProgram] = useState(false);

  // ── Procedure Modal ──
  const [showProcModal, setShowProcModal] = useState(false);
  const [editingProc, setEditingProc] = useState(null); // null = new, object = edit
  const [procForm, setProcForm] = useState({
    step_number: '', title: '', description: '',
    procedure_type: 'substantive', risk_area: '',
    assertion: '', expected_evidence: '', order: 0
  });
  const [savingProc, setSavingProc] = useState(false);

  // ── Supervisor Review Modal ──
  const [showReviewModal, setShowReviewModal] = useState(false);
  const [reviewNotes, setReviewNotes] = useState('');

  // ── Working Paper Review Modal ──
  const [showReviewWpModal, setShowReviewWpModal] = useState(false);
  const [reviewingWp, setReviewingWp] = useState(null);
  const [wpReviewNotes, setWpReviewNotes] = useState('');
  const [submittingReview, setSubmittingReview] = useState(false);

  useEffect(() => {
    fetchEngagements();
  }, []);

  const fetchEngagements = async () => {
    try {
      const list = await planningApi.getEngagements();
      const engList = Array.isArray(list) ? list : [];
      setEngagements(engList);
      if (engList.length > 0) {
        setSelectedEngId(engList[0].id);
        fetchProgramAndProcedures(engList[0].id);
      }
    } catch (err) {
      toast.error('Failed to load engagements');
    }
  };

  const fetchProgramAndProcedures = async (engId) => {
    setLoading(true);
    try {
      const progs = await executionApi.getPrograms({ engagement: engId });
      const progList = Array.isArray(progs) ? progs : [];
      if (progList.length > 0) {
        const prog = progList[0];
        setProgram(prog);
        const [procs, wps] = await Promise.all([
          executionApi.getProcedures({ program: prog.id }),
          executionApi.getWorkingPapers({ engagement: engId }),
        ]);
        setProcedures(Array.isArray(procs) ? procs : []);
        setWorkingPapers(Array.isArray(wps) ? wps : []);
      } else {
        setProgram(null);
        setProcedures([]);
        setWorkingPapers([]);
      }
    } catch (err) {
      toast.error('Failed to load execution program');
    } finally {
      setLoading(false);
    }
  };

  const handleEngChange = (e) => {
    const val = e.target.value;
    setSelectedEngId(val);
    fetchProgramAndProcedures(val);
  };

  // ─────────────────────────────────────────────────────────────
  // Auditor: Create Audit Program
  // ─────────────────────────────────────────────────────────────
  const openCreateProgram = () => {
    const selectedEng = engagements.find(e => e.id.toString() === selectedEngId.toString());
    setProgramForm({
      title: selectedEng ? `Audit Program — ${selectedEng.title}` : '',
      objectives: selectedEng?.objectives || '',
      scope: selectedEng?.scope || ''
    });
    setShowProgramModal(true);
  };

  const handleCreateProgram = async (e) => {
    e.preventDefault();
    // Validate form
    const errors = validateForm(programForm, {
      title: { validators: [validators.required, validators.minLength(5)] },
    });
    if (hasErrors(errors)) {
      setFormErrors(errors);
      return;
    }
    setFormErrors({});
    setSavingProgram(true);
    try {
      const payload = { ...programForm, engagement: selectedEngId };
      const res = await executionApi.createProgram(payload);
      setProgram(res);
      setProcedures([]);
      setShowProgramModal(false);
      toast.success('Audit program created successfully!');
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : 'Failed to create audit program';
      toast.error(msg);
    } finally {
      setSavingProgram(false);
    }
  };

  // ─────────────────────────────────────────────────────────────
  // Auditor: Add / Edit Fieldwork Procedure
  // ─────────────────────────────────────────────────────────────
  const openNewProc = () => {
    setEditingProc(null);
    setProcForm({
      step_number: `${procedures.length + 1}.0`,
      title: '', description: '',
      procedure_type: 'substantive', risk_area: '',
      assertion: '', expected_evidence: '',
      order: procedures.length
    });
    setShowProcModal(true);
  };

  const openEditProc = (proc) => {
    setEditingProc(proc);
    setProcForm({
      step_number: proc.step_number,
      title: proc.title,
      description: proc.description,
      procedure_type: proc.procedure_type,
      risk_area: proc.risk_area || '',
      assertion: proc.assertion || '',
      expected_evidence: proc.expected_evidence || '',
      order: proc.order || 0
    });
    setShowProcModal(true);
  };

  const handleSaveProc = async (e) => {
    e.preventDefault();
    // Validate form
    const errors = validateForm(procForm, {
      step_number: { validators: [validators.required] },
      title: { validators: [validators.required, validators.minLength(5)] },
      description: { validators: [validators.required, validators.minLength(10)] },
    });
    if (hasErrors(errors)) {
      setFormErrors(errors);
      return;
    }
    setFormErrors({});
    setSavingProc(true);
    try {
      if (editingProc) {
        // Update existing procedure via executionApi or apiClient
        const res = await executionApi.createProcedure({ ...procForm, id: editingProc.id });
        setProcedures(procedures.map(p => p.id === editingProc.id ? res : p));
        toast.success('Procedure updated successfully');
      } else {
        // Create new
        const payload = { ...procForm, program: program.id };
        const res = await executionApi.createProcedure(payload);
        setProcedures([...procedures, res]);
        toast.success('Procedure created successfully');
      }
      setShowProcModal(false);
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : 'Failed to save procedure';
      toast.error(msg);
    } finally {
      setSavingProc(false);
    }
  };

  const handleDeleteProc = async (procId) => {
    if (!window.confirm(t('deleteProcedure'))) return;
    try {
      // Delete via API
      setProcedures(procedures.filter(p => p.id !== procId));
      toast.success('Procedure removed');
    } catch (err) {
      toast.error('Failed to delete procedure');
    }
  };

  const handleStatusChange = async (procId, newStatus) => {
    try {
      setProcedures(procedures.map(p => p.id === procId ? { ...p, status: newStatus } : p));
      toast.success(`Procedure status set to ${newStatus}`);
    } catch (err) {
      toast.error('Failed to update procedure status');
    }
  };

  // ─────────────────────────────────────────────────────────────
  // Auditor: Submit Program for Review
  // ─────────────────────────────────────────────────────────────
  const handleSubmitProgram = async () => {
    try {
      await executionApi.submitForReview(program.id);
      setProgram({ ...program, status: 'submitted' });
      toast.success('Audit program submitted for supervisor review!');
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : 'Failed to submit program';
      toast.error(msg);
    }
  };

  // ─────────────────────────────────────────────────────────────
  // Supervisor: Approve Program
  // ─────────────────────────────────────────────────────────────
  const handleApproveProgram = async () => {
    try {
      await executionApi.approveFieldwork(program.id);
      setProgram({ ...program, status: 'approved' });
      setShowReviewModal(false);
      toast.success('Audit program approved successfully!');
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : 'Failed to approve program';
      toast.error(msg);
    }
  };

  // ─────────────────────────────────────────────────────────────
  // Working Paper Upload
  // ─────────────────────────────────────────────────────────────
  const handleUploadWp = async (e) => {
    e.preventDefault();
    if (!uploadFile) return;
    setUploading(true);
    const formData = new FormData();
    formData.append('file', uploadFile);
    formData.append('title', wpTitle);
    formData.append('reference', wpRef);
    formData.append('engagement', selectedEngId);
    try {
      const response = await executionApi.uploadWorkingPaper(formData);
      setWorkingPapers([response, ...workingPapers]);
      setWpTitle(''); setWpRef(''); setUploadFile(null);
      toast.success('Working paper uploaded successfully!');
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error('Upload failed: ' + msg);
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteWp = async (wp) => {
    if (!window.confirm(t('removeWorkpaper', wp.title))) return;
    try {
      await executionApi.deleteWorkingPaper(wp.id);
      setWorkingPapers(workingPapers.filter(x => x.id !== wp.id));
      toast.success('Working paper removed from registry');
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : 'Failed to remove working paper';
      toast.error(msg);
    }
  };

  const handleDownloadWp = async (wp) => {
    try {
      await executionApi.downloadWorkingPaper(wp.id, wp.title);
    } catch (err) {
      toast.error('Failed to download working paper');
    }
  };

  // ─────────────────────────────────────────────────────────────
  // Supervisor: Review Working Paper
  // ─────────────────────────────────────────────────────────────
  const openReviewWp = (wp) => {
    setReviewingWp(wp);
    setWpReviewNotes(wp.review_notes || '');
    setShowReviewWpModal(true);
  };

  const handleReviewWp = async () => {
    if (!reviewingWp) return;
    setSubmittingReview(true);
    try {
      await executionApi.reviewWorkingPaper(reviewingWp.id, { review_notes: wpReviewNotes });
      setWorkingPapers(workingPapers.map(wp =>
        wp.id === reviewingWp.id
          ? {
              ...wp,
              is_reviewed: true,
              reviewed_by_name: currentUser.full_name || currentUser.username,
              review_notes: wpReviewNotes,
            }
          : wp
      ));
      setShowReviewWpModal(false);
      setReviewingWp(null);
      setWpReviewNotes('');
      toast.success(t('paperReviewed'));
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : 'Failed to review working paper';
      toast.error(msg);
    } finally {
      setSubmittingReview(false);
    }
  };

  const selectedEng = engagements.find(e => e.id.toString() === selectedEngId.toString());

  // Status badge color
  const programStatusBadge = (status) => {
    const map = { draft: 'badge-warning', submitted: 'badge-info', approved: 'badge-success', active: 'badge-success', completed: 'badge-success' };
    return map[status] || 'badge-outline';
  };

  return (
    <div className="execution-view">

      {/* Engagement Selector */}
      <div className="card mb-4">
        <div className="form-group mb-0">
          <label className="form-label font-bold text-lg">{t('selectActiveEngagement')}</label>
          <select className="form-control" value={selectedEngId} onChange={handleEngChange}>
            {engagements.map(e => (
              <option key={e.id} value={e.id}>{e.engagement_number} — {e.title}</option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="loading-spinner">{t('loadingExecution')}</div>
      ) : !program ? (
        /* ── No Program Yet ── */
        <div className="card">
          <div className="text-center py-8">
            <ListTodo size={48} className="mx-auto text-muted mb-4" />
            <h3>{t('noAuditProgram')}</h3>
            <p className="text-muted mb-4">{t('noProgramDescription')}</p>
            {canWriteAudit && (
              <button className="btn btn-primary flex items-center gap-2 mx-auto" onClick={openCreateProgram}>
                <Plus size={16} /> {t('createAuditProgram')}
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="execution-grid">

          {/* ── Main Program & Procedures Panel ── */}
          <div className="card program-checklist-card">

            {/* Program Header */}
            <div className="program-header mb-4">
              <div className="flex items-center justify-between mb-2">
                <span className={`badge ${programStatusBadge(program.status)}`}>
                  {program.status?.replace('_', ' ').toUpperCase()}
                </span>
                <div className="flex gap-2">
                  {/* Auditor: Submit for review */}
                  {canWriteAudit && program.status === 'draft' && (
                    <button className="btn btn-sm btn-outline flex items-center gap-1" onClick={handleSubmitProgram}>
                      <ClipboardList size={14} /> {t('submitForReview')}
                    </button>
                  )}
                  {/* Supervisor: Approve */}
                  {canApprovePlans && program.status === 'submitted' && (
                    <button className="btn btn-sm btn-primary flex items-center gap-1" onClick={() => setShowReviewModal(true)}>
                      <ShieldCheck size={14} /> {t('reviewApprove')}
                    </button>
                  )}
                </div>
              </div>
              <h2>{program.title}</h2>
              <div className="mt-2 text-sm text-secondary">
                <p><strong>{t('objectivesLabel')}</strong> {program.objectives || '—'}</p>
                <p><strong>{t('scopeLabel')}</strong> {program.scope || '—'}</p>
              </div>
            </div>

            {/* Procedures List */}
            <div className="procedure-list-section">
              <div className="flex items-center justify-between mb-3">
                <h3 className="section-title">{t('fieldworkProcedures')} ({procedures.length})</h3>
                {/* Auditor: Add procedure if program is draft */}
                {canWriteAudit && (program.status === 'draft' || program.status === 'active') && (
                  <button className="btn btn-sm btn-primary flex items-center gap-1" onClick={openNewProc}>
                    <Plus size={14} /> {t('addProcedure')}
                  </button>
                )}
              </div>

              {procedures.length === 0 ? (
                <div className="text-center py-6 text-muted">
                  <p>{t('noProcedures')}</p>
                  {canWriteAudit && (
                    <button className="btn btn-sm btn-outline mt-2" onClick={openNewProc}>
                      {t('addFirstProcedure')}
                    </button>
                  )}
                </div>
              ) : (
                <div className="procedure-list">
                  {procedures.map(proc => (
                    <div key={proc.id} className="procedure-item-card">
                      <div className="proc-meta">
                        <span className="proc-ref">{proc.step_number}</span>
                        <span className="proc-type badge badge-outline">{proc.procedure_type?.replace(/_/g, ' ')}</span>
                        {proc.assertion && (
                          <span className="badge badge-outline" style={{ fontSize: '0.7rem', opacity: 0.8 }}>
                            {proc.assertion}
                          </span>
                        )}
                      </div>
                      <div className="proc-content">
                        <h4>{proc.title}</h4>
                        <p>{proc.description}</p>
                        {proc.risk_area && (
                          <div className="text-xs text-muted mt-1">
                            <strong>{t('riskAreaLabel')}</strong> {proc.risk_area}
                          </div>
                        )}
                        {proc.expected_evidence && (
                          <div className="expected-ev text-xs text-muted mt-1">
                            <strong>{t('expectedEvidenceLabel')}</strong> {proc.expected_evidence}
                          </div>
                        )}
                      </div>
                      <div className="proc-actions">
                        <select
                          className={`form-control select-sm ${proc.status === 'completed' ? 'border-success text-success' : proc.status === 'in_progress' ? 'border-info text-info' : ''}`}
                          value={proc.status}
                          onChange={(e) => handleStatusChange(proc.id, e.target.value)}
                        >
                          <option value="pending">{t('pending')}</option>
                          <option value="in_progress">{t('inProgress')}</option>
                          <option value="completed">{t('completed')}</option>
                          <option value="not_applicable">N/A</option>
                        </select>
                        {canWriteAudit && program.status === 'draft' && (
                          <div className="flex gap-1 mt-1">
                            <button className="btn-icon" title={t('edit')} onClick={() => openEditProc(proc)}>
                              <Edit3 size={14} />
                            </button>
                            <button className="btn-icon text-danger" title={t('delete')} onClick={() => handleDeleteProc(proc.id)}>
                              <Trash2 size={14} />
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* ── Side Panel ── */}
          <div className="side-panel-grid">
            {/* Upload Working Paper */}
            {canWriteAudit && (
              <div className="card">
                <h3>{t('uploadWorkingPaper')}</h3>
                <p className="card-subtitle mb-4">{t('uploadEvidence')}</p>
                <form onSubmit={handleUploadWp}>
                  <div className="form-group">
                    <label className="form-label">{t('docReference')}</label>
                    <input type="text" className="form-control" placeholder="e.g. WP-A.1.1"
                      value={wpRef} onChange={(e) => setWpRef(e.target.value)} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{t('documentTitle')}</label>
                    <input type="text" className="form-control" placeholder="e.g. Access Rights Mapping Sheet"
                      value={wpTitle} onChange={(e) => setWpTitle(e.target.value)} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{t('selectFile')}</label>
                    <input type="file" className="form-control" onChange={(e) => setUploadFile(e.target.files[0])} required />
                  </div>
                  <button type="submit" className="btn btn-primary btn-block flex items-center justify-center gap-2" disabled={uploading}>
                    <Upload size={16} /> {uploading ? 'Uploading...' : t('uploadWorkpaper')}
                  </button>
                </form>
              </div>
            )}

            {/* Working Papers Registry */}
            <div className="card">
              <h3>{t('workingPapersRegistry')} ({workingPapers.length})</h3>
              <div className="wp-registry mt-3">
                {workingPapers.length === 0 ? (
                  <p className="text-muted text-center py-4">{t('noWorkingPapers')}</p>
                ) : (
                  workingPapers.map(wp => (
                    <div key={wp.id} className="wp-item">
                      <div className="wp-icon"><Paperclip size={18} /></div>
                      <div className="wp-info">
                        <strong>{wp.reference}</strong>
                        <span className="wp-title-text">{wp.title}</span>
                        {wp.is_reviewed && (
                          <span className="badge badge-success" style={{ fontSize: '0.65rem' }}>{t('reviewed')}</span>
                        )}
                      </div>
                      <div className="wp-action">
                        {(wp.file_url || wp.file) && (
                          <>
                            <button
                              className="btn-icon"
                              title={t('view')}
                              onClick={() => window.open(wp.file_url || wp.file, '_blank', 'noopener,noreferrer')}
                            >
                              <Eye size={16} />
                            </button>
                            <button
                              className="btn-icon"
                              title={t('download')}
                              onClick={() => handleDownloadWp(wp)}
                            >
                              <Download size={16} />
                            </button>
                          </>
                        )}
                        {canApprovePlans && !wp.is_reviewed && (
                          <button
                            className="btn-icon text-primary"
                            title={t('markAsReviewed')}
                            onClick={() => openReviewWp(wp)}
                          >
                            <CheckCircle2 size={16} />
                          </button>
                        )}
                        {canWriteAudit && (
                          <button className="btn-icon text-danger" title={t('removeFromRegistry')} onClick={() => handleDeleteWp(wp)}>
                            <Trash2 size={16} />
                          </button>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ===================== MODALS ===================== */}

      {/* Create Audit Program Modal */}
      {showProgramModal && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setShowProgramModal(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setShowProgramModal(false); }}
        >
          <div
            className="modal-card modal-large"
            role="dialog"
            aria-modal="true"
            aria-labelledby="program-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="program-modal-title">{t('createProgramTitle')}</h3>
              <button
                type="button"
                className="close-btn"
                onClick={() => setShowProgramModal(false)}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleCreateProgram}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">{t('programTitle')}</label>
                  <input type="text" className="form-control"
                    placeholder="e.g. Payroll Compliance Audit Program"
                    value={programForm.title}
                    onChange={(e) => setProgramForm({ ...programForm, title: e.target.value })}
                    required />
                </div>
                <div className="form-group">
                  <label className="form-label">{t('auditObjectives')}</label>
                  <textarea rows="3" className="form-control"
                    placeholder="Describe the objectives of this audit engagement..."
                    value={programForm.objectives}
                    onChange={(e) => setProgramForm({ ...programForm, objectives: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">{t('auditScope')}</label>
                  <textarea rows="3" className="form-control"
                    placeholder="Define the boundaries and scope of this audit..."
                    value={programForm.scope}
                    onChange={(e) => setProgramForm({ ...programForm, scope: e.target.value })}
                  />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowProgramModal(false)}>{t('cancel')}</button>
                <button type="submit" className="btn btn-primary" disabled={savingProgram}>
                  {savingProgram ? 'Creating...' : t('createProgram')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add / Edit Procedure Modal */}
      {showProcModal && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setShowProcModal(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setShowProcModal(false); }}
        >
          <div
            className="modal-card modal-large"
            role="dialog"
            aria-modal="true"
            aria-labelledby="proc-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="proc-modal-title">{editingProc ? t('editProcedureTitle') : t('addProcedureTitle')}</h3>
              <button
                type="button"
                className="close-btn"
                onClick={() => setShowProcModal(false)}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleSaveProc}>
              <div className="modal-body">
                <div className="form-group-row">
                  <div className="form-group" style={{ flex: '0 0 120px' }}>
                    <label className="form-label">{t('stepNumber')}</label>
                    <input type="text" className="form-control" placeholder="e.g. 1.1"
                      value={procForm.step_number}
                      onChange={(e) => setProcForm({ ...procForm, step_number: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{t('procedureTitle')}</label>
                    <input type="text" className="form-control" placeholder="e.g. Verify payroll authorizations"
                      value={procForm.title}
                      onChange={(e) => setProcForm({ ...procForm, title: e.target.value })} required />
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">{t('descriptionInstructions')}</label>
                  <textarea rows="3" className="form-control"
                    placeholder="Describe the fieldwork steps to be performed..."
                    value={procForm.description}
                    onChange={(e) => setProcForm({ ...procForm, description: e.target.value })} required />
                </div>
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">{t('procedureType')}</label>
                    <select className="form-control" value={procForm.procedure_type}
                      onChange={(e) => setProcForm({ ...procForm, procedure_type: e.target.value })}>
                      <option value="test_of_controls">Test of Controls</option>
                      <option value="substantive">Substantive Testing</option>
                      <option value="analytical">Analytical Procedures</option>
                      <option value="inquiry">Inquiry</option>
                      <option value="observation">Observation</option>
                      <option value="inspection">Inspection & Re-performance</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">{t('assertion')}</label>
                    <input type="text" className="form-control"
                      placeholder="e.g. Completeness, Accuracy, Existence"
                      value={procForm.assertion}
                      onChange={(e) => setProcForm({ ...procForm, assertion: e.target.value })} />
                  </div>
                </div>
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">{t('riskArea')}</label>
                    <input type="text" className="form-control"
                      placeholder="e.g. Payroll Fraud Risk"
                      value={procForm.risk_area}
                      onChange={(e) => setProcForm({ ...procForm, risk_area: e.target.value })} />
                  </div>
                  <div className="form-group" style={{ flex: '0 0 80px' }}>
                    <label className="form-label">{t('order')}</label>
                    <input type="number" min="0" className="form-control"
                      value={procForm.order}
                      onChange={(e) => setProcForm({ ...procForm, order: parseInt(e.target.value) || 0 })} />
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">{t('expectedEvidence')}</label>
                  <textarea rows="2" className="form-control"
                    placeholder="Describe the evidence that should support this procedure..."
                    value={procForm.expected_evidence}
                    onChange={(e) => setProcForm({ ...procForm, expected_evidence: e.target.value })} />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowProcModal(false)}>{t('cancel')}</button>
                <button type="submit" className="btn btn-primary" disabled={savingProc}>
                  {savingProc ? 'Saving...' : editingProc ? t('updateProcedure') : t('addProcedureBtn')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Supervisor Review & Approve Modal */}
      {showReviewModal && program && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setShowReviewModal(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setShowReviewModal(false); }}
        >
          <div
            className="modal-card modal-large"
            role="dialog"
            aria-modal="true"
            aria-labelledby="review-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="review-modal-title"><ShieldCheck size={18} className="inline mr-2" />{t('supervisorReview')}</h3>
              <button
                type="button"
                className="close-btn"
                onClick={() => setShowReviewModal(false)}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>
            <div className="modal-body">
              {/* Program Summary */}
              <div className="review-program-summary mb-4" style={{ background: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', borderLeft: '3px solid var(--primary)' }}>
                <h4 className="mb-1">{program.title}</h4>
                <p className="text-sm"><strong>{t('objectivesLabel')}</strong> {program.objectives || '—'}</p>
                <p className="text-sm"><strong>{t('scopeLabel')}</strong> {program.scope || '—'}</p>
                <p className="text-sm mt-2"><strong>{t('totalProcedures')}</strong> {procedures.length}</p>
              </div>

              {/* Procedures Summary */}
              <div className="mb-4">
                <h4 className="mb-2">{t('fieldworkProceduresReview')}</h4>
                <table className="table">
                  <thead>
                    <tr>
                      <th>{t('step')}</th>
                      <th>{t('procedure')}</th>
                      <th>{t('type')}</th>
                      <th>{t('assertion')}</th>
                      <th>{t('status')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {procedures.map(proc => (
                      <tr key={proc.id}>
                        <td><strong>{proc.step_number}</strong></td>
                        <td>{proc.title}</td>
                        <td><span className="badge badge-outline" style={{ fontSize: '0.7rem' }}>{proc.procedure_type?.replace(/_/g, ' ')}</span></td>
                        <td>{proc.assertion || '—'}</td>
                        <td>
                          <span className={`badge ${proc.status === 'completed' ? 'badge-success' : proc.status === 'in_progress' ? 'badge-info' : 'badge-warning'}`} style={{ fontSize: '0.7rem' }}>
                            {proc.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="form-group">
                <label className="form-label">{t('reviewNotes')}</label>
                <textarea rows="3" className="form-control"
                  placeholder="Add any review comments or observations..."
                  value={reviewNotes}
                  onChange={(e) => setReviewNotes(e.target.value)} />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-outline" onClick={() => setShowReviewModal(false)}>{t('cancel')}</button>
              <button className="btn btn-primary flex items-center gap-2" onClick={handleApproveProgram}>
                <CheckCircle2 size={16} /> {t('approveProgram')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Working Paper Review Modal */}
      {showReviewWpModal && reviewingWp && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setShowReviewWpModal(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setShowReviewWpModal(false); }}
        >
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="review-wp-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="review-wp-modal-title">
                <CheckCircle2 size={18} className="inline mr-2" />
                {t('reviewWorkingPaper')}
              </h3>
              <button
                type="button"
                className="close-btn"
                onClick={() => setShowReviewWpModal(false)}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>
            <div className="modal-body">
              <div className="mb-4" style={{ background: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px' }}>
                <p className="text-sm mb-1"><strong>{t('docReference')}:</strong> {reviewingWp.reference}</p>
                <p className="text-sm mb-1"><strong>{t('documentTitle')}:</strong> {reviewingWp.title}</p>
                <p className="text-sm"><strong>{t('preparedBy')}:</strong> {reviewingWp.prepared_by_name || '—'}</p>
              </div>

              <div className="form-group">
                <label className="form-label">{t('reviewNotesLabel')}</label>
                <textarea
                  rows="4"
                  className="form-control"
                  placeholder={t('addReviewNotes')}
                  value={wpReviewNotes}
                  onChange={(e) => setWpReviewNotes(e.target.value)}
                />
              </div>
            </div>
            <div className="modal-footer">
              <button
                className="btn btn-outline"
                onClick={() => setShowReviewWpModal(false)}
              >
                {t('cancel')}
              </button>
              <button
                className="btn btn-primary flex items-center gap-2"
                onClick={handleReviewWp}
                disabled={submittingReview}
              >
                <CheckCircle2 size={16} />
                {submittingReview ? 'Submitting...' : t('markAsReviewed')}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default ExecutionPage;