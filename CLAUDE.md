# CLAUDE.md — Project Instructions

This file governs how Claude (or any coding agent) works in this repository. Read this in full before writing any code. Also read **@AGENTS.md** in this repo for the system architecture, both AI Employees' responsibilities, the Dapr handover, and the full KSOR design — that file is the source of truth for *what* to build; this file governs *how* to build it.

---

## 1. Stack — Always Use Latest Available Versions

Use the current/latest stable version of every tool in this stack unless a version is explicitly pinned in a config file (package.json, requirements.txt, pyproject.toml, etc.) already in the repo. If no version is pinned, check for the latest before scaffolding — do not default to a remembered/older version from training data.

- **Agent framework:** OpenAI Agents SDK
- **MCP (Model Context Protocol):** **use MCP wherever tool/agent interfaces are needed, and use the latest available spec/SDK version.** As of now the latest spec is **2026-07-28** (stateless core, Multi Round-Trip Requests, Tasks extension, MCP Apps, hardened OAuth-aligned authorization, Extensions framework). Before implementing any MCP server or client:
  - Confirm the installed SDK version actually supports 2026-07-28 — don't assume.
  - Build stateless-first (no reliance on `Mcp-Session-Id` / protocol-level sessions) — this matters for the Kubernetes deployment model in AGENTS.md.
  - If a needed capability was deprecated (Sampling, Roots, protocol-level Logging), use the replacement pattern (direct LLM provider calls, tool params/resource URIs, stderr/OpenTelemetry respectively) — do not build new code on deprecated primitives.
  - If in doubt about current MCP spec/SDK state at implementation time, say so and ask rather than assuming — the spec has moved fast in 2026.
- **API layer:** FastAPI
- **Communication:** Dapr (Service Invocation for DevOps↔AIOps comms)
- **Deployment:** Docker, Kubernetes, Helm, CI/CD
- **Observability:** Langfuse (production tracing,evals/CI)
- **Knowledge store (KSOR):** Postgres + pgvector

If any library's latest version introduces a breaking change relevant to this system, flag it before proceeding rather than silently working around it.

---

## 2. Sprint Discipline — Hard Constraints

This project is built **sprint by sprint**, not as one continuous build. For every sprint, before writing implementation code:

1. **Define user stories** for the sprint's scope (who/what/why format: "As a [DevOps/AIOps Employee / human operator], I want ___, so that ___").
2. **Define use cases** — the concrete scenarios/flows the sprint must handle, including edge cases and failure paths.
3. **Define acceptance criteria** — explicit, testable conditions for "this sprint is done." No vague criteria like "works correctly" — each criterion must be checkable.
4. Get these confirmed before writing code for that sprint.

**Test-as-you-go is mandatory:**
- Write tests alongside implementation, not after — do not batch testing to the end of a sprint.
- A sprint is not complete until its tests pass against its own acceptance criteria.
- **Do not move to the next sprint until the current sprint's tests pass and its acceptance criteria are demonstrably met.** No building ahead on an unverified foundation.
- If a test fails, stop and fix before adding new scope — do not layer new work on top of a known-broken piece.

---

## 3. Never Assume — Always Ask

This is a strict rule, not a style preference:

- If a requirement, edge case, data shape, approval flow, naming convention, or design decision is not explicitly covered in AGENTS.md or in the current sprint's user stories/acceptance criteria, **stop and ask** — do not infer or fill the gap with a "reasonable default."
- If multiple implementations are plausible (e.g., how a Dapr call is structured, what fields an API returns, how an error is surfaced), **ask which one** rather than picking one silently.
- If something in AGENTS.md seems ambiguous or possibly outdated, **ask** rather than reinterpreting it.
- It's always better to ask a clarifying question than to build the wrong thing and have to redo it.

---

## 4. Best Coding Practices

- Keep the two AI Employees (DevOps, AIOps) as separately deployable services from the start — do not build them as tightly coupled modules "to split later."
- Small, reviewable commits/changes scoped to one sprint's user stories at a time.
- Clear separation of concerns: agent logic / tool definitions / API layer / infra manifests should live in distinct, well-named locations — no God files.
- No hardcoded secrets, credentials, or environment-specific config in code — use the secrets/config review step described in AGENTS.md §3 as the model even for this repo's own config.
- Every KSOR write must be traceable to a human approver and timestamp (per AGENTS.md §4) — do not implement any code path that writes to KSOR without both fields populated.
- The human-approval gate before applying a fix (AGENTS.md §3) is a hard blocking step — do not implement a bypass, timeout-based auto-approve, or "trusted fix" shortcut unless explicitly instructed.
- Write meaningful commit messages and docstrings/comments explaining *why*, not just *what*, especially around the approval gates and Dapr communication points, since these are the accountability-critical parts of the system.
- Prefer explicit, typed interfaces (Pydantic models, typed function signatures) over loosely-shaped dicts, especially for the KSOR record and inter-employee Dapr payloads.

---

## 5. Implementation Notes for the Coding Agent

- Start of any work session in this repo: read `AGENTS.md` first, then this file, then check which sprint is currently active before touching code.
- Before generating code for a sprint: produce the user stories, use cases, and acceptance criteria for that sprint and get them confirmed — do not skip straight to implementation.
- When something is unclear: ask. Do not guess and move on. This applies to business logic, data shapes, naming, infra choices, and anything else not explicitly pinned down.
- When implementing MCP components: verify current SDK/spec support for 2026-07-28 features before using them; do not assume training-data knowledge of MCP is current, since the spec has changed substantially in 2026.
- Testing is not optional or deferrable — write tests with the code, run them before declaring a sprint done, and do not proceed to the next sprint on a failing or unverified one.
- If AGENTS.md and a sprint's user stories appear to conflict, stop and ask rather than picking one.