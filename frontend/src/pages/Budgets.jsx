import { useState } from "react";

import { BudgetProgressBar } from "../components/BudgetProgressBar";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DataTable } from "../components/DataTable";
import { useToast } from "../components/Toast";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

const emptyForm = () => ({
  scopeType: "project",
  organization_id: "",
  project_id: "",
  user_id: "",
  period: "monthly",
  limit_usd: 100,
  alert_threshold_pct: 80,
});

export function Budgets() {
  const { data: budgets, loading, refetch } = useApi(() => endpoints.listBudgets({}), []);
  const { data: organizations } = useApi(() => endpoints.listOrganizations(), []);
  const { data: projects } = useApi(() => endpoints.listProjects(), []);
  const { data: users } = useApi(() => endpoints.listUsers(), []);
  const { showToast } = useToast();

  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm());
  const [deleting, setDeleting] = useState(null);

  const orgName = (id) => organizations?.find((o) => o.id === id)?.name;
  const projectName = (id) => projects?.find((p) => p.id === id)?.name;
  const userEmail = (id) => users?.find((u) => u.id === id)?.email;

  const scopeLabel = (b) =>
    b.organization_id
      ? `org: ${orgName(b.organization_id) ?? b.organization_id}`
      : b.project_id
        ? `project: ${projectName(b.project_id) ?? b.project_id}`
        : `user: ${userEmail(b.user_id) ?? b.user_id}`;

  function openCreate() {
    setEditing("new");
    setForm(emptyForm());
  }

  async function handleSave() {
    if (editing === "new") {
      const payload = {
        period: form.period,
        limit_usd: Number(form.limit_usd),
        alert_threshold_pct: Number(form.alert_threshold_pct),
      };
      if (form.scopeType === "organization") payload.organization_id = form.organization_id;
      if (form.scopeType === "project") payload.project_id = form.project_id;
      if (form.scopeType === "user") payload.user_id = form.user_id;
      await endpoints.createBudget(payload);
      showToast("Budget created", "success");
    } else {
      await endpoints.updateBudget(editing, {
        period: form.period,
        limit_usd: Number(form.limit_usd),
        alert_threshold_pct: Number(form.alert_threshold_pct),
      });
      showToast("Budget updated", "success");
    }
    setEditing(null);
    refetch();
  }

  async function handleDelete() {
    await endpoints.deleteBudget(deleting.id);
    showToast("Budget deleted", "success");
    setDeleting(null);
    refetch();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Budgets</h2>
        <button onClick={openCreate} className="rounded bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700">
          New budget
        </button>
      </div>

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <DataTable
          columns={[
            { key: "scope", label: "Scope", render: scopeLabel },
            { key: "period", label: "Period" },
            { key: "limit_usd", label: "Limit", render: (b) => `$${b.limit_usd.toFixed(2)}` },
            { key: "current_spend_usd", label: "Spent", render: (b) => `$${b.current_spend_usd.toFixed(2)}` },
            {
              key: "progress",
              label: "Progress",
              render: (b) => (
                <div className="w-32">
                  <BudgetProgressBar percentUsed={b.percent_used} alertThresholdPct={b.alert_threshold_pct} />
                </div>
              ),
            },
            {
              key: "actions",
              label: "",
              render: (b) => (
                <div className="space-x-2">
                  <button
                    onClick={() => {
                      setEditing(b.id);
                      setForm({ ...b, scopeType: b.organization_id ? "organization" : b.project_id ? "project" : "user" });
                    }}
                    className="text-xs text-brand-600 hover:underline"
                  >
                    Edit
                  </button>
                  <button onClick={() => setDeleting(b)} className="text-xs text-red-600 hover:underline">
                    Delete
                  </button>
                </div>
              ),
            },
          ]}
          rows={budgets}
          emptyMessage="No budgets configured"
        />
      )}

      {editing && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg">
            <h3 className="mb-4 text-lg font-semibold">{editing === "new" ? "New budget" : "Edit budget"}</h3>

            {editing === "new" && (
              <>
                <label className="block text-xs text-gray-500">Scope</label>
                <select
                  value={form.scopeType}
                  onChange={(e) => setForm({ ...form, scopeType: e.target.value })}
                  className="mb-2 w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
                >
                  <option value="organization">Organization</option>
                  <option value="project">Project</option>
                  <option value="user">User</option>
                </select>

                {form.scopeType === "organization" && (
                  <select
                    value={form.organization_id}
                    onChange={(e) => setForm({ ...form, organization_id: e.target.value })}
                    className="mb-3 w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
                  >
                    <option value="">Select organization...</option>
                    {organizations?.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.name}
                      </option>
                    ))}
                  </select>
                )}
                {form.scopeType === "project" && (
                  <select
                    value={form.project_id}
                    onChange={(e) => setForm({ ...form, project_id: e.target.value })}
                    className="mb-3 w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
                  >
                    <option value="">Select project...</option>
                    {projects?.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                )}
                {form.scopeType === "user" && (
                  <select
                    value={form.user_id}
                    onChange={(e) => setForm({ ...form, user_id: e.target.value })}
                    className="mb-3 w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
                  >
                    <option value="">Select user...</option>
                    {users?.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.email}
                      </option>
                    ))}
                  </select>
                )}
              </>
            )}

            <label className="block text-xs text-gray-500">Period</label>
            <select
              value={form.period}
              onChange={(e) => setForm({ ...form, period: e.target.value })}
              className="mb-3 w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
            >
              <option value="monthly">Monthly</option>
              <option value="daily">Daily</option>
            </select>

            <label className="block text-xs text-gray-500">Limit (USD)</label>
            <input
              type="number"
              value={form.limit_usd}
              onChange={(e) => setForm({ ...form, limit_usd: e.target.value })}
              className="mb-3 w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
            />

            <label className="block text-xs text-gray-500">Alert threshold (%)</label>
            <input
              type="number"
              min="1"
              max="100"
              value={form.alert_threshold_pct}
              onChange={(e) => setForm({ ...form, alert_threshold_pct: e.target.value })}
              className="mb-4 w-full rounded border border-gray-300 px-3 py-1.5 text-sm"
            />

            <div className="flex justify-end gap-2">
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

      <ConfirmDialog
        open={Boolean(deleting)}
        title="Delete budget"
        message="Are you sure you want to delete this budget?"
        confirmLabel="Delete"
        onConfirm={handleDelete}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}
