import apiClient from './apiClient';

export const executionApi = {
  getPrograms: async (params = {}) => {
    const res = await apiClient.get('/execution/programs/', { params });
    return res.data?.results ?? res.data;
  },
  createProgram: async (data) => {
    const res = await apiClient.post('/execution/programs/', data);
    return res.data;
  },
  getProcedures: async (params = {}) => {
    const res = await apiClient.get('/execution/procedures/', { params });
    return res.data?.results ?? res.data;
  },
  createProcedure: async (data) => {
    const res = await apiClient.post('/execution/procedures/', data);
    return res.data;
  },
  getWorkingPapers: async (params = {}) => {
    const res = await apiClient.get('/execution/working-papers/', { params });
    return res.data?.results ?? res.data;
  },
  uploadWorkingPaper: async (formData) => {
    const res = await apiClient.post('/execution/working-papers/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },
  deleteWorkingPaper: async (wpId) => {
    const res = await apiClient.delete(`/execution/working-papers/${wpId}/`);
    return res.data;
  },
  reviewWorkingPaper: async (wpId, reviewData) => {
    const res = await apiClient.post(`/execution/working-papers/${wpId}/review/`, reviewData);
    return res.data;
  },
  // Fetch through apiClient so the JWT is attached, then hand the blob to the
  // browser as a download. A plain window.open would omit the auth header.
  downloadWorkingPaper: async (wpId, filename) => {
    const res = await apiClient.get(`/execution/working-papers/${wpId}/download/`, {
      responseType: 'blob',
    });
    // Prefer the server-provided filename from Content-Disposition.
    const disposition = res.headers['content-disposition'] || '';
    const match = disposition.match(/filename="?([^"]+)"?/);
    const name = match ? match[1] : (filename || `working-paper-${wpId}`);

    const url = window.URL.createObjectURL(new Blob([res.data]));
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
  submitForReview: async (programId) => {
    const res = await apiClient.post(`/execution/programs/${programId}/submit-for-review/`);
    return res.data;
  },
  approveFieldwork: async (programId) => {
    const res = await apiClient.post(`/execution/programs/${programId}/approve-fieldwork/`);
    return res.data;
  },
};

export default executionApi;