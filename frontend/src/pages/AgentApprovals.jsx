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
  const [reviewerInputs, setReviewerInputs] = useState({});
  const [evidenceInputs, setEvidenceInputs] = useState({});
  const [expandedId, setExpandedId] = useState(null);
  const [commentsById, setCommentsById] = useState({});
  const [commentDraft, setCommentDraft] = useState("");

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

  async function assignReviewer(task) {
    const reviewerUserId = reviewerInputs[task.id];
    if (!reviewerUserId) return;
    try {
      await endpoints.assignApprovalReviewer(task.id, { reviewer_user_id: reviewerUserId });
      showToast(`Reviewer assigned for ${task.agent_key} / ${task.stage}`, "success");
      refetch();
    } catch (err) {
      showToast(err?.message ?? "Assignment failed", "error");
    }
  }

  async function addEvidence(task) {
    const raw = evidenceInputs[task.id];
    if (!raw) return;
    const links = raw.split(",").map((l) => l.trim()).filter(Boolean);
    if (!links.length) return;
    try {
      await endpoints.addApprovalEvidence(task.id, { evidence_links: links });
      setEvidenceInputs((prev) => ({ ...prev, [task.id]: "" }));
      showToast(`Evidence added for ${task.agent_key} / ${task.stage}`, "success");
      refetch();
    } catch (err) {
      showToast(err?.message ?? "Adding evidence failed", "error");
    }
  }

  async function toggleExpand(task) {
    if (expandedId === task.id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(task.id);
    const res = await endpoints.listApprovalComments(task.id);
    setCommentsById((prev) => ({ ...prev, [task.id]: res.data }));
  }

  async function addComment(task) {
    if (!commentDraft.trim()) return;
    await endpoints.addApprovalComment(task.id, { body: commentDraft.trim() });
    setCommentDraft("");
    const res = await endpoints.listApprovalComments(task.id);
    setCommentsById((prev) => ({ ...prev, [task.id]: res.data }));
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">Agent Approvals</h2>
      <p className="text-sm text-gray-500">
        Pending review-stage tasks across every agent registration. An agent reaches <code>approved</code> only once
        every one of its required stages is approved here; any single rejection rejects the whole registration.
        Assigning a reviewer restricts who may decide that specific task -- an admin can always override.
      </p>

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <DataTable
          columns={[
            { key: "agent_key", label: "Agent" },
            { key: "stage", label: "Stage", render: (t) => <StatusBadge status="rate_limited" label={t.stage} /> },
            { key: "submission_round", label: "Round" },
            { key: "created_at", label: "Requested", render: (t) => new Date(t.created_at).toLocaleString() },
            {
              key: "due_at",
              label: "Due",
              render: (t) =>
                t.escalated_at ? (
                  <StatusBadge status="down" label="overdue" />
                ) : t.due_at ? (
                  new Date(t.due_at).toLocaleString()
                ) : (
                  "—"
                ),
            },
            {
              key: "assigned_reviewer_user_id",
              label: "Reviewer",
              render: (t) => (
                <div className="flex items-center gap-1">
                  <input
                    value={reviewerInputs[t.id] ?? t.assigned_reviewer_user_id ?? ""}
                    onChange={(e) => setReviewerInputs((prev) => ({ ...prev, [t.id]: e.target.value }))}
                    placeholder="user id (blank = any admin)"
                    className="w-36 rounded border border-gray-300 px-2 py-1 text-xs"
                  />
                  <button onClick={() => assignReviewer(t)} className="text-xs text-brand-600 hover:underline">
                    Set
                  </button>
                </div>
              ),
            },
            {
              key: "evidence_links",
              label: "Evidence",
              render: (t) => (
                <div className="flex items-center gap-1">
                  <input
                    value={evidenceInputs[t.id] ?? ""}
                    onChange={(e) => setEvidenceInputs((prev) => ({ ...prev, [t.id]: e.target.value }))}
                    placeholder="links, comma-separated"
                    className="w-40 rounded border border-gray-300 px-2 py-1 text-xs"
                  />
                  <button onClick={() => addEvidence(t)} className="text-xs text-brand-600 hover:underline">
                    Add
                  </button>
                  {t.evidence_links.length > 0 && <span className="text-xs text-gray-400">({t.evidence_links.length})</span>}
                </div>
              ),
            },
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
                  <button onClick={() => toggleExpand(t)} className="text-gray-500 hover:underline">
                    {expandedId === t.id ? "Hide comments" : "Comments"}
                  </button>
                </div>
              ),
            },
          ]}
          rows={tasks}
          emptyMessage="No pending approval tasks"
          renderExpanded={(t) =>
            expandedId === t.id && (
              <tr>
                <td colSpan={9} className="space-y-3 bg-gray-50 px-4 py-4">
                  <div className="space-y-2">
                    {(commentsById[t.id] || []).map((c) => (
                      <div key={c.id} className="rounded border border-gray-200 bg-white p-2 text-xs">
                        <div className="text-gray-400">{new Date(c.created_at).toLocaleString()}</div>
                        <div>{c.body}</div>
                      </div>
                    ))}
                    {(commentsById[t.id] || []).length === 0 && (
                      <div className="text-xs text-gray-400">No comments yet</div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      value={commentDraft}
                      onChange={(e) => setCommentDraft(e.target.value)}
                      placeholder="Add a comment for this review..."
                      className="w-96 rounded border border-gray-300 px-2 py-1 text-xs"
                    />
                    <button onClick={() => addComment(t)} className="text-xs text-brand-600 hover:underline">
                      Post
                    </button>
                  </div>
                </td>
              </tr>
            )
          }
        />
      )}
    </div>
  );
}
