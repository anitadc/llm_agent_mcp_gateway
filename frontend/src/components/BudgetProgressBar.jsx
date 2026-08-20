export function BudgetProgressBar({ percentUsed, alertThresholdPct }) {
  const pctDisplay = Math.min(percentUsed * 100, 100);
  let color = "bg-green-500";
  if (percentUsed * 100 >= 100) color = "bg-red-500";
  else if (percentUsed * 100 >= alertThresholdPct) color = "bg-amber-500";

  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
      <div className={`h-full ${color}`} style={{ width: `${pctDisplay}%` }} />
    </div>
  );
}
