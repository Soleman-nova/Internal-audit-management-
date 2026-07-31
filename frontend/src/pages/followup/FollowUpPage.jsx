import React, { useState, useEffect } from 'react';
import apiClient, { authApi } from '../../api/apiClient';
import { usePermissions } from '../../hooks/usePermissions';
import { CheckCircle2, Clock, ShieldAlert, MessageCircle, RefreshCw, Plus, FileUp } from 'lucide-react';

function FollowUpPage() {
  const { canWriteAudit } = usePermissions();
  const [capas, setCapas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('all');
  const [currentUser, setCurrentUser] = useState(null);

  // Spawning CAPA Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [findings, setFindings] = useState([]);
  const [auditees, setAuditees] = useState([]);
  const [newCapa, setNewCapa] = useState({
    finding: '',
    title: '',
    description: '',
    recommendation: '',
    owner: '',
    priority: 'medium',
    due_date: ''
  });
  const [creating, setCreating] = useState(false);

  // Auditee Response Modal State
  const [showResponseModal, setShowResponseModal] = useState(false);
  const [selectedCapa, setSelectedCapa] = useState(null);
  const [responseText, setResponseText] = useState('');
  const [statusUpdate, setStatusUpdate] = useState('in_progress');
  const [evidenceFile, setEvidenceFile] = useState(null);
  const [submittingResponse, setSubmittingResponse] = useState(false);

  useEffect(() => {
    const user = authApi.getCurrentUser();
    setCurrentUser(user);
    fetchCapas();
    if (user && user.role !== 'auditee') {
      fetchFindingsAndAuditees();
    }
  }, []);

  const fetchCapas = async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/corrective/actions/');
      setCapas(res.data.results || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchFindingsAndAuditees = async () => {
    try {
      const [findingsRes, usersRes] = await Promise.all([
        apiClient.get('/findings/findings/'),
        apiClient.get('/auth/users/?role=auditee')
      ]);
      setFindings(findingsRes.data.results || []);
      setAuditees(usersRes.data.results || []);
    } catch (err) {
      console.error('Error fetching findings/auditees:', err);
    }
  };

  const handleFindingChange = (e) => {
    const findingId = e.target.value;
    const selectedFinding = findings.find(f => f.id.toString() === findingId.toString());
    if (selectedFinding) {
      setNewCapa({
        ...newCapa,
        finding: findingId,
        title: `CAPA: ${selectedFinding.title}`,
        description: selectedFinding.description || '',
        recommendation: selectedFinding.recommendation || ''
      });
    } else {
      setNewCapa({
        ...newCapa,
        finding: findingId,
        title: '',
        description: '',
        recommendation: ''
      });
    }
  };

  const handleCreateCapa = async (e) => {
    e.preventDefault();
    setCreating(true);
    try {
      const res = await apiClient.post('/corrective/actions/', newCapa);
      setCapas([res.data, ...capas]);
      setShowCreateModal(false);
      setNewCapa({
        finding: '',
        title: '',
        description: '',
        recommendation: '',
        owner: '',
        priority: 'medium',
        due_date: ''
      });
      alert('CAPA task successfully spawned and assigned!');
    } catch (err) {
      alert('Failed to spawn CAPA: ' + JSON.stringify(err.response?.data || err.message));
    } finally {
      setCreating(false);
    }
  };

  const handleOpenResponse = (capa) => {
    setSelectedCapa(capa);
    setShowResponseModal(true);
    setResponseText('');
    setStatusUpdate(capa.status || 'in_progress');
    setEvidenceFile(null);
  };

  const handleSubmitResponse = async (e) => {
    e.preventDefault();
    if (!selectedCapa) return;
    setSubmittingResponse(true);

    try {
      const formData = new FormData();
      formData.append('response_text', responseText);
      formData.append('status_update', statusUpdate);
      if (evidenceFile) {
        formData.append('evidence_file', evidenceFile);
      }

      await apiClient.post(`/corrective/actions/${selectedCapa.id}/add-response/`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });

      // Update local state
      setCapas(capas.map(c => c.id === selectedCapa.id ? { ...c, status: statusUpdate } : c));
      setShowResponseModal(false);
      alert('Response recorded and CAPA status updated!');
      fetchCapas(); // Refresh list to get files or related fields updated
    } catch (err) {
      alert('Failed: ' + JSON.stringify(err.response?.data || err.message));
    } finally {
      setSubmittingResponse(false);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'resolved':
      case 'closed':
        return 'badge-success';
      case 'in_progress':
        return 'badge-info';
      case 'overdue':
        return 'badge-danger';
      default:
        return 'badge-warning';
    }
  };

  const filteredCapas = capas.filter(c => {
    if (activeTab === 'all') return true;
    if (activeTab === 'open') return c.status === 'open' || c.status === 'in_progress';
    if (activeTab === 'resolved') return c.status === 'resolved' || c.status === 'closed';
    if (activeTab === 'overdue') return c.status === 'overdue';
    return true;
  });

  const isAuditorOrManager = currentUser && currentUser.role !== 'auditee';

  return (
    <div className="followup-view">
      <div className="tab-container">
        <button className={`tab-btn ${activeTab === 'all' ? 'active' : ''}`} onClick={() => setActiveTab('all')}>
          All CAPAs ({capas.length})
        </button>
        <button className={`tab-btn ${activeTab === 'open' ? 'active' : ''}`} onClick={() => setActiveTab('open')}>
          Open / In Progress
        </button>
        <button className={`tab-btn ${activeTab === 'resolved' ? 'active' : ''}`} onClick={() => setActiveTab('resolved')}>
          Resolved
        </button>
        <button className={`tab-btn ${activeTab === 'overdue' ? 'active' : ''}`} onClick={() => setActiveTab('overdue')}>
          Overdue
        </button>
      </div>

      {loading ? (
        <div className="loading-spinner">Loading corrective actions...</div>
      ) : (
        <div className="card mt-4">
          <div className="card-header justify-between flex-wrap gap-4">
            <div>
              <h3>Corrective and Preventive Actions (CAPA)</h3>
              <p className="card-subtitle">Follow-up tracking on approved auditor recommendations</p>
            </div>
            <div className="flex gap-2">
              <button className="btn btn-outline flex items-center gap-2" onClick={fetchCapas}>
                <RefreshCw size={14} /> Refresh
              </button>
              {canWriteAudit && (
                <button className="btn btn-accent flex items-center gap-2" onClick={() => setShowCreateModal(true)}>
                  <Plus size={16} /> Spawn CAPA Task
                </button>
              )}
            </div>
          </div>

          <div className="table-responsive">
            <table className="table">
              <thead>
                <tr>
                  <th>Action Ref</th>
                  <th>Action Title</th>
                  <th>Owner</th>
                  <th>Priority</th>
                  <th>Due Date</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredCapas.length === 0 ? (
                  <tr>
                    <td colSpan="7" className="text-center py-8">No corrective action records found for this filter.</td>
                  </tr>
                ) : (
                  filteredCapas.map(c => (
                    <tr key={c.id}>
                      <td><strong>{c.action_number}</strong></td>
                      <td>
                        <div className="capa-title-container">
                          <strong>{c.title}</strong>
                          <span className="text-xs text-muted block max-w-md truncate">{c.description}</span>
                        </div>
                      </td>
                      <td>{c.owner_name || 'N/A'}</td>
                      <td>
                        <span className={`badge ${c.priority === 'high' || c.priority === 'immediate' ? 'badge-danger' : 'badge-outline'}`}>
                          {c.priority?.toUpperCase()}
                        </span>
                      </td>
                      <td>{c.due_date}</td>
                      <td>
                        <span className={`badge ${getStatusBadge(c.status)}`}>
                          {c.status?.replace('_', ' ').toUpperCase()}
                        </span>
                      </td>
                      <td>
                        <button className="btn btn-outline btn-sm flex items-center gap-1" onClick={() => handleOpenResponse(c)}>
                          <MessageCircle size={14} /> Respond
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Spawn CAPA Modal */}
      {showCreateModal && (
        <div className="modal-backdrop">
          <div className="modal-card modal-large">
            <div className="modal-header">
              <h3>Spawn CAPA Task linked to Finding</h3>
              <button className="close-btn" onClick={() => setShowCreateModal(false)}>×</button>
            </div>
            <form onSubmit={handleCreateCapa}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Link to Audit Finding</label>
                  <select
                    className="form-control"
                    value={newCapa.finding}
                    onChange={handleFindingChange}
                    required
                  >
                    <option value="">Select Audit Finding...</option>
                    {findings.map(f => (
                      <option key={f.id} value={f.id}>{f.finding_number} - {f.title}</option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Action / CAPA Title</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="e.g. Implement dual-authorization controls"
                    value={newCapa.title}
                    onChange={e => setNewCapa({ ...newCapa, title: e.target.value })}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Action Description</label>
                  <textarea
                    rows="3"
                    className="form-control"
                    placeholder="Provide detailed description of corrective action..."
                    value={newCapa.description}
                    onChange={e => setNewCapa({ ...newCapa, description: e.target.value })}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Auditor Recommendation Reference</label>
                  <textarea
                    rows="2"
                    className="form-control"
                    value={newCapa.recommendation}
                    onChange={e => setNewCapa({ ...newCapa, recommendation: e.target.value })}
                    placeholder="Auditor recommendation details..."
                    required
                  />
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Assign Owner (Auditee)</label>
                    <select
                      className="form-control"
                      value={newCapa.owner}
                      onChange={e => setNewCapa({ ...newCapa, owner: e.target.value })}
                      required
                    >
                      <option value="">Select Auditee Owner...</option>
                      {auditees.map(a => (
                        <option key={a.id} value={a.id}>{a.first_name} {a.last_name} ({a.department_name || 'Auditee'})</option>
                      ))}
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Priority</label>
                    <select
                      className="form-control"
                      value={newCapa.priority}
                      onChange={e => setNewCapa({ ...newCapa, priority: e.target.value })}
                    >
                      <option value="low">Low</option>
                      <option value="medium">Medium</option>
                      <option value="high">High</option>
                      <option value="immediate">Immediate</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Due Date</label>
                    <input
                      type="date"
                      className="form-control"
                      value={newCapa.due_date}
                      onChange={e => setNewCapa({ ...newCapa, due_date: e.target.value })}
                      required
                    />
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowCreateModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-accent" disabled={creating}>
                  {creating ? 'Spawning...' : 'Spawn & Assign CAPA'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Auditee Response Modal */}
      {showResponseModal && selectedCapa && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <div className="modal-header">
              <h3>Submit Management Update for {selectedCapa.action_number}</h3>
              <button className="close-btn" onClick={() => setShowResponseModal(false)}>×</button>
            </div>
            <form onSubmit={handleSubmitResponse}>
              <div className="modal-body">
                <div className="mb-4">
                  <span className="text-xs text-muted font-bold block">Recommendation:</span>
                  <p className="text-sm font-semibold">{selectedCapa.recommendation}</p>
                </div>

                <div className="form-group">
                  <label className="form-label">Progress Status</label>
                  <select
                    className="form-control"
                    value={statusUpdate}
                    onChange={(e) => setStatusUpdate(e.target.value)}
                  >
                    <option value="in_progress">In Progress</option>
                    <option value="partially_resolved">Partially Resolved</option>
                    <option value="resolved">Resolved / Actioned</option>
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Action / Update Notes</label>
                  <textarea
                    rows="4"
                    className="form-control"
                    placeholder="Provide details on action taken, systems modified, or policies published..."
                    value={responseText}
                    onChange={(e) => setResponseText(e.target.value)}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label flex items-center gap-1"><FileUp size={16} /> Upload Implementation Document</label>
                  <input
                    type="file"
                    className="form-control"
                    onChange={(e) => setEvidenceFile(e.target.files[0])}
                  />
                  {evidenceFile && (
                    <span className="text-xs text-success block mt-1">Selected file: {evidenceFile.name}</span>
                  )}
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowResponseModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={submittingResponse}>
                  {submittingResponse ? 'Submitting...' : 'Submit Response'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default FollowUpPage;

