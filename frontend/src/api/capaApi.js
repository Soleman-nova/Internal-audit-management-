import apiClient from './apiClient';

export const capaApi = {
  getActions: async (params = {}) => {
    const res = await apiClient.get('/corrective/actions/', { params });
    return res.data?.results ?? res.data;
  },
  createAction: async (data) => {
    const res = await apiClient.post('/corrective/actions/', data);
    return res.data;
  },
  updateAction: async (id, data) => {
    const res = await apiClient.patch(`/corrective/actions/${id}/`, data);
    return res.data;
  },
  addResponse: async (actionId, formData) => {
    const res = await apiClient.post(`/corrective/actions/${actionId}/add-response/`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },
};

export default capaApi;
