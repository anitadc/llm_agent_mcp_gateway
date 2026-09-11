import { useState } from "react";

import { DataTable } from "../components/DataTable";
import { useToast } from "../components/Toast";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

const PROVIDERS = ["openai", "anthropic", "bedrock"];

function emptyForm() {
  return { provider: "openai", display_name: "", credential_ref: "", enabled: true };
}

export function ProviderConfigs() {
  const { data: configs, loading, refetch } = useApi(() => endpoints.listProviderConfigs(), []);
  const { showToast } = useToast();

  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm());

  function openCreate() {
    setEditing("new");
    setForm(emptyForm());
  }

  function openEdit(config) {
    setEditing(config.id);
    setForm({
      provider: config.provider,
      display_name: config.display_name,
      credential_ref: config.credential_ref,
      enabled: config.enabled,
    });
  }

  async function handleSave() {
    if (!form.display_name || !form.credential_ref) return;
    if (editing === "new") {
      await endpoints.createProviderConfig(form);
      showToast("Provider config created", "success");
    } else {
      await endpoints.updateProviderConfig(editing, {
        display_name: form.display_name,
        credential_ref: form.credential_ref,
        enabled: form.enabled,
      });
      showToast("Provider config updated", "success");
    }
    setEditing(null);
    refetch();
  }

  async function toggleEnabled(config) {
    await endpoints.updateProviderConfig(config.id, { enabled: !config.enabled });
    showToast(config.enabled ? "Provider disabled" : "Provider enabled", "success");
    refetch();
  }

  async function handleDelete(config) {
    if (!window.confirm(`Delete provider config "${config.display_name}"?`)) return;
    await endpoints.deleteProviderConfig(config.id);
    showToast("Provider config deleted", "success");
    refetch();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Provider Configs</h2>
        <button
          onClick={openCreate}
          className="rounded bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          New provider config
        </button>
      </div>

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <DataTable
          columns={[
            { key: "provider", label: "Provider" },
            { key: "display_name", label: "Display name" },
            { key: "credential_ref", label: "Credential env var" },
            {
              key: "enabled",
              label: "Enabled",
              render: (c) => (
                <label className="inline-flex items-center gap-2 text-xs">
                  <input type="checkbox" checked={c.enabled} onChange={() => toggleEnabled(c)} />
                  {c.enabled ? "enabled" : "disabled"}
                </label>
              ),
            },
            {
              key: "actions",
              label: "",
              render: (c) => (
                <div className="flex gap-3">
                  <button onClick={() => openEdit(c)} className="text-xs text-brand-600 hover:underline">
                    Edit
                  </button>
                  <button onClick={() => handleDelete(c)} className="text-xs text-red-600 hover:underline">
                    Delete
                  </button>
                </div>
              ),
            },
          ]}
          rows={configs}
          emptyMessage="No providers configured yet"
        />
      )}

      {editing && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg">
            <h3 className="mb-4 text-lg font-semibold">{editing === "new" ? "New provider config" : "Edit provider config"}</h3>
            <select
              value={form.provider}
              disabled={editing !== "new"}
              onChange={(e) => setForm({ ...form, provider: e.target.value })}
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm disabled:bg-gray-100"
            >
              {PROVIDERS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <input
              value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
              placeholder="Display name (e.g. OpenAI prod)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <input
              value={form.credential_ref}
              onChange={(e) => setForm({ ...form, credential_ref: e.target.value })}
              placeholder="Credential env var (e.g. OPENAI_API_KEY)"
              className="mb-4 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <div className="flex justify-end gap-2">
              <button onClick={() => setEditing(null)} className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100">
                Cancel
              </button>
              <button onClick={handleSave} className="rounded bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700">
                {editing === "new" ? "Create" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
