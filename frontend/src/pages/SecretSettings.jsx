import { useState } from "react";

import { DataTable } from "../components/DataTable";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { useApi } from "../hooks/useApi";
import { usePagination } from "../hooks/usePagination";
import { endpoints } from "../services/api";

const PROVIDER_LABELS = {
  postgres: "PostgreSQL",
  infisical: "Infisical",
  aws: "AWS Secrets Manager",
  gcp: "Google Secret Manager",
  azure: "Azure Key Vault",
  vault: "HashiCorp Vault",
};

const LLM_PROVIDER_LABELS = {
  OPENAI: "OpenAI",
  ANTHROPIC: "Anthropic",
  GOOGLE_GEMINI: "Google Gemini",
  AWS_BEDROCK: "AWS Bedrock",
  AZURE_OPENAI: "Azure OpenAI",
};

// Mirrors backend/app/api/v1/secrets.py's _LLM_CREDENTIAL_CHECKS -- which
// underlying secret name(s) a "Rotate" click on this row should invalidate.
const LLM_PROVIDER_SECRET_NAMES = {
  OPENAI: ["OPENAI_API_KEY"],
  ANTHROPIC: ["ANTHROPIC_API_KEY"],
  GOOGLE_GEMINI: ["GOOGLE_API_KEY"],
  AWS_BEDROCK: ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
  AZURE_OPENAI: ["AZURE_OPENAI_KEY"],
};

const STATUS_BADGE = { configured: "ok", not_configured: "rate_limited", error: "down" };
const AUDIT_BADGE = { success: "ok", error: "down" };

export function SecretSettings() {
  const { showToast } = useToast();
  const [rotatingProvider, setRotatingProvider] = useState(null);
  const [savingSecret, setSavingSecret] = useState(false);
  const [secretForm, setSecretForm] = useState({ secret_name: "", value: "" });
  const { page, pageSize, setPage, nextPage, prevPage } = usePagination(1, 10);

  const { data: providerConfig, loading: providersLoading } = useApi(() => endpoints.getSecretProviders(), []);
  const { data: status, loading: statusLoading, refetch: refetchStatus } = useApi(() => endpoints.getSecretStatus(), []);
  const { data: auditLog, loading: auditLoading, refetch: refetchAuditLog } = useApi(
    () => endpoints.getSecretAuditLog({ page, page_size: pageSize }),
    [page, pageSize]
  );

  async function handleSetSecret(e) {
    e.preventDefault();
    setSavingSecret(true);
    try {
      await endpoints.setSecret(secretForm);
      showToast(`Saved ${secretForm.secret_name}`, "success");
      setSecretForm({ secret_name: "", value: "" });
      refetchStatus();
      refetchAuditLog();
    } catch (err) {
      showToast(err?.message ?? "Failed to save secret", "error");
    } finally {
      setSavingSecret(false);
    }
  }

  async function handleRotate(providerLabel) {
    setRotatingProvider(providerLabel);
    try {
      for (const secretName of LLM_PROVIDER_SECRET_NAMES[providerLabel]) {
        await endpoints.rotateSecret({ secret_name: secretName });
      }
      showToast(`Rotated ${LLM_PROVIDER_LABELS[providerLabel]} credentials`, "success");
      refetchStatus();
      refetchAuditLog();
    } catch (err) {
      showToast(err?.message ?? "Rotation failed", "error");
    } finally {
      setRotatingProvider(null);
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Secret Management</h2>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-gray-700">Secret Provider Configuration</h3>
        <p className="mb-3 text-xs text-gray-500">
          Set via the <code className="rounded bg-gray-100 px-1">SECRET_PROVIDER</code> environment variable --
          changing the active provider requires a backend restart, it isn't hot-swappable from this page.
        </p>
        {providersLoading ? (
          <div className="text-gray-400">Loading...</div>
        ) : (
          <DataTable
            columns={[
              {
                key: "name",
                label: "Provider",
                render: (p) => (
                  <span className={p.name === providerConfig.active_provider ? "font-semibold text-brand-700" : ""}>
                    {PROVIDER_LABELS[p.name] ?? p.name}
                    {p.name === providerConfig.active_provider && " (active)"}
                  </span>
                ),
              },
              {
                key: "available",
                label: "Configured",
                render: (p) => <StatusBadge status={p.available ? "ok" : "down"} />,
              },
            ]}
            rows={providerConfig?.providers}
            rowKey="name"
            emptyMessage="No providers found"
          />
        )}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-gray-700">Set a Secret Value</h3>
        <p className="mb-3 text-xs text-gray-500">
          Writes through to the active Secret Provider above (e.g. <code className="rounded bg-gray-100 px-1">OPENAI_API_KEY</code>,{" "}
          <code className="rounded bg-gray-100 px-1">ANTHROPIC_API_KEY</code>). The value is never shown again after this form
          submits -- only whether the write succeeded is recorded.
        </p>
        <form onSubmit={handleSetSecret} className="flex items-end gap-2">
          <div className="flex-1">
            <label className="block text-xs text-gray-500">Secret name</label>
            <input
              required
              value={secretForm.secret_name}
              onChange={(e) => setSecretForm({ ...secretForm, secret_name: e.target.value })}
              placeholder="OPENAI_API_KEY"
              className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
            />
          </div>
          <div className="flex-1">
            <label className="block text-xs text-gray-500">Value</label>
            <input
              required
              type="password"
              autoComplete="off"
              value={secretForm.value}
              onChange={(e) => setSecretForm({ ...secretForm, value: e.target.value })}
              className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={savingSecret}
            className="rounded bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {savingSecret ? "Saving..." : "Save"}
          </button>
        </form>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-gray-700">LLM Provider Credentials</h3>
        <p className="mb-3 text-xs text-gray-500">
          Status only -- credential values are never returned by this API or shown in this UI.
        </p>
        {statusLoading ? (
          <div className="text-gray-400">Loading...</div>
        ) : (
          <DataTable
            columns={[
              { key: "provider", label: "Provider", render: (s) => LLM_PROVIDER_LABELS[s.provider] ?? s.provider },
              {
                key: "status",
                label: "Status",
                render: (s) => <StatusBadge status={STATUS_BADGE[s.status] ?? s.status} />,
              },
              {
                key: "actions",
                label: "",
                render: (s) => (
                  <button
                    onClick={() => handleRotate(s.provider)}
                    disabled={rotatingProvider === s.provider}
                    className="text-xs text-brand-600 hover:underline disabled:opacity-50"
                  >
                    {rotatingProvider === s.provider ? "Rotating..." : "Rotate"}
                  </button>
                ),
              },
            ]}
            rows={status}
            rowKey="provider"
            emptyMessage="No LLM providers configured"
          />
        )}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-gray-700">Recent Secret Operations</h3>
        {auditLoading ? (
          <div className="text-gray-400">Loading...</div>
        ) : (
          <>
            <DataTable
              columns={[
                { key: "created_at", label: "Time", render: (a) => new Date(a.created_at).toLocaleString() },
                { key: "operation", label: "Operation" },
                { key: "provider", label: "Provider" },
                { key: "secret_name", label: "Secret" },
                { key: "tenant_id", label: "Tenant", render: (a) => a.tenant_id ?? "default" },
                { key: "status", label: "Status", render: (a) => <StatusBadge status={AUDIT_BADGE[a.status] ?? a.status} /> },
              ]}
              rows={auditLog?.items}
              emptyMessage="No secret operations recorded yet"
            />
            <div className="mt-2 flex items-center justify-between text-sm text-gray-500">
              <span>
                Page {page} -- {auditLog?.total ?? 0} total
              </span>
              <div className="space-x-2">
                <button onClick={prevPage} disabled={page <= 1} className="rounded px-3 py-1 hover:bg-gray-100 disabled:opacity-40">
                  Previous
                </button>
                <button onClick={nextPage} className="rounded px-3 py-1 hover:bg-gray-100">
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
