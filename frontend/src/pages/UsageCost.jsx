import { useState } from "react";

import { CostChart } from "../components/CostChart";
import { DataTable } from "../components/DataTable";
import { StatCard } from "../components/StatCard";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

export function UsageCost() {
  const [organizationId, setOrganizationId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const { data: projects } = useApi(() => endpoints.listProjects(), []);
  const { data: organizations } = useApi(() => endpoints.listOrganizations(), []);
  const {
    data: usage,
    loading,
    refetch,
  } = useApi(
    () =>
      endpoints.getUsageSummary({
        organization_id: organizationId || undefined,
        project_id: projectId || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      }),
    [organizationId, projectId, dateFrom, dateTo]
  );

  const projectsForSelectedOrg = organizationId
    ? projects?.filter((p) => p.organization_id === organizationId)
    : projects;

  function handleOrgChange(orgId) {
    setOrganizationId(orgId);
    setProjectId("");
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Usage &amp; Cost</h2>

      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-xs text-gray-500">Organization</label>
          <select
            value={organizationId}
            onChange={(e) => handleOrgChange(e.target.value)}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm"
          >
            <option value="">All organizations</option>
            {organizations?.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500">Project</label>
          <select
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm"
          >
            <option value="">All projects</option>
            {projectsForSelectedOrg?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500">From</label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500">To</label>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm"
          />
        </div>
        <button onClick={refetch} className="rounded bg-gray-100 px-3 py-1.5 text-sm hover:bg-gray-200">
          Apply
        </button>
      </div>

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard label="Total cost" value={`$${(usage?.total_cost_usd ?? 0).toFixed(2)}`} />
            <StatCard label="Total requests" value={usage?.total_requests ?? 0} />
            <StatCard label="Cache hit rate" value={`${((usage?.cache_hit_rate ?? 0) * 100).toFixed(1)}%`} />
          </div>

          <CostChart data={usage?.breakdown_by_model ?? []} />

          <DataTable
            columns={[
              { key: "model_alias", label: "Model alias" },
              { key: "resolved_provider", label: "Provider" },
              { key: "resolved_model", label: "Resolved model" },
              { key: "requests", label: "Requests" },
              { key: "cost_usd", label: "Cost", render: (r) => `$${r.cost_usd.toFixed(4)}` },
            ]}
            rows={usage?.breakdown_by_model}
            emptyMessage="No usage in this range"
          />
        </>
      )}
    </div>
  );
}
