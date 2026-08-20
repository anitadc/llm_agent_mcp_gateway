import { useState } from "react";

import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";
import { DataTable } from "./DataTable";
import { useToast } from "./Toast";

export function ProjectMembersPanel({ project, users }) {
  const {
    data: memberships,
    loading,
    refetch,
  } = useApi(() => endpoints.listProjectUsers(project.id), [project.id]);
  const [selectedUserId, setSelectedUserId] = useState("");
  const { showToast } = useToast();

  const userEmail = (userId) => users?.find((u) => u.id === userId)?.email ?? userId;

  async function handleAdd() {
    if (!selectedUserId) return;
    await endpoints.addProjectUser({ project_id: project.id, user_id: selectedUserId });
    setSelectedUserId("");
    showToast("Member added", "success");
    refetch();
  }

  async function handleEnd(membership) {
    await endpoints.updateProjectUser(membership.id, { end_date: new Date().toISOString().slice(0, 10) });
    showToast("Membership ended", "success");
    refetch();
  }

  if (loading) return <div className="p-4 text-sm text-gray-400">Loading members...</div>;

  return (
    <div className="border-t border-gray-100 bg-gray-50 p-4">
      <div className="mb-3 flex items-center gap-2">
        <select
          value={selectedUserId}
          onChange={(e) => setSelectedUserId(e.target.value)}
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        >
          <option value="">Add member...</option>
          {users?.map((u) => (
            <option key={u.id} value={u.id}>
              {u.email}
            </option>
          ))}
        </select>
        <button onClick={handleAdd} className="rounded bg-brand-600 px-3 py-1 text-sm text-white hover:bg-brand-700">
          Add
        </button>
      </div>
      <DataTable
        columns={[
          { key: "user", label: "User", render: (m) => userEmail(m.user_id) },
          { key: "start_date", label: "Since" },
          { key: "status", label: "Status", render: (m) => (m.end_date ? `Ended ${m.end_date}` : "Active") },
          {
            key: "actions",
            label: "",
            render: (m) =>
              !m.end_date && (
                <button onClick={() => handleEnd(m)} className="text-xs text-red-600 hover:underline">
                  End membership
                </button>
              ),
          },
        ]}
        rows={memberships}
        emptyMessage="No members yet"
      />
    </div>
  );
}
