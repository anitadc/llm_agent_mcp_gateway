const COLORS = {
  success: "bg-green-100 text-green-800",
  error: "bg-red-100 text-red-800",
  blocked: "bg-amber-100 text-amber-800",
  rate_limited: "bg-purple-100 text-purple-800",
  ok: "bg-green-100 text-green-800",
  down: "bg-red-100 text-red-800",
  mcp: "bg-blue-100 text-blue-800",
  rest: "bg-teal-100 text-teal-800",
};

export function StatusBadge({ status, label }) {
  const cls = COLORS[status] ?? "bg-gray-100 text-gray-800";
  return <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{label ?? status}</span>;
}
