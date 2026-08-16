import apiClient from './apiClient';

export const usersApi = {
  getUsers: async (params = {}) => {
    const res = await apiClient.get('/auth/users/', { params });
    return res.data?.results ?? res.data;
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
    const res = await apiClient.post(`/auth/users/${id}/reset-password/`, {
      new_password: newPassword,
    });
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
};

export default usersApi;
