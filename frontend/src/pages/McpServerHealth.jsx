import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

const HEALTH_BADGE = { healthy: "ok", unhealthy: "down", unknown: "rate_limited" };

export function McpServerHealth() {
  const { id } = useParams();
  const { showToast } = useToast();
  const [checking, setChecking] = useState(false);

  const { data: servers, loading: serversLoading, refetch: refetchServers } = useApi(
    () => endpoints.listMcpServers(),
    []
  );
  const { data: stats, loading: statsLoading, refetch: refetchStats } = useApi(
    () => endpoints.getMcpServerStats(id, 60),
    [id]
  );

  const server = servers?.find((s) => s.id === id);

  async function handleHealthCheck() {
    setChecking(true);
    try {
      await endpoints.healthCheckMcpServer(id);
      showToast("Health check complete", "success");
      refetchServers();
      refetchStats();
    } catch (err) {
      showToast(err?.message ?? "Health check failed", "error");
    } finally {
      setChecking(false);
    }
  }

  if (serversLoading) return <div className="text-gray-400">Loading...</div>;
  if (!server) return <div className="text-gray-400">Server not found. <Link to="/mcp/servers" className="text-brand-600 hover:underline">Back to registry</Link></div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <Link to="/mcp/servers" className="text-xs text-brand-600 hover:underline">
            &larr; Back to registry
          </Link>
          <h2 className="text-xl font-semibold">{server.name}</h2>
          <p className="text-sm text-gray-500">{server.base_url}</p>
        </div>
        <button
          onClick={handleHealthCheck}
          disabled={checking}
          className="rounded bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {checking ? "Checking..." : "Run health check"}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Status" value={server.status} />
        <StatCard label="Health" value={<StatusBadge status={HEALTH_BADGE[server.health_status] ?? server.health_status} />} />
        <StatCard label="Tools discovered" value={server.tool_count} />
        <StatCard label="Last heartbeat" value={server.last_heartbeat ? new Date(server.last_heartbeat).toLocaleString() : "never"} />
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-gray-700">Discovery (tool sync)</h3>
        <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
          <div>
            <dt className="text-xs text-gray-500">Last sync status</dt>
            <dd>{server.last_sync_status ? <StatusBadge status={server.last_sync_status === "success" ? "ok" : "down"} /> : "-"}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500">Last sync at</dt>
            <dd>{server.last_sync_at ? new Date(server.last_sync_at).toLocaleString() : "never"}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500">Sync latency</dt>
            <dd>{server.last_sync_latency_ms != null ? `${server.last_sync_latency_ms} ms` : "-"}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500">Protocol version</dt>
            <dd>{server.protocol_version ?? "-"}</dd>
          </div>
        </dl>
        {server.last_sync_error && (
          <div className="mt-3 rounded bg-red-50 px-3 py-2 text-xs text-red-700">{server.last_sync_error}</div>
        )}
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-gray-700">Usage (last {stats?.window_minutes ?? 60} minutes)</h3>
        {statsLoading ? (
          <div className="text-gray-400">Loading...</div>
        ) : (
          <div className="grid grid-cols-3 gap-4">
            <StatCard label="Requests" value={stats?.request_count ?? 0} />
            <StatCard label="Failures" value={stats?.error_count ?? 0} />
            <StatCard
              label="Avg latency"
              value={stats?.avg_latency_ms != null ? `${Math.round(stats.avg_latency_ms)} ms` : "-"}
            />
          </div>
        )}
      </div>
    </div>
  );
}
