import apiClient from './apiClient';

export const planningApi = {
  getUniverse: async (params = {}) => {
    const res = await apiClient.get('/planning/universe/', { params });
    return res.data?.results ?? res.data;
  },
  createUniverse: async (data) => {
    const res = await apiClient.post('/planning/universe/', data);
    return res.data;
  },
  updateUniverse: async (id, data) => {
    const res = await apiClient.patch(`/planning/universe/${id}/`, data);
    return res.data;
  },
  getDueForReAudit: async (params = {}) => {
    const res = await apiClient.get('/planning/universe/due-for-re-audit/', { params });
    return res.data?.results ?? res.data;
  },
  getPlans: async (params = {}) => {
    const res = await apiClient.get('/planning/plans/', { params });
    return res.data?.results ?? res.data;
  },
  createPlan: async (data) => {
    const res = await apiClient.post('/planning/plans/', data);
    return res.data;
  },
  updatePlan: async (id, data) => {
    const res = await apiClient.patch(`/planning/plans/${id}/`, data);
    return res.data;
  },
  submitPlan: async (id) => {
    const res = await apiClient.post(`/planning/plans/${id}/submit/`);
    return res.data;
  },
  approvePlan: async (id) => {
    const res = await apiClient.post(`/planning/plans/${id}/approve/`);
    return res.data;
  },
  getEngagements: async (params = {}) => {
    const res = await apiClient.get('/planning/engagements/', { params });
    return res.data?.results ?? res.data;
  },
  getEngagement: async (id) => {
    const res = await apiClient.get(`/planning/engagements/${id}/`);
    return res.data;
  },
  createEngagement: async (data) => {
    const res = await apiClient.post('/planning/engagements/', data);
    return res.data;
  },
  updateEngagement: async (id, data) => {
    const res = await apiClient.patch(`/planning/engagements/${id}/`, data);
    return res.data;
  },
  updateEngagementStatus: async (id, status) => {
    const res = await apiClient.post(`/planning/engagements/${id}/update-status/`, { status });
    return res.data;
  },
  addTeamMember: async (id, memberData) => {
    const res = await apiClient.post(`/planning/engagements/${id}/add-member/`, memberData);
    return res.data;
  },
};

export default planningApi;