import apiClient from './apiClient';

export const reportsApi = {
  getTemplates: async () => {
    const res = await apiClient.get('/reports/templates/');
    return res.data?.results ?? res.data;
  },
  getGeneratedReports: async (params = {}) => {
    const res = await apiClient.get('/reports/generated/', { params });
    return res.data?.results ?? res.data;
  },
  getReport: async (id) => {
    const res = await apiClient.get(`/reports/generated/${id}/`);
    return res.data;
  },
  generateReport: async (data) => {
    const res = await apiClient.post('/reports/generated/', data);
    return res.data;
  },
  getAnalytics: async () => {
    const res = await apiClient.get('/reports/generated/analytics/');
    return res.data;
  },
  // Same authenticated-blob pattern as executionApi.downloadWorkingPaper:
  // fetch through apiClient so the JWT is attached, then hand the bytes to the
  // browser. A window.open on the export URL sends no Authorization header and
  // 401s, and hardcoding the host breaks every non-local deployment.
  downloadReport: async (id, filename) => {
    const res = await apiClient.get(`/reports/generated/${id}/export/`, {
      responseType: 'blob',
    });
    const disposition = res.headers['content-disposition'] || '';
    const match = disposition.match(/filename="?([^"]+)"?/);
    const name = match ? match[1] : (filename || `report-${id}`);

    const url = window.URL.createObjectURL(new Blob([res.data]));
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};

export default reportsApi;
