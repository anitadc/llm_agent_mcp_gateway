import { useState } from "react";

import { DataTable } from "../components/DataTable";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

const ROLES = ["admin", "team_lead", "developer", "viewer"];

export function Users() {
  const { data: users, loading, refetch } = useApi(() => endpoints.listUsers(), []);
  const { data: organizations } = useApi(() => endpoints.listOrganizations(), []);
  const { showToast } = useToast();

  const [showCreate, setShowCreate] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newRole, setNewRole] = useState("developer");
  const [newOrgId, setNewOrgId] = useState("");
  const [editing, setEditing] = useState(null);
  const [editRole, setEditRole] = useState("developer");
  const [editOrgId, setEditOrgId] = useState("");

  const orgName = (id) => organizations?.find((o) => o.id === id)?.name ?? "-";

  async function handleCreate() {
    if (!newEmail) return;
    await endpoints.createUser({ email: newEmail, role: newRole, organization_id: newOrgId || null });
    showToast("User created", "success");
    setNewEmail("");
    setNewRole("developer");
    setNewOrgId("");
    setShowCreate(false);
    refetch();
  }

  async function handleUpdate(user) {
    await endpoints.updateUser(user.id, { role: editRole, organization_id: editOrgId || null });
    showToast("User updated", "success");
    setEditing(null);
    refetch();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Users</h2>
        <button
          onClick={() => setShowCreate(true)}
          className="rounded bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          New user
        </button>
      </div>

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <DataTable
          columns={[
            { key: "email", label: "Email" },
            {
              key: "role",
              label: "Role",
              render: (u) =>
                editing === u.id ? (
                  <select
                    value={editRole}
                    onChange={(e) => setEditRole(e.target.value)}
                    className="rounded border border-gray-300 px-2 py-1 text-sm"
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                ) : (
                  u.role
                ),
            },
            {
              key: "organization",
              label: "Organization",
              render: (u) =>
                editing === u.id ? (
                  <select
                    value={editOrgId}
                    onChange={(e) => setEditOrgId(e.target.value)}
                    className="rounded border border-gray-300 px-2 py-1 text-sm"
                  >
                    <option value="">None</option>
                    {organizations?.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  orgName(u.organization_id)
                ),
            },
            {
              key: "login_status",
              label: "Login status",
              render: (u) => <StatusBadge status={u.keycloak_sub ? "success" : "blocked"} />,
            },
            {
              key: "actions",
              label: "",
              render: (u) =>
                editing === u.id ? (
                  <div className="space-x-2">
                    <button onClick={() => handleUpdate(u)} className="text-xs text-brand-600 hover:underline">
                      Save
                    </button>
                    <button onClick={() => setEditing(null)} className="text-xs text-gray-500 hover:underline">
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => {
                      setEditing(u.id);
                      setEditRole(u.role);
                      setEditOrgId(u.organization_id ?? "");
                    }}
                    className="text-xs text-brand-600 hover:underline"
                  >
                    Edit
                  </button>
                ),
            },
          ]}
          rows={users}
          emptyMessage="No users yet"
        />
      )}

      {showCreate && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg">
            <h3 className="mb-4 text-lg font-semibold">New user</h3>
            <input
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              placeholder="Email"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <select
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            <select
              value={newOrgId}
              onChange={(e) => setNewOrgId(e.target.value)}
              className="mb-4 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            >
              <option value="">No organization</option>
              {organizations?.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
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
