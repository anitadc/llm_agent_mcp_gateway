import { useState } from "react";

import { DataTable } from "../components/DataTable";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

const AUTH_TYPES = ["none", "bearer", "api_key"];
const RISK_CLASSES = ["low", "medium", "high"];
const TRUST_LEVELS = [
  "t0_unknown",
  "t1_registered_internal",
  "t2_enterprise_trusted",
  "t3_privileged",
  "t4_approved_external_partner",
  "t5_public_untrusted",
];
const PROTOCOLS = ["remote_http", "a2a"];
const VISIBILITIES = ["published", "private"];

const STATUS_COLOR = {
  draft: "rate_limited",
  under_review: "rate_limited",
  approved: "ok",
  active: "ok",
  rejected: "down",
  suspended: "down",
  deprecated: "blocked",
  retired: "down",
};

const HEALTH_BADGE = { healthy: "ok", unhealthy: "down", unknown: "rate_limited" };

function emptyForm() {
  return {
    agent_key: "",
    name: "",
    description: "",
    owner_team: "",
    domain: "",
    capabilities: "",
    priority: "100",
    risk_class: "low",
    trust_level: "t1_registered_internal",
    endpoint_url: "",
    protocol: "remote_http",
    auth_type: "none",
    credential_ref: "",
    header_name: "",
    visibility: "published",
    project_id: "",
    deprecation_notice: "",
  };
}

function toAuthConfig(form) {
  if (form.auth_type === "none") return { type: "none" };
  const config = { type: form.auth_type, credential_ref: form.credential_ref || null };
  if (form.auth_type === "api_key") config.header_name = form.header_name || "X-API-Key";
  return config;
}

function formFromAgent(agent) {
  const authConfig = agent.auth_config || {};
  return {
    agent_key: agent.agent_key,
    name: agent.name,
    description: agent.description || "",
    owner_team: agent.owner_team || "",
    domain: agent.domain || "",
    capabilities: agent.capabilities.join(", "),
    priority: String(agent.priority),
    risk_class: agent.risk_class,
    trust_level: agent.trust_level,
    endpoint_url: agent.endpoint_url || "",
    protocol: agent.protocol,
    auth_type: authConfig.type || "none",
    credential_ref: authConfig.credential_ref || "",
    header_name: authConfig.header_name || "",
    visibility: agent.visibility,
    project_id: agent.project_id || "",
    deprecation_notice: agent.deprecation_notice || "",
  };
}

// Matches AgentRegistryService.update()'s own restriction -- editing past this point
// is rejected server-side, so there's no point offering the action in the UI.
const EDITABLE_STATUSES = new Set(["draft", "rejected"]);

export function Agents() {
  const { data: agents, loading, refetch } = useApi(() => endpoints.listAgents(), []);
  const { showToast } = useToast();

  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyForm());
  const [expandedId, setExpandedId] = useState(null);
  const [approvalsById, setApprovalsById] = useState({});
  const [cardById, setCardById] = useState({});
  const [auditLogById, setAuditLogById] = useState({});
  const [statsById, setStatsById] = useState({});
  const [pricingById, setPricingById] = useState({});
  const [priceInput, setPriceInput] = useState("");
  const [enableProjectInput, setEnableProjectInput] = useState("");

  function openCreate() {
    setEditingId("new");
    setForm(emptyForm());
  }

  function openEdit(agent) {
    setEditingId(agent.id);
    setForm(formFromAgent(agent));
  }

  async function handleSave() {
    if (!form.name || (editingId === "new" && !form.agent_key)) return;
    const payload = {
      name: form.name,
      description: form.description || null,
      owner_team: form.owner_team || null,
      domain: form.domain || null,
      capabilities: form.capabilities.split(",").map((c) => c.trim()).filter(Boolean),
      priority: Number(form.priority) || 100,
      risk_class: form.risk_class,
      trust_level: form.trust_level,
      endpoint_url: form.endpoint_url || null,
      protocol: form.protocol,
      auth_config: toAuthConfig(form),
      visibility: form.visibility,
      project_id: form.visibility === "private" ? form.project_id || null : null,
      deprecation_notice: form.deprecation_notice || null,
    };
    if (editingId === "new") {
      await endpoints.createAgent({ ...payload, agent_key: form.agent_key });
      showToast(`Agent "${form.agent_key}" registered as draft`, "success");
    } else {
      await endpoints.updateAgent(editingId, payload);
      showToast(`Agent "${form.agent_key}" updated`, "success");
    }
    setEditingId(null);
    refetch();
  }

  async function withErrorToast(action, successMessage) {
    try {
      await action();
      showToast(successMessage, "success");
      refetch();
    } catch (err) {
      showToast(err?.message ?? "Action failed", "error");
    }
  }

  async function toggleExpand(agent) {
    if (expandedId === agent.id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(agent.id);
    const [approvalsRes, cardRes, auditRes, statsRes] = await Promise.all([
      endpoints.listAgentApprovals(agent.id),
      endpoints.getAgentCard(agent.id),
      endpoints.getAgentAuditLog(agent.id, { page: 1, page_size: 10 }),
      endpoints.getAgentStats(agent.id),
    ]);
    setApprovalsById((prev) => ({ ...prev, [agent.id]: approvalsRes.data }));
    setCardById((prev) => ({ ...prev, [agent.id]: cardRes.data }));
    setAuditLogById((prev) => ({ ...prev, [agent.id]: auditRes.data.items }));
    setStatsById((prev) => ({ ...prev, [agent.id]: statsRes.data }));
    try {
      const pricingRes = await endpoints.getAgentPricing(agent.id);
      setPricingById((prev) => ({ ...prev, [agent.id]: pricingRes.data }));
    } catch {
      setPricingById((prev) => ({ ...prev, [agent.id]: null }));
    }
  }

  async function handleHealthCheck(agent) {
    await withErrorToast(() => endpoints.healthCheckAgent(agent.id), `Health check ran for "${agent.name}"`);
  }

  async function handleSetPricing(agent) {
    const cost = Number(priceInput);
    if (!priceInput || Number.isNaN(cost)) return;
    await endpoints.setAgentPricing(agent.id, { cost_per_invocation: cost });
    const pricingRes = await endpoints.getAgentPricing(agent.id);
    setPricingById((prev) => ({ ...prev, [agent.id]: pricingRes.data }));
    setPriceInput("");
    showToast(`Set cost/invocation for "${agent.name}"`, "success");
  }

  async function handleEnableProject(agent) {
    if (!enableProjectInput) return;
    await endpoints.enableAgentForProject(agent.id, { project_id: enableProjectInput });
    setEnableProjectInput("");
    showToast(`Enabled "${agent.name}" for project ${enableProjectInput}`, "success");
  }

  async function handleDisableProject(agent) {
    if (!enableProjectInput) return;
    await endpoints.disableAgentForProject(agent.id, { project_id: enableProjectInput });
    setEnableProjectInput("");
    showToast(`Disabled "${agent.name}" for project ${enableProjectInput}`, "success");
  }

  function nextActions(agent) {
    switch (agent.status) {
      case "draft":
      case "rejected":
        return [{ label: "Submit for approval", fn: () => endpoints.submitAgentForApproval(agent.id), msg: "Submitted for approval" }];
      case "approved":
        return [{ label: "Publish", fn: () => endpoints.publishAgent(agent.id), msg: "Agent published and now active" }];
      case "active":
        return [
          { label: "Suspend", fn: () => endpoints.suspendAgent(agent.id), msg: "Agent suspended" },
          { label: "Deprecate", fn: () => endpoints.deprecateAgent(agent.id), msg: "Agent deprecated" },
        ];
      case "suspended":
        return [
          { label: "Reactivate", fn: () => endpoints.reactivateAgent(agent.id), msg: "Agent reactivated" },
          { label: "Retire", fn: () => endpoints.retireAgent(agent.id), msg: "Agent retired" },
        ];
      case "deprecated":
        return [{ label: "Retire", fn: () => endpoints.retireAgent(agent.id), msg: "Agent retired" }];
      default:
        return [];
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Agent Registry</h2>
        <button
          onClick={openCreate}
          className="rounded bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          Register agent
        </button>
      </div>
      <p className="text-sm text-gray-500">
        Registering an agent never makes it callable -- it must pass its configured approval stages and be published
        before <code>POST /v1/agent-invocations</code> can route a capability request to it.
      </p>

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <DataTable
          columns={[
            { key: "agent_key", label: "Agent key" },
            { key: "name", label: "Name" },
            { key: "capabilities", label: "Capabilities", render: (a) => a.capabilities.join(", ") || "—" },
            { key: "risk_class", label: "Risk" },
            { key: "trust_level", label: "Trust", render: (a) => a.trust_level.replace(/^t\d_/, "") },
            { key: "priority", label: "Priority" },
            { key: "visibility", label: "Visibility", render: (a) => (a.visibility === "private" ? "private" : "published") },
            { key: "status", label: "Status", render: (a) => <StatusBadge status={STATUS_COLOR[a.status] ?? "blocked"} label={a.status} /> },
            {
              key: "health_status",
              label: "Health",
              render: (a) => <StatusBadge status={HEALTH_BADGE[a.health_status] ?? "rate_limited"} label={a.health_status} />,
            },
            {
              key: "actions",
              label: "",
              render: (a) => (
                <div className="flex flex-wrap gap-2 text-xs">
                  {EDITABLE_STATUSES.has(a.status) && (
                    <button onClick={() => openEdit(a)} className="text-brand-600 hover:underline">
                      Edit
                    </button>
                  )}
                  <button onClick={() => handleHealthCheck(a)} className="text-brand-600 hover:underline">
                    Health check
                  </button>
                  {nextActions(a).map((action) => (
                    <button
                      key={action.label}
                      onClick={() => withErrorToast(action.fn, action.msg)}
                      className="text-brand-600 hover:underline"
                    >
                      {action.label}
                    </button>
                  ))}
                  <button onClick={() => toggleExpand(a)} className="text-gray-500 hover:underline">
                    {expandedId === a.id ? "Hide detail" : "View detail"}
                  </button>
                </div>
              ),
            },
          ]}
          rows={agents}
          emptyMessage="No agents registered yet"
          renderExpanded={(a) =>
            expandedId === a.id && (
              <tr>
                <td colSpan={10} className="space-y-4 bg-gray-50 px-4 py-4">
                  <div>
                    <h4 className="mb-2 text-sm font-semibold text-gray-700">Approval tasks</h4>
                    <DataTable
                      columns={[
                        { key: "submission_round", label: "Round" },
                        { key: "stage", label: "Stage" },
                        { key: "decision", label: "Decision", render: (t) => <StatusBadge status={t.decision === "approved" ? "ok" : t.decision === "rejected" ? "down" : "rate_limited"} label={t.decision} /> },
                        { key: "reason", label: "Reason", render: (t) => t.reason || "—" },
                        { key: "decided_at", label: "Decided", render: (t) => (t.decided_at ? new Date(t.decided_at).toLocaleString() : "pending") },
                        { key: "due_at", label: "Due", render: (t) => (t.due_at ? new Date(t.due_at).toLocaleString() : "—") },
                        { key: "escalated_at", label: "Overdue", render: (t) => (t.escalated_at ? <StatusBadge status="down" label="overdue" /> : "—") },
                      ]}
                      rows={approvalsById[a.id] || []}
                      emptyMessage="Not yet submitted for approval"
                    />
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <div>
                      <h4 className="mb-2 text-sm font-semibold text-gray-700">Usage &amp; cost (last 60 min)</h4>
                      {statsById[a.id] ? (
                        <dl className="grid grid-cols-2 gap-2 rounded border border-gray-200 bg-white p-3 text-xs">
                          <dt className="text-gray-500">Requests</dt>
                          <dd>{statsById[a.id].request_count}</dd>
                          <dt className="text-gray-500">Errors</dt>
                          <dd>{statsById[a.id].error_count}</dd>
                          <dt className="text-gray-500">Avg latency</dt>
                          <dd>{statsById[a.id].avg_latency_ms != null ? `${Math.round(statsById[a.id].avg_latency_ms)} ms` : "—"}</dd>
                          <dt className="text-gray-500">Total cost</dt>
                          <dd>{statsById[a.id].total_cost_usd != null ? `$${statsById[a.id].total_cost_usd}` : "unpriced"}</dd>
                        </dl>
                      ) : (
                        <div className="text-xs text-gray-400">Loading...</div>
                      )}
                    </div>
                    <div>
                      <h4 className="mb-2 text-sm font-semibold text-gray-700">Cost per invocation</h4>
                      <div className="flex items-center gap-2">
                        <input
                          value={priceInput}
                          onChange={(e) => setPriceInput(e.target.value)}
                          placeholder={pricingById[a.id] ? String(pricingById[a.id].cost_per_invocation) : "unpriced -- e.g. 0.01"}
                          className="w-40 rounded border border-gray-300 px-2 py-1 text-xs"
                        />
                        <button onClick={() => handleSetPricing(a)} className="text-xs text-brand-600 hover:underline">
                          Set
                        </button>
                      </div>
                    </div>
                  </div>

                  {a.visibility === "private" && (
                    <div>
                      <h4 className="mb-2 text-sm font-semibold text-gray-700">Project enablement (private agent)</h4>
                      <div className="flex items-center gap-2">
                        <input
                          value={enableProjectInput}
                          onChange={(e) => setEnableProjectInput(e.target.value)}
                          placeholder="Project id"
                          className="w-64 rounded border border-gray-300 px-2 py-1 text-xs"
                        />
                        <button onClick={() => handleEnableProject(a)} className="text-xs text-brand-600 hover:underline">
                          Enable
                        </button>
                        <button onClick={() => handleDisableProject(a)} className="text-xs text-red-600 hover:underline">
                          Disable
                        </button>
                      </div>
                    </div>
                  )}

                  <div>
                    <h4 className="mb-2 text-sm font-semibold text-gray-700">Agent Card (A2A-shaped, not schema-validated)</h4>
                    <pre className="overflow-x-auto rounded border border-gray-200 bg-white p-3 text-xs text-gray-600">
                      {JSON.stringify(cardById[a.id] || {}, null, 2)}
                    </pre>
                  </div>

                  <div>
                    <h4 className="mb-2 text-sm font-semibold text-gray-700">Recent audit log</h4>
                    <DataTable
                      columns={[
                        { key: "action", label: "Action" },
                        { key: "created_at", label: "When", render: (e) => new Date(e.created_at).toLocaleString() },
                      ]}
                      rows={auditLogById[a.id] || []}
                      emptyMessage="No audit entries yet"
                    />
                  </div>
                </td>
              </tr>
            )
          }
        />
      )}

      {editingId && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30">
          <div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-lg bg-white p-6 shadow-lg">
            <h3 className="mb-4 text-lg font-semibold">{editingId === "new" ? "Register agent" : `Edit "${form.agent_key}"`}</h3>
            <input
              value={form.agent_key}
              disabled={editingId !== "new"}
              onChange={(e) => setForm({ ...form, agent_key: e.target.value })}
              placeholder="Agent key (e.g. pricing-agent)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm disabled:bg-gray-100"
            />
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Display name"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <input
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Description"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <div className="mb-3 grid grid-cols-2 gap-3">
              <input
                value={form.owner_team}
                onChange={(e) => setForm({ ...form, owner_team: e.target.value })}
                placeholder="Owner team"
                className="rounded border border-gray-300 px-3 py-2 text-sm"
              />
              <input
                value={form.domain}
                onChange={(e) => setForm({ ...form, domain: e.target.value })}
                placeholder="Domain (e.g. finance)"
                className="rounded border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <input
              value={form.capabilities}
              onChange={(e) => setForm({ ...form, capabilities: e.target.value })}
              placeholder="Capabilities (comma-separated, e.g. pricing)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <div className="mb-3 grid grid-cols-2 gap-3">
              <input
                value={form.endpoint_url}
                onChange={(e) => setForm({ ...form, endpoint_url: e.target.value })}
                placeholder="Endpoint URL (invocation target)"
                className="rounded border border-gray-300 px-3 py-2 text-sm"
              />
              <select
                value={form.protocol}
                onChange={(e) => setForm({ ...form, protocol: e.target.value })}
                className="rounded border border-gray-300 px-3 py-2 text-sm"
              >
                {PROTOCOLS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            <div className="mb-3 grid grid-cols-2 gap-3">
              <select
                value={form.visibility}
                onChange={(e) => setForm({ ...form, visibility: e.target.value })}
                className="rounded border border-gray-300 px-3 py-2 text-sm"
              >
                {VISIBILITIES.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
              {form.visibility === "private" && (
                <input
                  value={form.project_id}
                  onChange={(e) => setForm({ ...form, project_id: e.target.value })}
                  placeholder="Owning project id"
                  className="rounded border border-gray-300 px-3 py-2 text-sm"
                />
              )}
            </div>
            {editingId !== "new" && (
              <input
                value={form.deprecation_notice}
                onChange={(e) => setForm({ ...form, deprecation_notice: e.target.value })}
                placeholder="Deprecation notice (shown to catalog consumers once deprecated)"
                className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
              />
            )}
            <div className="mb-3 grid grid-cols-3 gap-3">
              <input
                value={form.priority}
                onChange={(e) => setForm({ ...form, priority: e.target.value })}
                placeholder="Priority"
                className="rounded border border-gray-300 px-3 py-2 text-sm"
              />
              <select
                value={form.risk_class}
                onChange={(e) => setForm({ ...form, risk_class: e.target.value })}
                className="rounded border border-gray-300 px-3 py-2 text-sm"
              >
                {RISK_CLASSES.map((r) => (
                  <option key={r} value={r}>
                    {r} risk
                  </option>
                ))}
              </select>
              <select
                value={form.trust_level}
                onChange={(e) => setForm({ ...form, trust_level: e.target.value })}
                className="rounded border border-gray-300 px-3 py-2 text-sm"
              >
                {TRUST_LEVELS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
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
                placeholder="Secret name (resolved via the Secret Provider layer)"
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
              <button onClick={() => setEditingId(null)} className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100">
                Cancel
              </button>
              <button onClick={handleSave} className="rounded bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700">
                {editingId === "new" ? "Register" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
