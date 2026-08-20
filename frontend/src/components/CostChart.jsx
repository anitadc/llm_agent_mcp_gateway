import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

// Renders cost-by-model, since UsageSummary (TDD.md §3.4.1) returns breakdown_by_model,
// not a daily time series -- a bar chart over real data beats a fabricated line chart.
//
// x-axis labels the actual provider model that served the request (resolved_model), not
// the routing-rule alias (model_alias) -- an alias like "gateway-fast" can resolve to
// different real models over time/strategy, so the alias alone isn't a useful chart label.
// Falls back to the alias only for rows with no resolved_model (e.g. a request that never
// reached a provider).
export function CostChart({ data, dataKey = "cost_usd", xKey = "resolved_model" }) {
  const chartData = (data ?? []).map((row) => ({ ...row, [xKey]: row[xKey] || row.model_alias }));
  return (
    <div className="h-64 w-full rounded-lg border border-gray-200 bg-white p-4">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData}>
          <XAxis dataKey={xKey} tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip />
          <Bar dataKey={dataKey} fill="#2563eb" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
