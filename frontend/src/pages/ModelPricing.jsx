import { useState } from "react";

import { ConfirmDialog } from "../components/ConfirmDialog";
import { DataTable } from "../components/DataTable";
import { useToast } from "../components/Toast";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

const PROVIDERS = ["openai", "anthropic", "bedrock"];

const emptyForm = () => ({ provider: "openai", model: "", prompt_per_1k: "", completion_per_1k: "" });

export function ModelPricing() {
  const { data: pricing, loading, refetch } = useApi(() => endpoints.listModelPricing(), []);
  const { showToast } = useToast();

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(emptyForm());
  const [editing, setEditing] = useState(null);
  const [editForm, setEditForm] = useState({ prompt_per_1k: "", completion_per_1k: "" });
  const [deleting, setDeleting] = useState(null);

  async function handleCreate() {
    if (!form.model || !form.prompt_per_1k) return;
    await endpoints.createModelPricing({
      provider: form.provider,
      model: form.model,
      prompt_per_1k: Number(form.prompt_per_1k),
      completion_per_1k: form.completion_per_1k === "" ? null : Number(form.completion_per_1k),
    });
    showToast("Pricing entry created", "success");
    setForm(emptyForm());
    setShowCreate(false);
    refetch();
  }

  function openEdit(entry) {
    setEditing(entry.id);
    setEditForm({
      prompt_per_1k: String(entry.prompt_per_1k),
      completion_per_1k: entry.completion_per_1k == null ? "" : String(entry.completion_per_1k),
    });
  }

  async function handleUpdate() {
    await endpoints.updateModelPricing(editing, {
      prompt_per_1k: Number(editForm.prompt_per_1k),
      completion_per_1k: editForm.completion_per_1k === "" ? null : Number(editForm.completion_per_1k),
    });
    showToast("Pricing entry updated", "success");
    setEditing(null);
    refetch();
  }

  async function handleDelete() {
    await endpoints.deleteModelPricing(deleting.id);
    showToast("Pricing entry deleted", "success");
    setDeleting(null);
    refetch();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Model Pricing</h2>
        <button
          onClick={() => setShowCreate(true)}
          className="rounded bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          New pricing entry
        </button>
      </div>
      <p className="text-sm text-gray-500">
        Drives both cost calculation (chat &amp; embeddings) and the <code>cost</code> routing strategy. A model with
        no entry here is treated as $0 cost.
      </p>

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <DataTable
          columns={[
            { key: "provider", label: "Provider" },
            { key: "model", label: "Model" },
            {
              key: "prompt_per_1k",
              label: "Prompt $/1k",
              render: (p) =>
                editing === p.id ? (
                  <input
                    type="number"
                    step="0.000001"
                    value={editForm.prompt_per_1k}
                    onChange={(e) => setEditForm({ ...editForm, prompt_per_1k: e.target.value })}
                    className="w-28 rounded border border-gray-300 px-2 py-1 text-sm"
                  />
                ) : (
                  `$${p.prompt_per_1k}`
                ),
            },
            {
              key: "completion_per_1k",
              label: "Completion $/1k",
              render: (p) =>
                editing === p.id ? (
                  <input
                    type="number"
                    step="0.000001"
                    placeholder="n/a (embedding)"
                    value={editForm.completion_per_1k}
                    onChange={(e) => setEditForm({ ...editForm, completion_per_1k: e.target.value })}
                    className="w-28 rounded border border-gray-300 px-2 py-1 text-sm"
                  />
                ) : p.completion_per_1k == null ? (
                  <span className="text-gray-400">n/a (embedding)</span>
                ) : (
                  `$${p.completion_per_1k}`
                ),
            },
            {
              key: "actions",
              label: "",
              render: (p) =>
                editing === p.id ? (
                  <div className="space-x-2">
                    <button onClick={handleUpdate} className="text-xs text-brand-600 hover:underline">
                      Save
                    </button>
                    <button onClick={() => setEditing(null)} className="text-xs text-gray-500 hover:underline">
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="space-x-2">
                    <button onClick={() => openEdit(p)} className="text-xs text-brand-600 hover:underline">
                      Edit
                    </button>
                    <button onClick={() => setDeleting(p)} className="text-xs text-red-600 hover:underline">
                      Delete
                    </button>
                  </div>
                ),
            },
          ]}
          rows={pricing}
          emptyMessage="No pricing entries yet"
        />
      )}

      {showCreate && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg">
            <h3 className="mb-4 text-lg font-semibold">New pricing entry</h3>
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
              value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value })}
              placeholder="Model name (e.g. gpt-4o-mini)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <input
              type="number"
              step="0.000001"
              value={form.prompt_per_1k}
              onChange={(e) => setForm({ ...form, prompt_per_1k: e.target.value })}
              placeholder="Prompt price per 1k tokens (USD)"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <input
              type="number"
              step="0.000001"
              value={form.completion_per_1k}
              onChange={(e) => setForm({ ...form, completion_per_1k: e.target.value })}
              placeholder="Completion price per 1k tokens (blank = embedding-only)"
              className="mb-4 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
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
        open={Boolean(deleting)}
        title="Delete pricing entry"
        message={`Delete pricing for ${deleting?.provider}/${deleting?.model}? Cost and cost-based routing will treat it as free until a new entry is added.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}
