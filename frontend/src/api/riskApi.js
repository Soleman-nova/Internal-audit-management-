import apiClient from './apiClient';

export const riskApi = {
  getParameters: async () => {
    const res = await apiClient.get('/risk/parameters/');
    return res.data?.results ?? res.data;
  },
  getAssessments: async (params = {}) => {
    const res = await apiClient.get('/risk/assessments/', { params });
    return res.data?.results ?? res.data;
  },
  getHeatmap: async () => {
    const res = await apiClient.get('/risk/assessments/heatmap/');
    return res.data;
  },
  getSummary: async () => {
    const res = await apiClient.get('/risk/assessments/summary/');
    return res.data;
  },
  createAssessment: async (data) => {
    const res = await apiClient.post('/risk/assessments/', data);
    return res.data;
  },
  updateAssessment: async (id, data) => {
    const res = await apiClient.patch(`/risk/assessments/${id}/`, data);
    return res.data;
  },
  getSelfAssessments: async (params = {}) => {
    const res = await apiClient.get('/risk/self-assessments/', { params });
    return res.data?.results ?? res.data;
  },
  createSelfAssessment: async (data) => {
    const res = await apiClient.post('/risk/self-assessments/', data);
    return res.data;
  },
  updateSelfAssessment: async (id, data) => {
    const res = await apiClient.patch(`/risk/self-assessments/${id}/`, data);
    return res.data;
  },
};

export default riskApi;
