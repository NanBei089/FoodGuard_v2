import axios from 'axios';

/** 统一的前端 API 客户端，负责鉴权注入和 token 刷新。 */
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api/v1',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      // 在这里统一注入 Bearer token，避免每个请求点重复处理鉴权头。
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

apiClient.interceptors.response.use(
  (response) => {
    return response.data;
  },
  async (error) => {
    const originalRequest = error.config;
    
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      const refreshToken = localStorage.getItem('refresh_token');
      
      if (refreshToken) {
        try {
          const res = await axios.post(`${import.meta.env.VITE_API_URL || '/api/v1'}/auth/refresh`, {
            refresh_token: refreshToken
          });
          
          if (res.data.code === 0) {
            localStorage.setItem('access_token', res.data.data.access_token);
            localStorage.setItem('refresh_token', res.data.data.refresh_token);
            apiClient.defaults.headers.common['Authorization'] = `Bearer ${res.data.data.access_token}`;
            // 刷新成功后重放原请求，最大限度减少用户感知到的登录态中断。
            return apiClient(originalRequest);
          }
        } catch (refreshError) {
          // refresh 失败说明当前登录态已经不可恢复，直接清空本地凭证并回到登录页。
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          window.location.href = '/login';
          return Promise.reject(refreshError);
        }
      } else {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/login';
      }
    }
    
    return Promise.reject(error);
  }
);
