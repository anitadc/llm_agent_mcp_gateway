import { useState } from "react";

import { DataTable } from "../components/DataTable";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

const AUTH_TYPES = ["none", "api_key", "bearer", "basic", "oauth2_client_credentials"];
const METHODS = ["GET", "POST", "PUT", "DELETE"];
const PARAM_TYPES = ["string", "integer", "number", "boolean"];
const PARAM_LOCATIONS = ["path", "query", "header", "body"];

function emptyServiceForm() {
  return {
    name: "",
    base_url: "",
    description: "",
    authentication_type: "none",
    credential_ref: "",
    header_name: "",
    username_ref: "",
    password_ref: "",
    token_url: "",
    client_id_ref: "",
    client_secret_ref: "",
    scope: "",
    timeout_seconds: "10",
    rate_limit_per_window: "",
  };
}

function toAuthConfig(form) {
  switch (form.authentication_type) {
    case "api_key":
      return { credential_ref: form.credential_ref || null, header_name: form.header_name || "X-API-Key" };
    case "bearer":
      return { credential_ref: form.credential_ref || null };
    case "basic":
      return { username_ref: form.username_ref || null, password_ref: form.password_ref || null };
    case "oauth2_client_credentials":
      return {
        token_url: form.token_url || null,
        client_id_ref: form.client_id_ref || null,
        client_secret_ref: form.client_secret_ref || null,
        scope: form.scope || null,
      };
    default:
      return {};
  }
}

function serviceFormFromModel(service) {
  const authConfig = service.auth_config || {};
  return {
    name: service.name,
    base_url: service.base_url,
    description: service.description || "",
    authentication_type: service.authentication_type,
    credential_ref: authConfig.credential_ref || "",
    header_name: authConfig.header_name || "",
    username_ref: authConfig.username_ref || "",
    password_ref: authConfig.password_ref || "",
    token_url: authConfig.token_url || "",
    client_id_ref: authConfig.client_id_ref || "",
    client_secret_ref: authConfig.client_secret_ref || "",
    scope: authConfig.scope || "",
    timeout_seconds: String(service.timeout_seconds),
    rate_limit_per_window: service.rate_limit_per_window != null ? String(service.rate_limit_per_window) : "",
  };
}

function emptyParamRow() {
  return { name: "", type: "string", required: false, location: "query" };
}

function emptyEndpointForm() {
  return { tool_name: "", description: "", method: "GET", path: "", params: [emptyParamRow()] };
}

function paramsToPayload(rows) {
  const parameters = {};
  for (const row of rows) {
    if (!row.name) continue;
    parameters[row.name] = { type: row.type, required: row.required, location: row.location };
  }
  return parameters;
}

export function ApiServices() {
  const { data: services, loading, refetch } = useApi(() => endpoints.listApiServices(), []);
  const { showToast } = useToast();

  const [editingId, setEditingId] = useState(null);
  const [serviceForm, setServiceForm] = useState(emptyServiceForm());
  const [expandedId, setExpandedId] = useState(null);
  const [endpointsById, setEndpointsById] = useState({});
  const [endpointForm, setEndpointForm] = useState(emptyEndpointForm());

  function openCreate() {
    setEditingId("new");
    setServiceForm(emptyServiceForm());
  }

  function openEdit(service) {
    setEditingId(service.id);
    setServiceForm(serviceFormFromModel(service));
  }

  async function handleSaveService() {
    if (!serviceForm.base_url || (editingId === "new" && !serviceForm.name)) return;
    const payload = {
      description: serviceForm.description || null,
      base_url: serviceForm.base_url,
      authentication_type: serviceForm.authentication_type,
      auth_config: toAuthConfig(serviceForm),
      timeout_seconds: Number(serviceForm.timeout_seconds) || 10,
      rate_limit_per_window: serviceForm.rate_limit_per_window ? Number(serviceForm.rate_limit_per_window) : null,
    };
    if (editingId === "new") {
      await endpoints.createApiService({ ...payload, name: serviceForm.name });
      showToast("REST API service registered", "success");
    } else {
      await endpoints.updateApiService(editingId, payload);
      showToast("REST API service updated", "success");
    }
    setEditingId(null);
    refetch();
  }

  async function toggleServiceStatus(service) {
    const next = service.status === "active" ? "inactive" : "active";
    await endpoints.updateApiService(service.id, { status: next });
    showToast(next === "active" ? "Service activated" : "Service deactivated", "success");
    refetch();
  }

  async function handleDeleteService(service) {
    if (!window.confirm(`Remove "${service.name}"? This also removes its registered endpoints and their tools.`)) return;
    await endpoints.deleteApiService(service.id);
    showToast("Service removed", "success");
    refetch();
  }

  async function toggleExpand(service) {
    if (expandedId === service.id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(service.id);
    if (!endpointsById[service.id]) {
      const res = await endpoints.listApiEndpoints(service.id);
      setEndpointsById((prev) => ({ ...prev, [service.id]: res.data }));
    }
  }

  async function refreshEndpoints(serviceId) {
    const res = await endpoints.listApiEndpoints(serviceId);
    setEndpointsById((prev) => ({ ...prev, [serviceId]: res.data }));
    refetch();
  }

  async function handleAddEndpoint(serviceId) {
    if (!endpointForm.tool_name || !endpointForm.path) return;
    await endpoints.createApiEndpoint(serviceId, {
      tool_name: endpointForm.tool_name,
      description: endpointForm.description || null,
      method: endpointForm.method,
      path: endpointForm.path,
      parameters: paramsToPayload(endpointForm.params),
    });
    showToast(`MCP tool "${endpointForm.tool_name}" generated from REST endpoint`, "success");
    setEndpointForm(emptyEndpointForm());
    refreshEndpoints(serviceId);
  }

  async function handleDeleteEndpoint(serviceId, endpoint) {
    if (!window.confirm(`Remove tool "${endpoint.tool_name}"?`)) return;
    await endpoints.deleteApiEndpoint(serviceId, endpoint.id);
    showToast("Endpoint removed", "success");
    refreshEndpoints(serviceId);
  }

  function updateParamRow(index, patch) {
    setEndpointForm((prev) => ({
      ...prev,
      params: prev.params.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    }));
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">API Service Registry</h2>
        <button
          onClick={openCreate}
          className="rounded bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          Register REST API
        </button>
      </div>
      <p className="text-sm text-gray-500">
        Enterprise REST APIs registered here are exposed to agents only as governed MCP tools -- every endpoint you add
        below immediately becomes callable via <code>POST /mcp tools/call</code>, alongside native MCP-server tools.
      </p>

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <DataTable
          columns={[
            { key: "name", label: "Name" },
            { key: "base_url", label: "Base URL" },
            { key: "authentication_type", label: "Auth" },
            { key: "endpoint_count", label: "Endpoints" },
            {
              key: "status",
              label: "Status",
              render: (s) => (
                <label className="inline-flex items-center gap-2 text-xs">
                  <input type="checkbox" checked={s.status === "active"} onChange={() => toggleServiceStatus(s)} />
                  {s.status}
                </label>
              ),
            },
            {
              key: "actions",
              label: "",
              render: (s) => (
                <div className="flex gap-3 text-xs">
                  <button onClick={() => toggleExpand(s)} className="text-brand-600 hover:underline">
                    {expandedId === s.id ? "Hide endpoints" : "Manage endpoints"}
                  </button>
                  <button onClick={() => openEdit(s)} className="text-brand-600 hover:underline">
                    Edit
                  </button>
                  <button onClick={() => handleDeleteService(s)} className="text-red-600 hover:underline">
                    Delete
                  </button>
                </div>
              ),
            },
          ]}
          rows={services}
          emptyMessage="No REST API services registered yet"
          renderExpanded={(s) =>
            expandedId === s.id && (
              <tr>
                <td colSpan={6} className="space-y-4 bg-gray-50 px-4 py-4">
                  <div>
                    <h4 className="mb-2 text-sm font-semibold text-gray-700">Registered endpoints -&gt; MCP tools</h4>
                    <DataTable
                      columns={[
                        { key: "tool_name", label: "Tool name" },
                        { key: "method", label: "Method" },
                        { key: "path", label: "Path" },
                        {
                          key: "enabled",
                          label: "Enabled",
                          render: (e) => <StatusBadge status={e.enabled ? "ok" : "down"} />,
                        },
                        {
                          key: "actions",
                          label: "",
                          render: (e) => (
                            <button
                              onClick={() => handleDeleteEndpoint(s.id, e)}
                              className="text-xs text-red-600 hover:underline"
                            >
                              Delete
                            </button>
                          ),
                        },
                      ]}
                      rows={endpointsById[s.id] || []}
                      emptyMessage="No endpoints registered yet"
                    />
                  </div>

                  <div className="rounded border border-gray-200 bg-white p-4">
                    <h4 className="mb-3 text-sm font-semibold text-gray-700">REST Tool Builder -- add an endpoint</h4>
                    <div className="mb-3 grid grid-cols-2 gap-3">
                      <input
                        value={endpointForm.tool_name}
                        onChange={(e) => setEndpointForm({ ...endpointForm, tool_name: e.target.value })}
                        placeholder="Tool name (e.g. get_customer)"
                        className="rounded border border-gray-300 px-3 py-2 text-sm"
                      />
                      <select
                        value={endpointForm.method}
                        onChange={(e) => setEndpointForm({ ...endpointForm, method: e.target.value })}
                        className="rounded border border-gray-300 px-3 py-2 text-sm"
                      >
                        {METHODS.map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </select>
                      <input
                        value={endpointForm.path}
                        onChange={(e) => setEndpointForm({ ...endpointForm, path: e.target.value })}
                        placeholder="Path (e.g. /customers/{id})"
                        className="col-span-2 rounded border border-gray-300 px-3 py-2 text-sm"
                      />
                      <input
                        value={endpointForm.description}
                        onChange={(e) => setEndpointForm({ ...endpointForm, description: e.target.value })}
                        placeholder="Description (optional)"
                        className="col-span-2 rounded border border-gray-300 px-3 py-2 text-sm"
                      />
                    </div>

                    <div className="mb-3 space-y-2">
                      <div className="text-xs font-medium text-gray-500">Parameters</div>
                      {endpointForm.params.map((row, i) => (
                        <div key={i} className="flex items-center gap-2">
                          <input
                            value={row.name}
                            onChange={(e) => updateParamRow(i, { name: e.target.value })}
                            placeholder="name (e.g. id)"
                            className="w-32 rounded border border-gray-300 px-2 py-1 text-sm"
                          />
                          <select
                            value={row.type}
                            onChange={(e) => updateParamRow(i, { type: e.target.value })}
                            className="rounded border border-gray-300 px-2 py-1 text-sm"
                          >
                            {PARAM_TYPES.map((t) => (
                              <option key={t} value={t}>
                                {t}
                              </option>
                            ))}
                          </select>
                          <select
                            value={row.location}
                            onChange={(e) => updateParamRow(i, { location: e.target.value })}
                            className="rounded border border-gray-300 px-2 py-1 text-sm"
                          >
                            {PARAM_LOCATIONS.map((l) => (
                              <option key={l} value={l}>
                                {l}
                              </option>
                            ))}
                          </select>
                          <label className="flex items-center gap-1 text-xs">
                            <input
                              type="checkbox"
                              checked={row.required}
                              onChange={(e) => updateParamRow(i, { required: e.target.checked })}
                            />
                            required
                          </label>
                          <button
                            onClick={() =>
                              setEndpointForm((prev) => ({ ...prev, params: prev.params.filter((_, idx) => idx !== i) }))
                            }
                            className="text-xs text-red-600 hover:underline"
                          >
                            Remove
                          </button>
                        </div>
                      ))}
                      <button
                        onClick={() =>
                          setEndpointForm((prev) => ({ ...prev, params: [...prev.params, emptyParamRow()] }))
                        }
                        className="text-xs text-brand-600 hover:underline"
                      >
                        + Add parameter
                      </button>
                    </div>

                    <button
                      onClick={() => handleAddEndpoint(s.id)}
                      className="rounded bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700"
                    >
                      Generate MCP tool
                    </button>
                  </div>
                </td>
              </tr>
            )
          }
        />
      )}

      {editingId && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg">
            <h3 className="mb-4 text-lg font-semibold">
              {editingId === "new" ? "Register REST API service" : `Edit "${serviceForm.name}"`}
            </h3>
            <input
              value={serviceForm.name}
              disabled={editingId !== "new"}
              onChange={(e) => setServiceForm({ ...serviceForm, name: e.target.value })}
              placeholder="Name (e.g. customer-service)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm disabled:bg-gray-100"
            />
            <input
              value={serviceForm.base_url}
              onChange={(e) => setServiceForm({ ...serviceForm, base_url: e.target.value })}
              placeholder="Base URL (e.g. https://customer.company.com)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <input
              value={serviceForm.description}
              onChange={(e) => setServiceForm({ ...serviceForm, description: e.target.value })}
              placeholder="Description (optional)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <select
              value={serviceForm.authentication_type}
              onChange={(e) => setServiceForm({ ...serviceForm, authentication_type: e.target.value })}
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            >
              {AUTH_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>

            {(serviceForm.authentication_type === "api_key" || serviceForm.authentication_type === "bearer") && (
              <input
                value={serviceForm.credential_ref}
                onChange={(e) => setServiceForm({ ...serviceForm, credential_ref: e.target.value })}
                placeholder="Secret name (resolved via the Secret Provider layer)"
                className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
              />
            )}
            {serviceForm.authentication_type === "api_key" && (
              <input
                value={serviceForm.header_name}
                onChange={(e) => setServiceForm({ ...serviceForm, header_name: e.target.value })}
                placeholder="Header name (default X-API-Key)"
                className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
              />
            )}
            {serviceForm.authentication_type === "basic" && (
              <>
                <input
                  value={serviceForm.username_ref}
                  onChange={(e) => setServiceForm({ ...serviceForm, username_ref: e.target.value })}
                  placeholder="Username secret name"
                  className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
                />
                <input
                  value={serviceForm.password_ref}
                  onChange={(e) => setServiceForm({ ...serviceForm, password_ref: e.target.value })}
                  placeholder="Password secret name"
                  className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
                />
              </>
            )}
            {serviceForm.authentication_type === "oauth2_client_credentials" && (
              <>
                <input
                  value={serviceForm.token_url}
                  onChange={(e) => setServiceForm({ ...serviceForm, token_url: e.target.value })}
                  placeholder="Token URL"
                  className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
                />
                <input
                  value={serviceForm.client_id_ref}
                  onChange={(e) => setServiceForm({ ...serviceForm, client_id_ref: e.target.value })}
                  placeholder="Client ID secret name"
                  className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
                />
                <input
                  value={serviceForm.client_secret_ref}
                  onChange={(e) => setServiceForm({ ...serviceForm, client_secret_ref: e.target.value })}
                  placeholder="Client secret name"
                  className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
                />
                <input
                  value={serviceForm.scope}
                  onChange={(e) => setServiceForm({ ...serviceForm, scope: e.target.value })}
                  placeholder="Scope (optional)"
                  className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
                />
              </>
            )}

            <div className="mb-4 grid grid-cols-2 gap-3">
              <input
                value={serviceForm.timeout_seconds}
                onChange={(e) => setServiceForm({ ...serviceForm, timeout_seconds: e.target.value })}
                placeholder="Timeout (seconds)"
                className="rounded border border-gray-300 px-3 py-2 text-sm"
              />
              <input
                value={serviceForm.rate_limit_per_window}
                onChange={(e) => setServiceForm({ ...serviceForm, rate_limit_per_window: e.target.value })}
                placeholder="Rate limit / window (optional)"
                className="rounded border border-gray-300 px-3 py-2 text-sm"
              />
            </div>

            <div className="flex justify-end gap-2">
              <button onClick={() => setEditingId(null)} className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100">
                Cancel
              </button>
              <button onClick={handleSaveService} className="rounded bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700">
                {editingId === "new" ? "Register" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
