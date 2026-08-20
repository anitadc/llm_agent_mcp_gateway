import { useState } from "react";

import { DataTable } from "../components/DataTable";
import { useToast } from "../components/Toast";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

const PROVIDERS = ["openai", "anthropic", "bedrock"];

export function ProviderConfigs() {
  const { data: configs, loading, refetch } = useApi(() => endpoints.listProviderConfigs(), []);
  const { showToast } = useToast();

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ provider: "openai", display_name: "", credential_ref: "", enabled: true });

  async function handleCreate() {
    if (!form.display_name || !form.credential_ref) return;
    await endpoints.createProviderConfig(form);
    showToast("Provider config created", "success");
    setForm({ provider: "openai", display_name: "", credential_ref: "", enabled: true });
    setShowCreate(false);
    refetch();
  }

  async function toggleEnabled(config) {
    await endpoints.updateProviderConfig(config.id, { enabled: !config.enabled });
    showToast(config.enabled ? "Provider disabled" : "Provider enabled", "success");
    refetch();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Provider Configs</h2>
        <button
          onClick={() => setShowCreate(true)}
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
          ]}
          rows={configs}
          emptyMessage="No providers configured yet"
        />
      )}

      {showCreate && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg">
            <h3 className="mb-4 text-lg font-semibold">New provider config</h3>
            <select
              value={form.provider}
              onChange={(e) => setForm({ ...form, provider: e.target.value })}
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
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
              <button onClick={() => setShowCreate(false)} className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100">
                Cancel
              </button>
              <button onClick={handleCreate} className="rounded bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700">
                Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
