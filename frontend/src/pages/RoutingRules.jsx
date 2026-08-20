import { useState } from "react";

import { DataTable } from "../components/DataTable";
import { useToast } from "../components/Toast";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

const PROVIDERS = ["openai", "anthropic", "bedrock"];
const STRATEGIES = ["priority", "cost", "latency"];
const CAPABILITIES = ["chat", "embedding"];

const emptyTarget = () => ({ provider: "openai", model: "", weight: 1 });

const emptyForm = () => ({
  model_alias: "",
  capability: "chat",
  strategy: "priority",
  targets: [emptyTarget()],
  priority: 100,
  is_active: true,
});

export function RoutingRules() {
  const { data: rules, loading, refetch } = useApi(() => endpoints.listRoutingRules(), []);
  const { showToast } = useToast();
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm());

  function openCreate() {
    setEditing("new");
    setForm(emptyForm());
  }

  function openEdit(rule) {
    setEditing(rule.id);
    setForm({ ...rule, targets: rule.targets.map((t) => ({ ...t })) });
  }

  function updateTarget(index, field, value) {
    const targets = form.targets.map((t, i) => (i === index ? { ...t, [field]: value } : t));
    setForm({ ...form, targets });
  }

  function addTarget() {
    setForm({ ...form, targets: [...form.targets, emptyTarget()] });
  }

  function removeTarget(index) {
    setForm({ ...form, targets: form.targets.filter((_, i) => i !== index) });
  }

  async function handleSave() {
    const payload = {
      ...form,
      targets: form.targets.filter((t) => t.model),
    };
    if (editing === "new") {
      await endpoints.createRoutingRule(payload);
      showToast("Routing rule created", "success");
    } else {
      const { model_alias, capability, ...updatable } = payload;
      await endpoints.updateRoutingRule(editing, updatable);
      showToast("Routing rule updated", "success");
    }
    setEditing(null);
    refetch();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Routing Rules</h2>
        <button onClick={openCreate} className="rounded bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700">
          New rule
        </button>
      </div>

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <DataTable
          columns={[
            { key: "model_alias", label: "Alias" },
            { key: "capability", label: "Capability" },
            { key: "strategy", label: "Strategy" },
            { key: "scope", label: "Scope", render: (r) => (r.project_id ? "project" : r.user_id ? "end-user" : "global") },
            { key: "priority", label: "Priority" },
            { key: "targets", label: "Targets", render: (r) => r.targets.map((t) => `${t.provider}/${t.model}`).join(", ") },
            { key: "is_active", label: "Active", render: (r) => (r.is_active ? "yes" : "no") },
            {
              key: "actions",
              label: "",
              render: (r) => (
                <button onClick={() => openEdit(r)} className="text-xs text-brand-600 hover:underline">
                  Edit
                </button>
              ),
            },
          ]}
          rows={rules}
          emptyMessage="No routing rules configured"
        />
      )}

      {editing && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-lg">
            <h3 className="mb-4 text-lg font-semibold">{editing === "new" ? "New routing rule" : "Edit routing rule"}</h3>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-500">Model alias</label>
                <input
                  value={form.model_alias}
                  disabled={editing !== "new"}
                  onChange={(e) => setForm({ ...form, model_alias: e.target.value })}
                  className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm disabled:bg-gray-100"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500">Capability</label>
                <select
                  value={form.capability}
                  disabled={editing !== "new"}
                  onChange={(e) => setForm({ ...form, capability: e.target.value })}
                  className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm disabled:bg-gray-100"
                >
                  {CAPABILITIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-500">Strategy</label>
                <select
                  value={form.strategy}
                  onChange={(e) => setForm({ ...form, strategy: e.target.value })}
                  className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
                >
                  {STRATEGIES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-500">Priority</label>
                <input
                  type="number"
                  value={form.priority}
                  onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })}
                  className="w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
                />
              </div>
            </div>

            <div className="mt-4">
              <label className="mb-1 block text-xs text-gray-500">Targets (tried in order)</label>
              <div className="space-y-2">
                {form.targets.map((target, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <select
                      value={target.provider}
                      onChange={(e) => updateTarget(i, "provider", e.target.value)}
                      className="rounded border border-gray-300 px-2 py-1 text-sm"
                    >
                      {PROVIDERS.map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                    <input
                      value={target.model}
                      onChange={(e) => updateTarget(i, "model", e.target.value)}
                      placeholder="model name"
                      className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm"
                    />
                    <input
                      type="number"
                      value={target.weight ?? ""}
                      onChange={(e) => updateTarget(i, "weight", Number(e.target.value))}
                      placeholder="weight"
                      className="w-20 rounded border border-gray-300 px-2 py-1 text-sm"
                    />
                    <button onClick={() => removeTarget(i)} className="text-xs text-red-600 hover:underline">
                      Remove
                    </button>
                  </div>
                ))}
              </div>
              <button onClick={addTarget} className="mt-2 text-xs text-brand-600 hover:underline">
                + Add target
              </button>
            </div>

            <label className="mt-4 flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
              />
              Active
            </label>

            <div className="mt-6 flex justify-end gap-2">
              <button onClick={() => setEditing(null)} className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100">
                Cancel
              </button>
              <button onClick={handleSave} className="rounded bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700">
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
