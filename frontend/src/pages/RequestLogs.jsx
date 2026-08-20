import { useState } from "react";

import { DataTable } from "../components/DataTable";
import { StatusBadge } from "../components/StatusBadge";
import { useApi } from "../hooks/useApi";
import { usePagination } from "../hooks/usePagination";
import { endpoints } from "../services/api";

const STATUS_OPTIONS = ["success", "error", "blocked", "rate_limited"];

export function RequestLogs() {
  const [organizationId, setOrganizationId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [status, setStatus] = useState("");
  const [modelAlias, setModelAlias] = useState("");
  const [expandedId, setExpandedId] = useState(null);
  const { page, pageSize, setPage, nextPage, prevPage } = usePagination();

  const { data: projects } = useApi(() => endpoints.listProjects(), []);
  const { data: organizations } = useApi(() => endpoints.listOrganizations(), []);
  const { data, loading } = useApi(
    () =>
      endpoints.listLogs({
        organization_id: organizationId || undefined,
        project_id: projectId || undefined,
        status: status || undefined,
        model_alias: modelAlias || undefined,
        page,
        page_size: pageSize,
      }),
    [organizationId, projectId, status, modelAlias, page, pageSize]
  );

  const projectsForSelectedOrg = organizationId
    ? projects?.filter((p) => p.organization_id === organizationId)
    : projects;

  function handleOrgChange(orgId) {
    setOrganizationId(orgId);
    setProjectId("");
    setPage(1);
  }

  const projectName = (id) => projects?.find((p) => p.id === id)?.name ?? id;
  const organizationName = (id) => organizations?.find((o) => o.id === id)?.name ?? "-";

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">Request Logs</h2>

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
            onChange={(e) => {
              setProjectId(e.target.value);
              setPage(1);
            }}
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
          <label className="block text-xs text-gray-500">Status</label>
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm"
          >
            <option value="">Any status</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500">Model alias</label>
          <input
            value={modelAlias}
            onChange={(e) => {
              setModelAlias(e.target.value);
              setPage(1);
            }}
            placeholder="e.g. gateway-fast"
            className="rounded border border-gray-300 px-3 py-1.5 text-sm"
          />
        </div>
      </div>

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <>
          <DataTable
            columns={[
              { key: "created_at", label: "Time" },
              { key: "organization", label: "Organization", render: (r) => organizationName(r.organization_id) },
              { key: "project", label: "Project", render: (r) => projectName(r.project_id) },
              { key: "model_alias", label: "Model alias" },
              { key: "capability", label: "Capability" },
              {
                key: "resolved",
                label: "Resolved",
                render: (r) => `${r.resolved_provider ?? "-"} / ${r.resolved_model ?? "-"}`,
              },
              { key: "status", label: "Status", render: (r) => <StatusBadge status={r.status} /> },
              { key: "latency_ms", label: "Latency (ms)" },
              { key: "tokens", label: "Tokens", render: (r) => `${r.prompt_tokens} / ${r.completion_tokens}` },
              { key: "cache_hit", label: "Cache", render: (r) => (r.cache_hit ? "hit" : "miss") },
              {
                key: "expand",
                label: "",
                render: (r) => (
                  <button
                    onClick={() => setExpandedId(expandedId === r.id ? null : r.id)}
                    className="text-xs text-brand-600 hover:underline"
                  >
                    {expandedId === r.id ? "Hide" : "Details"}
                  </button>
                ),
              },
            ]}
            rows={data?.items}
            emptyMessage="No requests match these filters"
            renderExpanded={(r) =>
              expandedId === r.id && (
                <tr>
                  <td colSpan={11} className="bg-gray-50 px-4 py-3 text-xs">
                    <div className="font-medium text-gray-600">Guardrail results</div>
                    {r.guardrail_results?.length ? (
                      <ul className="mt-1 space-y-1">
                        {r.guardrail_results.map((g, i) => (
                          <li key={i}>
                            <StatusBadge status={g.allowed ? "success" : "blocked"} /> {g.direction}
                            {g.violations?.length > 0 && ` — ${g.violations.map((v) => v.type).join(", ")}`}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div className="mt-1 text-gray-400">No guardrail results recorded</div>
                    )}
                  </td>
                </tr>
              )
            }
          />

          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>
              Page {page} — {data?.total ?? 0} total
            </span>
            <div className="space-x-2">
              <button onClick={prevPage} disabled={page <= 1} className="rounded px-3 py-1 hover:bg-gray-100 disabled:opacity-40">
                Previous
              </button>
              <button onClick={nextPage} className="rounded px-3 py-1 hover:bg-gray-100">
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
