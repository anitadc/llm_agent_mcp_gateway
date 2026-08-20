import { useState } from "react";
import { Link } from "react-router-dom";

import { DataTable } from "../components/DataTable";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

const AUTH_TYPES = ["none", "bearer", "api_key"];

const HEALTH_BADGE = { healthy: "ok", unhealthy: "down", unknown: "rate_limited" };

function emptyForm() {
  return {
    name: "",
    base_url: "",
    description: "",
    auth_type: "none",
    credential_ref: "",
    header_name: "",
  };
}

function toAuthConfig(form) {
  if (form.auth_type === "none") return { type: "none" };
  const config = { type: form.auth_type, credential_ref: form.credential_ref || null };
  if (form.auth_type === "api_key") config.header_name = form.header_name || "X-API-Key";
  return config;
}

export function McpServers() {
  const { data: servers, loading, refetch } = useApi(() => endpoints.listMcpServers(), []);
  const { showToast } = useToast();

  const [showCreate, setShowCreate] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [checkingId, setCheckingId] = useState(null);
  const [form, setForm] = useState(emptyForm());

  async function handleCreate() {
    if (!form.name || !form.base_url) return;
    await endpoints.createMcpServer({
      name: form.name,
      base_url: form.base_url,
      description: form.description || null,
      auth_config: toAuthConfig(form),
    });
    showToast("MCP server registered", "success");
    setForm(emptyForm());
    setShowCreate(false);
    refetch();
  }

  async function toggleStatus(server) {
    const next = server.status === "active" ? "inactive" : "active";
    await endpoints.updateMcpServer(server.id, { status: next });
    showToast(next === "active" ? "Server activated" : "Server deactivated", "success");
    refetch();
  }

  async function handleDelete(server) {
    if (!window.confirm(`Remove "${server.name}" from the registry? This also drops its discovered tools.`)) return;
    await endpoints.deleteMcpServer(server.id);
    showToast("Server removed", "success");
    refetch();
  }

  async function handleHealthCheck(server) {
    setCheckingId(server.id);
    try {
      await endpoints.healthCheckMcpServer(server.id);
      showToast(`Health check ran for ${server.name}`, "success");
      refetch();
    } catch (err) {
      showToast(err?.message ?? "Health check failed", "error");
    } finally {
      setCheckingId(null);
    }
  }

  async function handleSyncAll() {
    setSyncing(true);
    try {
      await endpoints.syncMcpTools();
      showToast("Tool discovery sync complete", "success");
      refetch();
    } catch (err) {
      showToast(err?.message ?? "Sync failed", "error");
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">MCP Server Registry</h2>
        <div className="flex gap-2">
          <button
            onClick={handleSyncAll}
            disabled={syncing}
            className="rounded border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:opacity-50"
          >
            {syncing ? "Syncing..." : "Sync all tools"}
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="rounded bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            Register server
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <DataTable
          columns={[
            { key: "name", label: "Name" },
            { key: "base_url", label: "Base URL" },
            { key: "tool_count", label: "Tools" },
            {
              key: "status",
              label: "Status",
              render: (s) => (
                <label className="inline-flex items-center gap-2 text-xs">
                  <input type="checkbox" checked={s.status === "active"} onChange={() => toggleStatus(s)} />
                  {s.status}
                </label>
              ),
            },
            {
              key: "health_status",
              label: "Health",
              render: (s) => <StatusBadge status={HEALTH_BADGE[s.health_status] ?? s.health_status} />,
            },
            {
              key: "last_heartbeat",
              label: "Last heartbeat",
              render: (s) => (s.last_heartbeat ? new Date(s.last_heartbeat).toLocaleString() : "never"),
            },
            {
              key: "actions",
              label: "",
              render: (s) => (
                <div className="flex gap-3 text-xs">
                  <button
                    onClick={() => handleHealthCheck(s)}
                    disabled={checkingId === s.id}
                    className="text-brand-600 hover:underline disabled:opacity-50"
                  >
                    {checkingId === s.id ? "Checking..." : "Check now"}
                  </button>
                  <Link to={`/mcp/servers/${s.id}/health`} className="text-brand-600 hover:underline">
                    Monitor
                  </Link>
                  <button onClick={() => handleDelete(s)} className="text-red-600 hover:underline">
                    Delete
                  </button>
                </div>
              ),
            },
          ]}
          rows={servers}
          emptyMessage="No MCP servers registered yet"
          renderExpanded={(s) =>
            s.last_sync_error && (
              <tr>
                <td colSpan={7} className="bg-red-50 px-4 py-2 text-xs text-red-700">
                  Last sync error: {s.last_sync_error}
                </td>
              </tr>
            )
          }
        />
      )}

      {showCreate && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg">
            <h3 className="mb-4 text-lg font-semibold">Register MCP server</h3>
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Name (e.g. threat-intel)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <input
              value={form.base_url}
              onChange={(e) => setForm({ ...form, base_url: e.target.value })}
              placeholder="Base URL (Streamable HTTP endpoint)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <input
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Description (optional)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <select
              value={form.auth_type}
              onChange={(e) => setForm({ ...form, auth_type: e.target.value })}
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            >
              {AUTH_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            {form.auth_type !== "none" && (
              <input
                value={form.credential_ref}
                onChange={(e) => setForm({ ...form, credential_ref: e.target.value })}
                placeholder="Credential env var (e.g. MCP_THREAT_INTEL_TOKEN)"
                className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
              />
            )}
            {form.auth_type === "api_key" && (
              <input
                value={form.header_name}
                onChange={(e) => setForm({ ...form, header_name: e.target.value })}
                placeholder="Header name (default X-API-Key)"
                className="mb-4 w-full rounded border border-gray-300 px-3 py-2 text-sm"
              />
            )}
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowCreate(false)} className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100">
                Cancel
              </button>
              <button onClick={handleCreate} className="rounded bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700">
                Register
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
