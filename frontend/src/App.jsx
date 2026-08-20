import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { useAuth } from "./hooks/useAuth";
import { AgentApprovals } from "./pages/AgentApprovals";
import { Agents } from "./pages/Agents";
import { ApiKeys } from "./pages/ApiKeys";
import { ApiServices } from "./pages/ApiServices";
import { Budgets } from "./pages/Budgets";
import { Dashboard } from "./pages/Dashboard";
import { IdentitySettings } from "./pages/IdentitySettings";
import { Login } from "./pages/Login";
import { McpPlayground } from "./pages/McpPlayground";
import { McpServerHealth } from "./pages/McpServerHealth";
import { McpServers } from "./pages/McpServers";
import { McpSessions } from "./pages/McpSessions";
import { McpTools } from "./pages/McpTools";
import { ModelPricing } from "./pages/ModelPricing";
import { NotFound } from "./pages/NotFound";
import { Organizations } from "./pages/Organizations";
import { Projects } from "./pages/Projects";
import { ProviderConfigs } from "./pages/ProviderConfigs";
import { RequestLogs } from "./pages/RequestLogs";
import { RoutingRules } from "./pages/RoutingRules";
import { SecretSettings } from "./pages/SecretSettings";
import { UsageCost } from "./pages/UsageCost";
import { Users } from "./pages/Users";

export default function App() {
  const { ready } = useAuth();

  if (!ready) {
    return <div className="flex h-screen items-center justify-center text-gray-500">Loading...</div>;
  }

  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/keys" element={<ApiKeys />} />
          <Route path="/usage" element={<UsageCost />} />
          <Route path="/logs" element={<RequestLogs />} />
          <Route path="/mcp/tools" element={<McpTools />} />
          <Route path="/mcp/playground" element={<McpPlayground />} />
          <Route path="/mcp/sessions" element={<McpSessions />} />

          <Route element={<ProtectedRoute roles={["admin"]} />}>
            <Route path="/routing-rules" element={<RoutingRules />} />
            <Route path="/organizations" element={<Organizations />} />
            <Route path="/users" element={<Users />} />
            <Route path="/providers" element={<ProviderConfigs />} />
            <Route path="/model-pricing" element={<ModelPricing />} />
            <Route path="/mcp/servers" element={<McpServers />} />
            <Route path="/mcp/servers/:id/health" element={<McpServerHealth />} />
            <Route path="/mcp/api-services" element={<ApiServices />} />
            <Route path="/agents" element={<Agents />} />
            <Route path="/agent-approvals" element={<AgentApprovals />} />
            <Route path="/settings/secrets" element={<SecretSettings />} />
            <Route path="/settings/identity-providers" element={<IdentitySettings />} />
          </Route>

          <Route element={<ProtectedRoute roles={["admin", "team_lead"]} />}>
            <Route path="/budgets" element={<Budgets />} />
            <Route path="/projects" element={<Projects />} />
          </Route>
        </Route>
      </Route>

      <Route path="/404" element={<NotFound />} />
      <Route path="*" element={<Navigate to="/404" replace />} />
    </Routes>
  );
}
