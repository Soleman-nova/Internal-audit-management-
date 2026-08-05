import apiClient from './apiClient';

export const findingsApi = {
  getFindings: async (params = {}) => {
    const res = await apiClient.get('/findings/findings/', { params });
    return res.data?.results ?? res.data;
  },
  createFinding: async (data) => {
    const res = await apiClient.post('/findings/findings/', data);
    return res.data;
  },
  updateFinding: async (id, data) => {
    const res = await apiClient.patch(`/findings/findings/${id}/`, data);
    return res.data;
  },
  submitFinding: async (id) => {
    const res = await apiClient.post(`/findings/findings/${id}/submit/`);
    return res.data;
  },
  reviewFinding: async (id, action, feedback = '') => {
    const res = await apiClient.post(`/findings/findings/${id}/review/`, {
      action,
      reviewer_feedback: feedback,
    });
    return res.data;
  },
};

export default findingsApi;
