import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import type {
  SentimentalAnalysisRequest,
  SentimentalAnalysisResponse,
  FundamentalAnalysisRequest,
  FundamentalAnalysisResponse,
  TechnicalAnalysisRequest,
  TechnicalAnalysisResponse,
  EnsembleBacktestRequest,
  EnsembleBacktestResponse,
  AnalysisHistory,
  AuthResponse,
  User,
} from '@/types';
import { getAuthStore } from '@/stores/authStore';

/**
 * API Client Configuration
 * Handles all HTTP requests to the backend
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Create axios instance
const apiClient: AxiosInstance = axios.create({
  baseURL: `${API_URL}/api`,
  timeout: 120000, // 120 seconds timeout for LLM-driven analysis
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Request Interceptor
 * Adds JWT token to all requests
 */
apiClient.interceptors.request.use(
  (config) => {
    const token = getAuthStore().token;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

/**
 * Response Interceptor
 * Handles common error responses
 */
type ApiErrorResponse = {
  detail?: string | Array<{ msg?: string; loc?: Array<string | number> }> | unknown;
  message?: string;
};

apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  (error: AxiosError<ApiErrorResponse>) => {
    if (error.response) {
      const status = error.response.status;
      
      // Handle 401 Unauthorized
      if (status === 401) {
        const authStore = getAuthStore();
        authStore.logout();
        window.location.href = '/login';
      }
      
      // Handle 429 Rate Limit
      if (status === 429) {
        return Promise.reject({
          message: 'Too many requests. Please try again later.',
          code: 'RATE_LIMIT_EXCEEDED',
        });
      }
      
      // Handle 500 Server Error
      if (status >= 500) {
        return Promise.reject({
          message: 'Server error. Please try again later.',
          code: 'SERVER_ERROR',
        });
      }
    }
    
    // Handle network errors
    if (error.code === 'ECONNABORTED') {
      return Promise.reject({
        message: 'Request timeout. Please try again.',
        code: 'TIMEOUT',
      });
    }
    
    if (error.code === 'ERR_NETWORK') {
      return Promise.reject({
        message: 'Network error. Please check your connection.',
        code: 'NETWORK_ERROR',
      });
    }
    
    return Promise.reject(error);
  }
);

/**
 * API Error Handler
 * Converts API errors to user-friendly messages
 */
export const handleApiError = (error: unknown): string => {
  if (axios.isAxiosError<ApiErrorResponse>(error)) {
    const data = error.response?.data;
    if (data?.detail) {
      if (typeof data.detail === 'string') {
        return data.detail;
      }

      if (Array.isArray(data.detail)) {
        return data.detail
          .map((item) => {
            if (item && typeof item === 'object' && 'msg' in item) {
              const location = 'loc' in item && Array.isArray(item.loc) ? ` (${item.loc.join('.')})` : '';
              return `${String(item.msg)}${location}`;
            }
            return JSON.stringify(item);
          })
          .join(' ');
      }

      return 'The request was rejected by the API. Please check the inputs and try again.';
    }
    if (data?.message) {
      return data.message;
    }
    if (error.message) {
      return error.message;
    }
  }

  if (error instanceof Error) {
    return error.message;
  }

  return 'An unexpected error occurred. Please try again.';
};

/**
 * Sentiment Analysis API
 */
export const sentimentApi = {
  /**
   * Analyze sentiment for a ticker
   */
  analyze: async (
    request: SentimentalAnalysisRequest,
    config?: InternalAxiosRequestConfig
  ): Promise<SentimentalAnalysisResponse> => {
    const response = await apiClient.post<SentimentalAnalysisResponse>(
      '/analyze/sentimental',
      request,
      config
    );
    return response.data;
  },
  
  /**
   * Get analysis history
   */
  getHistory: async (config?: InternalAxiosRequestConfig): Promise<AnalysisHistory[]> => {
    const response = await apiClient.get<AnalysisHistory[]>('/user/history', config);
    return response.data;
  },
  
  /**
   * Delete analysis from history
   */
  deleteHistoryItem: async (
    id: string,
    config?: InternalAxiosRequestConfig
  ): Promise<void> => {
    await apiClient.delete(`/user/history/${id}`, config);
  },
};

export const technicalApi = {
  analyze: async (
    request: TechnicalAnalysisRequest,
    config?: InternalAxiosRequestConfig
  ): Promise<TechnicalAnalysisResponse> => {
    const response = await apiClient.post<TechnicalAnalysisResponse>(
      '/analyze/technical',
      request,
      config
    );
    return response.data;
  },
};

export const fundamentalApi = {
  analyze: async (
    request: FundamentalAnalysisRequest,
    config?: InternalAxiosRequestConfig
  ): Promise<FundamentalAnalysisResponse> => {
    const response = await apiClient.post<FundamentalAnalysisResponse>(
      '/analyze/fundamental',
      request,
      config
    );
    return response.data;
  },
};

export const ensembleApi = {
  backtest: async (
    request: EnsembleBacktestRequest,
    config?: InternalAxiosRequestConfig
  ): Promise<EnsembleBacktestResponse> => {
    const response = await apiClient.post<EnsembleBacktestResponse>(
      '/analyze/ensemble/backtest',
      request,
      config
    );
    return response.data;
  },
};

/**
 * Authentication API
 */
export const authApi = {
  /**
   * Login user
   */
  login: async (
    email: string,
    password: string,
    config?: InternalAxiosRequestConfig
  ): Promise<AuthResponse> => {
    const response = await apiClient.post<AuthResponse>(
      '/auth/login',
      { email, password },
      config
    );
    return response.data;
  },
  
  /**
   * Register user
   */
  register: async (
    email: string,
    password: string,
    full_name?: string,
    config?: InternalAxiosRequestConfig
  ): Promise<AuthResponse> => {
    const response = await apiClient.post<AuthResponse>(
      '/auth/register',
      { email, password, full_name },
      config
    );
    return response.data;
  },
  
  /**
   * Logout user
   */
  logout: async (config?: InternalAxiosRequestConfig): Promise<void> => {
    await apiClient.post('/auth/logout', {}, config);
  },
  
  /**
   * Get user profile
   */
  getProfile: async (config?: InternalAxiosRequestConfig): Promise<User> => {
    const response = await apiClient.get<User>('/user/profile', config);
    return response.data;
  },
  
  /**
   * Update user profile
   */
  updateProfile: async (
    data: { full_name?: string; email?: string },
    config?: InternalAxiosRequestConfig
  ): Promise<User> => {
    const response = await apiClient.put<User>('/user/profile', data, config);
    return response.data;
  },
  
  /**
   * Change password
   */
  changePassword: async (
    current_password: string,
    new_password: string,
    config?: InternalAxiosRequestConfig
  ): Promise<void> => {
    await apiClient.put(
      '/user/change-password',
      { current_password, new_password },
      config
    );
  },
};

/**
 * Health Check API
 */
export const healthApi = {
  /**
   * Check API health
   */
  check: async (config?: InternalAxiosRequestConfig): Promise<{ status: string }> => {
    const response = await apiClient.get<{ status: string }>('/health', config);
    return response.data;
  },
};

export default apiClient;

export const marketApi = {
  overview: async (): Promise<{
    indexes: Array<{ label: string; value: string; change: string; positive: boolean }>;
    prices: Record<string, { price: number; change: number; changePercent: number }>;
    gainers: Array<{ ticker: string; name: string; price: string; change: string; positive: boolean }>;
    losers: Array<{ ticker: string; name: string; price: string; change: string; positive: boolean }>;
    news: Array<{ headline: string; url: string; source: string; time: string }>;
  }> => {
    const response = await apiClient.get('/market/overview');
    return response.data;
  },
};
