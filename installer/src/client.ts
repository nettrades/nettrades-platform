import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';

export interface ApiResponse<T = any> {
  status: 'success' | 'error';
  data?: T;
  message?: string;
}

class ApiClient {
  private client: AxiosInstance;
  private baseUrl: string;

  constructor(baseUrl: string = 'http://localhost:8080') {
    this.baseUrl = baseUrl;
    this.client = axios.create({
      baseURL: this.baseUrl,
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 30000,
    });

    // Add auth token interceptor
    this.client.interceptors.request.use((config) => {
      const token = localStorage.getItem('auth_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });
  }

  // ===== Authentication =====
  async login(username: string, password: string): Promise<ApiResponse> {
    const response = await this.client.post('/api/v1/auth/login', { username, password });
    return response.data;
  }

  async validateSession(): Promise<ApiResponse> {
    const token = localStorage.getItem('auth_token');
    if (!token) throw new Error('No token');
    const response = await this.client.get('/api/v1/auth/validate', {
      params: { token }
    });
    return response.data;
  }

  // ===== CRUD Operations =====
  async search(model: string, domain: any[] = [], fields?: string[], limit?: number, offset?: number): Promise<ApiResponse> {
    const params: any = { domain: JSON.stringify(domain) };
    if (fields) params.fields = fields.join(',');
    if (limit) params.limit = limit;
    if (offset) params.offset = offset;
    const response = await this.client.get(`/api/v1/db/${model}`, { params });
    return response.data;
  }

  async create(model: string, data: Record<string, any>): Promise<ApiResponse> {
    const response = await this.client.post(`/api/v1/db/${model}`, data);
    return response.data;
  }

  async read(model: string, id: string, fields?: string[]): Promise<ApiResponse> {
    const params: any = {};
    if (fields) params.fields = fields.join(',');
    const response = await this.client.get(`/api/v1/db/${model}/${id}`, { params });
    return response.data;
  }

  async update(model: string, id: string, data: Record<string, any>): Promise<ApiResponse> {
    const response = await this.client.put(`/api/v1/db/${model}/${id}`, data);
    return response.data;
  }

  async delete(model: string, id: string): Promise<ApiResponse> {
    const response = await this.client.delete(`/api/v1/db/${model}/${id}`);
    return response.data;
  }

  // ===== AI-Specific Endpoints =====
  async createJob(jobData: Record<string, any>): Promise<ApiResponse> {
    const response = await this.client.post('/api/v1/jobs', jobData);
    return response.data;
  }

  async updateJobStatus(jobId: string, status: string, result?: Record<string, any>): Promise<ApiResponse> {
    const response = await this.client.put(`/api/v1/jobs/${jobId}`, { status, result });
    return response.data;
  }

  async getGpuNodes(filters?: Record<string, any>): Promise<ApiResponse> {
    const params: any = {};
    if (filters) params.filters = JSON.stringify(filters);
    const response = await this.client.get('/api/v1/gpu/nodes', { params });
    return response.data;
  }

  async registerGpuNode(nodeData: Record<string, any>): Promise<ApiResponse> {
    const response = await this.client.post('/api/v1/gpu/nodes', nodeData);
    return response.data;
  }

  async sendHeartbeat(nodeId: string, status: Record<string, any>): Promise<ApiResponse> {
    const response = await this.client.post(`/api/v1/gpu/nodes/${nodeId}/heartbeat`, status);
    return response.data;
  }

  async getUsers(companyId?: string): Promise<ApiResponse> {
    const params: any = {};
    if (companyId) params.company_id = companyId;
    const response = await this.client.get('/api/v1/users', { params });
    return response.data;
  }

  // ===== Health =====
  async health(): Promise<ApiResponse> {
    const response = await this.client.get('/api/v1/health');
    return response.data;
  }
}

export const api = new ApiClient(process.env.REACT_APP_PROXY_URL || 'http://localhost:8080');