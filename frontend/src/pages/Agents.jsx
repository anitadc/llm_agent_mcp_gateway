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

export function Agents() {
  const { data: agents, loading, refetch } = useApi(() => endpoints.listAgents(), []);
  const { showToast } = useToast();

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(emptyForm());
  const [expandedId, setExpandedId] = useState(null);
  const [approvalsById, setApprovalsById] = useState({});
  const [cardById, setCardById] = useState({});

  async function handleCreate() {
    if (!form.agent_key || !form.name) return;
    await endpoints.createAgent({
      agent_key: form.agent_key,
      name: form.name,
      description: form.description || null,
      owner_team: form.owner_team || null,
      domain: form.domain || null,
      capabilities: form.capabilities.split(",").map((c) => c.trim()).filter(Boolean),
      priority: Number(form.priority) || 100,
      risk_class: form.risk_class,
      trust_level: form.trust_level,
      endpoint_url: form.endpoint_url || null,
      auth_config: toAuthConfig(form),
    });
    showToast(`Agent "${form.agent_key}" registered as draft`, "success");
    setForm(emptyForm());
    setShowCreate(false);
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
    const [approvalsRes, cardRes] = await Promise.all([
      endpoints.listAgentApprovals(agent.id),
      endpoints.getAgentCard(agent.id),
    ]);
    setApprovalsById((prev) => ({ ...prev, [agent.id]: approvalsRes.data }));
    setCardById((prev) => ({ ...prev, [agent.id]: cardRes.data }));
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
          onClick={() => setShowCreate(true)}
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
            { key: "status", label: "Status", render: (a) => <StatusBadge status={STATUS_COLOR[a.status] ?? "blocked"} label={a.status} /> },
            {
              key: "actions",
              label: "",
              render: (a) => (
                <div className="flex flex-wrap gap-2 text-xs">
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
                <td colSpan={8} className="space-y-4 bg-gray-50 px-4 py-4">
                  <div>
                    <h4 className="mb-2 text-sm font-semibold text-gray-700">Approval tasks</h4>
                    <DataTable
                      columns={[
                        { key: "stage", label: "Stage" },
                        { key: "decision", label: "Decision", render: (t) => <StatusBadge status={t.decision === "approved" ? "ok" : t.decision === "rejected" ? "down" : "rate_limited"} label={t.decision} /> },
                        { key: "reason", label: "Reason", render: (t) => t.reason || "—" },
                        { key: "decided_at", label: "Decided", render: (t) => (t.decided_at ? new Date(t.decided_at).toLocaleString() : "pending") },
                      ]}
                      rows={approvalsById[a.id] || []}
                      emptyMessage="Not yet submitted for approval"
                    />
                  </div>
                  <div>
                    <h4 className="mb-2 text-sm font-semibold text-gray-700">Agent Card (simplified -- not A2A-schema-validated)</h4>
                    <pre className="overflow-x-auto rounded border border-gray-200 bg-white p-3 text-xs text-gray-600">
                      {JSON.stringify(cardById[a.id] || {}, null, 2)}
                    </pre>
                  </div>
                </td>
              </tr>
            )
          }
        />
      )}

      {showCreate && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30">
          <div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-lg bg-white p-6 shadow-lg">
            <h3 className="mb-4 text-lg font-semibold">Register agent</h3>
            <input
              value={form.agent_key}
              onChange={(e) => setForm({ ...form, agent_key: e.target.value })}
              placeholder="Agent key (e.g. pricing-agent)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
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
            <input
              value={form.endpoint_url}
              onChange={(e) => setForm({ ...form, endpoint_url: e.target.value })}
              placeholder="Endpoint URL (REMOTE_HTTP invocation target)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
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
