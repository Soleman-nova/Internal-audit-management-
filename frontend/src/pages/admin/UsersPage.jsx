import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { usersApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import { usePermissions } from '../../hooks/usePermissions';
import { localizedName } from '../../utils/localizedName';
import { validateForm, validators, hasErrors, clearFieldError } from '../../utils/validation';
import Modal from '../../components/ui/Modal';
import DataTable from '../../components/ui/DataTable';
import Pagination from '../../components/ui/Pagination';
import Badge from '../../components/ui/Badge';
import FormField from '../../components/ui/FormField';
import OrgUnitSelect from '../../components/ui/OrgUnitSelect';
import { UserPlus, Shield, Activity, UserCheck, Edit2, Key, ArrowRight, Trash2 } from 'lucide-react';

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

const DEFAULT_PAGE_SIZE = 20;

function UsersPage() {
  const toast = useToast();
  const { t, lang } = useI18n();
  const { user: currentUser } = usePermissions();
  const [users, setUsers] = useState([]);
  const [formErrors, setFormErrors] = useState({});
  const [accountActivity, setAccountActivity] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // The users list is server-paginated; the account-activity panel is not.
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [totalUsers, setTotalUsers] = useState(0);

  // Add User State
  const [showAddModal, setShowAddModal] = useState(false);
  const [newUser, setNewUser] = useState(EMPTY_NEW_USER);

  // Edit User / Reset Password State
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [resetPasswordVal, setResetPasswordVal] = useState('');

  // Delete User State. `deleteBlockers` is null while the preflight request is
  // still in flight, [] when the account is safe to remove, and a non-empty
  // list when the delete must be refused.
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteBlockers, setDeleteBlockers] = useState(null);
  const [deleting, setDeleting] = useState(false);
  // Monotonic tag for in-flight preflight checks; see openDeleteModal.
  const deleteRequestRef = useRef(0);

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

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const res = await usersApi.getUsers({ page, page_size: pageSize });
      setUsers(Array.isArray(res) ? res : res.results || []);
      setTotalUsers(Array.isArray(res) ? res.length : res.count || 0);
    } catch (err) {
      // An out-of-range page is a 404, not a real failure — step back to the
      // first page rather than showing an error over an empty table.
      if (err.response?.status === 404 && page > 1) {
        setPage(1);
        return;
      }
      toast.error('Failed to load user management data');
    } finally {
      setLoading(false);
    }
  };

  // Departments are no longer fetched here — OrgUnitSelect loads the org tree
  // itself through useOrgUnits and shares one request across forms.
  //
  // model_name: 'User' is what makes this a *security* log rather than a second
  // copy of the Audit Trail page. log_audit stores instance.__class__.__name__,
  // and every account event — login, logout, create, edit, activate,
  // deactivate, password reset/change, profile update — is logged against the
  // User instance. Drop this filter and the panel silently becomes the global
  // feed again.
  const fetchAccountActivity = async () => {
    try {
      const trailRes = await usersApi.getAuditTrail({ model_name: 'User', page_size: 10 });
      setAccountActivity(trailRes?.results || trailRes || []);
    } catch (err) {
      toast.error('Failed to load account activity');
    }
  };

  useEffect(() => {
    fetchUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize]);

  useEffect(() => {
    fetchAccountActivity();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
      await usersApi.createUser(payload);
      setShowAddModal(false);
      // Reset
      setNewUser(EMPTY_NEW_USER);
      toast.success('User created successfully!');
      // Refetch rather than appending locally: the list is paginated, so an
      // extra row would push past the page size and the count would go stale.
      // The roster is ordered by name, so the new account lands wherever it
      // sorts — not necessarily on the page currently on screen.
      fetchUsers();
      fetchAccountActivity();
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
      await usersApi.updateUser(id, dataToUpdate);
      setShowEditModal(false);
      toast.success('User updated successfully!');
      // A renamed account can sort onto a different page, so refetch the
      // current one instead of patching the row in place.
      fetchUsers();
      fetchAccountActivity();
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

  // Ask the server what a delete would destroy before showing the dialog, so
  // the admin sees "this will erase 12 comments" up front rather than having a
  // confirmed delete rejected after the fact.
  const openDeleteModal = async (u) => {
    // A preflight can outlive the dialog it was opened for — the admin cancels
    // on a slow connection and immediately opens a different row. Tag each
    // request and drop any response that a newer one (or a close) superseded,
    // so blockers for one account can never render against another.
    const requestId = deleteRequestRef.current + 1;
    deleteRequestRef.current = requestId;
    setDeleteTarget(u);
    setDeleteBlockers(null);
    setDeleting(false);
    try {
      const res = await usersApi.checkUserDeletion(u.id);
      if (deleteRequestRef.current !== requestId) return;
      setDeleteBlockers(res?.blockers || []);
    } catch (err) {
      if (deleteRequestRef.current !== requestId) return;
      toast.error('Could not check this account: ' + formatApiError(err));
      setDeleteTarget(null);
    }
  };

  const closeDeleteModal = () => {
    deleteRequestRef.current += 1;
    setDeleteTarget(null);
    setDeleteBlockers(null);
  };

  const handleDeleteUser = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await usersApi.deleteUser(deleteTarget.id);
      toast.success(`${deleteTarget.first_name} ${deleteTarget.last_name} deleted.`);
      const wasLastRowOnPage = users.length === 1 && page > 1;
      closeDeleteModal();
      fetchAccountActivity();
      // Deleting the only row on a page would leave an empty table behind.
      if (wasLastRowOnPage) {
        setPage(page - 1);
      } else {
        fetchUsers();
      }
    } catch (err) {
      // A blocker can appear between the preflight and the delete (someone
      // else's edit, or a second admin tab). Surface the server's reason.
      const blockers = err.response?.data?.blockers;
      if (blockers?.length) {
        setDeleteBlockers(blockers);
      }
      toast.error('Failed to delete user: ' + formatApiError(err));
    } finally {
      setDeleting(false);
    }
  };

  // The alternative the blocked dialog offers. Deactivation keeps every
  // engagement-team and comment row intact and is reversible.
  const handleDeactivateInstead = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await usersApi.deactivateUser(deleteTarget.id);
      toast.success(`${deleteTarget.first_name} ${deleteTarget.last_name} deactivated.`);
      closeDeleteModal();
      fetchUsers();
      fetchAccountActivity();
    } catch (err) {
      toast.error('Failed to deactivate user: ' + formatApiError(err));
    } finally {
      setDeleting(false);
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
                        <div className="flex items-center justify-end gap-2">
                          <button
                            className="btn btn-sm btn-outline flex items-center gap-1"
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
                          {/* Hidden on your own row — the server refuses
                              self-deletion, so offering it would only
                              produce an error. */}
                          {String(currentUser?.id) !== String(u.id) && (
                            <button
                              className="btn btn-sm btn-danger flex items-center gap-1"
                              onClick={() => openDeleteModal(u)}
                              aria-label={`Delete ${u.first_name} ${u.last_name}`}
                            >
                              <Trash2 size={12} /> Delete
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {!loading && (
            <Pagination
              page={page}
              pageCount={Math.max(1, Math.ceil(totalUsers / pageSize))}
              totalCount={totalUsers}
              onPageChange={setPage}
              pageSize={pageSize}
              onPageSizeChange={(size) => { setPageSize(size); setPage(1); }}
              showPageSize
            />
          )}
        </div>
      </div>

      {/* Account activity — the same AuditTrail record as the Audit Trail page,
          filtered to User events. The full history lives on that page. */}
      <div className="card mt-6">
        <div className="card-header justify-between">
          <div>
            <h3><Activity size={18} className="inline mr-2 text-accent" /> {t('securityAuditLog')}</h3>
            <p className="card-subtitle">{t('accountActivitySubtitle')}</p>
          </div>
          <Link to="/audit-trail" className="btn btn-sm btn-outline flex items-center gap-1.5">
            {t('viewFullTrail')} <ArrowRight size={14} />
          </Link>
        </div>

        <div className="table-responsive mt-3">
          <table className="table table-sm">
            <thead>
              <tr>
                <th>{t('timestamp')}</th>
                <th>{t('operator')}</th>
                <th>{t('action')}</th>
                <th>{t('objectRepresentation')}</th>
              </tr>
            </thead>
            <tbody>
              {accountActivity.length === 0 ? (
                <tr>
                  <td colSpan="4" className="text-center py-4 text-muted">{t('noAccountActivity')}</td>
                </tr>
              ) : (
                accountActivity.map(log => (
                  <tr key={log.id}>
                    <td>{new Date(log.timestamp).toLocaleString()}</td>
                    <td><strong>{log.user_email || 'System'}</strong></td>
                    <td>
                      <span className={`badge ${log.action === 'CREATE' ? 'badge-success' : log.action === 'DELETE' ? 'badge-danger' : 'badge-outline'}`}>
                        {log.action}
                      </span>
                    </td>
                    <td><span className="font-mono text-xs">{log.object_repr}</span></td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add User Modal */}
      <Modal
        isOpen={showAddModal}
        onClose={closeAddModal}
        title={t('createStaffAccount')}
        size="lg"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={closeAddModal}>Cancel</button>
            {/* `form=` because Modal renders the footer as a sibling of its
                children, so the submit button sits outside the <form>. */}
            <button type="submit" form="add-user-form" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Creating…' : 'Create User'}
            </button>
          </>
        )}
      >
        <form id="add-user-form" onSubmit={handleAddUser} noValidate>
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
              idPrefix="add_dept"
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
        </form>
      </Modal>

      {/* Edit User / Reset Password Modal */}
      <Modal
        isOpen={Boolean(showEditModal && editingUser)}
        onClose={closeEditModal}
        title={editingUser ? t('editUserAccount', `${editingUser.first_name} ${editingUser.last_name}`) : 'Edit User Account'}
        size="lg"
        footer={(
          <>
            <button type="button" className="btn btn-outline" onClick={closeEditModal}>Cancel</button>
            <button type="submit" form="edit-user-form" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Saving…' : 'Save Changes'}
            </button>
          </>
        )}
      >
        {editingUser && (
          <>
            {/* Reset Password Form Section */}
            <div className="card bg-surface-variant p-4 mb-5 border border-primary/20">
              <h4 className="flex items-center gap-2 mb-2 text-primary">
                <Key size={16} /> Reset Password
              </h4>
              <p className="text-xs text-muted mb-3">
                Set a new password for this corporate user. At least 8 characters, with an
                uppercase letter, a lowercase letter, and a number.
              </p>
              {/* Its own form, and it stays in the body: it submits to a
                  different endpoint than Save Changes and must not be reachable
                  from the footer's submit button. */}
              <form onSubmit={handleResetPassword} noValidate>
                <div className="flex gap-2">
                  <label className="sr-only" htmlFor="reset_password">New password</label>
                  <input
                    id="reset_password"
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
            <form id="edit-user-form" onSubmit={handleEditUser} noValidate>
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
                  idPrefix="edit_dept"
                  label="Department / Unit"
                  value={editingUser.department || ''}
                  onChange={(id) => setEditingUserField('department', id)}
                  valueLabel={localizedName(lang, editingUser.department_name, editingUser.department_name_am)}
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
            </form>
          </>
        )}
      </Modal>

      {/* Delete User Confirmation. Three states: preflight in flight, safe to
          delete, or blocked with the reasons listed. */}
      <Modal
        isOpen={Boolean(deleteTarget)}
        onClose={deleting ? () => {} : closeDeleteModal}
        title={
          deleteBlockers?.length
            ? 'Cannot delete this account'
            : `Delete ${deleteTarget?.first_name || ''} ${deleteTarget?.last_name || ''}?`
        }
        size="md"
        footer={
          deleteBlockers === null ? (
            <button type="button" className="btn btn-outline" onClick={closeDeleteModal}>
              Cancel
            </button>
          ) : deleteBlockers.length > 0 ? (
            <>
              <button type="button" className="btn btn-outline" onClick={closeDeleteModal}>
                Cancel
              </button>
              {deleteTarget?.is_active && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleDeactivateInstead}
                  disabled={deleting}
                >
                  {deleting ? 'Deactivating…' : 'Deactivate instead'}
                </button>
              )}
            </>
          ) : (
            <>
              <button type="button" className="btn btn-outline" onClick={closeDeleteModal} disabled={deleting}>
                Cancel
              </button>
              <button type="button" className="btn btn-danger" onClick={handleDeleteUser} disabled={deleting}>
                {deleting ? 'Deleting…' : 'Delete user'}
              </button>
            </>
          )
        }
      >
        {deleteBlockers === null ? (
          <p className="text-muted">Checking this account…</p>
        ) : deleteBlockers.length > 0 ? (
          <>
            <div className="alert alert-red" role="alert">
              <span className="alert-icon">!</span>
              <span>
                Deleting this account would erase audit history that cannot be
                recovered.
              </span>
            </div>
            <ul className="list-disc pl-5 mt-4 space-y-1.5">
              {deleteBlockers.map((b) => (
                <li key={b.type}>{b.message}</li>
              ))}
            </ul>
            {deleteTarget?.is_active && (
              <p className="text-sm text-muted mt-4">
                Deactivating keeps all of it intact and can be undone later. The
                account can no longer sign in.
              </p>
            )}
          </>
        ) : (
          <>
            <div className="alert alert-red" role="alert">
              <span className="alert-icon">!</span>
              <span>This cannot be undone.</span>
            </div>
            <dl className="mt-4 space-y-1 text-sm">
              <div className="flex gap-2">
                <dt className="text-muted w-28">Name</dt>
                <dd className="font-medium">
                  {deleteTarget?.first_name} {deleteTarget?.last_name}
                </dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-muted w-28">Employee ID</dt>
                <dd className="font-mono">{deleteTarget?.employee_id || 'N/A'}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-muted w-28">Email</dt>
                <dd>{deleteTarget?.email}</dd>
              </div>
            </dl>
            <p className="text-sm text-muted mt-4">
              The account row is removed permanently. Allowing the same email or
              Employee ID to be re-registered later. The deletion is recorded in
              the audit trail.
            </p>
          </>
        )}
      </Modal>
    </div>
  );
}

export default UsersPage;
