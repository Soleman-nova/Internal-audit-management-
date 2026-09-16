import apiClient from './apiClient';

export const usersApi = {
  // Returns the DRF page envelope ({ count, next, previous, results }) so
  // callers can paginate. Pickers that need every option at once want
  // getAllUsers instead — this endpoint pages at 20 by default and dropping
  // the envelope would silently hide the rest of the roster.
  getUsers: async (params = {}) => {
    const res = await apiClient.get('/auth/users/', { params });
    return res.data;
  },
  // Every user, as a flat array, for the lead-auditor / supervisor / auditee
  // dropdowns. Walks `next` until the API stops handing out pages rather than
  // assuming one oversized page covers the whole roster.
  getAllUsers: async (params = {}) => {
    const all = [];
    // Bounded so a malformed `next` can't spin forever.
    for (let guard = 0; guard < 50; guard += 1) {
      const res = await apiClient.get('/auth/users/', {
        params: { ...params, page: guard + 1, page_size: 1000 },
      });
      const body = res.data;
      // Tolerate the endpoint ever being served unpaginated.
      if (!body || !Array.isArray(body.results)) {
        return Array.isArray(body) ? body : all;
      }
      all.push(...body.results);
      if (!body.next) break;
    }
    return all;
  },
  createUser: async (data) => {
    const res = await apiClient.post('/auth/users/', data);
    return res.data;
  },
  updateUser: async (id, data) => {
    const res = await apiClient.patch(`/auth/users/${id}/`, data);
    return res.data;
  },
  resetPassword: async (id, newPassword) => {
    // The backend action reads request.data['password'] — sending any other key
    // makes every reset fail with "Password is required."
    const res = await apiClient.post(`/auth/users/${id}/reset-password/`, {
      password: newPassword,
    });
    return res.data;
  },
  deactivateUser: async (id) => {
    const res = await apiClient.post(`/auth/users/${id}/deactivate/`);
    return res.data;
  },
  deleteUser: async (id) => {
    const res = await apiClient.delete(`/auth/users/${id}/`);
    return res.data;
  },
  // Preflight for the delete button. Returns
  // { can_delete, blockers: [{ type, count, message }] } so the confirmation
  // dialog can say what would be destroyed by the CASCADE before the admin
  // commits. POST because the endpoint is admin-only and the viewset opens
  // safe methods to any authenticated user.
  checkUserDeletion: async (id) => {
    const res = await apiClient.post(`/auth/users/${id}/deletion-check/`);
    return res.data;
  },
  getDepartments: async (params = {}) => {
    const res = await apiClient.get('/auth/departments/', { params });
    return res.data?.results ?? res.data;
  },
  // Compact, unpaginated org tree for the cascading department picker. The full
  // department list is paginated and 600+ rows deep once service centers exist,
  // so the picker needs this instead.
  getDepartmentTree: async () => {
    const res = await apiClient.get('/auth/departments/tree/');
    return res.data?.results ?? res.data;
  },
  getAuditTrail: async (params = {}) => {
    const res = await apiClient.get('/auth/audit-trail/', { params });
    return res.data;
  },
  // Dashboard KPI cards and chart series. Pass { directorate: <department id> }
  // to scope every number to one audit directorate; omit it for EEU-wide totals.
  getDashboardStats: async (params = {}) => {
    const res = await apiClient.get('/auth/dashboard/stats/', { params });
    return res.data;
  },
};

export default usersApi;
