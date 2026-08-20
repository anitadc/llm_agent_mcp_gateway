import { DataTable } from "../components/DataTable";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

export function McpSessions() {
  const { data: sessions, loading } = useApi(() => endpoints.listMcpSessions(), []);

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">MCP Sessions</h2>

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <DataTable
          columns={[
            { key: "client_session_id", label: "Client session id" },
            {
              key: "server_sessions",
              label: "Server sessions",
              render: (s) => (
                <span className="text-xs text-gray-600">
                  {Object.keys(s.server_sessions ?? {}).length} server(s)
                </span>
              ),
            },
            { key: "created_at", label: "Created", render: (s) => new Date(s.created_at).toLocaleString() },
            { key: "last_used_at", label: "Last used", render: (s) => new Date(s.last_used_at).toLocaleString() },
          ]}
          rows={sessions}
          emptyMessage="No MCP sessions yet"
          renderExpanded={(s) => (
            <tr>
              <td colSpan={4} className="bg-gray-50 px-4 py-3">
                <pre className="overflow-x-auto text-xs text-gray-600">{JSON.stringify(s.server_sessions, null, 2)}</pre>
              </td>
            </tr>
          )}
        />
      )}
    </div>
  );
}
