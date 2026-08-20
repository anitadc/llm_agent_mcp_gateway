import { useState } from "react";

import { DataTable } from "../components/DataTable";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { useApi } from "../hooks/useApi";
import { endpoints } from "../services/api";

export function AgentApprovals() {
  const { data: tasks, loading, refetch } = useApi(() => endpoints.listPendingAgentApprovals(), []);
  const { showToast } = useToast();
  const [reasons, setReasons] = useState({});

  async function decide(task, approve) {
    try {
      const action = approve ? endpoints.approveAgentTask : endpoints.rejectAgentTask;
      await action(task.id, { reason: reasons[task.id] || null });
      showToast(`${task.agent_key} / ${task.stage} ${approve ? "approved" : "rejected"}`, "success");
      refetch();
    } catch (err) {
      showToast(err?.message ?? "Decision failed", "error");
    }
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">Agent Approvals</h2>
      <p className="text-sm text-gray-500">
        Pending review-stage tasks across every agent registration. An agent reaches <code>approved</code> only once
        every one of its required stages is approved here; any single rejection rejects the whole registration.
      </p>

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <DataTable
          columns={[
            { key: "agent_key", label: "Agent" },
            { key: "stage", label: "Stage", render: (t) => <StatusBadge status="rate_limited" label={t.stage} /> },
            { key: "created_at", label: "Requested", render: (t) => new Date(t.created_at).toLocaleString() },
            {
              key: "reason",
              label: "Reason (optional)",
              render: (t) => (
                <input
                  value={reasons[t.id] || ""}
                  onChange={(e) => setReasons((prev) => ({ ...prev, [t.id]: e.target.value }))}
                  placeholder="Decision reason"
                  className="w-48 rounded border border-gray-300 px-2 py-1 text-xs"
                />
              ),
            },
            {
              key: "actions",
              label: "",
              render: (t) => (
                <div className="flex gap-3 text-xs">
                  <button onClick={() => decide(t, true)} className="text-green-700 hover:underline">
                    Approve
                  </button>
                  <button onClick={() => decide(t, false)} className="text-red-600 hover:underline">
                    Reject
                  </button>
                </div>
              ),
            },
          ]}
          rows={tasks}
          emptyMessage="No pending approval tasks"
        />
      )}
    </div>
  );
}
