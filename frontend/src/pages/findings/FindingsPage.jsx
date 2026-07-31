import React, { useState, useEffect } from 'react';
import apiClient from '../../api/apiClient';
import { usePermissions } from '../../hooks/usePermissions';
import { ShieldAlert, Plus, Layers, List, MessageCircle, FileText, ChevronRight } from 'lucide-react';

function FindingsPage() {
  const { canWriteAudit, canCloseFindings } = usePermissions();
  const [engagements, setEngagements] = useState([]);
  const [selectedEngId, setSelectedEngId] = useState('');
  const [findings, setFindings] = useState([]);
  const [viewMode, setViewMode] = useState('list'); // 'list' or 'kanban'
  const [loading, setLoading] = useState(false);

  // Selected Finding Inspection Detail
  const [activeFinding, setActiveFinding] = useState(null);

  // Add Finding Modal State
  const [showAddModal, setShowAddModal] = useState(false);
  const [newFinding, setNewFinding] = useState({
    title: '', severity: 'medium', category: 'control_deficiency',
    description: '', condition: '', criteria: '', cause: '', effect: '', recommendation: ''
  });

  useEffect(() => {
    fetchEngagements();
  }, []);

  const fetchEngagements = async () => {
    try {
      const res = await apiClient.get('/planning/engagements/');
      setEngagements(res.data.results || []);
      if (res.data.results?.length > 0) {
        setSelectedEngId(res.data.results[0].id);
        fetchFindings(res.data.results[0].id);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const fetchFindings = async (engId) => {
    setLoading(true);
    try {
      const res = await apiClient.get(`/findings/findings/?engagement=${engId}`);
      setFindings(res.data.results || []);
      if (res.data.results?.length > 0) {
        setActiveFinding(res.data.results[0]);
      } else {
        setActiveFinding(null);
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
    fetchFindings(val);
  };

  const handleCreateFinding = async (e) => {
    e.preventDefault();
    const data = {
      ...newFinding,
      engagement: selectedEngId,
      finding_number: `FIND-${Date.now().toString().slice(-4)}`
    };

    try {
      const response = await apiClient.post('/findings/findings/', data);
      setFindings([response.data, ...findings]);
      setActiveFinding(response.data);
      setShowAddModal(false);
      // Reset
      setNewFinding({
        title: '', severity: 'medium', category: 'control_deficiency',
        description: '', condition: '', criteria: '', cause: '', effect: '', recommendation: ''
      });
      alert('Finding logged successfully!');
    } catch (err) {
      alert('Failed: ' + JSON.stringify(err.response?.data || err.message));
    }
  };

  // Kanban Columns configuration
  const columns = [
    { id: 'draft', title: 'Draft' },
    { id: 'open', title: 'Open' },
    { id: 'in_progress', title: 'In Progress' },
    { id: 'resolved', title: 'Resolved' },
  ];

  return (
    <div className="findings-view">
      {/* Top selector bar */}
      <div className="card mb-4 flex justify-between items-center flex-wrap gap-4">
        <div className="form-group mb-0 flex-grow max-w-md">
          <label className="form-label font-bold">Select Audit Engagement</label>
          <select className="form-control" value={selectedEngId} onChange={handleEngChange}>
            {engagements.map(e => (
              <option key={e.id} value={e.id}>{e.engagement_number} - {e.title}</option>
            ))}
          </select>
        </div>

        <div className="flex gap-2">
          <button
            className={`btn ${viewMode === 'list' ? 'btn-primary' : 'btn-outline'}`}
            onClick={() => setViewMode('list')}
          >
            <List size={16} className="inline mr-1" /> List View
          </button>
          <button
            className={`btn ${viewMode === 'kanban' ? 'btn-primary' : 'btn-outline'}`}
            onClick={() => setViewMode('kanban')}
          >
            <Layers size={16} className="inline mr-1" /> Kanban Board
          </button>
          {canWriteAudit && (
            <button className="btn btn-accent" onClick={() => setShowAddModal(true)}>
              <Plus size={16} className="inline mr-1" /> Log Finding
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="loading-spinner">Loading findings registry...</div>
      ) : (
        <div className="tab-content active">
          {viewMode === 'list' ? (
            <div className="findings-split-layout">
              {/* Left Column: Finding list */}
              <div className="card list-column">
                <h3>Findings Registered ({findings.length})</h3>
                <div className="findings-list mt-3">
                  {findings.length === 0 ? (
                    <p className="text-muted text-center py-8">No findings reported for this audit.</p>
                  ) : (
                    findings.map(f => (
                      <div
                        key={f.id}
                        className={`finding-list-item ${activeFinding?.id === f.id ? 'active' : ''}`}
                        onClick={() => setActiveFinding(f)}
                      >
                        <div className="finding-item-meta">
                          <span className="finding-num">{f.finding_number}</span>
                          <span className={`risk-tag ${f.severity === 'critical' ? 'critical' : f.severity === 'high' ? 'high' : 'medium'}`}>
                            {f.severity?.toUpperCase()}
                          </span>
                        </div>
                        <h4>{f.title}</h4>
                        <span className="badge badge-outline mt-1">{f.status?.toUpperCase()}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Right Column: Finding details */}
              {activeFinding ? (
                <div className="card detail-column">
                  <div className="detail-header mb-4">
                    <span className="badge badge-outline mb-2">{activeFinding.category?.replace('_', ' ').toUpperCase()}</span>
                    <h2>{activeFinding.finding_number}: {activeFinding.title}</h2>
                    <span className={`badge ${activeFinding.status === 'open' ? 'badge-warning' : activeFinding.status === 'resolved' ? 'badge-success' : 'badge-info'} mt-2`}>
                      {activeFinding.status?.toUpperCase()}
                    </span>
                  </div>

                  <div className="detail-body">
                    <div className="detail-section">
                      <h4>Description</h4>
                      <p>{activeFinding.description}</p>
                    </div>

                    <div className="detail-section">
                      <h4>Condition (What was found?)</h4>
                      <p>{activeFinding.condition || 'N/A'}</p>
                    </div>

                    <div className="detail-section">
                      <h4>Criteria (What policies/standards apply?)</h4>
                      <p>{activeFinding.criteria || 'N/A'}</p>
                    </div>

                    <div className="detail-section">
                      <h4>Root Cause Analysis</h4>
                      <p>{activeFinding.cause || 'N/A'}</p>
                    </div>

                    <div className="detail-section">
                      <h4>Effect & Impact (Potential Risk)</h4>
                      <p>{activeFinding.effect || 'N/A'}</p>
                    </div>

                    <div className="detail-section highlight-box">
                      <h4>Auditor Recommendation</h4>
                      <p>{activeFinding.recommendation || 'N/A'}</p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="card text-center py-8">
                  <h3>No Finding Selected</h3>
                  <p className="text-muted">Select a finding from the left panel to inspect details.</p>
                </div>
              )}
            </div>
          ) : (
            /* Kanban view */
            <div className="kanban-board mt-4">
              {columns.map(col => {
                const colFindings = findings.filter(f => f.status === col.id);
                return (
                  <div key={col.id} className="kanban-column">
                    <div className="kanban-column-header">
                      <h3>{col.title}</h3>
                      <span className="count-badge">{colFindings.length}</span>
                    </div>
                    <div className="kanban-cards-container">
                      {colFindings.map(f => (
                        <div key={f.id} className="kanban-card" onClick={() => { setViewMode('list'); setActiveFinding(f); }}>
                          <span className={`risk-tag tag-xs ${f.severity === 'critical' ? 'critical' : f.severity === 'high' ? 'high' : 'medium'}`}>
                            {f.severity?.toUpperCase()}
                          </span>
                          <h4>{f.title}</h4>
                          <span className="kanban-card-ref">{f.finding_number}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Add Finding Modal */}
      {showAddModal && (
        <div className="modal-backdrop">
          <div className="modal-card modal-large">
            <div className="modal-header">
              <h3>Log New Audit Finding</h3>
              <button className="close-btn" onClick={() => setShowAddModal(false)}>×</button>
            </div>
            <form onSubmit={handleCreateFinding}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Finding Title</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="e.g. Inadequate data replication verification logs"
                    value={newFinding.title}
                    onChange={(e) => setNewFinding({...newFinding, title: e.target.value})}
                    required
                  />
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Severity Level</label>
                    <select
                      className="form-control"
                      value={newFinding.severity}
                      onChange={(e) => setNewFinding({...newFinding, severity: e.target.value})}
                    >
                      <option value="critical">Critical</option>
                      <option value="high">High</option>
                      <option value="medium">Medium</option>
                      <option value="low">Low</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Finding Category</label>
                    <select
                      className="form-control"
                      value={newFinding.category}
                      onChange={(e) => setNewFinding({...newFinding, category: e.target.value})}
                    >
                      <option value="control_deficiency">Control Deficiency</option>
                      <option value="compliance">Compliance Issue</option>
                      <option value="fraud">Fraud Risk</option>
                      <option value="operational">Operational Weakness</option>
                      <option value="it_security">IT/Security Issue</option>
                    </select>
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Description (Summary)</label>
                  <textarea
                    rows="3"
                    className="form-control"
                    value={newFinding.description}
                    onChange={(e) => setNewFinding({...newFinding, description: e.target.value})}
                    required
                  />
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Condition (Actual Situation)</label>
                    <textarea
                      rows="2"
                      className="form-control"
                      value={newFinding.condition}
                      onChange={(e) => setNewFinding({...newFinding, condition: e.target.value})}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Criteria (Policy / Policy Standard)</label>
                    <textarea
                      rows="2"
                      className="form-control"
                      value={newFinding.criteria}
                      onChange={(e) => setNewFinding({...newFinding, criteria: e.target.value})}
                    />
                  </div>
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Root Cause (Why it happened?)</label>
                    <textarea
                      rows="2"
                      className="form-control"
                      value={newFinding.cause}
                      onChange={(e) => setNewFinding({...newFinding, cause: e.target.value})}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Effect & Risk (Impact)</label>
                    <textarea
                      rows="2"
                      className="form-control"
                      value={newFinding.effect}
                      onChange={(e) => setNewFinding({...newFinding, effect: e.target.value})}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Auditor Recommendation</label>
                  <textarea
                    rows="2"
                    className="form-control"
                    placeholder="Provide actionable correction advice..."
                    value={newFinding.recommendation}
                    onChange={(e) => setNewFinding({...newFinding, recommendation: e.target.value})}
                    required
                  />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowAddModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-accent">Save & Log Finding</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default FindingsPage;
