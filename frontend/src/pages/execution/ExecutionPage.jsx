import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { executionApi, planningApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { usePermissions } from '../../hooks/usePermissions';
import useAsyncData from '../../hooks/useAsyncData';
import { useI18n } from '../../context/I18nContext';
import { validateForm, validators, hasErrors } from '../../utils/validation';
import Modal from '../../components/ui/Modal';
import FormErrorSummary from '../../components/ui/FormErrorSummary';
import EngagementPickerBar from '../../components/ui/EngagementPickerBar';
import {
  ListTodo, Plus, Paperclip, Upload, Eye, CheckCircle2,
  ClipboardList, ShieldCheck, Edit3, Trash2, Download
} from 'lucide-react';

/**
 * Which engagement a `/execution?...` deep link should open.
 *
 * Notifications link here as `?program=<id>` or `?engagement=<id>`, so a program
 * id is resolved back to the engagement that owns it rather than defaulting to
 * whatever engagement happens to be first. A stale or out-of-scope link is not
 * worth an error toast — it just falls through to the default.
 *
 * Module-level rather than a component closure: the loader below reads it, and
 * the compiler flags a `const` used at a call site textually before its own
 * declaration (the same error the old `useEffect` calling a later-declared
 * `fetchEngagements` produced).
 */
async function resolveDeepLinkEngagement(engList, focusEngagementId, focusProgramId) {
  const has = (id) => engList.some(e => String(e.id) === id);
  if (focusEngagementId && has(focusEngagementId)) return focusEngagementId;
  if (focusProgramId) {
    try {
      const prog = await executionApi.getProgram(focusProgramId);
      if (prog?.engagement && has(String(prog.engagement))) {
        return String(prog.engagement);
      }
    } catch {
      // Fall through to the default engagement.
    }
  }
  return String(engList[0].id);
}

function ExecutionPage() {
  const toast = useToast();
  const { t } = useI18n();
  const { canWriteAudit, canApprovePlans } = usePermissions();
  const [searchParams] = useSearchParams();
  const focusProgramId = searchParams.get('program');
  const focusEngagementId = searchParams.get('engagement');
  // The engagement the user has picked, held as an id and left empty until they
  // touch the picker. Anything that has to act on "the engagement on screen"
  // reads the resolved `activeEngId` below instead: before that first touch the
  // raw state is '' while the page is displaying the deep-linked one.
  const [selectedEngId, setSelectedEngId] = useState('');
  const [formErrors, setFormErrors] = useState({});

  // Current user for role-based UI
  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');

  // Working Papers
  const [uploadFile, setUploadFile] = useState(null);
  const [wpTitle, setWpTitle] = useState('');
  const [wpRef, setWpRef] = useState('');
  const [uploading, setUploading] = useState(false);

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

  // ─────────────────────────────────────────────────────────────
  // Data loading
  // ─────────────────────────────────────────────────────────────
  // Two independent hooks rather than one fetch chained onto the end of another.
  // Previously `fetchEngagements` ended by calling `fetchProgramAndProcedures`,
  // which set six pieces of state between its own awaits, none of them
  // cancellable or versioned — switching engagement twice in quick succession
  // could let the slower, earlier response land last and repaint the screen with
  // the program the user had already left, with nothing to hint at it.
  const { data: engagementsData, loading: engagementsLoading } = useAsyncData(
    async () => {
      const page = await planningApi.getEngagements();
      const items = page.items ?? [];
      // Which engagement to open on — the deep link's target, else the first —
      // rides back as part of the same value. Returning it from the loader is
      // what keeps it out of an effect that would write it back into a
      // dependency.
      const defaultId = items.length > 0
        ? await resolveDeepLinkEngagement(items, focusEngagementId, focusProgramId)
        : '';
      return { items, defaultId };
    },
    [focusEngagementId, focusProgramId],
    { onError: () => toast.error(t('engagementsLoadFailed')) },
  );

  const engagements = engagementsData?.items ?? [];
  // The resolved id, never the raw selection. The picker has to show the
  // engagement whose program is on screen, and every write payload below has to
  // file against that same engagement — posting `selectedEngId` while it is
  // still '' would file a program or working paper against no engagement at
  // all, a 400 that looks like the button is broken.
  const activeEngId = selectedEngId || engagementsData?.defaultId || '';

  const {
    data: executionData,
    loading: programLoading,
    error: programError,
    setData: setExecutionData,
  } = useAsyncData(
    async () => {
      const progs = await executionApi.getPrograms({ engagement: activeEngId });
      const progList = Array.isArray(progs) ? progs : [];
      const prog = progList[0] ?? null;
      // No program is a real answer, not a failure — it is what the page renders
      // the "create audit program" prompt from. Returning the same shape either
      // way means the render never has to tell "not loaded" from "none yet".
      if (!prog) {
        return {
          program: null,
          procedures: [], procedureCount: 0, proceduresTruncated: false,
          workingPapers: [], workingPaperCount: 0, workingPapersTruncated: false,
        };
      }
      const [procs, wps] = await Promise.all([
        executionApi.getProcedures({ program: prog.id }),
        executionApi.getWorkingPapers({ engagement: activeEngId }),
      ]);
      // Both answer with `{ items, count, hasMore }`: the section headings render
      // the server's total, which a bare array stops short of at DRF's PAGE_SIZE.
      return {
        program: prog,
        procedures: procs.items,
        procedureCount: procs.count,
        proceduresTruncated: procs.hasMore,
        workingPapers: wps.items,
        workingPaperCount: wps.count,
        workingPapersTruncated: wps.hasMore,
      };
    },
    [activeEngId],
    // `enabled` is load-bearing, not a nicety: `activeEngId` is '' until the
    // engagements arrive, and an unfiltered request would return every program
    // in the system.
    { enabled: Boolean(activeEngId), onError: () => toast.error(t('executionLoadFailed')) },
  );

  // All seven values are read off the one composite the request returned, rather
  // than each being its own `useState` that some handler had to keep in step by
  // hand.
  const program = executionData?.program ?? null;
  const procedures = executionData?.procedures ?? [];
  const procedureCount = executionData?.procedureCount ?? 0;
  const proceduresTruncated = executionData?.proceduresTruncated ?? false;
  const workingPapers = executionData?.workingPapers ?? [];
  const workingPaperCount = executionData?.workingPaperCount ?? 0;
  const workingPapersTruncated = executionData?.workingPapersTruncated ?? false;

  // The last clause covers the gap between `activeEngId` becoming non-empty and
  // the hook above flipping its own `loading` on: without it the "no audit
  // program" prompt paints for a frame over an engagement that has one.
  // `programError` keeps a failed load from spinning forever.
  const loading = engagementsLoading || programLoading
    || (Boolean(activeEngId) && executionData === null && !programError);

  // Optimistic edits go through the hook's `setData`: each touches one slice of
  // that composite, so merging into it is enough — no refetch to receive data
  // the handler already has in hand.
  const patchExecution = (patch) => setExecutionData(prev => ({ ...prev, ...patch }));

  const handleEngChange = (val) => {
    // Setting the selection *is* the request now: `activeEngId` is the
    // dependency of the load above, so re-picking the same engagement is a
    // no-op rather than a redundant refetch.
    setSelectedEngId(val);
  };

  // ─────────────────────────────────────────────────────────────
  // Auditor: Create Audit Program
  // ─────────────────────────────────────────────────────────────
  const openCreateProgram = () => {
    const selectedEng = engagements.find(e => String(e.id) === activeEngId);
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
      // The resolved engagement, not `selectedEngId`: the picker only leaves ''
      // once the user has touched it, so posting the raw state would file the
      // program against no engagement on the path every user takes when the
      // default is already the one they want.
      const payload = { ...programForm, engagement: activeEngId };
      const res = await executionApi.createProgram(payload);
      patchExecution({ program: res, procedures: [], procedureCount: 0, proceduresTruncated: false });
      setShowProgramModal(false);
      toast.success(t('executionProgramCreated'));
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : t('executionProgramCreateFailed');
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
        // PATCH — posting the form back with an `id` would create a duplicate.
        const res = await executionApi.updateProcedure(editingProc.id, procForm);
        patchExecution({
          procedures: procedures.map(p => p.id === editingProc.id ? res : p),
        });
        toast.success(t('executionProcedureUpdated'));
      } else {
        // Create new
        const payload = { ...procForm, program: program.id };
        const res = await executionApi.createProcedure(payload);
        patchExecution({
          procedures: [...procedures, res],
          procedureCount: procedureCount + 1,
        });
        toast.success(t('executionProcedureCreated'));
      }
      setShowProcModal(false);
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : t('executionProcedureSaveFailed');
      toast.error(msg);
    } finally {
      setSavingProc(false);
    }
  };

  const handleDeleteProc = async (procId) => {
    if (!window.confirm(t('deleteProcedure'))) return;
    try {
      await executionApi.deleteProcedure(procId);
      patchExecution({
        procedures: procedures.filter(p => p.id !== procId),
        procedureCount: Math.max(0, procedureCount - 1),
      });
      toast.success(t('executionProcedureRemoved'));
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : t('executionProcedureDeleteFailed');
      toast.error(msg);
    }
  };

  const handleStatusChange = async (procId, newStatus) => {
    try {
      // 'completed' goes through the dedicated action so the server stamps
      // completed_by/completed_at and notifies the engagement lead; anything
      // else is a plain status PATCH.
      const res = newStatus === 'completed'
        ? await executionApi.completeProcedure(procId)
        : await executionApi.updateProcedure(procId, { status: newStatus });
      // The complete action returns a detail message, not the record, so fall
      // back to patching status locally when there is no object to merge.
      patchExecution({
        procedures: procedures.map(p => (
          p.id === procId ? { ...p, ...(res?.id ? res : { status: newStatus }) } : p
        )),
      });
      toast.success(t('executionProcedureStatusSet', newStatus));
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : t('executionProcedureStatusFailed');
      toast.error(msg);
    }
  };

  // ─────────────────────────────────────────────────────────────
  // Auditor: Submit Program for Review
  // ─────────────────────────────────────────────────────────────
  const handleSubmitProgram = async () => {
    try {
      await executionApi.submitForReview(program.id);
      patchExecution({ program: { ...program, status: 'submitted' } });
      toast.success(t('executionProgramSubmitted'));
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : t('executionProgramSubmitFailed');
      toast.error(msg);
    }
  };

  // ─────────────────────────────────────────────────────────────
  // Supervisor: Approve Program
  // ─────────────────────────────────────────────────────────────
  const handleApproveProgram = async () => {
    try {
      await executionApi.approveFieldwork(program.id);
      patchExecution({ program: { ...program, status: 'approved' } });
      setShowReviewModal(false);
      toast.success(t('executionProgramApproved'));
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : t('executionProgramApproveFailed');
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
    // Resolved, as above: `selectedEngId` is '' until the picker is touched.
    formData.append('engagement', activeEngId);
    try {
      const response = await executionApi.uploadWorkingPaper(formData);
      patchExecution({
        workingPapers: [response, ...workingPapers],
        workingPaperCount: workingPaperCount + 1,
      });
      setWpTitle(''); setWpRef(''); setUploadFile(null);
      toast.success(t('executionWpUploaded'));
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error(t('executionWpUploadFailed', msg));
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteWp = async (wp) => {
    if (!window.confirm(t('removeWorkpaper', wp.title))) return;
    try {
      await executionApi.deleteWorkingPaper(wp.id);
      patchExecution({
        workingPapers: workingPapers.filter(x => x.id !== wp.id),
        workingPaperCount: Math.max(0, workingPaperCount - 1),
      });
      toast.success(t('executionWpRemoved'));
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : t('executionWpRemoveFailed');
      toast.error(msg);
    }
  };

  const handleDownloadWp = async (wp) => {
    try {
      await executionApi.downloadWorkingPaper(wp.id, wp.title);
    } catch {
      toast.error(t('executionWpDownloadFailed'));
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
      patchExecution({
        workingPapers: workingPapers.map(wp =>
          wp.id === reviewingWp.id
            ? {
                ...wp,
                is_reviewed: true,
                reviewed_by_name: currentUser.full_name || currentUser.username,
                review_notes: wpReviewNotes,
              }
            : wp
        ),
      });
      setShowReviewWpModal(false);
      setReviewingWp(null);
      setWpReviewNotes('');
      toast.success(t('paperReviewed'));
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : t('executionWpReviewFailed');
      toast.error(msg);
    } finally {
      setSubmittingReview(false);
    }
  };

  // Status badge color
  const programStatusBadge = (status) => {
    const map = { draft: 'badge-warning', submitted: 'badge-info', approved: 'badge-success', active: 'badge-success', completed: 'badge-success' };
    return map[status] || 'badge-outline';
  };

  return (
    <div className="execution-view">

      {/* Engagement Selector */}
      <div className="card mb-4">
        <EngagementPickerBar
          idPrefix="active"
          engagements={engagements}
          // The resolved id, not the raw selection: the picker has to show the
          // engagement whose program is on screen, and that is the deep-linked
          // (or first) one until the user picks otherwise.
          value={activeEngId}
          onChange={handleEngChange}
          label={t('selectActiveEngagement')}
        />
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
                <div>
                  <h3 className="section-title">{t('fieldworkProcedures')} ({procedureCount})</h3>
                  {proceduresTruncated && (
                    <p className="text-xs text-muted">{t('showingFirstOf', procedures.length, procedureCount)}</p>
                  )}
                </div>
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
                {/* Deliberately no `noValidate`: `handleUploadWp` runs no
                    `validateForm` and this form has no error banner, so the
                    browser's `required` is the only thing enforcing
                    `wp_reference` / `wp_title` / `wp_file`. Turning it off would
                    convert a browser block into a silent no-op. */}
                <form onSubmit={handleUploadWp}>
                  <div className="form-group">
                    <label className="form-label" htmlFor="wp_reference">{t('docReference')}</label>
                    <input id="wp_reference" type="text" className="form-control" placeholder={t('executionWpRefPlaceholder')}
                      value={wpRef} onChange={(e) => setWpRef(e.target.value)} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="wp_title">{t('documentTitle')}</label>
                    <input id="wp_title" type="text" className="form-control" placeholder={t('executionWpTitlePlaceholder')}
                      value={wpTitle} onChange={(e) => setWpTitle(e.target.value)} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="wp_file">{t('selectFile')}</label>
                    <input id="wp_file" type="file" className="form-control" onChange={(e) => setUploadFile(e.target.files[0])} required />
                  </div>
                  <button type="submit" className="btn btn-primary btn-block flex items-center justify-center gap-2" disabled={uploading}>
                    <Upload size={16} /> {uploading ? t('executionUploading') : t('uploadWorkpaper')}
                  </button>
                </form>
              </div>
            )}

            {/* Working Papers Registry */}
            <div className="card">
              <h3>{t('workingPapersRegistry')} ({workingPaperCount})</h3>
              {workingPapersTruncated && (
                <p className="text-xs text-muted">{t('showingFirstOf', workingPapers.length, workingPaperCount)}</p>
              )}
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
      <Modal
        isOpen={showProgramModal}
        onClose={() => setShowProgramModal(false)}
        title={t('createProgramTitle')}
        size="xl"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={() => setShowProgramModal(false)}>{t('cancel')}</button>
            {/* `form=` because Modal renders the footer as a sibling of its
                children, so the submit button sits outside the <form>. */}
            <button type="submit" form="program-form" className="btn btn-primary" disabled={savingProgram}>
              {savingProgram ? t('executionCreating') : t('createProgram')}
            </button>
          </>
        )}
      >
        {/* `noValidate` hands validation to the app, as UsersPage's forms do.
            Without it the browser intercepts an empty submit and React's
            onSubmit never fires — so `validateForm` never runs, the banner
            below never renders, and the user gets a tooltip instead of the
            named field. The one `required` input here (`program_title`) is also
            covered by the schema below, so nothing stops being enforced. */}
        <form id="program-form" onSubmit={handleCreateProgram} noValidate>
          <FormErrorSummary errors={formErrors} />
          <div className="form-group">
            <label className="form-label" htmlFor="program_title">{t('programTitle')}</label>
            <input id="program_title" type="text" className="form-control"
              placeholder={t('executionProgramTitlePlaceholder')}
              value={programForm.title}
              onChange={(e) => setProgramForm({ ...programForm, title: e.target.value })}
              required />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="program_objectives">{t('auditObjectives')}</label>
            <textarea id="program_objectives" rows="3" className="form-control"
              placeholder={t('executionObjectivesPlaceholder')}
              value={programForm.objectives}
              onChange={(e) => setProgramForm({ ...programForm, objectives: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="program_scope">{t('auditScope')}</label>
            <textarea id="program_scope" rows="3" className="form-control"
              placeholder={t('executionScopePlaceholder')}
              value={programForm.scope}
              onChange={(e) => setProgramForm({ ...programForm, scope: e.target.value })}
            />
          </div>
        </form>
      </Modal>

      {/* Add / Edit Procedure Modal */}
      <Modal
        isOpen={showProcModal}
        onClose={() => setShowProcModal(false)}
        title={editingProc ? t('editProcedureTitle') : t('addProcedureTitle')}
        size="xl"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={() => setShowProcModal(false)}>{t('cancel')}</button>
            <button type="submit" form="procedure-form" className="btn btn-primary" disabled={savingProc}>
              {savingProc ? t('layoutSaving') : editingProc ? t('updateProcedure') : t('addProcedureBtn')}
            </button>
          </>
        )}
      >
        {/* `noValidate` for the same reason as the program form above: all three
            `required` inputs (`proc_step_number`, `proc_title`,
            `proc_description`) are also covered by `validateForm`, so the app's
            banner replaces a browser tooltip rather than weakening anything. */}
        <form id="procedure-form" onSubmit={handleSaveProc} noValidate>
          <FormErrorSummary errors={formErrors} />
          <div className="form-group-row">
            <div className="form-group" style={{ flex: '0 0 120px' }}>
              <label className="form-label" htmlFor="proc_step_number">{t('stepNumber')}</label>
              <input id="proc_step_number" type="text" className="form-control" placeholder={t('executionStepPlaceholder')}
                value={procForm.step_number}
                onChange={(e) => setProcForm({ ...procForm, step_number: e.target.value })} required />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="proc_title">{t('procedureTitle')}</label>
              <input id="proc_title" type="text" className="form-control" placeholder={t('executionProcedureTitlePlaceholder')}
                value={procForm.title}
                onChange={(e) => setProcForm({ ...procForm, title: e.target.value })} required />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="proc_description">{t('descriptionInstructions')}</label>
            <textarea id="proc_description" rows="3" className="form-control"
              placeholder={t('executionDescriptionPlaceholder')}
              value={procForm.description}
              onChange={(e) => setProcForm({ ...procForm, description: e.target.value })} required />
          </div>
          <div className="form-group-row">
            <div className="form-group">
              <label className="form-label" htmlFor="proc_type">{t('procedureType')}</label>
              <select id="proc_type" className="form-control" value={procForm.procedure_type}
                onChange={(e) => setProcForm({ ...procForm, procedure_type: e.target.value })}>
                <option value="test_of_controls">{t('procedureTestOfControls')}</option>
                <option value="substantive">{t('procedureSubstantive')}</option>
                <option value="analytical">{t('procedureAnalytical')}</option>
                <option value="inquiry">{t('procedureInquiry')}</option>
                <option value="observation">{t('procedureObservation')}</option>
                <option value="inspection">{t('procedureInspection')}</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="proc_assertion">{t('assertion')}</label>
              <input id="proc_assertion" type="text" className="form-control"
                placeholder={t('executionAssertionPlaceholder')}
                value={procForm.assertion}
                onChange={(e) => setProcForm({ ...procForm, assertion: e.target.value })} />
            </div>
          </div>
          <div className="form-group-row">
            <div className="form-group">
              <label className="form-label" htmlFor="proc_risk_area">{t('riskArea')}</label>
              <input id="proc_risk_area" type="text" className="form-control"
                placeholder={t('executionRiskAreaPlaceholder')}
                value={procForm.risk_area}
                onChange={(e) => setProcForm({ ...procForm, risk_area: e.target.value })} />
            </div>
            <div className="form-group" style={{ flex: '0 0 80px' }}>
              <label className="form-label" htmlFor="proc_order">{t('order')}</label>
              <input id="proc_order" type="number" min="0" className="form-control"
                value={procForm.order}
                onChange={(e) => setProcForm({ ...procForm, order: parseInt(e.target.value) || 0 })} />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="proc_expected_evidence">{t('expectedEvidence')}</label>
            <textarea id="proc_expected_evidence" rows="2" className="form-control"
              placeholder={t('executionEvidencePlaceholder')}
              value={procForm.expected_evidence}
              onChange={(e) => setProcForm({ ...procForm, expected_evidence: e.target.value })} />
          </div>
        </form>
      </Modal>

      {/* Supervisor Review & Approve Modal */}
      <Modal
        isOpen={Boolean(showReviewModal && program)}
        onClose={() => setShowReviewModal(false)}
        title={t('supervisorReview')}
        size="xl"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={() => setShowReviewModal(false)}>{t('cancel')}</button>
            <button type="button" className="btn btn-primary flex items-center gap-2" onClick={handleApproveProgram}>
              <CheckCircle2 size={16} /> {t('approveProgram')}
            </button>
          </>
        )}
      >
        {program && (
          <>
            {/* Program Summary */}
            <div className="review-program-summary mb-4" style={{ background: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', borderLeft: '3px solid var(--primary)' }}>
              <h4 className="mb-1">{program.title}</h4>
              <p className="text-sm"><strong>{t('objectivesLabel')}</strong> {program.objectives || '—'}</p>
              <p className="text-sm"><strong>{t('scopeLabel')}</strong> {program.scope || '—'}</p>
              <p className="text-sm mt-2"><strong>{t('totalProcedures')}</strong> {procedureCount}</p>
            </div>

            {/* Procedures Summary */}
            <div className="mb-4">
              <h4 className="mb-2">{t('fieldworkProceduresReview')}</h4>
              {/* .table has no min-width of its own, so without this wrapper the
                  columns compress instead of scrolling on a narrow screen. */}
              <div className="table-responsive">
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
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="program_review_notes">{t('reviewNotes')}</label>
              <textarea id="program_review_notes" rows="3" className="form-control"
                placeholder={t('executionReviewNotesPlaceholder')}
                value={reviewNotes}
                onChange={(e) => setReviewNotes(e.target.value)} />
            </div>
          </>
        )}
      </Modal>

      {/* Working Paper Review Modal */}
      <Modal
        isOpen={Boolean(showReviewWpModal && reviewingWp)}
        onClose={() => setShowReviewWpModal(false)}
        title={t('reviewWorkingPaper')}
        size="lg"
        footer={(
          <>
            <button
              type="button"
              className="btn btn-outline"
              onClick={() => setShowReviewWpModal(false)}
            >
              {t('cancel')}
            </button>
            <button
              type="button"
              className="btn btn-primary flex items-center gap-2"
              onClick={handleReviewWp}
              disabled={submittingReview}
            >
              <CheckCircle2 size={16} />
              {submittingReview ? t('executionSubmitting') : t('markAsReviewed')}
            </button>
          </>
        )}
      >
        {reviewingWp && (
          <>
            <div className="mb-4" style={{ background: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px' }}>
              <p className="text-sm mb-1"><strong>{t('docReference')}:</strong> {reviewingWp.reference}</p>
              <p className="text-sm mb-1"><strong>{t('documentTitle')}:</strong> {reviewingWp.title}</p>
              <p className="text-sm"><strong>{t('preparedBy')}:</strong> {reviewingWp.prepared_by_name || '—'}</p>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="wp_review_notes">{t('reviewNotesLabel')}</label>
              <textarea
                id="wp_review_notes"
                rows="4"
                className="form-control"
                placeholder={t('addReviewNotes')}
                value={wpReviewNotes}
                onChange={(e) => setWpReviewNotes(e.target.value)}
              />
            </div>
          </>
        )}
      </Modal>

    </div>
  );
}

export default ExecutionPage;