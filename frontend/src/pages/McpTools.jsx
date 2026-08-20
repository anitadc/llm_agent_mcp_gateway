import { useState } from "react";

import { DataTable } from "../components/DataTable";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

export function McpTools() {
  const [q, setQ] = useState("");
  const [expandedId, setExpandedId] = useState(null);
  const { data: tools, loading, refetch } = useApi(() => endpoints.listMcpTools(q), [q]);
  const { showToast } = useToast();

  async function handleSync() {
    try {
      await endpoints.syncMcpTools();
      showToast("Tool registry synced", "success");
      refetch();
    } catch (err) {
      showToast(err?.message ?? "Sync failed", "error");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Tools Explorer</h2>
        <button
          onClick={handleSync}
          className="rounded border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
        >
          Sync now
        </button>
      </div>

      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search tools by name or description..."
        className="w-full max-w-md rounded border border-gray-300 px-3 py-2 text-sm"
      />

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <DataTable
          columns={[
            { key: "name", label: "Tool" },
            {
              key: "source_type",
              label: "Type",
              render: (t) => <StatusBadge status={t.source_type} label={t.source_type.toUpperCase()} />,
            },
            { key: "target", label: "Target" },
            { key: "description", label: "Description" },
            { key: "enabled", label: "Enabled", render: (t) => <StatusBadge status={t.enabled ? "ok" : "down"} /> },
            {
              key: "expand",
              label: "",
              render: (t) => (
                <button
                  onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}
                  className="text-xs text-brand-600 hover:underline"
                >
                  {expandedId === t.id ? "Hide schema" : "View schema"}
                </button>
              ),
            },
          ]}
          rows={tools}
          emptyMessage="No tools registered yet -- register an MCP server or a REST API service"
          renderExpanded={(t) =>
            expandedId === t.id && (
              <tr>
                <td colSpan={6} className="bg-gray-50 px-4 py-3">
                  <pre className="overflow-x-auto text-xs text-gray-600">{JSON.stringify(t.input_schema, null, 2)}</pre>
                </td>
              </tr>
            )
          }
        />
      )}
    </div>
  );
}
