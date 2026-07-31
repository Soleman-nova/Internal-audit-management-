import React, { useState, useEffect } from 'react';
import apiClient from '../../api/apiClient';
import { usePermissions } from '../../hooks/usePermissions';
import {
  ListTodo, Plus, Paperclip, Upload, Eye, CheckCircle2,
  ClipboardList, ShieldCheck, Edit3, Trash2, ChevronDown
} from 'lucide-react';

function ExecutionPage() {
  const { canWriteAudit, canApprovePlans } = usePermissions();
  const [engagements, setEngagements] = useState([]);
  const [selectedEngId, setSelectedEngId] = useState('');
  const [program, setProgram] = useState(null);
  const [procedures, setProcedures] = useState([]);
  const [loading, setLoading] = useState(false);

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

  useEffect(() => {
    fetchEngagements();
  }, []);

  const fetchEngagements = async () => {
    try {
      const res = await apiClient.get('/planning/engagements/');
      const list = res.data.results || [];
      setEngagements(list);
      if (list.length > 0) {
        setSelectedEngId(list[0].id);
        fetchProgramAndProcedures(list[0].id);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const fetchProgramAndProcedures = async (engId) => {
    setLoading(true);
    try {
      const progRes = await apiClient.get(`/execution/programs/?engagement=${engId}`);
      if (progRes.data.results?.length > 0) {
        const prog = progRes.data.results[0];
        setProgram(prog);
        const procRes = await apiClient.get(`/execution/procedures/?program=${prog.id}`);
        setProcedures(procRes.data.results || []);
        const wpRes = await apiClient.get(`/execution/working-papers/?engagement=${engId}`);
        setWorkingPapers(wpRes.data.results || []);
      } else {
        setProgram(null);
        setProcedures([]);
        setWorkingPapers([]);
      }
    } catch (err) {
      console.error(err);
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
    setSavingProgram(true);
    try {
      const payload = { ...programForm, engagement: selectedEngId };
      const res = await apiClient.post('/execution/programs/', payload);
      setProgram(res.data);
      setProcedures([]);
      setShowProgramModal(false);
    } catch (err) {
      alert(err.response?.data ? JSON.stringify(err.response.data) : 'Failed to create audit program');
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
    setSavingProc(true);
    try {
      if (editingProc) {
        // Update existing
        const res = await apiClient.patch(`/execution/procedures/${editingProc.id}/`, procForm);
        setProcedures(procedures.map(p => p.id === editingProc.id ? res.data : p));
      } else {
        // Create new
        const payload = { ...procForm, program: program.id };
        const res = await apiClient.post('/execution/procedures/', payload);
        setProcedures([...procedures, res.data]);
      }
      setShowProcModal(false);
    } catch (err) {
      alert(err.response?.data ? JSON.stringify(err.response.data) : 'Failed to save procedure');
    } finally {
      setSavingProc(false);
    }
  };

  const handleDeleteProc = async (procId) => {
    if (!window.confirm('Delete this procedure?')) return;
    try {
      await apiClient.delete(`/execution/procedures/${procId}/`);
      setProcedures(procedures.filter(p => p.id !== procId));
    } catch (err) {
      alert('Failed to delete procedure');
    }
  };

  const handleStatusChange = async (procId, newStatus) => {
    try {
      await apiClient.patch(`/execution/procedures/${procId}/`, { status: newStatus });
      setProcedures(procedures.map(p => p.id === procId ? { ...p, status: newStatus } : p));
    } catch (err) {
      console.error(err);
    }
  };

  // ─────────────────────────────────────────────────────────────
  // Auditor: Submit Program for Review
  // ─────────────────────────────────────────────────────────────
  const handleSubmitProgram = async () => {
    try {
      await apiClient.post(`/execution/programs/${program.id}/submit/`);
      setProgram({ ...program, status: 'submitted' });
      alert('Audit program submitted for supervisor review!');
    } catch (err) {
      alert(err.response?.data ? JSON.stringify(err.response.data) : 'Failed to submit program');
    }
  };

  // ─────────────────────────────────────────────────────────────
  // Supervisor: Approve Program
  // ─────────────────────────────────────────────────────────────
  const handleApproveProgram = async () => {
    try {
      await apiClient.post(`/execution/programs/${program.id}/approve/`);
      setProgram({ ...program, status: 'approved' });
      setShowReviewModal(false);
      alert('Audit program approved successfully!');
    } catch (err) {
      alert(err.response?.data ? JSON.stringify(err.response.data) : 'Failed to approve program');
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
      const response = await apiClient.post('/execution/working-papers/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setWorkingPapers([response.data, ...workingPapers]);
      setWpTitle(''); setWpRef(''); setUploadFile(null);
      alert('Working paper uploaded successfully!');
    } catch (err) {
      alert('Upload failed: ' + JSON.stringify(err.response?.data || err.message));
    } finally {
      setUploading(false);
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
          <label className="form-label font-bold text-lg">Select Active Audit Engagement</label>
          <select className="form-control" value={selectedEngId} onChange={handleEngChange}>
            {engagements.map(e => (
              <option key={e.id} value={e.id}>{e.engagement_number} — {e.title}</option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="loading-spinner">Loading audit program &amp; fieldwork data...</div>
      ) : !program ? (
        /* ── No Program Yet ── */
        <div className="card">
          <div className="text-center py-8">
            <ListTodo size={48} className="mx-auto text-muted mb-4" />
            <h3>No Audit Program Defined</h3>
            <p className="text-muted mb-4">An audit program has not been created for this engagement yet.</p>
            {canWriteAudit && (
              <button className="btn btn-primary flex items-center gap-2 mx-auto" onClick={openCreateProgram}>
                <Plus size={16} /> Create Audit Program
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
                      <ClipboardList size={14} /> Submit for Review
                    </button>
                  )}
                  {/* Supervisor: Approve */}
                  {canApprovePlans && program.status === 'submitted' && (
                    <button className="btn btn-sm btn-primary flex items-center gap-1" onClick={() => setShowReviewModal(true)}>
                      <ShieldCheck size={14} /> Review &amp; Approve
                    </button>
                  )}
                </div>
              </div>
              <h2>{program.title}</h2>
              <div className="mt-2 text-sm text-secondary">
                <p><strong>Objectives:</strong> {program.objectives || '—'}</p>
                <p><strong>Scope:</strong> {program.scope || '—'}</p>
              </div>
            </div>

            {/* Procedures List */}
            <div className="procedure-list-section">
              <div className="flex items-center justify-between mb-3">
                <h3 className="section-title">Fieldwork Procedures ({procedures.length})</h3>
                {/* Auditor: Add procedure if program is draft */}
                {canWriteAudit && (program.status === 'draft' || program.status === 'active') && (
                  <button className="btn btn-sm btn-primary flex items-center gap-1" onClick={openNewProc}>
                    <Plus size={14} /> Add Procedure
                  </button>
                )}
              </div>

              {procedures.length === 0 ? (
                <div className="text-center py-6 text-muted">
                  <p>No fieldwork procedures defined yet.</p>
                  {canWriteAudit && (
                    <button className="btn btn-sm btn-outline mt-2" onClick={openNewProc}>
                      Add First Procedure
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
                          <span className="badge badge-outline" style={{fontSize:'0.7rem', opacity:0.8}}>
                            {proc.assertion}
                          </span>
                        )}
                      </div>
                      <div className="proc-content">
                        <h4>{proc.title}</h4>
                        <p>{proc.description}</p>
                        {proc.risk_area && (
                          <div className="text-xs text-muted mt-1">
                            <strong>Risk Area:</strong> {proc.risk_area}
                          </div>
                        )}
                        {proc.expected_evidence && (
                          <div className="expected-ev text-xs text-muted mt-1">
                            <strong>Expected Evidence:</strong> {proc.expected_evidence}
                          </div>
                        )}
                      </div>
                      <div className="proc-actions">
                        <select
                          className={`form-control select-sm ${proc.status === 'completed' ? 'border-success text-success' : proc.status === 'in_progress' ? 'border-info text-info' : ''}`}
                          value={proc.status}
                          onChange={(e) => handleStatusChange(proc.id, e.target.value)}
                        >
                          <option value="pending">Pending</option>
                          <option value="in_progress">In Progress</option>
                          <option value="completed">Completed</option>
                          <option value="not_applicable">N/A</option>
                        </select>
                        {canWriteAudit && program.status === 'draft' && (
                          <div className="flex gap-1 mt-1">
                            <button className="btn-icon" title="Edit" onClick={() => openEditProc(proc)}>
                              <Edit3 size={14} />
                            </button>
                            <button className="btn-icon text-danger" title="Delete" onClick={() => handleDeleteProc(proc.id)}>
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
              <h3>Upload Working Paper</h3>
              <p className="card-subtitle mb-4">Attach evidence, worksheets, or review matrices</p>
              <form onSubmit={handleUploadWp}>
                <div className="form-group">
                  <label className="form-label">Doc Reference #</label>
                  <input type="text" className="form-control" placeholder="e.g. WP-A.1.1"
                    value={wpRef} onChange={(e) => setWpRef(e.target.value)} required />
                </div>
                <div className="form-group">
                  <label className="form-label">Document Title</label>
                  <input type="text" className="form-control" placeholder="e.g. Access Rights Mapping Sheet"
                    value={wpTitle} onChange={(e) => setWpTitle(e.target.value)} required />
                </div>
                <div className="form-group">
                  <label className="form-label">Select File</label>
                  <input type="file" className="form-control" onChange={(e) => setUploadFile(e.target.files[0])} required />
                </div>
                <button type="submit" className="btn btn-primary btn-block flex items-center justify-center gap-2" disabled={uploading}>
                  <Upload size={16} /> {uploading ? 'Uploading...' : 'Upload Workpaper'}
                </button>
              </form>
            </div>
            )}

            {/* Working Papers Registry */}
            <div className="card">
              <h3>Working Papers Registry ({workingPapers.length})</h3>
              <div className="wp-registry mt-3">
                {workingPapers.length === 0 ? (
                  <p className="text-muted text-center py-4">No working papers uploaded yet.</p>
                ) : (
                  workingPapers.map(wp => (
                    <div key={wp.id} className="wp-item">
                      <div className="wp-icon"><Paperclip size={18} /></div>
                      <div className="wp-info">
                        <strong>{wp.reference}</strong>
                        <span className="wp-title-text">{wp.title}</span>
                        {wp.is_reviewed && (
                          <span className="badge badge-success" style={{fontSize:'0.65rem'}}>Reviewed</span>
                        )}
                      </div>
                      <div className="wp-action">
                        {wp.file && (
                          <a href={wp.file} target="_blank" rel="noreferrer" className="btn-icon">
                            <Eye size={16} />
                          </a>
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
        <div className="modal-backdrop">
          <div className="modal-card modal-large">
            <div className="modal-header">
              <h3>Create Audit Program</h3>
              <button className="close-btn" onClick={() => setShowProgramModal(false)}>×</button>
            </div>
            <form onSubmit={handleCreateProgram}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Program Title</label>
                  <input type="text" className="form-control"
                    placeholder="e.g. Payroll Compliance Audit Program"
                    value={programForm.title}
                    onChange={(e) => setProgramForm({...programForm, title: e.target.value})}
                    required />
                </div>
                <div className="form-group">
                  <label className="form-label">Audit Objectives</label>
                  <textarea rows="3" className="form-control"
                    placeholder="Describe the objectives of this audit engagement..."
                    value={programForm.objectives}
                    onChange={(e) => setProgramForm({...programForm, objectives: e.target.value})}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Audit Scope</label>
                  <textarea rows="3" className="form-control"
                    placeholder="Define the boundaries and scope of this audit..."
                    value={programForm.scope}
                    onChange={(e) => setProgramForm({...programForm, scope: e.target.value})}
                  />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowProgramModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={savingProgram}>
                  {savingProgram ? 'Creating...' : 'Create Program'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add / Edit Procedure Modal */}
      {showProcModal && (
        <div className="modal-backdrop">
          <div className="modal-card modal-large">
            <div className="modal-header">
              <h3>{editingProc ? 'Edit Fieldwork Procedure' : 'Add Fieldwork Procedure'}</h3>
              <button className="close-btn" onClick={() => setShowProcModal(false)}>×</button>
            </div>
            <form onSubmit={handleSaveProc}>
              <div className="modal-body">
                <div className="form-group-row">
                  <div className="form-group" style={{flex:'0 0 120px'}}>
                    <label className="form-label">Step Number</label>
                    <input type="text" className="form-control" placeholder="e.g. 1.1"
                      value={procForm.step_number}
                      onChange={(e) => setProcForm({...procForm, step_number: e.target.value})} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Procedure Title</label>
                    <input type="text" className="form-control" placeholder="e.g. Verify payroll authorizations"
                      value={procForm.title}
                      onChange={(e) => setProcForm({...procForm, title: e.target.value})} required />
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Description / Instructions</label>
                  <textarea rows="3" className="form-control"
                    placeholder="Describe the fieldwork steps to be performed..."
                    value={procForm.description}
                    onChange={(e) => setProcForm({...procForm, description: e.target.value})} required />
                </div>
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Procedure Type</label>
                    <select className="form-control" value={procForm.procedure_type}
                      onChange={(e) => setProcForm({...procForm, procedure_type: e.target.value})}>
                      <option value="test_of_controls">Test of Controls</option>
                      <option value="substantive">Substantive Testing</option>
                      <option value="analytical">Analytical Procedures</option>
                      <option value="inquiry">Inquiry</option>
                      <option value="observation">Observation</option>
                      <option value="inspection">Inspection &amp; Re-performance</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Assertion(s)</label>
                    <input type="text" className="form-control"
                      placeholder="e.g. Completeness, Accuracy, Existence"
                      value={procForm.assertion}
                      onChange={(e) => setProcForm({...procForm, assertion: e.target.value})} />
                  </div>
                </div>
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Risk Area</label>
                    <input type="text" className="form-control"
                      placeholder="e.g. Payroll Fraud Risk"
                      value={procForm.risk_area}
                      onChange={(e) => setProcForm({...procForm, risk_area: e.target.value})} />
                  </div>
                  <div className="form-group" style={{flex:'0 0 80px'}}>
                    <label className="form-label">Order</label>
                    <input type="number" min="0" className="form-control"
                      value={procForm.order}
                      onChange={(e) => setProcForm({...procForm, order: parseInt(e.target.value) || 0})} />
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Expected Evidence</label>
                  <textarea rows="2" className="form-control"
                    placeholder="Describe the evidence that should support this procedure..."
                    value={procForm.expected_evidence}
                    onChange={(e) => setProcForm({...procForm, expected_evidence: e.target.value})} />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowProcModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={savingProc}>
                  {savingProc ? 'Saving...' : editingProc ? 'Update Procedure' : 'Add Procedure'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Supervisor Review & Approve Modal */}
      {showReviewModal && program && (
        <div className="modal-backdrop">
          <div className="modal-card modal-large">
            <div className="modal-header">
              <h3><ShieldCheck size={18} className="inline mr-2" />Supervisor Review — Audit Program</h3>
              <button className="close-btn" onClick={() => setShowReviewModal(false)}>×</button>
            </div>
            <div className="modal-body">
              {/* Program Summary */}
              <div className="review-program-summary mb-4" style={{background:'var(--bg-secondary)', padding:'1rem', borderRadius:'8px', borderLeft:'3px solid var(--primary)'}}>
                <h4 className="mb-1">{program.title}</h4>
                <p className="text-sm"><strong>Objectives:</strong> {program.objectives || '—'}</p>
                <p className="text-sm"><strong>Scope:</strong> {program.scope || '—'}</p>
                <p className="text-sm mt-2"><strong>Total Procedures:</strong> {procedures.length}</p>
              </div>

              {/* Procedures Summary */}
              <div className="mb-4">
                <h4 className="mb-2">Fieldwork Procedures Review</h4>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Step</th>
                      <th>Procedure</th>
                      <th>Type</th>
                      <th>Assertion</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {procedures.map(proc => (
                      <tr key={proc.id}>
                        <td><strong>{proc.step_number}</strong></td>
                        <td>{proc.title}</td>
                        <td><span className="badge badge-outline" style={{fontSize:'0.7rem'}}>{proc.procedure_type?.replace(/_/g,' ')}</span></td>
                        <td>{proc.assertion || '—'}</td>
                        <td>
                          <span className={`badge ${proc.status === 'completed' ? 'badge-success' : proc.status === 'in_progress' ? 'badge-info' : 'badge-warning'}`} style={{fontSize:'0.7rem'}}>
                            {proc.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="form-group">
                <label className="form-label">Review Notes (Optional)</label>
                <textarea rows="3" className="form-control"
                  placeholder="Add any review comments or observations..."
                  value={reviewNotes}
                  onChange={(e) => setReviewNotes(e.target.value)} />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-outline" onClick={() => setShowReviewModal(false)}>Cancel</button>
              <button className="btn btn-primary flex items-center gap-2" onClick={handleApproveProgram}>
                <CheckCircle2 size={16} /> Approve Program
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default ExecutionPage;
