import axios from 'axios';

const API_BASE_URL = localStorage.getItem('apiBaseUrl') || 'http://localhost:8000/api';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to attach JWT token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('accessToken');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor to handle token expiry / logout
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      const refreshToken = localStorage.getItem('refreshToken');
      if (refreshToken) {
        try {
          const res = await axios.post(`${API_BASE_URL}/auth/token/refresh/`, {
            refresh: refreshToken,
          });
          const newToken = res.data.access;
          localStorage.setItem('accessToken', newToken);
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          return apiClient(originalRequest);
        } catch (refreshError) {
          // Refresh token expired or invalid
          localStorage.clear();
          window.location.href = '/login';
        }
      } else {
        localStorage.clear();
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export const authApi = {
  login: async (employeeId, password) => {
    const response = await apiClient.post('/auth/login/', { employee_id: employeeId, password });
    if (response.data.access) {
      localStorage.setItem('accessToken', response.data.access);
      localStorage.setItem('refreshToken', response.data.refresh);
      localStorage.setItem('user', JSON.stringify(response.data.user || { employee_id: employeeId, role: 'auditor' }));
    }
    return response.data;
  },
  logout: () => {
    localStorage.clear();
    window.location.href = '/login';
  },
  getCurrentUser: () => {
    const userStr = localStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
  },
  changePassword: async (currentPassword, newPassword) => {
    const response = await apiClient.post('/auth/change-password/', {
      current_password: currentPassword,
      new_password: newPassword,
    });
    return response.data;
  },
  updateProfile: async (profileData) => {
    const response = await apiClient.patch('/auth/profile/', profileData);
    // Update local stored user data
    const current = localStorage.getItem('user');
    if (current) {
      const updated = { ...JSON.parse(current), ...response.data };
      localStorage.setItem('user', JSON.stringify(updated));
    }
    return response.data;
  },
};

export const notificationApi = {
  // List the current user's notifications (newest first, per the backend ordering).
  list: async (params = {}) => {
    const response = await apiClient.get('/notifications/', { params });
    // Support both paginated ({ results: [...] }) and plain-array responses.
    return response.data?.results ?? response.data;
  },
  markRead: async (id) => {
    const response = await apiClient.post(`/notifications/${id}/mark-read/`);
    return response.data;
  },
  markAllRead: async () => {
    const response = await apiClient.post('/notifications/mark-all-read/');
    return response.data;
  },
  unreadCount: async () => {
    const response = await apiClient.get('/notifications/unread-count/');
    return response.data?.unread ?? 0;
  },
};

export default apiClient;
