import React, { useState, useEffect } from 'react';
import { usersApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import { validateForm, validators, hasErrors } from '../../utils/validation';
import Modal from '../../components/ui/Modal';
import DataTable from '../../components/ui/DataTable';
import Badge from '../../components/ui/Badge';
import FormField from '../../components/ui/FormField';
import { UserPlus, Shield, Activity, UserCheck, Edit2, Key, X } from 'lucide-react';

function UsersPage() {
  const toast = useToast();
  const { t } = useI18n();
  const [users, setUsers] = useState([]);
  const [formErrors, setFormErrors] = useState({});
  const [auditTrail, setAuditTrail] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);

  // Add User State
  const [showAddModal, setShowAddModal] = useState(false);
  const [newUser, setNewUser] = useState({
    username: '', email: '', first_name: '', last_name: '',
    role: 'auditor', employee_id: '', password: 'user1234',
    department: '', phone: ''
  });

  // Edit User / Reset Password State
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [resetPasswordVal, setResetPasswordVal] = useState('');

  useEffect(() => {
    fetchUsersAndTrail();
  }, []);

  const fetchUsersAndTrail = async () => {
    setLoading(true);
    try {
      const [usersRes, trailRes, deptsRes] = await Promise.all([
        usersApi.getUsers(),
        usersApi.getAuditTrail(),
        usersApi.getDepartments()
      ]);
      setUsers(usersRes || []);
      setAuditTrail(trailRes?.results || trailRes || []);
      setDepartments(deptsRes || []);
    } catch (err) {
      toast.error('Failed to load user management data');
    } finally {
      setLoading(false);
    }
  };

  const handleAddUser = async (e) => {
    e.preventDefault();
    // Validate form
    const errors = validateForm(newUser, {
      first_name: { validators: [validators.required, validators.minLength(2)] },
      last_name: { validators: [validators.required, validators.minLength(2)] },
      username: { validators: [validators.required, validators.minLength(3)] },
      email: { validators: [validators.required, validators.email] },
      employee_id: { validators: [validators.required, validators.employeeId] },
      password: { validators: [validators.required, validators.password] },
      phone: { validators: [validators.phone] },
    });
    if (hasErrors(errors)) {
      setFormErrors(errors);
      return;
    }
    setFormErrors({});
    try {
      const payload = { ...newUser };
      if (payload.department === '') {
        payload.department = null;
      }
      const res = await usersApi.createUser(payload);
      setUsers([...users, res]);
      setShowAddModal(false);
      // Reset
      setNewUser({
        username: '', email: '', first_name: '', last_name: '',
        role: 'auditor', employee_id: '', password: 'user1234',
        department: '', phone: ''
      });
      toast.success('User created successfully!');
      fetchUsersAndTrail(); // Refresh audit trail for user creation
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error('Failed to create user: ' + msg);
    }
  };

  const handleEditUser = async (e) => {
    e.preventDefault();
    // Validate form
    const errors = validateForm(editingUser, {
      first_name: { validators: [validators.required, validators.minLength(2)] },
      last_name: { validators: [validators.required, validators.minLength(2)] },
      username: { validators: [validators.required, validators.minLength(3)] },
      email: { validators: [validators.required, validators.email] },
      employee_id: { validators: [validators.required, validators.employeeId] },
      phone: { validators: [validators.phone] },
    });
    if (hasErrors(errors)) {
      setFormErrors(errors);
      return;
    }
    setFormErrors({});
    try {
      const { id, ...dataToUpdate } = editingUser;
      if (dataToUpdate.department === '') {
        dataToUpdate.department = null;
      }
      const res = await usersApi.updateUser(id, dataToUpdate);
      setUsers(users.map(u => u.id === id ? res : u));
      setShowEditModal(false);
      toast.success('User updated successfully!');
      fetchUsersAndTrail();
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error('Failed to update user: ' + msg);
    }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    if (!resetPasswordVal || resetPasswordVal.length < 8) {
      toast.warning('Password must be at least 8 characters long.');
      return;
    }
    try {
      await usersApi.resetPassword(editingUser.id, resetPasswordVal);
      toast.success('Password reset successfully!');
      setResetPasswordVal('');
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : err.message;
      toast.error('Failed to reset password: ' + msg);
    }
  };

  return (
    <div className="users-view">
      <div className="users-grid">
        {/* Left Side: Users list */}
        <div className="card users-list-card">
          <div className="card-header justify-between">
            <div>
              <h3>{t('corporateUsers')}</h3>
              <p className="card-subtitle">{t('maintainAccounts')}</p>
            </div>
            <button className="btn btn-primary flex items-center gap-1" onClick={() => setShowAddModal(true)}>
              <UserPlus size={16} /> {t('addAccount')}
            </button>
          </div>

          {loading ? (
            <div className="loading-spinner">{t('loadingUsers')}</div>
          ) : (
            <div className="table-responsive mt-3">
              <table className="table">
                <thead>
                  <tr>
                    <th>Emp ID</th>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th className="text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map(u => (
                    <tr key={u.id}>
                      <td><strong>{u.employee_id || 'N/A'}</strong></td>
                      <td>{u.first_name} {u.last_name}</td>
                      <td>{u.email}</td>
                      <td>
                        <span className="badge badge-outline">
                          {u.role?.replace('_', ' ').toUpperCase()}
                        </span>
                      </td>
                      <td>
                        <span className={`badge ${u.is_active ? 'badge-success' : 'badge-danger'}`}>
                          {u.is_active ? 'ACTIVE' : 'INACTIVE'}
                        </span>
                      </td>
                      <td className="text-right">
                        <button
                          className="btn btn-sm btn-outline flex items-center gap-1 ml-auto"
                          onClick={() => {
                            setEditingUser({
                              id: u.id,
                              username: u.username,
                              email: u.email,
                              first_name: u.first_name,
                              last_name: u.last_name,
                              role: u.role,
                              employee_id: u.employee_id || '',
                              phone: u.phone || '',
                              department: u.department || '',
                              is_active: u.is_active
                            });
                            setResetPasswordVal('');
                            setShowEditModal(true);
                          }}
                        >
                          <Edit2 size={12} /> Edit / Reset
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Audit Trail Section */}
      <div className="card mt-6">
        <div className="card-header">
          <h3><Activity size={18} className="inline mr-2 text-accent" /> {t('securityAuditLog')}</h3>
          <p className="card-subtitle">{t('realTimeLog')}</p>
        </div>

        <div className="table-responsive mt-3">
          <table className="table table-sm">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Operator</th>
                <th>Action</th>
                <th>Impacted Module</th>
                <th>Object Representation</th>
              </tr>
            </thead>
            <tbody>
              {auditTrail.length === 0 ? (
                <tr>
                  <td colSpan="5" className="text-center py-4 text-muted">No audit trail records registered.</td>
                </tr>
              ) : (
                auditTrail.map(log => (
                  <tr key={log.id}>
                    <td>{new Date(log.timestamp).toLocaleString()}</td>
                    <td><strong>{log.user_email || 'System'}</strong></td>
                    <td>
                      <span className={`badge ${log.action === 'CREATE' ? 'badge-success' : log.action === 'DELETE' ? 'badge-danger' : 'badge-outline'}`}>
                        {log.action}
                      </span>
                    </td>
                    <td>{log.model_name}</td>
                    <td><span className="font-mono text-xs">{log.object_repr}</span></td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add User Modal */}
      {showAddModal && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setShowAddModal(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setShowAddModal(false); }}
        >
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="add-user-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="add-user-modal-title">{t('createStaffAccount')}</h3>
              <button
                type="button"
                className="close-btn"
                onClick={() => setShowAddModal(false)}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleAddUser}>
              <div className="modal-body">
                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">First Name</label>
                    <input
                      type="text"
                      className="form-control"
                      value={newUser.first_name}
                      onChange={(e) => setNewUser({ ...newUser, first_name: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Last Name</label>
                    <input
                      type="text"
                      className="form-control"
                      value={newUser.last_name}
                      onChange={(e) => setNewUser({ ...newUser, last_name: e.target.value })}
                      required
                    />
                  </div>
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Username</label>
                    <input
                      type="text"
                      className="form-control"
                      value={newUser.username}
                      onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Employee ID</label>
                    <input
                      type="text"
                      className="form-control"
                      placeholder="e.g. EEU-10255"
                      value={newUser.employee_id}
                      onChange={(e) => setNewUser({ ...newUser, employee_id: e.target.value })}
                      required
                    />
                  </div>
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Email Address</label>
                    <input
                      type="email"
                      className="form-control"
                      placeholder="name@eeu.com"
                      value={newUser.email}
                      onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Phone Number</label>
                    <input
                      type="text"
                      className="form-control"
                      placeholder="e.g. +251911..."
                      value={newUser.phone}
                      onChange={(e) => setNewUser({ ...newUser, phone: e.target.value })}
                    />
                  </div>
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Security Role</label>
                    <select
                      className="form-control"
                      value={newUser.role}
                      onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
                    >
                      <option value="admin">System Administrator</option>
                      <option value="audit_manager">Audit Manager</option>
                      <option value="supervisor">Supervisor</option>
                      <option value="auditor">Lead Auditor</option>
                      <option value="auditee">Auditee Representative</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Department / Unit</label>
                    <select
                      className="form-control"
                      value={newUser.department}
                      onChange={(e) => setNewUser({ ...newUser, department: e.target.value })}
                    >
                      <option value="">Select Department (Optional)</option>
                      {departments.map(d => (
                        <option key={d.id} value={d.id}>{d.name} ({d.code})</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Default Password</label>
                  <input
                    type="password"
                    className="form-control"
                    value={newUser.password}
                    onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                    required
                  />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowAddModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Create User</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit User / Reset Password Modal */}
      {showEditModal && editingUser && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => setShowEditModal(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setShowEditModal(false); }}
        >
          <div
            className="modal-card"
            style={{ maxWidth: '600px' }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="edit-user-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="edit-user-modal-title">{t('editUserAccount', `${editingUser.first_name} ${editingUser.last_name}`)}</h3>
              <button
                type="button"
                className="close-btn"
                onClick={() => setShowEditModal(false)}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>

            <div className="modal-body">
              {/* Reset Password Form Section */}
              <div className="card bg-surface-variant p-4 mb-5 border border-primary/20">
                <h4 className="flex items-center gap-2 mb-2 text-primary">
                  <Key size={16} /> Reset Password
                </h4>
                <p className="text-xs text-muted mb-3">Set a new password for this corporate user. Minimum 8 characters.</p>
                <form onSubmit={handleResetPassword} className="flex gap-2">
                  <input
                    type="password"
                    className="form-control"
                    placeholder="New password (min 8 chars)"
                    value={resetPasswordVal}
                    onChange={(e) => setResetPasswordVal(e.target.value)}
                    required
                  />
                  <button type="submit" className="btn btn-secondary whitespace-nowrap">
                    Update Password
                  </button>
                </form>
              </div>

              {/* Edit Account Details Form Section */}
              <form onSubmit={handleEditUser}>
                <h4 className="flex items-center gap-2 mb-3 text-accent">
                  <Edit2 size={16} /> Edit Account Details
                </h4>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">First Name</label>
                    <input
                      type="text"
                      className="form-control"
                      value={editingUser.first_name}
                      onChange={(e) => setEditingUser({ ...editingUser, first_name: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Last Name</label>
                    <input
                      type="text"
                      className="form-control"
                      value={editingUser.last_name}
                      onChange={(e) => setEditingUser({ ...editingUser, last_name: e.target.value })}
                      required
                    />
                  </div>
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Username</label>
                    <input
                      type="text"
                      className="form-control"
                      value={editingUser.username}
                      onChange={(e) => setEditingUser({ ...editingUser, username: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Employee ID</label>
                    <input
                      type="text"
                      className="form-control"
                      value={editingUser.employee_id}
                      onChange={(e) => setEditingUser({ ...editingUser, employee_id: e.target.value })}
                      required
                    />
                  </div>
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Email Address</label>
                    <input
                      type="email"
                      className="form-control"
                      value={editingUser.email}
                      onChange={(e) => setEditingUser({ ...editingUser, email: e.target.value })}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Phone Number</label>
                    <input
                      type="text"
                      className="form-control"
                      placeholder="e.g. +251911..."
                      value={editingUser.phone}
                      onChange={(e) => setEditingUser({ ...editingUser, phone: e.target.value })}
                    />
                  </div>
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label">Department / Unit</label>
                    <select
                      className="form-control"
                      value={editingUser.department || ''}
                      onChange={(e) => setEditingUser({ ...editingUser, department: e.target.value })}
                    >
                      <option value="">Select Department (Optional)</option>
                      {departments.map(d => (
                        <option key={d.id} value={d.id}>{d.name} ({d.code})</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Security Role</label>
                    <select
                      className="form-control"
                      value={editingUser.role}
                      onChange={(e) => setEditingUser({ ...editingUser, role: e.target.value })}
                    >
                      <option value="admin">System Administrator</option>
                      <option value="audit_manager">Audit Manager</option>
                      <option value="supervisor">Supervisor</option>
                      <option value="auditor">Lead Auditor</option>
                      <option value="auditee">Auditee Representative</option>
                    </select>
                  </div>
                </div>

                <div className="form-group flex items-center gap-2 mt-4">
                  <input
                    type="checkbox"
                    id="edit_is_active"
                    checked={editingUser.is_active}
                    onChange={(e) => setEditingUser({ ...editingUser, is_active: e.target.checked })}
                  />
                  <label htmlFor="edit_is_active" className="form-label mb-0 cursor-pointer">
                    Account is Active and Enabled
                  </label>
                </div>

                <div className="modal-footer mt-5">
                  <button type="button" className="btn btn-outline" onClick={() => setShowEditModal(false)}>Cancel</button>
                  <button type="submit" className="btn btn-primary">Save Changes</button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default UsersPage;
