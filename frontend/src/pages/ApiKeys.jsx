import { useState } from "react";

import { ConfirmDialog } from "../components/ConfirmDialog";
import { DataTable } from "../components/DataTable";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

export function ApiKeys() {
  const { data: keys, loading, refetch } = useApi(() => endpoints.listKeys(), []);
  const { data: organizations } = useApi(() => endpoints.listOrganizations(), []);
  const { data: projects } = useApi(() => endpoints.listProjects(), []);
  const { showToast } = useToast();

  const [showCreate, setShowCreate] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyOrg, setNewKeyOrg] = useState("");
  const [newKeyProject, setNewKeyProject] = useState("");
  const [createdKey, setCreatedKey] = useState(null);
  const [revoking, setRevoking] = useState(null);

  const projectsForSelectedOrg = projects?.filter((p) => p.organization_id === newKeyOrg) ?? [];

  function handleOrgChange(orgId) {
    setNewKeyOrg(orgId);
    setNewKeyProject("");
  }

  async function handleCreate() {
    if (!newKeyName || !newKeyProject) return;
    const { data } = await endpoints.createKey({ name: newKeyName, project_id: newKeyProject, scopes: [] });
    setCreatedKey(data);
    setNewKeyName("");
    setNewKeyOrg("");
    setNewKeyProject("");
    setShowCreate(false);
    refetch();
  }

  async function handleRevoke() {
    await endpoints.revokeKey(revoking.id);
    showToast("API key revoked", "success");
    setRevoking(null);
    refetch();
  }

  const projectName = (id) => projects?.find((p) => p.id === id)?.name ?? id;
  const organizationNameForProject = (projectId) => {
    const project = projects?.find((p) => p.id === projectId);
    if (!project) return "-";
    return organizations?.find((o) => o.id === project.organization_id)?.name ?? "-";
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">API Keys</h2>
        <button
          onClick={() => setShowCreate(true)}
          className="rounded bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          Create key
        </button>
      </div>

      {createdKey && (
        <div className="rounded border border-amber-300 bg-amber-50 p-4 text-sm">
          <p className="font-medium text-amber-800">Copy this key now — it won't be shown again.</p>
          <code className="mt-2 block break-all rounded bg-white p-2 text-xs">{createdKey.raw_key}</code>
          <button onClick={() => setCreatedKey(null)} className="mt-2 text-xs text-amber-700 underline">
            Dismiss
          </button>
        </div>
      )}

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <DataTable
          columns={[
            { key: "name", label: "Name" },
            { key: "prefix", label: "Prefix" },
            { key: "organization", label: "Organization", render: (k) => organizationNameForProject(k.project_id) },
            { key: "project", label: "Project", render: (k) => projectName(k.project_id) },
            {
              key: "status",
              label: "Status",
              render: (k) => <StatusBadge status={k.is_active ? "success" : "error"} />,
            },
            { key: "last_used_at", label: "Last used", render: (k) => k.last_used_at ?? "Never" },
            {
              key: "actions",
              label: "",
              render: (k) =>
                k.is_active && (
                  <button onClick={() => setRevoking(k)} className="text-xs text-red-600 hover:underline">
                    Revoke
                  </button>
                ),
            },
          ]}
          rows={keys}
          emptyMessage="No API keys yet"
        />
      )}

      {showCreate && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg">
            <h3 className="mb-4 text-lg font-semibold">Create API key</h3>
            <input
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
              placeholder="Key name"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <select
              value={newKeyOrg}
              onChange={(e) => handleOrgChange(e.target.value)}
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            >
              <option value="">Select organization...</option>
              {organizations?.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
            <select
              value={newKeyProject}
              onChange={(e) => setNewKeyProject(e.target.value)}
              disabled={!newKeyOrg}
              className="mb-4 w-full rounded border border-gray-300 px-3 py-2 text-sm disabled:bg-gray-100 disabled:text-gray-400"
            >
              <option value="">{newKeyOrg ? "Select project..." : "Select an organization first"}</option>
              {projectsForSelectedOrg.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowCreate(false)}
                className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                className="rounded bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={Boolean(revoking)}
        title="Revoke API key"
        message={`Are you sure you want to revoke "${revoking?.name}"? This cannot be undone.`}
        confirmLabel="Revoke"
        onConfirm={handleRevoke}
        onCancel={() => setRevoking(null)}
      />
    </div>
  );
}
