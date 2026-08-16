import React, { useState, useEffect } from 'react';
import { planningApi, usersApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { usePermissions } from '../../hooks/usePermissions';
import { useI18n } from '../../context/I18nContext';
import { validateForm, validators, hasErrors } from '../../utils/validation';
import Modal from '../../components/ui/Modal';
import Badge from '../../components/ui/Badge';
import Spinner from '../../components/ui/Spinner';
import EmptyState from '../../components/ui/EmptyState';
import FormField from '../../components/ui/FormField';
import OrgUnitSelect from '../../components/ui/OrgUnitSelect';
import { Calendar, Plus, Users, Shield, Clock, Pencil, X } from 'lucide-react';

function PlanningPage() {
  const toast = useToast();
  const { t } = useI18n();
  const { canWriteAudit, canApprovePlans } = usePermissions();
  const [activeTab, setActiveTab] = useState('universe');
  const [formErrors, setFormErrors] = useState({});
  const [universe, setUniverse] = useState([]);
  const [plans, setPlans] = useState([]);
  const [engagements, setEngagements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [allUsers, setAllUsers] = useState([]);
  const [dueForAudit, setDueForAudit] = useState([]);

  // Form State
  const emptyUniverse = { name: '', code: '', category: 'system', risk_score: 3.5, audit_frequency: 'Annually', owner: '', department: '', status: 'active' };
  const emptyPlan = { title: '', year: new Date().getFullYear(), total_budget_days: 0, start_date: '', end_date: '', description: '', objectives: '', scope: '' };
  const emptyEngagement = {
    title: '', plan: '', audit_universe: '', department: '',
    engagement_type: 'operational', risk_level: 'medium',
    planned_start: '', planned_end: '', planned_days: 0,
    lead_auditor: '', supervisor: ''
  };

  const [showUniverseModal, setShowUniverseModal] = useState(false);
  const [editingUniverseId, setEditingUniverseId] = useState(null);
  const [editingUniverseDeptName, setEditingUniverseDeptName] = useState('');
  const [newUniverse, setNewUniverse] = useState(emptyUniverse);

  const [showPlanModal, setShowPlanModal] = useState(false);
  const [editingPlanId, setEditingPlanId] = useState(null);
  const [newPlan, setNewPlan] = useState(emptyPlan);

  const [showEngagementModal, setShowEngagementModal] = useState(false);
  const [editingEngagementId, setEditingEngagementId] = useState(null);
  const [editingEngagementDeptName, setEditingEngagementDeptName] = useState('');
  const [newEngagement, setNewEngagement] = useState(emptyEngagement);

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
      // Departments are not fetched here — OrgUnitSelect loads the org tree
      // itself through useOrgUnits and shares one request across forms.
      const [univRes, plansRes, engRes, usersRes, dueRes] = await Promise.all([
        planningApi.getUniverse(),
        planningApi.getPlans(),
        planningApi.getEngagements(),
        usersApi.getUsers(),
        planningApi.getDueForReAudit(),
      ]);
      setUniverse(univRes || []);
      setPlans(plansRes || []);
      setEngagements(engRes || []);
      setAllUsers(usersRes || []);
      setDueForAudit(dueRes || []);
    } catch (err) {
      toast.error("Failed to load planning data");
    } finally {
      setLoading(false);
    }
  };

  const auditors = allUsers.filter(u => u.role === 'auditor' || u.role === 'audit_manager');
  const supervisors = allUsers.filter(u => u.role === 'supervisor' || u.role === 'audit_manager');

  const openAddUniverse = () => {
    setEditingUniverseId(null);
    setNewUniverse(emptyUniverse);
    setShowUniverseModal(true);
  };

  const openEditUniverse = (item) => {
    setEditingUniverseId(item.id);
    // department_name is tracked separately from the form payload so the picker
    // can still name a retired unit, which the org tree omits.
    setEditingUniverseDeptName(item.department_name || '');
    setNewUniverse({
      name: item.name || '', code: item.code || '', category: item.category || 'system',
      risk_score: item.risk_score ?? 3.5, audit_frequency: item.audit_frequency || 'Annually',
      owner: item.owner || '', department: item.department || '', status: item.status || 'active',
    });
    setShowUniverseModal(true);
  };

  const closeUniverseModal = () => {
    setShowUniverseModal(false);
    setEditingUniverseId(null);
    setEditingUniverseDeptName('');
    setNewUniverse(emptyUniverse);
  };

  const handleSaveUniverse = async (e) => {
    e.preventDefault();
    // Validate form
    const errors = validateForm(newUniverse, {
      name: { validators: [validators.required, validators.minLength(3)] },
      code: { validators: [validators.required, validators.code] },
      risk_score: { validators: [validators.required, validators.min(1), validators.max(5)] },
    });
    if (hasErrors(errors)) {
      setFormErrors(errors);
      return;
    }
    setFormErrors({});
    try {
      const payload = { ...newUniverse };
      if (!payload.department) delete payload.department;
      if (editingUniverseId) {
        const response = await planningApi.updateUniverse(editingUniverseId, payload);
        setUniverse(universe.map(u => (u.id === editingUniverseId ? response : u)));
        toast.success('Audit universe item updated successfully');
      } else {
        const response = await planningApi.createUniverse(payload);
        setUniverse([response, ...universe]);
        toast.success('Audit universe item created successfully');
      }
      closeUniverseModal();
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : 'Failed to save universe item';
      toast.error(msg);
    }
  };

  const openAddPlan = () => {
    setEditingPlanId(null);
    setNewPlan(emptyPlan);
    setShowPlanModal(true);
  };

  const openEditPlan = (plan) => {
    setEditingPlanId(plan.id);
    setNewPlan({
      title: plan.title || '', year: plan.year || new Date().getFullYear(),
      total_budget_days: plan.total_budget_days ?? 0, start_date: plan.start_date || '',
      end_date: plan.end_date || '', description: plan.description || '',
      objectives: plan.objectives || '', scope: plan.scope || '',
    });
    setShowPlanModal(true);
  };

  const closePlanModal = () => {
    setShowPlanModal(false);
    setEditingPlanId(null);
    setNewPlan(emptyPlan);
  };

  const handleSavePlan = async (e) => {
    e.preventDefault();
    // Validate form
    const errors = validateForm(newPlan, {
      title: { validators: [validators.required, validators.minLength(5)] },
      year: { validators: [validators.required, validators.integer] },
      total_budget_days: { validators: [validators.required, validators.integer, validators.min(0)] },
      start_date: { validators: [validators.required, validators.date] },
      end_date: {
        validators: [validators.required, validators.date],
        crossField: (values) => {
          if (!values.start_date || !values.end_date) return {};
          if (new Date(values.end_date) < new Date(values.start_date)) {
            return { end_date: 'End date must be after start date.' };
          }
          return {};
        },
      },
    });
    if (hasErrors(errors)) {
      setFormErrors(errors);
      return;
    }
    setFormErrors({});
    try {
      if (editingPlanId) {
        const response = await planningApi.updatePlan(editingPlanId, newPlan);
        setPlans(plans.map(p => (p.id === editingPlanId ? response : p)));
        toast.success('Annual plan updated successfully');
      } else {
        const response = await planningApi.createPlan(newPlan);
        setPlans([response, ...plans]);
        toast.success('Annual plan created successfully');
      }
      closePlanModal();
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : 'Failed to save plan';
      toast.error(msg);
    }
  };

  const openAddEngagement = () => {
    setEditingEngagementId(null);
    setNewEngagement(emptyEngagement);
    setShowEngagementModal(true);
  };

  const openEditEngagement = (eng) => {
    setEditingEngagementId(eng.id);
    setEditingEngagementDeptName(eng.department_name || '');
    setNewEngagement({
      title: eng.title || '', plan: eng.plan || '', audit_universe: eng.audit_universe || '',
      department: eng.department || '', engagement_type: eng.engagement_type || 'operational',
      risk_level: eng.risk_level || 'medium', planned_start: eng.planned_start || '',
      planned_end: eng.planned_end || '', planned_days: eng.planned_days ?? 0,
      lead_auditor: eng.lead_auditor || '', supervisor: eng.supervisor || '',
    });
    setShowEngagementModal(true);
  };

  const closeEngagementModal = () => {
    setShowEngagementModal(false);
    setEditingEngagementId(null);
    setEditingEngagementDeptName('');
    setNewEngagement(emptyEngagement);
  };

  const handleSaveEngagement = async (e) => {
    e.preventDefault();
    // Validate form
    const errors = validateForm(newEngagement, {
      title: { validators: [validators.required, validators.minLength(5)] },
      plan: { validators: [validators.required] },
      planned_days: { validators: [validators.integer, validators.min(0)] },
      planned_start: { validators: [validators.required, validators.date] },
      planned_end: {
        validators: [validators.required, validators.date],
        crossField: (values) => {
          if (!values.planned_start || !values.planned_end) return {};
          if (new Date(values.planned_end) < new Date(values.planned_start)) {
            return { planned_end: 'End date must be after start date.' };
          }
          return {};
        },
      },
    });
    if (hasErrors(errors)) {
      setFormErrors(errors);
      return;
    }
    setFormErrors({});
    try {
      const payload = { ...newEngagement };
      if (!payload.department) delete payload.department;
      if (!payload.audit_universe) delete payload.audit_universe;
      if (!payload.lead_auditor) delete payload.lead_auditor;
      if (!payload.supervisor) delete payload.supervisor;
      if (editingEngagementId) {
        const response = await planningApi.updateEngagement(editingEngagementId, payload);
        setEngagements(engagements.map(en => (en.id === editingEngagementId ? response : en)));
        toast.success('Audit engagement updated successfully');
      } else {
        const response = await planningApi.createEngagement(payload);
        setEngagements([response, ...engagements]);
        toast.success('Audit engagement created successfully');
      }
      closeEngagementModal();
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : 'Failed to save engagement';
      toast.error(msg);
    }
  };

  const handleSubmitPlan = async (planId) => {
    try {
      await planningApi.submitPlan(planId);
      toast.success('Plan submitted for approval successfully!');
      fetchPlanningData();
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : 'Failed to submit plan';
      toast.error(msg);
    }
  };

  const handleApprovePlan = async (planId) => {
    try {
      await planningApi.approvePlan(planId);
      toast.success('Plan approved successfully!');
      fetchPlanningData();
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : 'Failed to approve plan';
      toast.error(msg);
    }
  };

  const openTeamModal = async (engagement) => {
    setSelectedEngagement(engagement);
    setShowTeamModal(true);
    setTeamMember({ user: '', role: 'member', allocated_days: 0 });
    // Fetch current team for this engagement
    try {
      const res = await planningApi.getEngagement(engagement.id);
      setEngagementTeam(res.team_members || []);
    } catch (err) {
      toast.error('Failed to load engagement team members');
    }
  };

  const handleAddTeamMember = async (e) => {
    e.preventDefault();
    try {
      await planningApi.addTeamMember(selectedEngagement.id, teamMember);
      toast.success('Team member assigned successfully!');
      // Refresh team
      const res = await planningApi.getEngagement(selectedEngagement.id);
      setEngagementTeam(res.team_members || []);
      setTeamMember({ user: '', role: 'member', allocated_days: 0 });
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : 'Failed to assign team member';
      toast.error(msg);
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
                <div className="flex gap-2">
                  {dueForAudit.length > 0 && (
                    <span className="badge badge-danger flex items-center gap-1">
                      <Clock size={13} /> {dueForAudit.length} due for re-audit
                    </span>
                  )}
                  {canWriteAudit && (
                    <button className="btn btn-primary flex items-center gap-2" onClick={openAddUniverse}>
                      <Plus size={16} /> Add Entity
                    </button>
                  )}
                </div>
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
                      <th>Last Audited</th>
                      <th>Re-Audit</th>
                      <th>Status</th>
                      <th>Actions</th>
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
                        <td>{item.last_audited || 'Never'}</td>
                        <td>
                          {item.due_for_re_audit ? (
                            <span className="badge badge-danger">Due</span>
                          ) : (
                            <span className="badge badge-success">OK</span>
                          )}
                        </td>
                        <td>
                          <span className={`badge ${item.status === 'active' ? 'badge-success' : 'badge-warning'}`}>
                            {item.status}
                          </span>
                        </td>
                        <td>
                          {canWriteAudit && (
                            <button className="btn btn-sm btn-outline flex items-center gap-1" onClick={() => openEditUniverse(item)}>
                              <Pencil size={13} /> Edit
                            </button>
                          )}
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
                {canWriteAudit && (
                  <button className="btn btn-primary flex items-center gap-2" onClick={openAddPlan}>
                    <Plus size={16} /> Create Plan
                  </button>
                )}
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
                        {canWriteAudit && (
                          <button className="btn btn-sm btn-outline flex items-center gap-1" onClick={() => openEditPlan(plan)}>
                            <Pencil size={13} /> Edit
                          </button>
                        )}
                        {plan.status === 'draft' && canWriteAudit && (
                          <button className="btn btn-sm btn-outline flex-1" onClick={() => handleSubmitPlan(plan.id)}>
                            Submit for Approval
                          </button>
                        )}
                        {plan.status === 'submitted' && canApprovePlans && (
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
                {canWriteAudit && (
                  <button className="btn btn-primary flex items-center gap-2" onClick={openAddEngagement}>
                    <Plus size={16} /> Schedule Engagement
                  </button>
                )}
              </div>
              <div className="table-responsive">
                <table className="table engagements-table">
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
                          <div className="flex gap-1">
                            <button className="btn btn-sm btn-outline flex items-center gap-1" onClick={() => openEditEngagement(eng)}>
                              <Pencil size={13} /> Edit
                            </button>
                            <button className="btn btn-sm btn-outline" onClick={() => openTeamModal(eng)}>
                              Assign
                            </button>
                          </div>
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
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={closeUniverseModal}
          onKeyDown={(e) => { if (e.key === 'Escape') closeUniverseModal(); }}
        >
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="universe-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="universe-modal-title">{editingUniverseId ? 'Edit Auditable Entity' : 'Add Auditable Entity'}</h3>
              <button
                type="button"
                className="close-btn"
                onClick={closeUniverseModal}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleSaveUniverse}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Entity Name</label>
                  <input type="text" className="form-control" placeholder="e.g. Substation Asset Management"
                    value={newUniverse.name} onChange={(e) => setNewUniverse({ ...newUniverse, name: e.target.value })} required />
                </div>
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Unique Code</label>
                    <input type="text" className="form-control" placeholder="e.g. UNIV-DIST-06"
                      value={newUniverse.code} onChange={(e) => setNewUniverse({ ...newUniverse, code: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Category</label>
                    <select className="form-control" value={newUniverse.category} onChange={(e) => setNewUniverse({ ...newUniverse, category: e.target.value })}>
                      <option value="department">Department</option>
                      <option value="process">Business Process</option>
                      <option value="system">IT System</option>
                      <option value="project">Project</option>
                    </select>
                  </div>
                </div>
                <div className="form-group-row">
                  <OrgUnitSelect
                    label="Associated Department"
                    value={newUniverse.department}
                    onChange={(id) => setNewUniverse({ ...newUniverse, department: id })}
                    valueLabel={editingUniverseDeptName}
                  />
                  <div className="form-group">
                    <label className="form-label">Initial Risk Score (1-5)</label>
                    <input type="number" step="0.05" min="1" max="5" className="form-control"
                      value={newUniverse.risk_score} onChange={(e) => setNewUniverse({ ...newUniverse, risk_score: parseFloat(e.target.value) })} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Audit Frequency</label>
                    <select className="form-control" value={newUniverse.audit_frequency} onChange={(e) => setNewUniverse({ ...newUniverse, audit_frequency: e.target.value })}>
                      <option value="Annually">Annually</option>
                      <option value="Bi-annually">Bi-annually</option>
                      <option value="Tri-annually">Tri-annually</option>
                    </select>
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={closeUniverseModal}>Cancel</button>
                <button type="submit" className="btn btn-primary">{editingUniverseId ? 'Save Changes' : 'Save Entity'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Annual Plan Modal */}
      {showPlanModal && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={closePlanModal}
          onKeyDown={(e) => { if (e.key === 'Escape') closePlanModal(); }}
        >
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="plan-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="plan-modal-title">{editingPlanId ? 'Edit Annual Audit Plan' : 'Create Annual Audit Plan'}</h3>
              <button
                type="button"
                className="close-btn"
                onClick={closePlanModal}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleSavePlan}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Plan Title</label>
                  <input type="text" className="form-control" placeholder="e.g. FY 2026 Comprehensive Audit Plan"
                    value={newPlan.title} onChange={(e) => setNewPlan({ ...newPlan, title: e.target.value })} required />
                </div>
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Year</label>
                    <input type="number" className="form-control" value={newPlan.year}
                      onChange={(e) => setNewPlan({ ...newPlan, year: parseInt(e.target.value) })} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Budget Days</label>
                    <input type="number" className="form-control" value={newPlan.total_budget_days}
                      onChange={(e) => setNewPlan({ ...newPlan, total_budget_days: parseInt(e.target.value) })} />
                  </div>
                </div>
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Start Date</label>
                    <input type="date" className="form-control" value={newPlan.start_date}
                      onChange={(e) => setNewPlan({ ...newPlan, start_date: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">End Date</label>
                    <input type="date" className="form-control" value={newPlan.end_date}
                      onChange={(e) => setNewPlan({ ...newPlan, end_date: e.target.value })} />
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Description / Objectives</label>
                  <textarea rows="2" className="form-control" value={newPlan.description}
                    onChange={(e) => setNewPlan({ ...newPlan, description: e.target.value })} />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={closePlanModal}>Cancel</button>
                <button type="submit" className="btn btn-primary">{editingPlanId ? 'Save Changes' : 'Create Plan'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Engagement Modal — with Lead Auditor, Supervisor & Days */}
      {showEngagementModal && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={closeEngagementModal}
          onKeyDown={(e) => { if (e.key === 'Escape') closeEngagementModal(); }}
        >
          <div
            className="modal-card modal-large"
            role="dialog"
            aria-modal="true"
            aria-labelledby="engagement-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="engagement-modal-title">{editingEngagementId ? 'Edit Audit Engagement' : 'Schedule Audit Engagement'}</h3>
              <button
                type="button"
                className="close-btn"
                onClick={closeEngagementModal}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleSaveEngagement}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Engagement Title</label>
                  <input type="text" className="form-control" placeholder="e.g. Q1 Payroll Compliance Audit"
                    value={newEngagement.title} onChange={(e) => setNewEngagement({ ...newEngagement, title: e.target.value })} required />
                </div>
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Target Annual Plan</label>
                    <select className="form-control" value={newEngagement.plan}
                      onChange={(e) => setNewEngagement({ ...newEngagement, plan: e.target.value })} required>
                      <option value="">Select Plan...</option>
                      {plans.map(p => (<option key={p.id} value={p.id}>{p.title}</option>))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Engagement Type</label>
                    <select className="form-control" value={newEngagement.engagement_type}
                      onChange={(e) => setNewEngagement({ ...newEngagement, engagement_type: e.target.value })}>
                      <option value="operational">Operational</option>
                      <option value="financial">Financial</option>
                      <option value="compliance">Compliance</option>
                      <option value="it">IT Audit</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Risk Level</label>
                    <select className="form-control" value={newEngagement.risk_level}
                      onChange={(e) => setNewEngagement({ ...newEngagement, risk_level: e.target.value })}>
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
                      onChange={(e) => setNewEngagement({ ...newEngagement, lead_auditor: e.target.value })}>
                      <option value="">Select Lead Auditor...</option>
                      {auditors.map(u => (
                        <option key={u.id} value={u.id}>{u.full_name || `${u.first_name} ${u.last_name}`} ({u.employee_id})</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Supervisor</label>
                    <select className="form-control" value={newEngagement.supervisor}
                      onChange={(e) => setNewEngagement({ ...newEngagement, supervisor: e.target.value })}>
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
                      onChange={(e) => setNewEngagement({ ...newEngagement, planned_days: parseInt(e.target.value) || 0 })} />
                  </div>
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Audit Universe Node (Optional)</label>
                    <select className="form-control" value={newEngagement.audit_universe}
                      onChange={(e) => setNewEngagement({ ...newEngagement, audit_universe: e.target.value })}>
                      <option value="">Select Entity...</option>
                      {universe.map(u => (<option key={u.id} value={u.id}>{u.code} - {u.name}</option>))}
                    </select>
                  </div>
                  <OrgUnitSelect
                    label="Department"
                    value={newEngagement.department}
                    onChange={(id) => setNewEngagement({ ...newEngagement, department: id })}
                    valueLabel={editingEngagementDeptName}
                  />
                </div>
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Planned Start</label>
                    <input type="date" className="form-control" value={newEngagement.planned_start}
                      onChange={(e) => setNewEngagement({ ...newEngagement, planned_start: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Planned End</label>
                    <input type="date" className="form-control" value={newEngagement.planned_end}
                      onChange={(e) => setNewEngagement({ ...newEngagement, planned_end: e.target.value })} />
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={closeEngagementModal}>Cancel</button>
                <button type="submit" className="btn btn-primary">{editingEngagementId ? 'Save Changes' : 'Schedule Engagement'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Team Assignment Modal */}
      {showTeamModal && selectedEngagement && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setShowTeamModal(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setShowTeamModal(false); }}
        >
          <div
            className="modal-card modal-large"
            role="dialog"
            aria-modal="true"
            aria-labelledby="team-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="team-modal-title">Manage Team — {selectedEngagement.title}</h3>
              <button
                type="button"
                className="close-btn"
                onClick={() => setShowTeamModal(false)}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
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
                      onChange={(e) => setTeamMember({ ...teamMember, user: e.target.value })} required>
                      <option value="">Select User...</option>
                      {allUsers.map(u => (
                        <option key={u.id} value={u.id}>{u.full_name || `${u.first_name} ${u.last_name}`} ({u.role})</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Role in Engagement</label>
                    <select className="form-control" value={teamMember.role}
                      onChange={(e) => setTeamMember({ ...teamMember, role: e.target.value })}>
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
                      onChange={(e) => setTeamMember({ ...teamMember, allocated_days: parseInt(e.target.value) || 0 })} />
                  </div>
                </div>
                <div className="modal-footer" style={{ padding: 0, marginTop: '1rem' }}>
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
