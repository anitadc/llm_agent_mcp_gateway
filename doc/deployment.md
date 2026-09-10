# Deployment Diagram — Microsoft 365 Copilot Prompt

Paste the prompt below into Microsoft 365 Copilot (Copilot in PowerPoint's "Create a
presentation/diagram" prompt box, Copilot in Whiteboard, or the Visio Copilot agent all
accept this format). It describes the current Docker Compose deployment topology of the
AI Gateway platform (`docker-compose.yml`) plus the external systems it integrates with
through configuration, so Copilot has enough detail to lay out a real deployment diagram
rather than a generic three-tier sketch.

If your Copilot surface asks for a diagram *type*, choose **deployment diagram** or
**architecture diagram**. If it offers a layout choice, prefer **layered / swimlane** so
the three tiers below stay visually separated.

---

## Prompt

```
Create a deployment architecture diagram for a system called "AI Gateway" (a Custom LLM
Gateway providing LLM routing, an Agent Gateway, and an MCP Gateway). Lay it out as three
horizontal swimlanes, top to bottom: "Clients", "Docker Compose Host (single node)", and
"External Integrations (configurable)". Use rounded rectangles for every node, group
boxes with a dashed-border container labeled "docker-compose.yml" around the middle
lane, and draw labeled, directional arrows for every connection below. Use a distinct
fill color per lane. Add a small legend noting: solid arrows = always active with the
default configuration; dashed arrows = one of several interchangeable backends selected
by environment variable (only one is active per deployment).

LANE 1 — Clients (outside the host):
- "Admin Browser (React SPA user)"
- "External API Clients (API-key callers)" -- programmatic callers of the gateway's REST
  API using a scoped API key instead of a browser session

LANE 2 — Docker Compose Host (single node), six containers:
- "tcsaigateway-frontend" -- React SPA, served via `serve`, container port 5173
- "tcsaigateway-backend" -- FastAPI app (Uvicorn), container port 8000, runs `alembic upgrade
  head` on startup before serving traffic
- "postgres" -- postgres:16-alpine, container port 5432, database "ai_gateway"
- "valkey" -- valkey/valkey (Redis-compatible), container port 6379
- "keycloak" -- quay.io/keycloak/keycloak:25.0, start-dev with a pre-imported realm,
  container port 8080 -- the default Identity Provider
- "guardrails-mock" -- reference/mock content-guardrails HTTP service, container port
  9000

Connections inside/from Lane 2 (solid, always active):
- "Admin Browser" -> "tcsaigateway-frontend" : HTTPS, browser loads the SPA
- "Admin Browser" -> "keycloak" : HTTPS, browser-facing login/redirect flow (OIDC)
- "tcsaigateway-frontend" -> "tcsaigateway-backend" : HTTPS/REST, VITE_API_BASE
- "External API Clients" -> "tcsaigateway-backend" : HTTPS/REST, Bearer API key or IdP token
- "tcsaigateway-backend" -> "postgres" : asyncpg (SQL), primary datastore for all app tables
  including request logs, cost ledger, and (new) an encrypted `secrets` table
- "tcsaigateway-backend" -> "valkey" : Redis protocol, response cache / secret cache / rate
  limiter counters / MCP OAuth2 token cache
- "tcsaigateway-backend" -> "keycloak" : HTTPS, JWKS fetch for token validation (internal
  Docker network hostname, distinct from the browser-facing URL above)
- "tcsaigateway-backend" -> "guardrails-mock" : HTTPS/REST, content safety checks on
  prompts/completions

LANE 3 — External Integrations (outside the host, each reached only if configured):
- "LLM Providers" node containing three sub-items: "OpenAI", "Anthropic", "AWS Bedrock"
- "Enterprise Identity Providers" node containing five sub-items: "Microsoft Entra ID",
  "Auth0", "Okta", "AWS IAM Identity Center", "Google Identity" -- alternatives to the
  built-in Keycloak, selected via the IDENTITY_PROVIDER setting
- "Secret Backends" node containing four sub-items: "AWS Secrets Manager", "GCP Secret
  Manager", "Azure Key Vault", "HashiCorp Vault" -- alternatives to the default
  Postgres-backed secret storage, selected via the SECRET_PROVIDER setting
- "MCP Tool Servers" -- externally hosted Model Context Protocol servers, registered
  dynamically at runtime, not fixed at deploy time
- "Registered REST APIs (API Registry)" -- arbitrary enterprise REST endpoints exposed
  to agents/MCP callers as tools, credentials resolved through the Secret Provider layer

Connections from Lane 2 to Lane 3 (dashed, outbound HTTPS, only the selected backend per
category is actually reached at runtime):
- "tcsaigateway-backend" -> "LLM Providers" : HTTPS, chat/embeddings completion calls (via
  LiteLLM routing)
- "tcsaigateway-backend" -> "Enterprise Identity Providers" : HTTPS, JWKS/token validation,
  selected instead of Keycloak
- "tcsaigateway-backend" -> "Secret Backends" : HTTPS, credential resolution, selected instead
  of the built-in Postgres secret storage
- "tcsaigateway-backend" -> "MCP Tool Servers" : HTTPS, JSON-RPC (MCP protocol) tool discovery
  and invocation
- "tcsaigateway-backend" -> "Registered REST APIs (API Registry)" : HTTPS, REST tool execution

Title the diagram "AI Gateway — Deployment Architecture (Docker Compose)". Add a footnote
under the diagram: "Every external dependency (identity provider, secret backend, LLM
provider) is selected through configuration, not hard-coded -- the same container images
run unmodified on a VM, an existing container platform, or a managed Kubernetes cluster
with an externally provisioned Postgres/Redis-compatible pair. Kubernetes manifests and a
CI/CD pipeline are not yet part of this repository."
```

---

## After generating

Save the resulting image/diagram alongside this file (e.g. `doc/deployment-diagram.png`)
and reference it in `doc/HLD.md` §6 "Deployment Architecture" if you want it to replace or
sit next to the existing Mermaid sketch there.
