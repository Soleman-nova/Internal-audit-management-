import apiClient from './apiClient';

export const reportsApi = {
  getTemplates: async () => {
    const res = await apiClient.get('/reports/templates/');
    return res.data?.results ?? res.data;
  },
  getGeneratedReports: async () => {
    const res = await apiClient.get('/reports/generated/');
    return res.data?.results ?? res.data;
  },
  generateReport: async (data) => {
    const res = await apiClient.post('/reports/generated/', data);
    return res.data;
  },
  getAnalytics: async () => {
    const res = await apiClient.get('/reports/generated/analytics/');
    return res.data;
  },
};

export default reportsApi;
