# ai-gateway

Consists of LLM Gateway, Agent Gateway and MCP Gateway — a single FastAPI backend that
fronts LLM providers (OpenAI, Anthropic, AWS Bedrock), lets you register and invoke
governed AI agents, and exposes/consumes Model Context Protocol (MCP) tool servers,
all behind one auth/RBAC/rate-limit/audit layer with a pluggable Identity Provider and
Secret Provider underneath. See `doc/HLD.md` and `doc/LLD.md` for the full architecture.

## Prerequisites

- **Docker Desktop** (with Compose v2/v5) — everything else runs in containers; no local
  Python/Node install is required just to run the app.

## Running it

From the repo root:

```bash
docker compose up --build -d
```

This builds and starts six containers: `postgres`, `valkey`, `keycloak`, `guardrails-mock`,
`gateway-backend`, `gateway-frontend`. The backend runs its database migrations
(`alembic upgrade head`) automatically on startup.

**First boot takes a bit longer** — Keycloak needs ~30-60s to initialize its schema before
it starts serving requests. If `gateway-backend`'s `/ready` check reports
`"keycloak":"down"` right after starting, give it another 30-60 seconds and check again:

```bash
curl http://localhost:8010/ready
# {"db":"ok","valkey":"ok","keycloak":"ok","guardrails":"ok"}  <- all healthy
```

To stop everything: `docker compose down`. To rebuild after a code change: re-run
`docker compose up --build -d`.

## Access points

| Component | URL |
|---|---|
| **Admin UI** | http://localhost:5173 |
| Backend API (Swagger docs) | http://localhost:8010/docs |
| Backend health / readiness | http://localhost:8010/health, http://localhost:8010/ready |
| Keycloak admin console | http://localhost:8180 |

## Default credentials (local/dev only — change before sharing this deployment)

| What | Username | Password |
|---|---|---|
| AI Gateway app login (via Keycloak) | `admin@gateway.local` | `admin123` |
| Keycloak admin console itself | `admin` | `admin` |

The app login has the `admin` realm role, which maps to the gateway's own `admin`
application role — full access to every admin page.

## First-time setup: getting an API key

API keys are scoped to a **Project**, which belongs to an **Organization** — logging in
for the first time provisions your `User` row, but you still need to create these once:

1. Log in at http://localhost:5173 with `admin@gateway.local` / `admin123`.
2. **Organizations** page → create one.
3. **Projects** page → create one under that organization.
4. **API Keys** page → create a key scoped to that project. The raw key (`gw_...`) is
   shown **once**, at creation time only — copy it immediately, it can't be retrieved
   again afterward (only revoked).

Equivalent via the API directly:

```bash
TOKEN=$(curl -s -X POST http://localhost:8180/realms/gateway/protocol/openid-connect/token \
  -d client_id=gateway-frontend -d grant_type=password \
  -d username=admin@gateway.local -d password=admin123 | jq -r .access_token)

ORG_ID=$(curl -s -X POST http://localhost:8010/v1/organizations \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Acme"}' | jq -r .id)

PROJECT_ID=$(curl -s -X POST http://localhost:8010/v1/projects \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"organization_id\":\"$ORG_ID\",\"name\":\"default\"}" | jq -r .id)

curl -s -X POST http://localhost:8010/v1/keys \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"name\":\"my-key\",\"project_id\":\"$PROJECT_ID\",\"scopes\":[]}"
```

## Configuring an LLM provider

Two things need to exist before a chat/embedding call will succeed:

1. **A provider credential**, via the **Secret Management** page ("Set a Secret Value"
   form) or the API — e.g. for OpenAI:

   ```bash
   curl -X POST http://localhost:8010/admin/secrets \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d "{\"secret_name\":\"OPENAI_API_KEY\",\"value\":\"<your key>\"}"
   ```

   Recognized names: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `AWS_ACCESS_KEY_ID` +
   `AWS_SECRET_ACCESS_KEY` (Bedrock). Values are stored encrypted at rest (Postgres +
   Fernet, by default) and never shown again once set.

2. **A routing rule**, via the **Routing Rules** page or the API — this maps the
   `model` alias your requests will use onto a real provider + model:

   | Field | Example |
   |---|---|
   | Model alias | `gpt-4o-mini` (whatever string you'll pass as `"model"`) |
   | Capability | `chat` |
   | Strategy | `priority` |
   | Targets | provider `openai`, model `gpt-4o-mini`, weight `1` |
   | Active | checked |

   A rule created via the UI is global (matches any project), which is what you want
   for a first test.

## Calling the gateway

With an API key from the steps above:

```bash
curl -X POST http://localhost:8010/v1/chat/completions \
  -H "Authorization: Bearer gw_xxxxxxxxxxxx" -H "Content-Type: application/json" \
  -d "{\"model\":\"gpt-4o-mini\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}"
```

No Keycloak token is needed for this call — API keys authenticate directly.

## Configuration notes

- **Env var precedence**: `docker-compose.yml` sets every backend setting explicitly in
  its own `environment:` block, and real Docker environment variables always win over
  `backend/.env`. Editing `backend/.env` only has an effect for a setting that *isn't*
  already listed in `docker-compose.yml`; to change one that is, edit
  `docker-compose.yml` directly (or use a **root-level** `.env`, which Compose itself
  reads for its `${VAR:-default}` substitutions).
- **LLM provider credentials are never read from env/`.env`** — only from the Secret
  Provider (see "Configuring an LLM provider" above), regardless of restart/redeploy.
- Architecture, deployment topology, and a ready-to-use diagram-generation prompt live
  in `doc/HLD.md`, `doc/LLD.md`, and `doc/deployment.md`.
