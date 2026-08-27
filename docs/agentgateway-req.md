Agent Gateway Platform

Master Specification for GenAI Code Generation of a Runnable Enterprise

Platform

Version 1.0 • 14 August 2026 • Implementation Baseline

0. Generator Directive — Read First
This document is the controlling specification for an AI coding agent that must generate a runnable Agent Gateway
Platform. The generator MUST implement the platform, not merely produce examples, stubs or pseudo-code. Every P0
requirement in this document must be backed by executable code, configuration, migrations, tests, documentation and a
working local deployment.
GENERATOR CONTRACT
You are the principal engineer implementing an enterprise Agent Gateway Platform.
Generate a complete runnable monorepo for the PLATFORM only.
The DEMO CONSUMER APPLICATION MUST be a separate repository/code base.
The platform and demo must communicate exactly as an external consumer would:
through documented public SDK/API/A2A interfaces. The platform MUST NOT import
demo application source code or depend on demo-only modules.
Do not create fake implementations for critical P0 paths.
Do not hard-code agents, endpoints, policies, approvals or routes.
Do not bypass approval, authentication, authorization, trust or audit.
Use configuration, database state and standard protocol contracts.
Use the official A2A specification as the interoperability contract.
A2A is the preferred protocol for Agent-to-Agent communication wherever applicable.
Use the exact current official A2A Agent Card/schema rather than inventing a proprietary card.
Generate:
- source code
- database migrations
- seed/configuration
- OpenAPI
- A2A endpoints/adapters
- Python SDK
- LangGraph integration package
- tests
- Docker Compose
- production-oriented deployment manifests
- README and runbook
The generated result must start locally and demonstrate a real end-to-end
consumer invocation without modifying the consumer&#39;s business-agent logic.
The official A2A specification currently identifies 1.0.0 as the latest released version. Its normative protocol definition is
the authoritative A2A data contract; the generator must pin a compatible A2A 1.0.x implementation and isolate protocol-
version-specific code so future upgrades do not require redesign. citeturn0search0turn0search4

1. Product Vision

Agent Gateway is the enterprise control and interoperability plane for agent-to-agent communication. It provides governed
agent registration, approval, discovery, A2A interoperability, identity, access control, trust, policy, routing, execution
mediation, resilience, observability, audit and runtime control.
Consumer / Agent
|
v
+------------------------------------------------+
| AGENT GATEWAY |
| Registration | Approval | Registry | Discovery |
| Identity | Authentication | Authorization |
| Trust | Data Policy | A2A | Routing |
| Invocation | Resilience | Audit | Telemetry |
+----------------------+-------------------------+
|
+---------+----------+
| |
Local LangGraph Remote Agent
Agent Boundary A2A
| |
same process independent
The design should take useful architectural inspiration from the open-source agentgateway project, which positions itself
as an AI-native proxy for A2A/MCP with security, governance and observability, but this specification defines the target
platform independently. citeturn0search1turn0search6

2. Hard Architectural Principles
1. A2A-first: for Agent-to-Agent interactions, prefer A2A whenever applicable and supported.
2. AgentCard is standards-based: use the official A2A Agent Card schema and discovery semantics.
3. Approval before publication: no production agent is discoverable/routeable until the configured approval gates pass.
4. Approval is not authorization: every invocation is separately authenticated and authorized.
5. Zero trust: registered agents are not inherently trusted.
6. Consumer independence: consumers request capabilities; they do not select protocol, endpoint or route.
7. Same-process governance: LangGraph subgraphs that are designated Agent Boundaries receive the same logical
invocation, security, policy and audit treatment as remote agents.
8. No consumer coupling: the demo consumer is a separate repository and is never imported by the platform.
9. Configuration-first: routes, policies, agents, approvals, trust, endpoints and environments are data/configuration.
10. Fail closed: missing identity, invalid authorization or failed governance checks deny protected invocations.
11. Observable by default: every governed invocation has trace, metrics, structured logs and audit events.
12. Protocol fallback is explicit: HTTP/gRPC fallback cannot bypass A2A eligibility, access control or policy.

3. Scope and P0/P1/P2
Capability Priority Required outcome
Agent Registration P0 Submit and validate agents
Approval Workflow P0 Configurable human/automated gates
A2A Agent Card P0 Official standard-compatible card
A2A Discovery P0 Well-known/catalog/direct discovery

support

Agent Registry P0 Versioned lifecycle and metadata
Access Control P0 RBAC+ABAC, deny by default
Identity/Auth P0 JWT/OIDC + workload identity; mTLS

adapter

Trust P0 Trust relationships and levels
A2A Invocation P0 Remote agent communication
LangGraph Boundary Adapter P0 Same-process governed subgraph
Routing P0 A2A-first, health-aware, failover

HTTP fallback P0 Explicitly configured only
Resilience P0 Timeout/retry/circuit/fallback
Audit/Telemetry P0 OpenTelemetry + immutable audit
Python SDK P0 Consumer-facing invocation API
Admin API P0 Registration/approval/policy/config

APIs

Demo Consumer Separate repo External consumer validation
Semantic Discovery P2 Embedding-based capability

matching

Federation P1/P2 Gateway-to-gateway federation
Reputation P2 Quality/reputation route scoring

4. Platform vs Consumer Repository Boundary
This is a non-negotiable repository boundary. The platform repository contains reusable gateway infrastructure. The
demo repository is an independent consumer and must be capable of being moved to another Git repository without
changing the platform.
Platform repository Separate demo repository
Gateway control plane Order consumer application
Agent registry/approval Order business workflow
A2A server/client adapter Demo LangGraph graph
Policy/trust/access control Demo Pricing Agent
Routing/executors Demo Risk Agent
LangGraph integration SDK Demo UI/API
Python SDK Demo configuration
DB migrations Demo test scenarios
Observability/audit Demo-specific assertions
Docker/K8s platform deployment Consumer deployment
REPOSITORY A
agent-gateway-platform/
control-plane/
data-plane/
sdk/
integrations/langgraph/
schemas/
deploy/
tests/
REPOSITORY B
agent-gateway-demo-consumer/
order-agent/
agents/
consumer-api/
tests/
docker-compose.demo.yml
README.md
Repository A MUST NOT import Repository B.
Repository B MUST consume Repository A via SDK/API/A2A.

5. External Contract Boundary
The consumer-facing contract consists of the Python SDK, REST/OpenAPI APIs and A2A protocol endpoints. Internal
Python modules are not consumer contracts.
Consumer:
gateway = AgentGatewayClient(...)
result = await gateway.invoke_capability(
capability=&quot;pricing&quot;,

operation=&quot;calculate-price&quot;,
payload=payload,
context=InvocationContext(...)
)
The consumer does NOT specify:
- target endpoint
- HTTP vs A2A
- route
- retry implementation
- credentials for target
- internal registry ID

6. Agent Lifecycle and Approval
DRAFT
-&gt; SUBMITTED
-&gt; VALIDATING
-&gt; UNDER_REVIEW
|-- SECURITY
|-- TECHNICAL
|-- BUSINESS
|-- DATA/GOVERNANCE
|-- PRODUCTION (risk dependent)
-&gt; APPROVED
-&gt; PUBLISHED
-&gt; ACTIVE
|-- SUSPENDED
|-- DEPRECATED
|-- RETIRED
-&gt; REJECTED (from validation/review)
 Registration alone never makes an agent active.
 Approval is version-specific.
 Material changes trigger re-validation/re-approval.
 Approval tasks record approver, decision, reason and timestamp.
 Suspension immediately removes route eligibility.
 External/federated agents require explicit trust/partner approval.

7. A2A Standards Contract
The implementation must conform to the current official A2A specification. A2A defines Agent Cards, discovery,
tasks/messages, modalities, protocol bindings and security semantics. The current specification says Agent Cards are
available through a well-known URI, registries/catalogs or direct configuration. citeturn0search0turn0search4
https://&lt;agent-domain&gt;/.well-known/agent-card.json
The implementation must:
- validate AgentCard against the pinned A2A schema
- support supportedInterfaces
- support protocol version negotiation
- support declared security requirements
- support capabilities and skills
- preserve A2A task/message semantics
- support signed cards where configured
- avoid exposing secrets in AgentCards

A2A 1.0 supports multiple protocol bindings; the official specification defines AgentInterface entries containing URL,
protocol binding and protocol version. The gateway should select among declared interfaces according to policy and
compatibility. citeturn0search4

8. Agent Card vs Enterprise Metadata
STANDARD A2A AGENT CARD
identity
description
provider
version
supportedInterfaces
capabilities
securitySchemes/securityRequirements
input/output modes
skills
documentation
optional signature/extensions
INTERNAL ENTERPRISE REGISTRY
agentId
owner/team
domain
risk
trust
approval state
data classification
workload identity
artifact digest
source commit
deployment
SLA
policy bindings
route bindings
The platform may expose authenticated extended Agent Cards when supported, but sensitive enterprise metadata
remains access-controlled. The official A2A specification explicitly describes extended cards and recommends protecting
sensitive information. citeturn0search0

9. Registration Validation
13. Parse registration.
14. Validate Agent Card against official A2A schema.
15. Validate A2A version/interface declarations.
16. Validate endpoint ownership and HTTPS requirements for production.
17. Validate security scheme declarations.
18. Validate skills, capabilities and modalities.
19. Validate identity/workload binding.
20. Validate deployment artifact/version.
21. Classify risk.
22. Create approval workflow.
23. Publish only after approval completion.

10. Identity and Access Control
Use zero-trust, deny-by-default authorization. Hybrid RBAC + ABAC should evaluate caller, target, capability, operation,
tenant, environment, region, data classification, human delegation, trust and route context.

decision = authorize(
callerIdentity,
targetAgent,
capability,
operation,
tenant,
environment,
dataClassification,
trustContext,
delegationContext
)
ALLOW only if all mandatory controls pass.
 JWT/OIDC validation.
 Workload identity.
 mTLS adapter.
 Target-audience-bound downstream credentials.
 No blind forwarding of inbound credentials.
 Optional on-behalf-of/delegation context.
 Tenant and region isolation.
 Field/data-classification policy.
 Approval state is an eligibility condition.

11. Trust Model
Level Meaning
T0 Unknown
T1 Registered internal
T2 Enterprise trusted
T3 Privileged
T4 Approved external partner
T5 Public/untrusted
Trust never replaces authorization. It is an input to authorization and route eligibility.

12. A2A-First Routing
route(request):
candidates = discover(request)
candidates = lifecycle_filter(candidates)
candidates = access_filter(candidates)
candidates = trust_filter(candidates)
candidates = data_policy_filter(candidates)
candidates = health_filter(candidates)
if eligible A2A route exists:
choose A2A
elif explicit fallback is approved:
choose fallback
emit ProtocolFallback
else:
deny
return route
 Local same-process Agent Boundary is represented as A2A-semantic invocation but executes locally.
 Remote A2A is preferred.

 HTTP/gRPC fallback is explicit and auditable.
 Policy denial cannot be bypassed by fallback.
 Consumer code never chooses the protocol.

13. Same-Process LangGraph Integration
A network proxy cannot observe a Python subgraph call that stays within one process. The platform therefore provides a
framework adapter, not invasive modifications to every node.
Order Agent LangGraph
|
+-- ordinary nodes -----------------&gt; unchanged
|
+-- configured Agent Boundary
|
v
GatewayLangGraphInterceptor
|
+-- context extraction
+-- identity
+-- authorization
+-- trust/policy
+-- logical A2A invocation
+-- local executor
+-- telemetry/audit
|
v
Pricing subgraph
 Only configured Agent Boundaries are governed.
 Business node/subgraph logic is not changed.
 LangGraph-specific code is isolated in integrations/langgraph.
 Use public framework APIs where possible; version-specific internals are isolated behind adapters.
 Same-process execution cannot bypass gateway policy.

14. Invocation Contract
InvokeRequest:
capability
operation
payload
callerAgentId?
workflowId?
threadId?
runId?
nodeId?
correlationId?
traceId?
tenant?
environment?
dataClassification?
delegationContext?
metadata?
InvokeResponse:
invocationId
status
targetAgentId
targetVersion
protocol

executionMode
routeId
authorizationDecision
policyDecision
latencyMs
result?
error?

15. Protocol/Execution Model
Mode Protocol Use
LOCAL_SUBGRAPH A2A-semantic logical contract Same-process LangGraph agent

boundary

REMOTE_A2A A2A Preferred remote agent
communication

REMOTE_HTTP HTTP Explicit fallback/non-agent integration
REMOTE_GRPC gRPC Explicit fallback/legacy integration
FEDERATED_A2A A2A External gateway/partner agent
The platform must not confuse protocol binding with the semantic agent contract. A2A remains the canonical
interoperability contract for remote agent-to-agent communication.

16. Resilience
 Per-route timeout.
 Bounded retries with backoff and jitter.
 Circuit breaker.
 Health/readiness filtering.
 Explicit fallback.
 Idempotency key for retryable operations.
 Long-running A2A task handling.
 Streaming support where declared.
 Dead-letter/error event support for asynchronous workflows.

17. Observability and Audit
Every governed invocation must produce trace context, structured logs, metrics, route decision, authorization decision
and audit record.
Trace:
workflow
-&gt; langgraph node
-&gt; agent boundary
-&gt; gateway invocation
-&gt; authz
-&gt; policy
-&gt; route
-&gt; A2A
-&gt; target agent
 Never log tokens/secrets.
 Payload logging is opt-in and redacted.
 Record selected protocol and fallback reason.
 Record approval state used for route eligibility.
 Record policy IDs and decision reason codes.
 Audit approval lifecycle separately from runtime invocation audit.

18. Data Model
Entity Core fields
AgentRegistration id, agentId, version, card, submittedBy, status, riskClass
AgentCardSnapshot agentId, version, schemaVersion, cardJson, digest,

signature

AgentVersion agentId, version, artifactDigest, lifecycle, approvalStatus
ApprovalWorkflow id, registrationId, state, stages
ApprovalTask id, workflowId, role, approver, decision, reason
AgentIdentityBinding agentId, workloadIdentity, endpoint, certRef, artifactDigest
Capability/Skill agentId, skillId, operation, schemas
Endpoint/Interface agentId, url, protocolBinding, protocolVersion, health
Policy scope, priority, conditions, effect, version
Permission subject, action, resource, conditions
TrustRelationship source, target, level, status
Route capability, operation, target, protocol, priority, strategy
Invocation id, caller, target, route, protocol, status, timings
AuditRecord actor, action, resource, decision, reason, timestamp
Configuration scope, key, value, version

19. API Surface
Method Path Purpose
POST /api/v1/registrations Submit agent
GET /api/v1/registrations/{id} Registration details
POST /api/v1/registrations/{id}/validate Validate
POST /api/v1/registrations/{id}/submit Submit approval
GET /api/v1/registrations/{id}/approvals Approval tasks
POST /api/v1/approvals/{taskId}/approve Approve
POST /api/v1/approvals/{taskId}/reject Reject
POST /api/v1/registrations/{id}/publish Publish
GET /api/v1/agents/{id} Agent details
GET /api/v1/agents/{id}/agent-card Approved Agent Card
POST /api/v1/agents/{id}/suspend Suspend
POST /api/v1/discovery Capability discovery
POST /api/v1/policy/evaluate Authorization/policy decision
POST /api/v1/routes/evaluate Route decision
POST /api/v1/invocations Invoke
GET /api/v1/invocations/{id} Invocation detail
GET /api/v1/audit Audit search

20. A2A Endpoint Requirements
 Expose the standards-compliant Agent Card at the applicable well-known URI.
 Implement the selected A2A 1.0 binding(s).
 Validate A2A-Version and protocol compatibility.
 Support authentication declared by the Agent Card.
 Support task lifecycle and message semantics.
 Support streaming/async features when enabled.
 Propagate trace/correlation context.
 Apply authorization and trust before dispatch.
 Provide a gateway facade when the platform represents multiple approved agents behind a controlled endpoint.

21. Configuration
platform:
defaultAuthorization: DENY
a2a:

preferredVersion: &quot;1.0&quot;
preferA2A: true
allowFallback: false
approval:
requiredForProduction: true
telemetry:
enabled: true
routing:
strategy: HEALTH_AWARE
a2aFirst: true
security:
authentication:
jwt: true
workloadIdentity: true
mtls: true
authorization:
model: RBAC_ABAC
failClosed: true

22. Repository Structure — Platform
agent-gateway-platform/
├── README.md
├── AGENTS.md
├── Makefile
├── pyproject.toml
├── .env.example
├── docker-compose.yml
├── docs/
│ ├── architecture/
│ ├── api/
│ ├── operations/
│ └── security/
├── schemas/
│ ├── a2a/
│ ├── invocation/
│ ├── approval/
│ └── events/
├── control-plane/
│ ├── app/
│ │ ├── api/
│ │ ├── domain/
│ │ ├── application/
│ │ ├── discovery/
│ │ ├── approval/
│ │ ├── identity/
│ │ ├── authorization/
│ │ ├── trust/
│ │ ├── policy/
│ │ ├── routing/
│ │ ├── invocation/
│ │ ├── registry/
│ │ ├── observability/
│ │ └── main.py
│ ├── migrations/
│ └── tests/
├── runtime/
│ ├── core/
│ └── executors/
│ ├── local_subgraph/
│ ├── a2a/

│ ├── http/
│ └── grpc/
├── sdk/
│ └── python/
├── integrations/
│ └── langgraph/
├── data-plane/
│ └── rust/
└── deploy/
├── docker/
├── helm/
└── k8s/

23. Separate Demo Repository
agent-gateway-demo-consumer/
├── README.md
├── pyproject.toml
├── .env.example
├── docker-compose.demo.yml
├── consumer-api/
├── order-agent/
│ ├── graph.py
│ ├── nodes.py
│ └── boundaries.py
├── agents/
│ ├── pricing-agent/
│ └── risk-agent/
├── scenarios/
│ ├── happy_path.py
│ ├── approval.py
│ ├── denial.py
│ ├── a2a.py
│ └── failover.py
└── tests/
The demo repository must use the published platform SDK/API/A2A contract. It must not access the platform&#39;s
PostgreSQL tables directly, import platform internals, call internal services, or depend on platform source paths.

24. Demo Application — Consumer Perspective
Consumer
|
v
Order Agent (LangGraph)
|
+-- validate_order
|
+-- pricing Agent Boundary
| |
| v
| Agent Gateway
| |
| +--&gt; A2A --&gt; Pricing Agent
|
+-- risk Agent Boundary
|
v
Agent Gateway
|

+--&gt; A2A --&gt; Risk Agent
|
v
Final Order Decision
 Consumer requests capability, not endpoint/protocol.
 Pricing and Risk agents are independently registered and approved.
 At least one demo agent is remote A2A.
 At least one demo agent is a same-process LangGraph subgraph.
 Switching a route from local to remote must not require consumer business-code changes.

25. Demo Scenarios
Scenario Expected proof
Agent onboarding Registration → validation → approvals → publication
A2A happy path Consumer → gateway → remote A2A agent
Local subgraph Gateway governance around same-process subgraph
Authorization denial Unauthorized capability never executes
Data policy denial Restricted data blocked
A2A fallback Only explicit approved fallback is selected
Retry/failover Primary failure routes to approved fallback
Suspension Suspended agent is not discoverable/routeable
Agent Card discovery External A2A client can consume standard card
Audit Registration and invocation history is visible

26. Demo Deployment
# Platform repository
docker compose up -d
make migrate
make seed
make test
# Separate demo repository
docker compose -f docker-compose.demo.yml up
python -m consumer_api
The demo&#39;s only platform dependency is the deployed platform contract.

27. Testing Strategy
Test layer Mandatory coverage
Unit Domain, validation, approval state machine, policy, trust,

route scoring

Schema Official A2A AgentCard and protocol contracts
API Registration, approvals, publication, discovery, invocation
Security JWT, workload identity, RBAC/ABAC, tenant/data controls
A2A Agent Card, discovery, protocol version, tasks, streaming

as configured

LangGraph Boundary interception and local execution
Resilience Timeout/retry/circuit/fallback
Persistence PostgreSQL migrations and transaction behavior
Observability Trace propagation and audit events
E2E External demo repository against deployed platform
Compatibility A2A 1.0.x interoperability tests

28. Critical Negative Tests
 Unapproved agent cannot publish.
 Rejected agent cannot be discovered.
 Suspended agent cannot be invoked.
 Registered agent without authorization cannot be invoked.
 Invalid Agent Card cannot be published.
 Invalid A2A version is rejected.
 Invalid token/audience is rejected.
 Fallback cannot bypass authorization.
 Local subgraph cannot bypass policy.
 Consumer cannot access internal database.
 Consumer cannot invoke an internal platform endpoint.
 Malformed A2A task/message is rejected safely.
 Secrets never appear in Agent Card/logs/audit.

29. Security Requirements
 TLS everywhere in production.
 JWT/OIDC and workload identity.
 mTLS support.
 RBAC + ABAC.
 Default deny.
 Short-lived target-audience credentials.
 Secret manager integration.
 Credential redaction.
 Tenant isolation.
 Data classification enforcement.
 Region/residency enforcement.
 Approval-state enforcement.
 Signed Agent Card verification where configured.
 Security event audit.

30. Non-Functional Requirements
Area P0 target
Availability 99.9% for control-plane production baseline
API latency P95 &lt; 200 ms for control-plane decision path excluding

target execution

Traceability 100% governed invocations have correlation/invocation

IDs

Audit 100% approval and governed invocation decisions

recorded

Security Fail closed on authorization uncertainty
Configuration No restart required for policy/route changes where

supported

Scalability Stateless API services; horizontally scalable
Recovery Database-backed durable control state
Compatibility A2A 1.0.x adapter isolated/versioned

31. Development Phases
24. Phase 0 — repository/build foundation, shared contracts and Docker Compose.
25. Phase 1 — Agent Registry, Agent Card validation and lifecycle.

26. Phase 2 — approval workflow and audit.
27. Phase 3 — identity, authentication, RBAC/ABAC and trust.
28. Phase 4 — A2A server/client and discovery.
29. Phase 5 — discovery, route engine and invocation service.
30. Phase 6 — LangGraph Agent Boundary integration and local executor.
31. Phase 7 — resilience, observability and audit completion.
32. Phase 8 — Python SDK and public API hardening.
33. Phase 9 — separate consumer demo repository and E2E interoperability.
34. Phase 10 — Kubernetes/Helm and production operations.
35. Phase 11 — P1 federation and advanced protocol capabilities.

32. GenAI Code Generation Order
36. Generate platform repository skeleton only.
37. Generate shared domain and contract models.
38. Generate PostgreSQL schema/migrations.
39. Generate Agent Card validator using pinned official A2A schema.
40. Generate registration and approval state machine.
41. Generate Agent Registry.
42. Generate identity/authentication.
43. Generate authorization and trust.
44. Generate policy engine.
45. Generate A2A discovery and protocol adapter.
46. Generate route engine.
47. Generate invocation service.
48. Generate local subgraph executor.
49. Generate HTTP fallback executor.
50. Generate resilience.
51. Generate telemetry/audit.
52. Generate Python SDK.
53. Generate API/OpenAPI.
54. Generate platform tests.
55. Only after platform P0 is stable, generate the separate demo repository.
56. Run E2E tests from the demo repository against the platform as an external dependency.

33. Definition of Done — Platform
 Clean checkout builds with documented commands.
 PostgreSQL and Redis start with Docker Compose.
 Agent registration works.
 Official A2A Agent Card validation works.
 Approval workflow works.
 Unapproved agents cannot publish.
 Approved agents can be published and discovered.
 Authentication and authorization work.
 A2A remote invocation works.
 Same-process LangGraph Agent Boundary works.
 Consumer never selects transport.
 A2A is selected when applicable.
 Explicit fallback works only when allowed.
 OpenTelemetry traces work.
 Audit records work.
 OpenAPI is generated.
 Python SDK works.

 All P0 tests pass.
 Demo repository can be deleted without affecting platform build or tests.

34. Definition of Done — Separate Demo
 Demo builds independently.
 Demo has its own pyproject/package configuration.
 Demo does not import platform internals.
 Demo does not access platform DB.
 Demo uses platform SDK/API/A2A only.
 Demo demonstrates agent registration/approval as an administrative flow where appropriate.
 Demo demonstrates A2A remote invocation.
 Demo demonstrates same-process LangGraph boundary.
 Demo demonstrates access denial.
 Demo demonstrates fallback/failover.
 Demo demonstrates audit/trace correlation.
 Demo README contains exact startup/test commands.

35. Final End-to-End Architecture
EXTERNAL CONSUMERS
+-----------------------------+
| Order App | Other Agent | UI |
+-------------+---------------+
|
Public SDK / API
|
v
+----------------------------------------------------------------+
| AGENT GATEWAY |
| |
| Registration -&gt; Approval -&gt; Registry -&gt; A2A Discovery |
| | | | |
| +--------------+-------------+ |
| | |
| Identity -&gt; Authentication -&gt; Authorization -&gt; Trust |
| | |
| Data/Policy Governance |
| | |
| A2A-first Routing |
| | |
| Invocation + Resilience |
| | |
| OpenTelemetry + Audit |
+-----------------------+----------------------------------------+
|
+----------+-----------+
| |
Local Agent Boundary Remote A2A Agent
LangGraph subgraph independent runtime
| |
same process A2A protocol
SEPARATE DEMO REPOSITORY
|
+---- uses only public contracts

36. Final Non-Negotiable Rules for the Generator
1. Generate runnable code, not a conceptual prototype.
2. Keep the demo consumer in a separate repository/code base.
3. Never import demo code into the platform.
4. Use official A2A AgentCard/schema.
5. A2A-first for Agent-to-Agent communication.
6. Require approval before production publication.
7. Approval is version-specific.
8. Registration does not imply authorization.
9. Default authorization is DENY.
10. Apply security/policy to local LangGraph boundaries.
11. Consumer asks for capability; gateway decides protocol and route.
12. No hard-coded endpoints, agents, routes or policies.
13. A2A fallback is explicit and cannot bypass authorization.
14. Record every important decision in telemetry/audit.
15. Keep protocol-specific code behind adapters.
16. Keep LangGraph-specific code behind an integration package.
17. Generate tests with every implementation phase.
18. Do not mark a feature complete until it is executable and tested.
19. Use database-backed configuration/state.
20. Provide exact commands for build, test, run and demo interoperability.

37. Reference Standards and Sources
The implementation team should use the following as normative/technical references:
 A2A official specification: latest released version and normative protocol definitions.
 A2A Agent Card and discovery specification, including /.well-known/agent-card.json.
 A2A protocol bindings and version negotiation.
 OpenTelemetry semantic conventions and APIs.
 OAuth 2.0 / OpenID Connect / JWT standards for authentication.
 RFC 7515 JWS for signed Agent Cards where enabled.
A2A official documentation: urlA2A Protocol Specificationhttps://a2a-protocol.org/latest/specification/. The official
specification states that the Agent Card can be discovered through the well-known URI, registries/catalogs or direct
configuration and that supported interfaces should be declared in preference order. citeturn0search0turn0search4
Agentgateway reference repository: urlagentgateway GitHub
repositoryhttps://github.com/agentgateway/agentgateway. It is useful as an implementation reference for AI-native
gateway concerns such as A2A/MCP, security, observability and governance; it is not a substitute for this specification.
citeturn0search1