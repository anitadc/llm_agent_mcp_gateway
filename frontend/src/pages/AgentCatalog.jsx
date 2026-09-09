import { useMemo, useState } from "react";

import { DataTable } from "../components/DataTable";
import { StatusBadge } from "../components/StatusBadge";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

const HEALTH_BADGE = { healthy: "ok", unhealthy: "down", unknown: "rate_limited" };
const STATUS_BADGE = { active: "ok", deprecated: "blocked" };

export function AgentCatalog() {
  const { data: agents, loading } = useApi(() => endpoints.getAgentCatalog(), []);
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!agents) return [];
    const q = search.trim().toLowerCase();
    if (!q) return agents;
    return agents.filter((a) =>
      [a.name, a.description, a.domain, a.owner_team, ...(a.capabilities || [])]
        .filter(Boolean)
        .some((field) => field.toLowerCase().includes(q))
    );
  }, [agents, search]);

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">Agent Catalog</h2>
      <p className="text-sm text-gray-500">
        Browse every agent your project can invoke via <code className="rounded bg-gray-100 px-1">POST /v1/agent-invocations</code> --
        request by <code className="rounded bg-gray-100 px-1">capability</code>, not by name; the gateway resolves which agent
        actually handles it.
      </p>

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search by name, capability, domain, or owner team..."
        className="w-full max-w-md rounded border border-gray-300 px-3 py-2 text-sm"
      />

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <DataTable
          columns={[
            { key: "name", label: "Name" },
            { key: "version", label: "Version" },
            { key: "capabilities", label: "Capabilities", render: (a) => a.capabilities.join(", ") || "—" },
            { key: "domain", label: "Domain", render: (a) => a.domain || "—" },
            { key: "owner_team", label: "Owner", render: (a) => a.owner_team || "—" },
            { key: "status", label: "Status", render: (a) => <StatusBadge status={STATUS_BADGE[a.status] ?? "blocked"} label={a.status} /> },
            {
              key: "health_status",
              label: "Health",
              render: (a) => <StatusBadge status={HEALTH_BADGE[a.health_status] ?? "rate_limited"} label={a.health_status} />,
            },
          ]}
          rows={filtered}
          emptyMessage="No agents available to your project yet"
          renderExpanded={(a) =>
            a.deprecation_notice && (
              <tr>
                <td colSpan={7} className="bg-yellow-50 px-4 py-2 text-xs text-yellow-800">
                  Deprecation notice: {a.deprecation_notice}
                </td>
              </tr>
            )
          }
        />
      )}
    </div>
  );
}
