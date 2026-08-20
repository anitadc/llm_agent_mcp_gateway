import { CostChart } from "../components/CostChart";
import { StatCard } from "../components/StatCard";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

export function Dashboard() {
  const { data: usage, loading } = useApi(() => endpoints.getUsageSummary({}), []);

  if (loading) return <div className="text-gray-400">Loading...</div>;

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Dashboard</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Requests (30d)" value={usage?.total_requests ?? 0} />
        <StatCard label="Cost (30d)" value={`$${(usage?.total_cost_usd ?? 0).toFixed(2)}`} />
        <StatCard label="Cache hit rate" value={`${((usage?.cache_hit_rate ?? 0) * 100).toFixed(1)}%`} />
        <StatCard
          label="Tokens (prompt / completion)"
          value={`${usage?.total_prompt_tokens ?? 0} / ${usage?.total_completion_tokens ?? 0}`}
        />
      </div>
      <div>
        <h3 className="mb-2 text-sm font-medium text-gray-600">Cost by model</h3>
        <CostChart data={usage?.breakdown_by_model ?? []} />
      </div>
    </div>
  );
}
