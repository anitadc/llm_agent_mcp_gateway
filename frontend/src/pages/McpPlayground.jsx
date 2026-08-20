import { useState } from "react";

import { useToast } from "../components/Toast";
import { endpoints } from "../services/api";

const METHODS = ["initialize", "tools/list", "tools/call"];

const DEFAULT_PARAMS = {
  initialize: "{}",
  "tools/list": "{}",
  "tools/call": '{\n  "name": "get_top_threats",\n  "arguments": {}\n}',
};

export function McpPlayground() {
  const { showToast } = useToast();
  const [method, setMethod] = useState("initialize");
  const [paramsText, setParamsText] = useState(DEFAULT_PARAMS.initialize);
  const [sessionId, setSessionId] = useState("");
  const [response, setResponse] = useState(null);
  const [sending, setSending] = useState(false);

  function handleMethodChange(next) {
    setMethod(next);
    setParamsText(DEFAULT_PARAMS[next] ?? "{}");
  }

  async function handleSend() {
    let params;
    try {
      params = paramsText.trim() ? JSON.parse(paramsText) : {};
    } catch {
      showToast("Params must be valid JSON", "error");
      return;
    }

    setSending(true);
    try {
      const res = await endpoints.callMcp(
        { jsonrpc: "2.0", id: String(Date.now()), method, params },
        sessionId || undefined
      );
      const returnedSessionId = res.headers?.["mcp-session-id"];
      if (returnedSessionId) setSessionId(returnedSessionId);
      setResponse(res.data);
    } catch (err) {
      setResponse({ error: err });
      showToast(err?.message ?? "Request failed", "error");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">MCP Playground</h2>
      <p className="text-sm text-gray-500">
        Send raw JSON-RPC requests to POST /mcp to test tool discovery and execution end to end.
      </p>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-gray-500">Method</label>
            <select
              value={method}
              onChange={(e) => handleMethodChange(e.target.value)}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
            >
              {METHODS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs text-gray-500">Params (JSON)</label>
            <textarea
              value={paramsText}
              onChange={(e) => setParamsText(e.target.value)}
              rows={10}
              className="w-full rounded border border-gray-300 px-3 py-2 font-mono text-xs"
            />
          </div>

          <div>
            <label className="block text-xs text-gray-500">Mcp-Session-Id (auto-filled after initialize)</label>
            <input
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              placeholder="none yet -- call initialize first"
              className="w-full rounded border border-gray-300 px-3 py-2 font-mono text-xs"
            />
          </div>

          <button
            onClick={handleSend}
            disabled={sending}
            className="rounded bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {sending ? "Sending..." : "Send"}
          </button>
        </div>

        <div>
          <label className="block text-xs text-gray-500">Response</label>
          <pre className="h-full min-h-[16rem] overflow-auto rounded border border-gray-200 bg-gray-50 p-3 text-xs">
            {response ? JSON.stringify(response, null, 2) : "No request sent yet"}
          </pre>
        </div>
      </div>
    </div>
  );
}
