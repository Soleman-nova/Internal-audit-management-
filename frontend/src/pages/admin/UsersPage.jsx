import React, { useState, useEffect } from 'react';
import { usersApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import { validateForm, validators, hasErrors, clearFieldError } from '../../utils/validation';
import Modal from '../../components/ui/Modal';
import DataTable from '../../components/ui/DataTable';
import Badge from '../../components/ui/Badge';
import FormField from '../../components/ui/FormField';
import OrgUnitSelect from '../../components/ui/OrgUnitSelect';
import { UserPlus, Shield, Activity, UserCheck, Edit2, Key, X } from 'lucide-react';

// Turn a DRF error body into one readable sentence. Raw JSON.stringify output
// ("{"email":["..."]}") is unreadable in a toast.
const formatApiError = (err) => {
  const data = err.response?.data;
  if (!data) return err.message || 'Unexpected error.';
  if (typeof data === 'string') return data;
  if (data.detail) return String(data.detail);
  return Object.entries(data)
    .map(([field, msg]) => `${field}: ${Array.isArray(msg) ? msg.join(' ') : msg}`)
    .join(' | ');
};

// A pre-filled starter password for new accounts. It must satisfy both
// validators.password (upper + lower + digit, 8+) and Django's
// AUTH_PASSWORD_VALIDATORS, otherwise the create form blocks its own default.
const DEFAULT_NEW_PASSWORD = 'Eeu@1234';

const EMPTY_NEW_USER = {
  username: '', email: '', first_name: '', last_name: '',
  role: 'auditor', employee_id: '', password: DEFAULT_NEW_PASSWORD,
  department: '', phone: ''
};

function UsersPage() {
  const toast = useToast();
  const { t } = useI18n();
  const [users, setUsers] = useState([]);
  const [formErrors, setFormErrors] = useState({});
  const [auditTrail, setAuditTrail] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // Add User State
  const [showAddModal, setShowAddModal] = useState(false);
  const [newUser, setNewUser] = useState(EMPTY_NEW_USER);

  // Edit User / Reset Password State
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [resetPasswordVal, setResetPasswordVal] = useState('');

  // Field edits clear their own error so a corrected field stops showing stale
  // feedback before the next submit.
  const setNewUserField = (field, value) => {
    setNewUser((prev) => ({ ...prev, [field]: value }));
    setFormErrors((prev) => clearFieldError(prev, field));
  };

  const setEditingUserField = (field, value) => {
    setEditingUser((prev) => ({ ...prev, [field]: value }));
    setFormErrors((prev) => clearFieldError(prev, field));
  };

  const closeAddModal = () => {
    setShowAddModal(false);
    setFormErrors({});
  };

  const closeEditModal = () => {
    setShowEditModal(false);
    setFormErrors({});
  };

  useEffect(() => {
    fetchUsersAndTrail();
  }, []);

  const fetchUsersAndTrail = async () => {
    setLoading(true);
    try {
      // Departments are no longer fetched here — OrgUnitSelect loads the org
      // tree itself through useOrgUnits and shares one request across forms.
      const [usersRes, trailRes] = await Promise.all([
        usersApi.getUsers(),
        usersApi.getAuditTrail()
      ]);
      setUsers(usersRes || []);
      setAuditTrail(trailRes?.results || trailRes || []);
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
      toast.warning('Please correct the highlighted fields before creating the user.');
      return;
    }
    setFormErrors({});
    setSubmitting(true);
    try {
      const payload = { ...newUser };
      if (payload.department === '') {
        payload.department = null;
      }
      const res = await usersApi.createUser(payload);
      setUsers([...users, res]);
      setShowAddModal(false);
      // Reset
      setNewUser(EMPTY_NEW_USER);
      toast.success('User created successfully!');
      fetchUsersAndTrail(); // Refresh audit trail for user creation
    } catch (err) {
      // Map DRF field errors ({ email: [...] }) back onto the form so the
      // offending input is highlighted rather than only named in a toast.
      const data = err.response?.data;
      if (data && typeof data === 'object' && !Array.isArray(data)) {
        const fieldErrors = {};
        for (const [field, msg] of Object.entries(data)) {
          fieldErrors[field] = Array.isArray(msg) ? msg.join(' ') : String(msg);
        }
        setFormErrors(fieldErrors);
      }
      toast.error('Failed to create user: ' + formatApiError(err));
    } finally {
      setSubmitting(false);
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
      toast.warning('Please correct the highlighted fields before saving.');
      return;
    }
    setFormErrors({});
    setSubmitting(true);
    try {
      // department_name is display-only (read-only on the serializer) and only
      // carried so the picker can label a retired unit — don't send it back.
      const { id, ...dataToUpdate } = editingUser;
      delete dataToUpdate.department_name;
      if (dataToUpdate.department === '') {
        dataToUpdate.department = null;
      }
      const res = await usersApi.updateUser(id, dataToUpdate);
      setUsers(users.map(u => u.id === id ? res : u));
      setShowEditModal(false);
      toast.success('User updated successfully!');
      fetchUsersAndTrail();
    } catch (err) {
      const data = err.response?.data;
      if (data && typeof data === 'object' && !Array.isArray(data)) {
        const fieldErrors = {};
        for (const [field, msg] of Object.entries(data)) {
          fieldErrors[field] = Array.isArray(msg) ? msg.join(' ') : String(msg);
        }
        setFormErrors(fieldErrors);
      }
      toast.error('Failed to update user: ' + formatApiError(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    const pwError = validators.required(resetPasswordVal) || validators.password(resetPasswordVal);
    if (pwError) {
      setFormErrors((prev) => ({ ...prev, reset_password: pwError }));
      return;
    }
    setFormErrors((prev) => clearFieldError(prev, 'reset_password'));
    try {
      await usersApi.resetPassword(editingUser.id, resetPasswordVal);
      toast.success('Password reset successfully!');
      setResetPasswordVal('');
    } catch (err) {
      const msg = formatApiError(err);
      setFormErrors((prev) => ({ ...prev, reset_password: msg }));
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
            <button className="btn btn-primary flex items-center gap-1" onClick={() => { setFormErrors({}); setShowAddModal(true); }}>
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
                              // Carried so OrgUnitSelect can still name a
                              // retired unit, which the org tree omits.
                              department_name: u.department_name || '',
                              is_active: u.is_active
                            });
                            setResetPasswordVal('');
                            setFormErrors({});
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
          onClick={closeAddModal}
          onKeyDown={(e) => { if (e.key === 'Escape') closeAddModal(); }}
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
                onClick={closeAddModal}
                aria-label="Close dialog"
              >
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleAddUser} noValidate>
              <div className="modal-body">
                {hasErrors(formErrors) && (
                  <div className="alert alert-red" role="alert">
                    <span className="alert-icon">!</span>
                    <span>Some fields need attention before this account can be created.</span>
                  </div>
                )}

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label" htmlFor="add_first_name">First Name</label>
                    <input
                      id="add_first_name"
                      type="text"
                      className={`form-control ${formErrors.first_name ? 'is-invalid' : ''}`}
                      value={newUser.first_name}
                      onChange={(e) => setNewUserField('first_name', e.target.value)}
                      aria-invalid={!!formErrors.first_name}
                      aria-describedby={formErrors.first_name ? 'add_first_name_error' : undefined}
                    />
                    {formErrors.first_name && (
                      <p className="form-error" id="add_first_name_error">{formErrors.first_name}</p>
                    )}
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="add_last_name">Last Name</label>
                    <input
                      id="add_last_name"
                      type="text"
                      className={`form-control ${formErrors.last_name ? 'is-invalid' : ''}`}
                      value={newUser.last_name}
                      onChange={(e) => setNewUserField('last_name', e.target.value)}
                      aria-invalid={!!formErrors.last_name}
                      aria-describedby={formErrors.last_name ? 'add_last_name_error' : undefined}
                    />
                    {formErrors.last_name && (
                      <p className="form-error" id="add_last_name_error">{formErrors.last_name}</p>
                    )}
                  </div>
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label" htmlFor="add_username">Username</label>
                    <input
                      id="add_username"
                      type="text"
                      className={`form-control ${formErrors.username ? 'is-invalid' : ''}`}
                      value={newUser.username}
                      onChange={(e) => setNewUserField('username', e.target.value)}
                      aria-invalid={!!formErrors.username}
                      aria-describedby={formErrors.username ? 'add_username_error' : undefined}
                    />
                    {formErrors.username && (
                      <p className="form-error" id="add_username_error">{formErrors.username}</p>
                    )}
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="add_employee_id">Employee ID</label>
                    <input
                      id="add_employee_id"
                      type="text"
                      className={`form-control ${formErrors.employee_id ? 'is-invalid' : ''}`}
                      placeholder="e.g. EEU-10255"
                      value={newUser.employee_id}
                      onChange={(e) => setNewUserField('employee_id', e.target.value)}
                      aria-invalid={!!formErrors.employee_id}
                      aria-describedby={formErrors.employee_id ? 'add_employee_id_error' : undefined}
                    />
                    {formErrors.employee_id && (
                      <p className="form-error" id="add_employee_id_error">{formErrors.employee_id}</p>
                    )}
                  </div>
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label" htmlFor="add_email">Email Address</label>
                    <input
                      id="add_email"
                      type="email"
                      className={`form-control ${formErrors.email ? 'is-invalid' : ''}`}
                      placeholder="name@eeu.com"
                      value={newUser.email}
                      onChange={(e) => setNewUserField('email', e.target.value)}
                      aria-invalid={!!formErrors.email}
                      aria-describedby={formErrors.email ? 'add_email_error' : undefined}
                    />
                    {formErrors.email && (
                      <p className="form-error" id="add_email_error">{formErrors.email}</p>
                    )}
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="add_phone">Phone Number</label>
                    <input
                      id="add_phone"
                      type="text"
                      className={`form-control ${formErrors.phone ? 'is-invalid' : ''}`}
                      placeholder="e.g. +251911..."
                      value={newUser.phone}
                      onChange={(e) => setNewUserField('phone', e.target.value)}
                      aria-invalid={!!formErrors.phone}
                      aria-describedby={formErrors.phone ? 'add_phone_error' : undefined}
                    />
                    {formErrors.phone && (
                      <p className="form-error" id="add_phone_error">{formErrors.phone}</p>
                    )}
                  </div>
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label" htmlFor="add_role">Security Role</label>
                    <select
                      id="add_role"
                      className="form-control"
                      value={newUser.role}
                      onChange={(e) => setNewUserField('role', e.target.value)}
                    >
                      <option value="admin">System Administrator</option>
                      <option value="audit_manager">Audit Manager</option>
                      <option value="supervisor">Supervisor</option>
                      <option value="auditor">Lead Auditor</option>
                      <option value="auditee">Auditee Representative</option>
                    </select>
                  </div>
                  <OrgUnitSelect
                    label="Department / Unit"
                    value={newUser.department}
                    onChange={(id) => setNewUserField('department', id)}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="add_password">Default Password</label>
                  <input
                    id="add_password"
                    type="password"
                    className={`form-control ${formErrors.password ? 'is-invalid' : ''}`}
                    value={newUser.password}
                    onChange={(e) => setNewUserField('password', e.target.value)}
                    aria-invalid={!!formErrors.password}
                    aria-describedby={formErrors.password ? 'add_password_error' : 'add_password_hint'}
                  />
                  {formErrors.password ? (
                    <p className="form-error" id="add_password_error">{formErrors.password}</p>
                  ) : (
                    <p className="form-hint" id="add_password_hint">
                      At least 8 characters, with an uppercase letter, a lowercase letter, and a number.
                    </p>
                  )}
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={closeAddModal}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? 'Creating…' : 'Create User'}
                </button>
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
          onClick={closeEditModal}
          onKeyDown={(e) => { if (e.key === 'Escape') closeEditModal(); }}
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
                onClick={closeEditModal}
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
                <p className="text-xs text-muted mb-3">
                  Set a new password for this corporate user. At least 8 characters, with an
                  uppercase letter, a lowercase letter, and a number.
                </p>
                <form onSubmit={handleResetPassword} noValidate>
                  <div className="flex gap-2">
                    <input
                      type="password"
                      className={`form-control ${formErrors.reset_password ? 'is-invalid' : ''}`}
                      placeholder="New password"
                      value={resetPasswordVal}
                      onChange={(e) => {
                        setResetPasswordVal(e.target.value);
                        setFormErrors((prev) => clearFieldError(prev, 'reset_password'));
                      }}
                      aria-invalid={!!formErrors.reset_password}
                      aria-describedby={formErrors.reset_password ? 'reset_password_error' : undefined}
                    />
                    <button type="submit" className="btn btn-secondary whitespace-nowrap">
                      Update Password
                    </button>
                  </div>
                  {formErrors.reset_password && (
                    <p className="form-error" id="reset_password_error">{formErrors.reset_password}</p>
                  )}
                </form>
              </div>

              {/* Edit Account Details Form Section */}
              <form onSubmit={handleEditUser} noValidate>
                <h4 className="flex items-center gap-2 mb-3 text-accent">
                  <Edit2 size={16} /> Edit Account Details
                </h4>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label" htmlFor="edit_first_name">First Name</label>
                    <input
                      id="edit_first_name"
                      type="text"
                      className={`form-control ${formErrors.first_name ? 'is-invalid' : ''}`}
                      value={editingUser.first_name}
                      onChange={(e) => setEditingUserField('first_name', e.target.value)}
                      aria-invalid={!!formErrors.first_name}
                      aria-describedby={formErrors.first_name ? 'edit_first_name_error' : undefined}
                    />
                    {formErrors.first_name && (
                      <p className="form-error" id="edit_first_name_error">{formErrors.first_name}</p>
                    )}
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="edit_last_name">Last Name</label>
                    <input
                      id="edit_last_name"
                      type="text"
                      className={`form-control ${formErrors.last_name ? 'is-invalid' : ''}`}
                      value={editingUser.last_name}
                      onChange={(e) => setEditingUserField('last_name', e.target.value)}
                      aria-invalid={!!formErrors.last_name}
                      aria-describedby={formErrors.last_name ? 'edit_last_name_error' : undefined}
                    />
                    {formErrors.last_name && (
                      <p className="form-error" id="edit_last_name_error">{formErrors.last_name}</p>
                    )}
                  </div>
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label" htmlFor="edit_username">Username</label>
                    <input
                      id="edit_username"
                      type="text"
                      className={`form-control ${formErrors.username ? 'is-invalid' : ''}`}
                      value={editingUser.username}
                      onChange={(e) => setEditingUserField('username', e.target.value)}
                      aria-invalid={!!formErrors.username}
                      aria-describedby={formErrors.username ? 'edit_username_error' : undefined}
                    />
                    {formErrors.username && (
                      <p className="form-error" id="edit_username_error">{formErrors.username}</p>
                    )}
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="edit_employee_id">Employee ID</label>
                    <input
                      id="edit_employee_id"
                      type="text"
                      className={`form-control ${formErrors.employee_id ? 'is-invalid' : ''}`}
                      value={editingUser.employee_id}
                      onChange={(e) => setEditingUserField('employee_id', e.target.value)}
                      aria-invalid={!!formErrors.employee_id}
                      aria-describedby={formErrors.employee_id ? 'edit_employee_id_error' : undefined}
                    />
                    {formErrors.employee_id && (
                      <p className="form-error" id="edit_employee_id_error">{formErrors.employee_id}</p>
                    )}
                  </div>
                </div>

                <div className="form-group-row">
                  <div className="form-group">
                    <label className="form-label" htmlFor="edit_email">Email Address</label>
                    <input
                      id="edit_email"
                      type="email"
                      className={`form-control ${formErrors.email ? 'is-invalid' : ''}`}
                      value={editingUser.email}
                      onChange={(e) => setEditingUserField('email', e.target.value)}
                      aria-invalid={!!formErrors.email}
                      aria-describedby={formErrors.email ? 'edit_email_error' : undefined}
                    />
                    {formErrors.email && (
                      <p className="form-error" id="edit_email_error">{formErrors.email}</p>
                    )}
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="edit_phone">Phone Number</label>
                    <input
                      id="edit_phone"
                      type="text"
                      className={`form-control ${formErrors.phone ? 'is-invalid' : ''}`}
                      placeholder="e.g. +251911..."
                      value={editingUser.phone}
                      onChange={(e) => setEditingUserField('phone', e.target.value)}
                      aria-invalid={!!formErrors.phone}
                      aria-describedby={formErrors.phone ? 'edit_phone_error' : undefined}
                    />
                    {formErrors.phone && (
                      <p className="form-error" id="edit_phone_error">{formErrors.phone}</p>
                    )}
                  </div>
                </div>

                <div className="form-group-row">
                  <OrgUnitSelect
                    label="Department / Unit"
                    value={editingUser.department || ''}
                    onChange={(id) => setEditingUserField('department', id)}
                    valueLabel={editingUser.department_name}
                  />
                  <div className="form-group">
                    <label className="form-label" htmlFor="edit_role">Security Role</label>
                    <select
                      id="edit_role"
                      className="form-control"
                      value={editingUser.role}
                      onChange={(e) => setEditingUserField('role', e.target.value)}
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
                    onChange={(e) => setEditingUserField('is_active', e.target.checked)}
                  />
                  <label htmlFor="edit_is_active" className="form-label mb-0 cursor-pointer">
                    Account is Active and Enabled
                  </label>
                </div>

                <div className="modal-footer mt-5">
                  <button type="button" className="btn btn-outline" onClick={closeEditModal}>Cancel</button>
                  <button type="submit" className="btn btn-primary" disabled={submitting}>
                    {submitting ? 'Saving…' : 'Save Changes'}
                  </button>
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
