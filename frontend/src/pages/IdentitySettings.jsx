import { useState } from "react";

import { DataTable } from "../components/DataTable";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

const PROVIDER_LABELS = {
  keycloak: "Keycloak",
  entra: "Microsoft Entra ID",
  auth0: "Auth0",
  okta: "Okta Workforce Identity Cloud",
  aws_identity: "AWS IAM Identity Center",
  google: "Google Identity",
};

const PROVIDER_NAMES = Object.keys(PROVIDER_LABELS);

function emptyTenantConfigForm() {
  return { tenant_id: "", provider: "keycloak", issuer: "", configuration: "{}" };
}

function emptyPolicyForm() {
  return { name: "", project_id: "", allowed_roles: "", allowed_identity_providers: "", max_tokens: "", is_active: true };
}

export function IdentitySettings() {
  const { showToast } = useToast();

  const { data: session, loading: sessionLoading } = useApi(() => endpoints.exchangeToken(), []);
  const { data: providerConfig, loading: providersLoading } = useApi(() => endpoints.getIdentityProviders(), []);
  const { data: tenantConfigs, loading: tenantConfigsLoading, refetch: refetchTenantConfigs } = useApi(
    () => endpoints.listTenantIdentityConfigs(),
    []
  );
  const { data: policies, loading: policiesLoading, refetch: refetchPolicies } = useApi(
    () => endpoints.listAccessPolicies(),
    []
  );

  const [showTenantForm, setShowTenantForm] = useState(false);
  const [tenantForm, setTenantForm] = useState(emptyTenantConfigForm());
  const [showPolicyForm, setShowPolicyForm] = useState(false);
  const [policyForm, setPolicyForm] = useState(emptyPolicyForm());

  async function handleCreateTenantConfig() {
    let configuration;
    try {
      configuration = tenantForm.configuration.trim() ? JSON.parse(tenantForm.configuration) : {};
    } catch {
      showToast("Configuration must be valid JSON", "error");
      return;
    }
    await endpoints.createTenantIdentityConfig({
      tenant_id: tenantForm.tenant_id,
      provider: tenantForm.provider,
      issuer: tenantForm.issuer,
      configuration,
    });
    showToast("Tenant identity config created", "success");
    setTenantForm(emptyTenantConfigForm());
    setShowTenantForm(false);
    refetchTenantConfigs();
  }

  async function handleDeleteTenantConfig(config) {
    if (!window.confirm(`Remove the identity config for tenant "${config.tenant_id}"?`)) return;
    await endpoints.deleteTenantIdentityConfig(config.id);
    showToast("Tenant identity config removed", "success");
    refetchTenantConfigs();
  }

  async function handleCreatePolicy() {
    await endpoints.createAccessPolicy({
      name: policyForm.name,
      project_id: policyForm.project_id || null,
      allowed_roles: policyForm.allowed_roles.split(",").map((r) => r.trim()).filter(Boolean),
      allowed_identity_providers: policyForm.allowed_identity_providers.split(",").map((p) => p.trim()).filter(Boolean),
      max_tokens: policyForm.max_tokens ? Number(policyForm.max_tokens) : null,
      is_active: policyForm.is_active,
    });
    showToast("Access policy created", "success");
    setPolicyForm(emptyPolicyForm());
    setShowPolicyForm(false);
    refetchPolicies();
  }

  async function handleTogglePolicy(policy) {
    await endpoints.updateAccessPolicy(policy.id, { is_active: !policy.is_active });
    showToast(policy.is_active ? "Policy deactivated" : "Policy activated", "success");
    refetchPolicies();
  }

  async function handleDeletePolicy(policy) {
    if (!window.confirm(`Delete access policy "${policy.name}"?`)) return;
    await endpoints.deleteAccessPolicy(policy.id);
    showToast("Access policy deleted", "success");
    refetchPolicies();
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Identity Providers</h2>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-gray-700">Your Session</h3>
        {sessionLoading ? (
          <div className="text-gray-400">Loading...</div>
        ) : (
          <div className="rounded-lg border border-gray-200 bg-white p-4 text-sm">
            <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <div>
                <dt className="text-xs text-gray-500">Email</dt>
                <dd>{session?.email}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Identity Provider</dt>
                <dd>{PROVIDER_LABELS[session?.identity_provider] ?? session?.identity_provider ?? "-"}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Tenant</dt>
                <dd>{session?.tenant_id ?? "-"}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Internal role</dt>
                <dd>{session?.role}</dd>
              </div>
              <div className="col-span-2">
                <dt className="text-xs text-gray-500">IdP roles</dt>
                <dd>{session?.roles?.length ? session.roles.join(", ") : "-"}</dd>
              </div>
              <div className="col-span-2">
                <dt className="text-xs text-gray-500">IdP groups</dt>
                <dd>{session?.groups?.length ? session.groups.join(", ") : "-"}</dd>
              </div>
            </dl>
          </div>
        )}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-gray-700">Identity Provider Configuration</h3>
        <p className="mb-3 text-xs text-gray-500">
          Set via the <code className="rounded bg-gray-100 px-1">IDENTITY_PROVIDER</code> environment variable --
          changing the process-wide default requires a backend restart. Per-tenant overrides are managed below.
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
              { key: "available", label: "Configured", render: (p) => <StatusBadge status={p.available ? "ok" : "down"} /> },
            ]}
            rows={providerConfig?.providers}
            rowKey="name"
            emptyMessage="No providers found"
          />
        )}
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-700">Multi-Tenant Identity Configs</h3>
          <button
            onClick={() => setShowTenantForm(true)}
            className="rounded bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700"
          >
            Add tenant config
          </button>
        </div>
        <p className="mb-3 text-xs text-gray-500">
          Lets different customers authenticate via different providers against this same gateway -- e.g. Customer A via
          Entra, Customer B via Keycloak. Resolved by matching a token's issuer.
        </p>
        {tenantConfigsLoading ? (
          <div className="text-gray-400">Loading...</div>
        ) : (
          <DataTable
            columns={[
              { key: "tenant_id", label: "Tenant" },
              { key: "provider", label: "Provider", render: (c) => PROVIDER_LABELS[c.provider] ?? c.provider },
              { key: "issuer", label: "Issuer" },
              {
                key: "actions",
                label: "",
                render: (c) => (
                  <button onClick={() => handleDeleteTenantConfig(c)} className="text-xs text-red-600 hover:underline">
                    Delete
                  </button>
                ),
              },
            ]}
            rows={tenantConfigs}
            emptyMessage="No per-tenant identity configs -- every tenant uses the process-wide default provider"
          />
        )}
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-700">Access Policies (RBAC / ABAC)</h3>
          <button
            onClick={() => setShowPolicyForm(true)}
            className="rounded bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700"
          >
            Add policy
          </button>
        </div>
        <p className="mb-3 text-xs text-gray-500">
          Evaluated generically over roles/identity-provider, regardless of which IdP authenticated the caller. No
          active policy for a project means unrestricted. <code className="rounded bg-gray-100 px-1">max_tokens</code> is
          stored for forward-compatibility but not yet enforced (same as Budgets).
        </p>
        {policiesLoading ? (
          <div className="text-gray-400">Loading...</div>
        ) : (
          <DataTable
            columns={[
              { key: "name", label: "Name" },
              { key: "allowed_roles", label: "Allowed roles", render: (p) => p.allowed_roles.join(", ") || "any" },
              {
                key: "allowed_identity_providers",
                label: "Allowed providers",
                render: (p) => p.allowed_identity_providers.map((n) => PROVIDER_LABELS[n] ?? n).join(", ") || "any",
              },
              { key: "max_tokens", label: "Max tokens", render: (p) => p.max_tokens ?? "-" },
              {
                key: "is_active",
                label: "Active",
                render: (p) => (
                  <label className="inline-flex items-center gap-2 text-xs">
                    <input type="checkbox" checked={p.is_active} onChange={() => handleTogglePolicy(p)} />
                    {p.is_active ? "active" : "inactive"}
                  </label>
                ),
              },
              {
                key: "actions",
                label: "",
                render: (p) => (
                  <button onClick={() => handleDeletePolicy(p)} className="text-xs text-red-600 hover:underline">
                    Delete
                  </button>
                ),
              },
            ]}
            rows={policies}
            emptyMessage="No access policies configured -- access is currently unrestricted by role/provider"
          />
        )}
      </div>

      {showTenantForm && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg">
            <h3 className="mb-4 text-lg font-semibold">Add tenant identity config</h3>
            <input
              value={tenantForm.tenant_id}
              onChange={(e) => setTenantForm({ ...tenantForm, tenant_id: e.target.value })}
              placeholder="Tenant id (e.g. customer-a)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <select
              value={tenantForm.provider}
              onChange={(e) => setTenantForm({ ...tenantForm, provider: e.target.value })}
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            >
              {PROVIDER_NAMES.map((name) => (
                <option key={name} value={name}>
                  {PROVIDER_LABELS[name]}
                </option>
              ))}
            </select>
            <input
              value={tenantForm.issuer}
              onChange={(e) => setTenantForm({ ...tenantForm, issuer: e.target.value })}
              placeholder="Token issuer (e.g. https://login.microsoftonline.com/{tid}/v2.0)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <textarea
              value={tenantForm.configuration}
              onChange={(e) => setTenantForm({ ...tenantForm, configuration: e.target.value })}
              rows={4}
              placeholder='{"entra_tenant_id": "...", "entra_client_id": "..."}'
              className="mb-4 w-full rounded border border-gray-300 px-3 py-2 font-mono text-xs"
            />
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowTenantForm(false)} className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100">
                Cancel
              </button>
              <button onClick={handleCreateTenantConfig} className="rounded bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700">
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {showPolicyForm && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg">
            <h3 className="mb-4 text-lg font-semibold">Add access policy</h3>
            <input
              value={policyForm.name}
              onChange={(e) => setPolicyForm({ ...policyForm, name: e.target.value })}
              placeholder="Policy name (e.g. finance-ai)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <input
              value={policyForm.project_id}
              onChange={(e) => setPolicyForm({ ...policyForm, project_id: e.target.value })}
              placeholder="Project id (optional -- blank = global)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <input
              value={policyForm.allowed_roles}
              onChange={(e) => setPolicyForm({ ...policyForm, allowed_roles: e.target.value })}
              placeholder="Allowed roles, comma-separated (blank = any)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <input
              value={policyForm.allowed_identity_providers}
              onChange={(e) => setPolicyForm({ ...policyForm, allowed_identity_providers: e.target.value })}
              placeholder="Allowed identity providers, comma-separated (blank = any)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <input
              value={policyForm.max_tokens}
              onChange={(e) => setPolicyForm({ ...policyForm, max_tokens: e.target.value })}
              placeholder="Max tokens (optional, not yet enforced)"
              type="number"
              className="mb-4 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowPolicyForm(false)} className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100">
                Cancel
              </button>
              <button onClick={handleCreatePolicy} className="rounded bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700">
                Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
