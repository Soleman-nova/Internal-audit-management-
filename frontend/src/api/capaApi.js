import apiClient from './apiClient';

export const capaApi = {
  getActions: async (params = {}) => {
    const res = await apiClient.get('/corrective/actions/', { params });
    return res.data?.results ?? res.data;
  },
  // Single-record fetch — the detail page must not filter the paginated list.
  getAction: async (id) => {
    const res = await apiClient.get(`/corrective/actions/${id}/`);
    return res.data;
  },
  createAction: async (data) => {
    const res = await apiClient.post('/corrective/actions/', data);
    return res.data;
  },
  updateAction: async (id, data) => {
    const res = await apiClient.patch(`/corrective/actions/${id}/`, data);
    return res.data;
  },
  deleteAction: async (id) => {
    const res = await apiClient.delete(`/corrective/actions/${id}/`);
    return res.data;
  },
  addResponse: async (actionId, formData) => {
    const res = await apiClient.post(`/corrective/actions/${actionId}/add-response/`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },
  // Supervisor/manager verification visit. Records scheduled_date, notes and
  // outcome against the action and notifies its owner.
  scheduleFollowup: async (actionId, data) => {
    const res = await apiClient.post(`/corrective/actions/${actionId}/schedule-followup/`, data);
    return res.data;
  },
  // Derived from due_date server-side, so it is correct even before the
  // flag_overdue_actions command has stamped status='overdue'.
  getOverdue: async (params = {}) => {
    const res = await apiClient.get('/corrective/actions/overdue/', { params });
    return res.data?.results ?? res.data;
  },
  getSummary: async () => {
    const res = await apiClient.get('/corrective/actions/summary/');
    return res.data;
  },
};

export default capaApi;
