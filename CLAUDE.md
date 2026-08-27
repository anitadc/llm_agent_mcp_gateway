# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

## Project Overview

Custom LLM Gateway — a self-hosted middleware layer between internal applications and multiple LLM providers (OpenAI, Anthropic, Bedrock). Presents OpenAI-compatible APIs for both chat completions (`/v1/chat/completions`) and embeddings (`/v1/embeddings`), enforces auth/RBAC/rate-limits/guardrails before any provider call, routes with automatic failover, and tracks cost/usage attributed to user → project → organization.

Full requirements: see [PRD.md](PRD.md). This file is about *how to work in the repo*; PRD.md is about *what it must do and why*.

**Status**: scaffold in progress. If a section below describes something not yet present on disk, treat it as the target layout to build toward, not a description of current state — check the actual directory contents before assuming a file exists.

## Commands

### Backend (Python)

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env               # fill in provider keys, DB/Valkey/Keycloak URLs
alembic upgrade head                # apply migrations
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# Swagger UI at http://localhost:8000/docs
```

### Frontend (Node.js)

```bash
cd frontend
npm install
npm run dev      # Vite dev server, proxies /api -> localhost:8000
npm run build
```

### Everything via Docker Compose

```bash
docker compose up --build
# postgres, valkey, keycloak, guardrails-mock, gateway-backend, gateway-frontend
```

### Tests

```bash
cd backend && pytest
```

## Architecture

### Request lifecycle (owned by `backend/app/`)

```
Client -> request_id_middleware -> auth_middleware (API key or Keycloak token)
       -> rate_limit_middleware (Valkey)
       -> api/v1/chat.py handler
       -> services/guardrails (pre-call check on prompt)
       -> services/cache_service (Valkey cache lookup)
       -> services/routing/router.py (resolve model alias -> provider/model via routing_rules, LiteLLM Router)
       -> LiteLLM provider call with automatic fallback
       -> services/guardrails (post-call check on completion)
       -> response returned to client
       -> BackgroundTask: logging_service + cost_service write request_logs/cost_ledger/guardrail_results
```

`api/v1/embeddings.py` follows this same lifecycle with two differences, not a parallel pipeline: `services/routing/router.py` resolves against `routing_rules` rows tagged `capability='embedding'` (never the `chat` ones, and vice versa), and there is no post-call guardrails step — an embedding response is a vector, not text, so only the pre-call (input) check applies. See TDD.md §3.2.5/§3.3 before changing either router.

See PRD.md §8 for the four key architecture decisions (LiteLLM embedded not sidecar, Keycloak scoped to human auth only, guardrails as a pluggable adapter, embeddings as a stateless proxy not a vector store) — don't relitigate these without checking there first.

### Backend (`backend/app/`)

| Path | Role |
|---|---|
| `core/config.py` | Pydantic Settings — all env vars, single source of config |
| `core/security.py` | API key hashing/verification, JWT/OIDC token validation |
| `db/models/` | SQLAlchemy models: organizations, projects, users, project_users, api_keys, provider_configs, routing_rules, request_logs, cost_ledger, budgets, guardrail_results |
| `repositories/` | Thin per-model DB-access classes, used only by services, never by routers directly |
| `services/routing/` | `router.py` wraps `litellm.Router`, resolves model aliases via `routing_rules` (filtered by `capability`: chat vs. embedding), handles fallback; exposes both `complete()` (chat) and `embed()` |
| `services/guardrails/` | `base.py` defines the `GuardrailsClient` interface; `http_client.py` is the REST implementation against `GUARDRAILS_BASE_URL`. Chat calls both `check_prompt`/`check_response`; embeddings only ever call `check_prompt` |
| `services/cost_service.py` | Token usage → cost calculation, writes `cost_ledger`; embedding pricing entries omit `completion_per_1k` |
| `services/rate_limit_service.py` / `cache_service.py` | Valkey-backed sliding-window limits and response cache |
| `api/v1/` | Routers — one file per domain (`chat`, `embeddings`, `keys`, `organizations`, `projects`, `users`, `project_users`, `provider_configs`, `usage`, `logs`, `routing_rules`, `budgets`, `health`), each with its own OpenAPI tag |
| `middleware/` | `request_id_middleware`, `auth_middleware`, `rate_limit_middleware` |
| `alembic/` | Migrations — always add a migration for schema changes, never hand-edit the DB |

Each `services/<domain>/` package exposes one primary class via its `__init__.py` (facade pattern) — routers call the facade, never reach into internals.

### Frontend (`frontend/src/`)

| Path | Role |
|---|---|
| `App.jsx` | React Router routes |
| `pages/` | Login, Dashboard, ApiKeys, UsageCost, RequestLogs, RoutingRules, Budgets, Organizations, Projects, Users, ProviderConfigs (no dedicated page for embeddings — it's a machine-to-machine API, surfaced only via UsageCost/RequestLogs capability filters) |
| `services/api.js` | Centralized Axios client; every backend call defined here, interceptor attaches bearer token |
| `services/authService.js` | `keycloak-js` adapter — login/logout/token refresh |
| `hooks/useApi.js` | Data-fetching hook (loading/error/retry) |
| `components/` | Shared UI: Layout, StatCard, DataTable, CostChart, StatusBadge |

Vite proxies `/api` to `http://localhost:8000` in dev (`vite.config.js`).

## Conventions

- Async SQLAlchemy + asyncpg on the hot path; DB sessions only via FastAPI `Depends`, never module-level globals.
- All config through `core/config.py` (Pydantic Settings) — no bare `os.environ` reads scattered in the codebase.
- Logging/cost writes happen in `BackgroundTasks` so they never add latency to the client response.
- API keys are stored hashed; never log a raw key or provider credential.
- Every schema change goes through Alembic — no manual `CREATE TABLE`/`ALTER TABLE`.
- New routers get their own OpenAPI tag and their own file under `api/v1/`.

## Configuration

All runtime config lives in `backend/.env` (template: `backend/.env.example`). Key sections: `DATABASE_URL`, `VALKEY_URL`, `KEYCLOAK_*` (realm/client/URL), `GUARDRAILS_BASE_URL`, per-provider API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, Bedrock creds), rate-limit defaults, cache TTL. Root-level `.env.example` documents the variables `docker-compose.yml` itself consumes (image versions, ports).

## Known Deferred Items (see PRD.md §4, §11, §12)

Do not silently "complete" these unless asked — they're intentionally out of scope for the current MVP pass: true token-streaming with incremental guardrail scanning (MVP buffers full completions), hard budget enforcement/blocking, encrypted-at-rest provider credentials, Kubernetes manifests, CI pipeline. The guardrails microservice's real API contract is also unconfirmed — the gateway is built against the `GuardrailsClient` adapter interface specifically so the real contract can be dropped in later without touching call sites.
