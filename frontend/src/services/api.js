import axios from "axios";

import { authService } from "./authService";

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE });

api.interceptors.request.use(async (config) => {
  const token = await authService.getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const payload = error.response?.data?.error;
    if (error.response?.status === 401) {
      authService.logout();
    }
    return Promise.reject(payload ? { ...payload, status: error.response.status } : error);
  }
);

export const endpoints = {
  exchangeToken: () => api.post("/v1/auth/token/exchange"),

  listKeys: () => api.get("/v1/keys"),
  createKey: (data) => api.post("/v1/keys", data),
  revokeKey: (id) => api.delete(`/v1/keys/${id}`),

  listOrganizations: () => api.get("/v1/organizations"),
  createOrganization: (data) => api.post("/v1/organizations", data),
  updateOrganization: (id, data) => api.patch(`/v1/organizations/${id}`, data),

  listProjects: (organizationId) => api.get("/v1/projects", { params: { organization_id: organizationId } }),
  createProject: (data) => api.post("/v1/projects", data),
  updateProject: (id, data) => api.patch(`/v1/projects/${id}`, data),

  listUsers: (organizationId) => api.get("/v1/users", { params: { organization_id: organizationId } }),
  createUser: (data) => api.post("/v1/users", data),
  updateUser: (id, data) => api.patch(`/v1/users/${id}`, data),

  listProjectUsers: (projectId, userId) =>
    api.get("/v1/project-users", { params: { project_id: projectId, user_id: userId } }),
  addProjectUser: (data) => api.post("/v1/project-users", data),
  updateProjectUser: (id, data) => api.patch(`/v1/project-users/${id}`, data),

  listProviderConfigs: () => api.get("/v1/provider-configs"),
  createProviderConfig: (data) => api.post("/v1/provider-configs", data),
  updateProviderConfig: (id, data) => api.patch(`/v1/provider-configs/${id}`, data),

  listModelPricing: () => api.get("/v1/model-pricing"),
  createModelPricing: (data) => api.post("/v1/model-pricing", data),
  updateModelPricing: (id, data) => api.patch(`/v1/model-pricing/${id}`, data),
  deleteModelPricing: (id) => api.delete(`/v1/model-pricing/${id}`),

  getUsageSummary: (params) => api.get("/v1/usage/summary", { params }),

  listLogs: (params) => api.get("/v1/logs", { params }),

  listRoutingRules: () => api.get("/v1/routing-rules"),
  createRoutingRule: (data) => api.post("/v1/routing-rules", data),
  updateRoutingRule: (id, data) => api.patch(`/v1/routing-rules/${id}`, data),

  listBudgets: (params) => api.get("/v1/budgets", { params }),
  createBudget: (data) => api.post("/v1/budgets", data),
  updateBudget: (id, data) => api.patch(`/v1/budgets/${id}`, data),
  deleteBudget: (id) => api.delete(`/v1/budgets/${id}`),

  getHealth: () => api.get("/health"),
  getReadiness: () => api.get("/ready"),

  listMcpServers: () => api.get("/mcp/servers"),
  createMcpServer: (data) => api.post("/mcp/servers", data),
  updateMcpServer: (id, data) => api.put(`/mcp/servers/${id}`, data),
  deleteMcpServer: (id) => api.delete(`/mcp/servers/${id}`),
  healthCheckMcpServer: (id) => api.post(`/mcp/servers/${id}/health-check`),
  getMcpServerStats: (id, windowMinutes) =>
    api.get(`/mcp/servers/${id}/stats`, { params: { window_minutes: windowMinutes || undefined } }),

  listMcpTools: (q, includeUnavailable) =>
    api.get("/mcp/tools", { params: { q: q || undefined, include_unavailable: includeUnavailable || undefined } }),
  syncMcpTools: () => api.post("/mcp/tools/sync"),

  listApiServices: () => api.get("/mcp/api-services"),
  createApiService: (data) => api.post("/mcp/api-services", data),
  updateApiService: (id, data) => api.put(`/mcp/api-services/${id}`, data),
  deleteApiService: (id) => api.delete(`/mcp/api-services/${id}`),
  listApiEndpoints: (serviceId) => api.get(`/mcp/api-services/${serviceId}/endpoints`),
  createApiEndpoint: (serviceId, data) => api.post(`/mcp/api-services/${serviceId}/endpoints`, data),
  updateApiEndpoint: (serviceId, endpointId, data) =>
    api.put(`/mcp/api-services/${serviceId}/endpoints/${endpointId}`, data),
  deleteApiEndpoint: (serviceId, endpointId) => api.delete(`/mcp/api-services/${serviceId}/endpoints/${endpointId}`),

  listMcpSessions: () => api.get("/mcp/sessions"),
  getMcpSession: (clientSessionId) => api.get(`/mcp/sessions/${clientSessionId}`),

  callMcp: (body, sessionId) =>
    api.post("/mcp", body, sessionId ? { headers: { "Mcp-Session-Id": sessionId } } : undefined),

  getSecretProviders: () => api.get("/admin/secrets/providers"),
  getSecretStatus: () => api.get("/admin/secrets/status"),
  setSecret: (data) => api.post("/admin/secrets", data),
  rotateSecret: (data) => api.post("/admin/secrets/rotate", data),
  getSecretAuditLog: (params) => api.get("/admin/secrets/audit-log", { params }),

  getIdentityProviders: () => api.get("/admin/identity/providers"),

  listTenantIdentityConfigs: () => api.get("/admin/identity/tenant-configs"),
  createTenantIdentityConfig: (data) => api.post("/admin/identity/tenant-configs", data),
  updateTenantIdentityConfig: (id, data) => api.put(`/admin/identity/tenant-configs/${id}`, data),
  deleteTenantIdentityConfig: (id) => api.delete(`/admin/identity/tenant-configs/${id}`),

  listAccessPolicies: () => api.get("/admin/identity/access-policies"),
  createAccessPolicy: (data) => api.post("/admin/identity/access-policies", data),
  updateAccessPolicy: (id, data) => api.patch(`/admin/identity/access-policies/${id}`, data),
  deleteAccessPolicy: (id) => api.delete(`/admin/identity/access-policies/${id}`),

  listAgents: () => api.get("/v1/agents"),
  createAgent: (data) => api.post("/v1/agents", data),
  updateAgent: (id, data) => api.patch(`/v1/agents/${id}`, data),
  getAgentCard: (id) => api.get(`/v1/agents/${id}/agent-card`),
  submitAgentForApproval: (id) => api.post(`/v1/agents/${id}/submit`),
  listAgentApprovals: (id) => api.get(`/v1/agents/${id}/approvals`),
  publishAgent: (id) => api.post(`/v1/agents/${id}/publish`),
  suspendAgent: (id) => api.post(`/v1/agents/${id}/suspend`),
  reactivateAgent: (id) => api.post(`/v1/agents/${id}/reactivate`),
  deprecateAgent: (id) => api.post(`/v1/agents/${id}/deprecate`),
  retireAgent: (id) => api.post(`/v1/agents/${id}/retire`),

  listPendingAgentApprovals: () => api.get("/v1/agent-approvals"),
  approveAgentTask: (taskId, data) => api.post(`/v1/agent-approvals/${taskId}/approve`, data),
  rejectAgentTask: (taskId, data) => api.post(`/v1/agent-approvals/${taskId}/reject`, data),

  invokeAgent: (data) => api.post("/v1/agent-invocations", data),
  listAgentInvocations: () => api.get("/v1/agent-invocations"),
};

export default api;
