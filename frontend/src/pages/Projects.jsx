import { useState } from "react";

import { DataTable } from "../components/DataTable";
import { ProjectMembersPanel } from "../components/ProjectMembersPanel";
import { useToast } from "../components/Toast";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

export function Projects() {
  const { data: projects, loading, refetch } = useApi(() => endpoints.listProjects(), []);
  const { data: organizations } = useApi(() => endpoints.listOrganizations(), []);
  const { data: users } = useApi(() => endpoints.listUsers(), []);
  const { showToast } = useToast();

  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newOrgId, setNewOrgId] = useState("");
  const [renaming, setRenaming] = useState(null);
  const [renameValue, setRenameValue] = useState("");
  const [expandedId, setExpandedId] = useState(null);

  const orgName = (id) => organizations?.find((o) => o.id === id)?.name ?? id;

  async function handleCreate() {
    if (!newName || !newOrgId) return;
    await endpoints.createProject({ name: newName, organization_id: newOrgId });
    showToast("Project created", "success");
    setNewName("");
    setNewOrgId("");
    setShowCreate(false);
    refetch();
  }

  async function handleRename(project) {
    await endpoints.updateProject(project.id, { name: renameValue });
    showToast("Project renamed", "success");
    setRenaming(null);
    refetch();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Projects</h2>
        <button
          onClick={() => setShowCreate(true)}
          className="rounded bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          New project
        </button>
      </div>

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <DataTable
          columns={[
            {
              key: "name",
              label: "Name",
              render: (p) =>
                renaming === p.id ? (
                  <div className="flex items-center gap-2">
                    <input
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      className="rounded border border-gray-300 px-2 py-1 text-sm"
                    />
                    <button onClick={() => handleRename(p)} className="text-xs text-brand-600 hover:underline">
                      Save
                    </button>
                    <button onClick={() => setRenaming(null)} className="text-xs text-gray-500 hover:underline">
                      Cancel
                    </button>
                  </div>
                ) : (
                  p.name
                ),
            },
            { key: "organization", label: "Organization", render: (p) => orgName(p.organization_id) },
            { key: "created_at", label: "Created" },
            {
              key: "actions",
              label: "",
              render: (p) => (
                <div className="space-x-2">
                  {renaming !== p.id && (
                    <button
                      onClick={() => {
                        setRenaming(p.id);
                        setRenameValue(p.name);
                      }}
                      className="text-xs text-brand-600 hover:underline"
                    >
                      Rename
                    </button>
                  )}
                  <button
                    onClick={() => setExpandedId(expandedId === p.id ? null : p.id)}
                    className="text-xs text-brand-600 hover:underline"
                  >
                    {expandedId === p.id ? "Hide members" : "Members"}
                  </button>
                </div>
              ),
            },
          ]}
          rows={projects}
          emptyMessage="No projects yet"
          renderExpanded={(p) =>
            expandedId === p.id && (
              <tr>
                <td colSpan={4} className="p-0">
                  <ProjectMembersPanel project={p} users={users} />
                </td>
              </tr>
            )
          }
        />
      )}

      {showCreate && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg">
            <h3 className="mb-4 text-lg font-semibold">New project</h3>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Project name"
              className="mb-3 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
            <select
              value={newOrgId}
              onChange={(e) => setNewOrgId(e.target.value)}
              className="mb-4 w-full rounded border border-gray-300 px-3 py-2 text-sm"
            >
              <option value="">Select organization...</option>
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
