import React, { useState, useEffect } from 'react';
import apiClient from '../../api/apiClient';
import { Calendar, Plus, Users, Shield, Clock } from 'lucide-react';

function PlanningPage() {
  const [activeTab, setActiveTab] = useState('universe');
  const [universe, setUniverse] = useState([]);
  const [plans, setPlans] = useState([]);
  const [engagements, setEngagements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [departments, setDepartments] = useState([]);
  const [allUsers, setAllUsers] = useState([]);

  // Form State
  const [showUniverseModal, setShowUniverseModal] = useState(false);
  const [newUniverse, setNewUniverse] = useState({ name: '', code: '', category: 'system', risk_score: 3.5, audit_frequency: 'Annually', owner: '', department: '' });

  const [showPlanModal, setShowPlanModal] = useState(false);
  const [newPlan, setNewPlan] = useState({ title: '', year: new Date().getFullYear(), total_budget_days: 0, start_date: '', end_date: '', description: '', objectives: '', scope: '' });

  const [showEngagementModal, setShowEngagementModal] = useState(false);
  const [newEngagement, setNewEngagement] = useState({
    title: '', plan: '', audit_universe: '', department: '',
    engagement_type: 'operational', risk_level: 'medium',
    planned_start: '', planned_end: '', planned_days: 0,
    lead_auditor: '', supervisor: ''
  });

  // Team Member Assignment State
  const [showTeamModal, setShowTeamModal] = useState(false);
  const [selectedEngagement, setSelectedEngagement] = useState(null);
  const [teamMember, setTeamMember] = useState({ user: '', role: 'member', allocated_days: 0 });
  const [engagementTeam, setEngagementTeam] = useState([]);

  useEffect(() => {
    fetchPlanningData();
  }, []);

  const fetchPlanningData = async () => {
    setLoading(true);
    try {
      const [univRes, plansRes, engRes, depRes, usersRes] = await Promise.all([
        apiClient.get('/planning/universe/'),
        apiClient.get('/planning/plans/'),
        apiClient.get('/planning/engagements/'),
        apiClient.get('/auth/departments/'),
        apiClient.get('/auth/users/')
      ]);
      setUniverse(univRes.data.results || []);
      setPlans(plansRes.data.results || []);
      setEngagements(engRes.data.results || []);
      setDepartments(depRes.data.results || []);
      setAllUsers(usersRes.data.results || []);
    } catch (err) {
      console.error("Error loading planning data:", err);
    } finally {
      setLoading(false);
    }
  };

  const auditors = allUsers.filter(u => u.role === 'auditor' || u.role === 'audit_manager');
  const supervisors = allUsers.filter(u => u.role === 'supervisor' || u.role === 'audit_manager');

  const handleAddUniverse = async (e) => {
    e.preventDefault();
    try {
      const payload = { ...newUniverse };
      if (!payload.department) delete payload.department;
      const response = await apiClient.post('/planning/universe/', payload);
      setUniverse([response.data, ...universe]);
      setShowUniverseModal(false);
      setNewUniverse({ name: '', code: '', category: 'system', risk_score: 3.5, audit_frequency: 'Annually', owner: '', department: '' });
    } catch (err) {
      alert(err.response?.data ? JSON.stringify(err.response.data) : 'Failed to add universe item');
    }
  };

  const handleAddPlan = async (e) => {
    e.preventDefault();
    try {
      const response = await apiClient.post('/planning/plans/', newPlan);
      setPlans([response.data, ...plans]);
      setShowPlanModal(false);
      setNewPlan({ title: '', year: new Date().getFullYear(), total_budget_days: 0, start_date: '', end_date: '', description: '', objectives: '', scope: '' });
    } catch (err) {
      alert(err.response?.data ? JSON.stringify(err.response.data) : 'Failed to create plan');
    }
  };

  const handleAddEngagement = async (e) => {
    e.preventDefault();
    try {
      const payload = { ...newEngagement };
      if (!payload.department) delete payload.department;
      if (!payload.audit_universe) delete payload.audit_universe;
      if (!payload.lead_auditor) delete payload.lead_auditor;
      if (!payload.supervisor) delete payload.supervisor;
      const response = await apiClient.post('/planning/engagements/', payload);
      setEngagements([response.data, ...engagements]);
      setShowEngagementModal(false);
      setNewEngagement({ title: '', plan: '', audit_universe: '', department: '', engagement_type: 'operational', risk_level: 'medium', planned_start: '', planned_end: '', planned_days: 0, lead_auditor: '', supervisor: '' });
    } catch (err) {
      alert(err.response?.data ? JSON.stringify(err.response.data) : 'Failed to create engagement');
    }
  };

  const handleSubmitPlan = async (planId) => {
    try {
      await apiClient.post(`/planning/plans/${planId}/submit/`);
      alert('Plan submitted for approval successfully!');
      fetchPlanningData();
    } catch (err) {
      alert(err.response?.data ? JSON.stringify(err.response.data) : 'Failed to submit plan');
    }
  };

  const handleApprovePlan = async (planId) => {
    try {
      await apiClient.post(`/planning/plans/${planId}/approve/`);
      alert('Plan approved successfully!');
      fetchPlanningData();
    } catch (err) {
      alert(err.response?.data ? JSON.stringify(err.response.data) : 'Failed to approve plan');
    }
  };

  const openTeamModal = async (engagement) => {
    setSelectedEngagement(engagement);
    setShowTeamModal(true);
    setTeamMember({ user: '', role: 'member', allocated_days: 0 });
    // Fetch current team for this engagement
    try {
      const res = await apiClient.get(`/planning/engagements/${engagement.id}/`);
      setEngagementTeam(res.data.team_members || []);
    } catch (err) {
      console.error(err);
    }
  };

  const handleAddTeamMember = async (e) => {
    e.preventDefault();
    try {
      await apiClient.post(`/planning/engagements/${selectedEngagement.id}/add-member/`, teamMember);
      alert('Team member assigned successfully!');
      // Refresh team
      const res = await apiClient.get(`/planning/engagements/${selectedEngagement.id}/`);
      setEngagementTeam(res.data.team_members || []);
      setTeamMember({ user: '', role: 'member', allocated_days: 0 });
    } catch (err) {
      alert(err.response?.data ? JSON.stringify(err.response.data) : 'Failed to assign team member');
    }
  };

  return (
    <div className="planning-view">
      <div className="tab-container">
        <button className={`tab-btn ${activeTab === 'universe' ? 'active' : ''}`} onClick={() => setActiveTab('universe')}>
          Audit Universe
        </button>
        <button className={`tab-btn ${activeTab === 'plans' ? 'active' : ''}`} onClick={() => setActiveTab('plans')}>
          Annual Audit Plans
        </button>
        <button className={`tab-btn ${activeTab === 'engagements' ? 'active' : ''}`} onClick={() => setActiveTab('engagements')}>
          Engagements ({engagements.length})
        </button>
      </div>

      {loading ? (
        <div className="loading-spinner">Loading planning records...</div>
      ) : (
        <div className="tab-content active mt-4">

          {/* === AUDIT UNIVERSE TAB === */}
          {activeTab === 'universe' && (
            <div className="card">
              <div className="card-header justify-between">
                <div>
                  <h3>EEU Risk-Weighted Audit Universe</h3>
                  <p className="card-subtitle">Complete directory of all auditable operational nodes and systems</p>
                </div>
                <button className="btn btn-primary flex items-center gap-2" onClick={() => setShowUniverseModal(true)}>
                  <Plus size={16} /> Add Entity
                </button>
              </div>
              <div className="table-responsive">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Code</th>
                      <th>Entity Name</th>
                      <th>Category</th>
                      <th>Department</th>
                      <th>Risk Score</th>
                      <th>Frequency</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {universe.map(item => (
                      <tr key={item.id}>
                        <td><strong>{item.code}</strong></td>
                        <td>{item.name}</td>
                        <td><span className="badge badge-outline">{item.category?.toUpperCase()}</span></td>
                        <td>{item.department_name || 'N/A'}</td>
                        <td>
                          <span className={`risk-tag ${item.risk_score >= 4 ? 'critical' : item.risk_score >= 3 ? 'high' : 'medium'}`}>
                            {item.risk_score}
                          </span>
                        </td>
                        <td>{item.audit_frequency}</td>
                        <td>
                          <span className={`badge ${item.status === 'active' ? 'badge-success' : 'badge-warning'}`}>
                            {item.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* === ANNUAL PLANS TAB === */}
          {activeTab === 'plans' && (
            <div className="card">
              <div className="card-header justify-between">
                <div>
                  <h3>Annual Audit Plans</h3>
                  <p className="card-subtitle">Active and historical approved annual audit schedules</p>
                </div>
                <button className="btn btn-primary flex items-center gap-2" onClick={() => setShowPlanModal(true)}>
                  <Plus size={16} /> Create Plan
                </button>
              </div>
              <div className="plans-grid mt-4">
                {plans.map(plan => (
                  <div key={plan.id} className="plan-card">
                    <div className="plan-card-header">
                      <h4>{plan.title}</h4>
                      <span className={`badge ${plan.status === 'approved' || plan.status === 'active' ? 'badge-success' : 'badge-info'}`}>
                        {plan.status.toUpperCase()}
                      </span>
                    </div>
                    <div className="plan-card-body">
                      <p>{plan.description}</p>
                      <div className="plan-meta-row">
                        <div><span>Year:</span><strong>{plan.year}</strong></div>
                        <div><span>Budget Days:</span><strong>{plan.total_budget_days} Days</strong></div>
                      </div>
                      <div className="plan-dates text-sm">
                        <span>Timeline:</span>
                        <strong>{plan.start_date} to {plan.end_date}</strong>
                      </div>
                      <div className="mt-4 flex gap-2 border-t pt-3 border-border-color">
                        {plan.status === 'draft' && (
                          <button className="btn btn-sm btn-outline flex-1" onClick={() => handleSubmitPlan(plan.id)}>
                            Submit for Approval
                          </button>
                        )}
                        {plan.status === 'submitted' && (
                          <button className="btn btn-sm btn-primary flex-1" onClick={() => handleApprovePlan(plan.id)}>
                            Approve Plan
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* === ENGAGEMENTS TAB === */}
          {activeTab === 'engagements' && (
            <div className="card">
              <div className="card-header justify-between">
                <div>
                  <h3>Audit Engagements</h3>
                  <p className="card-subtitle">Individual operational audits configured under current plans</p>
                </div>
                <button className="btn btn-primary flex items-center gap-2" onClick={() => setShowEngagementModal(true)}>
                  <Plus size={16} /> Schedule Engagement
                </button>
              </div>
              <div className="table-responsive">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Ref Number</th>
                      <th>Audit Title</th>
                      <th>Type</th>
                      <th>Lead Auditor</th>
                      <th>Supervisor</th>
                      <th>Days</th>
                      <th>Timeline</th>
                      <th>Risk Level</th>
                      <th>Status</th>
                      <th>Team</th>
                    </tr>
                  </thead>
                  <tbody>
                    {engagements.map(eng => (
                      <tr key={eng.id}>
                        <td><strong>{eng.engagement_number}</strong></td>
                        <td>{eng.title}</td>
                        <td><span className="badge badge-outline">{eng.engagement_type?.toUpperCase()}</span></td>
                        <td>
                          {eng.lead_auditor_name ? (
                            <span className="flex items-center gap-1">
                              <Users size={13} className="text-primary" />
                              {eng.lead_auditor_name}
                            </span>
                          ) : <span className="text-muted">—</span>}
                        </td>
                        <td>
                          {eng.supervisor_name ? (
                            <span className="flex items-center gap-1">
                              <Shield size={13} className="text-warning" />
                              {eng.supervisor_name}
                            </span>
                          ) : <span className="text-muted">—</span>}
                        </td>
                        <td>
                          <span className="flex items-center gap-1">
                            <Clock size={13} />
                            {eng.planned_days || 0}d
                          </span>
                        </td>
                        <td>{eng.planned_start} – {eng.planned_end}</td>
                        <td>
                          <span className={`risk-tag ${eng.risk_level === 'critical' ? 'critical' : eng.risk_level === 'high' ? 'high' : 'medium'}`}>
                            {eng.risk_level?.toUpperCase()}
                          </span>
                        </td>
                        <td>
                          <span className={`badge ${eng.status === 'in_progress' ? 'badge-info' : eng.status === 'fieldwork' ? 'badge-warning' : 'badge-success'}`}>
                            {eng.status?.replace('_', ' ')}
                          </span>
                        </td>
                        <td>
                          <button className="btn btn-sm btn-outline" onClick={() => openTeamModal(eng)}>
                            Assign
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

        </div>
      )}

      {/* ==================== MODALS ==================== */}

      {/* Universe Entity Modal */}
      {showUniverseModal && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <div className="modal-header">
              <h3>Add Auditable Entity</h3>
              <button className="close-btn" onClick={() => setShowUniverseModal(false)}>×</button>
            </div>
            <form onSubmit={handleAddUniverse}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Entity Name</label>
                  <input type="text" className="form-control" placeholder="e.g. Substation Asset Management"
                    value={newUniverse.name} onChange={(e) => setNewUniverse({...newUniverse, name: e.target.value})} required />
                </div>
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Unique Code</label>
                    <input type="text" className="form-control" placeholder="e.g. UNIV-DIST-06"
                      value={newUniverse.code} onChange={(e) => setNewUniverse({...newUniverse, code: e.target.value})} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Category</label>
                    <select className="form-control" value={newUniverse.category} onChange={(e) => setNewUniverse({...newUniverse, category: e.target.value})}>
                      <option value="department">Department</option>
                      <option value="process">Business Process</option>
                      <option value="system">IT System</option>
                      <option value="project">Project</option>
                    </select>
                  </div>
                </div>
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Associated Department</label>
                    <select className="form-control" value={newUniverse.department} onChange={(e) => setNewUniverse({...newUniverse, department: e.target.value})}>
                      <option value="">Select Department...</option>
                      {departments.map(d => (<option key={d.id} value={d.id}>{d.name}</option>))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Initial Risk Score (1-5)</label>
                    <input type="number" step="0.05" min="1" max="5" className="form-control"
                      value={newUniverse.risk_score} onChange={(e) => setNewUniverse({...newUniverse, risk_score: parseFloat(e.target.value)})} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Audit Frequency</label>
                    <select className="form-control" value={newUniverse.audit_frequency} onChange={(e) => setNewUniverse({...newUniverse, audit_frequency: e.target.value})}>
                      <option value="Annually">Annually</option>
                      <option value="Bi-annually">Bi-annually</option>
                      <option value="Tri-annually">Tri-annually</option>
                    </select>
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowUniverseModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Save Entity</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Annual Plan Modal */}
      {showPlanModal && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <div className="modal-header">
              <h3>Create Annual Audit Plan</h3>
              <button className="close-btn" onClick={() => setShowPlanModal(false)}>×</button>
            </div>
            <form onSubmit={handleAddPlan}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Plan Title</label>
                  <input type="text" className="form-control" placeholder="e.g. FY 2026 Comprehensive Audit Plan"
                    value={newPlan.title} onChange={(e) => setNewPlan({...newPlan, title: e.target.value})} required />
                </div>
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Year</label>
                    <input type="number" className="form-control" value={newPlan.year}
                      onChange={(e) => setNewPlan({...newPlan, year: parseInt(e.target.value)})} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Budget Days</label>
                    <input type="number" className="form-control" value={newPlan.total_budget_days}
                      onChange={(e) => setNewPlan({...newPlan, total_budget_days: parseInt(e.target.value)})} />
                  </div>
                </div>
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Start Date</label>
                    <input type="date" className="form-control" value={newPlan.start_date}
                      onChange={(e) => setNewPlan({...newPlan, start_date: e.target.value})} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">End Date</label>
                    <input type="date" className="form-control" value={newPlan.end_date}
                      onChange={(e) => setNewPlan({...newPlan, end_date: e.target.value})} />
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Description / Objectives</label>
                  <textarea rows="2" className="form-control" value={newPlan.description}
                    onChange={(e) => setNewPlan({...newPlan, description: e.target.value})} />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowPlanModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Create Plan</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Engagement Modal — with Lead Auditor, Supervisor & Days */}
      {showEngagementModal && (
        <div className="modal-backdrop">
          <div className="modal-card modal-large">
            <div className="modal-header">
              <h3>Schedule Audit Engagement</h3>
              <button className="close-btn" onClick={() => setShowEngagementModal(false)}>×</button>
            </div>
            <form onSubmit={handleAddEngagement}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Engagement Title</label>
                  <input type="text" className="form-control" placeholder="e.g. Q1 Payroll Compliance Audit"
                    value={newEngagement.title} onChange={(e) => setNewEngagement({...newEngagement, title: e.target.value})} required />
                </div>
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Target Annual Plan</label>
                    <select className="form-control" value={newEngagement.plan}
                      onChange={(e) => setNewEngagement({...newEngagement, plan: e.target.value})} required>
                      <option value="">Select Plan...</option>
                      {plans.map(p => (<option key={p.id} value={p.id}>{p.title}</option>))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Engagement Type</label>
                    <select className="form-control" value={newEngagement.engagement_type}
                      onChange={(e) => setNewEngagement({...newEngagement, engagement_type: e.target.value})}>
                      <option value="operational">Operational</option>
                      <option value="financial">Financial</option>
                      <option value="compliance">Compliance</option>
                      <option value="it">IT Audit</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Risk Level</label>
                    <select className="form-control" value={newEngagement.risk_level}
                      onChange={(e) => setNewEngagement({...newEngagement, risk_level: e.target.value})}>
                      <option value="low">Low</option>
                      <option value="medium">Medium</option>
                      <option value="high">High</option>
                      <option value="critical">Critical</option>
                    </select>
                  </div>
                </div>

                {/* ★ Manager Section: Lead Auditor, Supervisor & Allocated Days */}
                <div className="form-section-divider">
                  <span><Users size={14} /> Team Assignment</span>
                </div>
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Lead Auditor</label>
                    <select className="form-control" value={newEngagement.lead_auditor}
                      onChange={(e) => setNewEngagement({...newEngagement, lead_auditor: e.target.value})}>
                      <option value="">Select Lead Auditor...</option>
                      {auditors.map(u => (
                        <option key={u.id} value={u.id}>{u.full_name || `${u.first_name} ${u.last_name}`} ({u.employee_id})</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Supervisor</label>
                    <select className="form-control" value={newEngagement.supervisor}
                      onChange={(e) => setNewEngagement({...newEngagement, supervisor: e.target.value})}>
                      <option value="">Select Supervisor...</option>
                      {supervisors.map(u => (
                        <option key={u.id} value={u.id}>{u.full_name || `${u.first_name} ${u.last_name}`} ({u.employee_id})</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Allocated Days</label>
                    <input type="number" min="0" className="form-control"
                      placeholder="e.g. 10"
                      value={newEngagement.planned_days}
                      onChange={(e) => setNewEngagement({...newEngagement, planned_days: parseInt(e.target.value) || 0})} />
                  </div>
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Audit Universe Node (Optional)</label>
                    <select className="form-control" value={newEngagement.audit_universe}
                      onChange={(e) => setNewEngagement({...newEngagement, audit_universe: e.target.value})}>
                      <option value="">Select Entity...</option>
                      {universe.map(u => (<option key={u.id} value={u.id}>{u.code} - {u.name}</option>))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Department</label>
                    <select className="form-control" value={newEngagement.department}
                      onChange={(e) => setNewEngagement({...newEngagement, department: e.target.value})}>
                      <option value="">Select Department...</option>
                      {departments.map(d => (<option key={d.id} value={d.id}>{d.name}</option>))}
                    </select>
                  </div>
                </div>
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Planned Start</label>
                    <input type="date" className="form-control" value={newEngagement.planned_start}
                      onChange={(e) => setNewEngagement({...newEngagement, planned_start: e.target.value})} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Planned End</label>
                    <input type="date" className="form-control" value={newEngagement.planned_end}
                      onChange={(e) => setNewEngagement({...newEngagement, planned_end: e.target.value})} />
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowEngagementModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Schedule Engagement</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Team Assignment Modal */}
      {showTeamModal && selectedEngagement && (
        <div className="modal-backdrop">
          <div className="modal-card modal-large">
            <div className="modal-header">
              <h3>Manage Team — {selectedEngagement.title}</h3>
              <button className="close-btn" onClick={() => setShowTeamModal(false)}>×</button>
            </div>
            <div className="modal-body">
              {/* Existing team */}
              {engagementTeam.length > 0 && (
                <div className="mb-4">
                  <h4 className="mb-2">Current Team Members</h4>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Role</th>
                        <th>Allocated Days</th>
                      </tr>
                    </thead>
                    <tbody>
                      {engagementTeam.map(tm => (
                        <tr key={tm.id}>
                          <td>{tm.user_details?.full_name || tm.user_details?.employee_id}</td>
                          <td><span className="badge badge-outline">{tm.role?.toUpperCase()}</span></td>
                          <td>{tm.allocated_days} days</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Add new member form */}
              <form onSubmit={handleAddTeamMember}>
                <div className="form-section-divider"><span>Add Team Member</span></div>
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">User</label>
                    <select className="form-control" value={teamMember.user}
                      onChange={(e) => setTeamMember({...teamMember, user: e.target.value})} required>
                      <option value="">Select User...</option>
                      {allUsers.map(u => (
                        <option key={u.id} value={u.id}>{u.full_name || `${u.first_name} ${u.last_name}`} ({u.role})</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Role in Engagement</label>
                    <select className="form-control" value={teamMember.role}
                      onChange={(e) => setTeamMember({...teamMember, role: e.target.value})}>
                      <option value="lead">Lead Auditor</option>
                      <option value="member">Team Member</option>
                      <option value="supervisor">Supervisor</option>
                      <option value="specialist">Subject Matter Expert</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Allocated Days</label>
                    <input type="number" min="0" className="form-control"
                      value={teamMember.allocated_days}
                      onChange={(e) => setTeamMember({...teamMember, allocated_days: parseInt(e.target.value) || 0})} />
                  </div>
                </div>
                <div className="modal-footer" style={{padding: 0, marginTop: '1rem'}}>
                  <button type="button" className="btn btn-outline" onClick={() => setShowTeamModal(false)}>Close</button>
                  <button type="submit" className="btn btn-primary">Add Member</button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default PlanningPage;
