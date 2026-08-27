#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://localhost:8010}"
TOKEN="${TOKEN:-}"
API_KEY="${API_KEY:-}"

if [[ -z "$TOKEN" && -z "$API_KEY" ]]; then
  echo "Set TOKEN for admin/user endpoints or API_KEY for machine endpoints."
  echo "Example:"
  echo "  export TOKEN=..."
  echo "  export API_KEY=..."
  echo "  export BASE=http://localhost:8010"
  exit 1
fi

echo "== Health =="
curl -sS "$BASE/health"
echo

echo "== Ready =="
curl -sS "$BASE/ready"
echo

echo "== Auth token exchange =="
if [[ -n "$TOKEN" ]]; then
  curl -sS -X POST "$BASE/v1/auth/token/exchange" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json"
  echo
fi

echo "== List organizations =="
if [[ -n "$TOKEN" ]]; then
  curl -sS "$BASE/v1/organizations" \
    -H "Authorization: Bearer $TOKEN"
  echo
fi

echo "== Create organization =="
if [[ -n "$TOKEN" ]]; then
  curl -sS -X POST "$BASE/v1/organizations" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name":"Acme Corp"}'
  echo
fi

echo "== Create project =="
if [[ -n "$TOKEN" ]]; then
  curl -sS -X POST "$BASE/v1/projects" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"organization_id":"ORG_ID","name":"Default Project"}'
  echo
fi

echo "== Create API key =="
if [[ -n "$TOKEN" ]]; then
  curl -sS -X POST "$BASE/v1/keys" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name":"dev-key","project_id":"PROJECT_ID","scopes":["tool:read","tool:execute"]}'
  echo
fi

echo "== Routing rule: chat alias =="
if [[ -n "$TOKEN" ]]; then
  curl -sS -X POST "$BASE/v1/routing-rules" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "model_alias":"gateway-fast",
      "project_id":"PROJECT_ID",
      "capability":"chat",
      "strategy":"priority",
      "targets":[{"provider":"openai","model":"gpt-4o-mini","weight":1}],
      "priority":100,
      "is_active":true
    }'
  echo
fi

echo "== Chat completions =="
if [[ -n "$API_KEY" ]]; then
  curl -sS -X POST "$BASE/v1/chat/completions" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
      "model":"gateway-fast",
      "messages":[{"role":"user","content":"Hello from the gateway"}],
      "temperature":0.7,
      "max_tokens":256
    }'
  echo
fi

echo "== Embeddings =="
if [[ -n "$API_KEY" ]]; then
  curl -sS -X POST "$BASE/v1/embeddings" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
      "model":"text-embedding-3-small",
      "input":"hello world",
      "user":"demo-user"
    }'
  echo
fi

echo "== Usage summary =="
if [[ -n "$TOKEN" ]]; then
  curl -sS "$BASE/v1/usage/summary?organization_id=ORG_ID&project_id=PROJECT_ID" \
    -H "Authorization: Bearer $TOKEN"
  echo
fi

echo "== Request logs =="
if [[ -n "$TOKEN" ]]; then
  curl -sS "$BASE/v1/logs?organization_id=ORG_ID&project_id=PROJECT_ID&page=1&page_size=25" \
    -H "Authorization: Bearer $TOKEN"
  echo
fi

echo "== MCP JSON-RPC tools/list =="
if [[ -n "$API_KEY" ]]; then
  curl -sS -X POST "$BASE/mcp" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
      "jsonrpc":"2.0",
      "id":1,
      "method":"tools/list",
      "params":{}
    }'
  echo
fi

echo "== MCP JSON-RPC initialize =="
if [[ -n "$API_KEY" ]]; then
  curl -sS -X POST "$BASE/mcp" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
      "jsonrpc":"2.0",
      "id":1,
      "method":"initialize",
      "params":{"protocolVersion":"2024-11-05","capabilities":{"tools":{}}}
    }'
  echo
fi

echo "== Secret providers =="
if [[ -n "$TOKEN" ]]; then
  curl -sS "$BASE/admin/secrets/providers" \
    -H "Authorization: Bearer $TOKEN"
  echo
fi

echo "== Identity providers =="
if [[ -n "$TOKEN" ]]; then
  curl -sS "$BASE/admin/identity/providers" \
    -H "Authorization: Bearer $TOKEN"
  echo
fi

echo "== List agents =="
if [[ -n "$TOKEN" ]]; then
  curl -sS "$BASE/v1/agents" \
    -H "Authorization: Bearer $TOKEN"
  echo
fi

echo "== Agent invocation =="
if [[ -n "$API_KEY" ]]; then
  curl -sS -X POST "$BASE/v1/agent-invocations" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
      "capability":"lead_research",
      "operation":"get_profile",
      "payload":{"company":"Contoso"}
    }'
  echo
fi
