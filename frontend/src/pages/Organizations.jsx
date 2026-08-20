import { useState } from "react";

import { DataTable } from "../components/DataTable";
import { useToast } from "../components/Toast";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

export function Organizations() {
  const { data: organizations, loading, refetch } = useApi(() => endpoints.listOrganizations(), []);
  const { showToast } = useToast();
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [renaming, setRenaming] = useState(null);
  const [renameValue, setRenameValue] = useState("");

  async function handleCreate() {
    if (!name) return;
    await endpoints.createOrganization({ name });
    showToast("Organization created", "success");
    setName("");
    setShowCreate(false);
    refetch();
  }

  async function handleRename(org) {
    await endpoints.updateOrganization(org.id, { name: renameValue });
    showToast("Organization renamed", "success");
    setRenaming(null);
    refetch();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Organizations</h2>
        <button
          onClick={() => setShowCreate(true)}
          className="rounded bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          New organization
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
              render: (o) =>
                renaming === o.id ? (
                  <div className="flex items-center gap-2">
                    <input
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      className="rounded border border-gray-300 px-2 py-1 text-sm"
                    />
                    <button onClick={() => handleRename(o)} className="text-xs text-brand-600 hover:underline">
                      Save
                    </button>
                    <button onClick={() => setRenaming(null)} className="text-xs text-gray-500 hover:underline">
                      Cancel
                    </button>
                  </div>
                ) : (
                  o.name
                ),
            },
            { key: "created_at", label: "Created" },
            {
              key: "actions",
              label: "",
              render: (o) =>
                renaming !== o.id && (
                  <button
                    onClick={() => {
                      setRenaming(o.id);
                      setRenameValue(o.name);
                    }}
                    className="text-xs text-brand-600 hover:underline"
                  >
                    Rename
                  </button>
                ),
            },
          ]}
          rows={organizations}
          emptyMessage="No organizations yet"
        />
      )}

      {showCreate && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg">
            <h3 className="mb-4 text-lg font-semibold">New organization</h3>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Organization name"
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
