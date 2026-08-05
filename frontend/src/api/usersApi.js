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
  getDepartments: async () => {
    const res = await apiClient.get('/auth/departments/');
    return res.data?.results ?? res.data;
  },
  getAuditTrail: async (params = {}) => {
    const res = await apiClient.get('/auth/audit-trail/', { params });
    return res.data;
  },
};

export default usersApi;
