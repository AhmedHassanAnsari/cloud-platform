# AGENTS.md — AI DevOps & AIOps Employee System

This file gives coding agents (Claude Code, etc.) the context needed to implement this system correctly. Read this before writing code in this repo.

## 1. System Purpose

Two independent AI Employees that take over **after** application development and testing are complete:

1. **AI DevOps Employee** — prepares and deploys the application to production.
2. **AI AIOps Employee** — operates the deployed system continuously (monitoring, troubleshooting, fixing).

They communicate via **Dapr Service Invocation**. They are separate services/agents, not one monolith — do not merge their responsibilities into a single agent or process.

---

## 2. AI DevOps Employee

**Trigger:** event-driven. Activates when a new/changed application is ready for deployment. Goes idle after a successful deployment. Re-activates automatically when new code changes are detected.

**Responsibilities (in order):**
1. Review application source code
2. Review project services
3. Review project dependencies
4. Review project configuration
5. Review project secrets
6. Plan the deployment
7. Perform DevOps activities required for deployment
8. Handle CI-related deployment activities when application changes occur
9. Build container image
10. Push container image to the image repository
11. Generate Kubernetes manifests
12. Deploy the application
13. Verify successful deployment

**Handover:** On successful deployment, notify the AI AIOps Employee via Dapr Service Invocation. This is the *only* way responsibility transfers between the two employees.

**Scope boundary:** Its job ends at successful deployment + handover. It does not monitor production. It only re-engages on new code/application changes.

---

## 3. AI AIOps Employee

**Trigger:** runs continuously, not event-driven like DevOps.

**Responsibilities:**
1. Monitor the production environment continuously
2. Analyse production logs
3. Detect operational errors
4. Troubleshoot production issues
5. Use Skills when appropriate
6. Use RAG when appropriate (see KSOR, §4)
7. Notify a human before implementing fixes
8. Apply fixes **only after** human approval
9. Continue monitoring after the fix is applied

**Human-approval gate (hard requirement, do not implement autonomous fix application):**

```
Detect issue
  → Analyse issue
  → Determine proposed fix
  → Notify human
  → WAIT for approval        ← blocking gate, no bypass
  → If approved: apply fix
  → If rejected: drop entirely, nothing applied, nothing stored
  → Continue monitoring
```

This gate applies to **applying the fix to production**. It is not optional and not skippable for "low-risk" fixes unless a future spec revision explicitly says so.

**Collaboration:** The AI AIOps Employee may request information from the AI DevOps Employee during troubleshooting, via Dapr Service Invocation.

---

## 4. KSOR — Knowledge System of Record (replaces plain Solution RAG)

KSOR is the accountability-governed replacement for a naive "store everything the AI tried" RAG. **Do not implement a self-writing RAG where the agent stores its own solutions unsupervised.**

**Storage backend:** pgvector (same underlying RAG/vector-search mechanism as a standard Solution RAG). The difference from a plain Solution RAG is entirely in the **write path governance**, not the retrieval mechanism.

**Write path (single approval gate — same approval as fix application, not a second review step):**
1. Human approves the proposed fix (per §3 gate)
2. Fix is applied to production
3. On successful application, the system writes **one accountable record** to KSOR containing:
   - The problem/issue description
   - The solution/fix that was applied
   - `approved_by` (the human identity who approved it)
   - `approved_at` (timestamp)
4. If the human rejects the fix: **nothing is applied and nothing is stored.** The attempt is dropped entirely — do not persist rejected proposals, even for "don't suggest this again" purposes, unless explicitly requested later.

**Read path:**
- The AI AIOps Employee retrieves candidate solutions from KSOR **only**. It must never fall back to or blend in unapproved/self-generated past solutions.
- On a new issue: search KSOR → if a matching approved solution exists, retrieve and use it → if no match, run normal troubleshooting (§3) → if that succeeds and is approved, store it per the write path above.

**Suggested KSOR record schema (starting point — refine during implementation):**

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | primary key |
| `issue_description` | text | what was detected/analysed |
| `issue_embedding` | vector | pgvector column for semantic search |
| `solution` | text | the fix that was applied |
| `approved_by` | text/fk | human identity |
| `approved_at` | timestamptz | approval time |
| `applied_at` | timestamptz | when the fix was actually applied |
| `source_issue_ref` | text/fk | link back to the originating incident/log event |

---

## 5. Inter-employee Communication

- Transport: **Dapr Service Invocation** (not raw HTTP/gRPC directly between services — go through Dapr).
- Two communication events only:
  1. **Deployment Notification** — DevOps → AIOps, fired once per successful deployment.
  2. **Troubleshooting Collaboration** — AIOps → DevOps, on-demand during troubleshooting (e.g. asking about recent deploys, config, or manifests relevant to an incident).

---

## 6. High-Level Workflow

```
Application Development Completed
  → Application Testing Completed
  → AI DevOps Employee (review → plan → build → push → manifest → deploy)
  → Successful Deployment
  → Dapr Service Invocation (handover)
  → AI AIOps Employee (monitor → detect → KSOR lookup → troubleshoot →
                         human approval → apply fix → store to KSOR → monitor)
  → If new application changes occur:
      AI DevOps Employee reactivates, repeats deployment workflow
```

---

## 7. Implementation Notes for Coding Agents

- **Do not** collapse the human-approval gate in §3/§4 into a single "auto-apply then review" flow. Fix approval happens *before* production application, not after.
- **Do not** let the AIOps Employee write to KSOR without a completed, successful, human-approved fix. There is no "draft" or "unapproved" write path.
- Treat DevOps and AIOps as separately deployable services communicating over Dapr — build them as independent components from the start, not as modules of one app that you split later.
- Preferred stack (confirm before deviating): OpenAI Agents SDK, FastAPI,Dapr, MCP for tool/agent interfaces; Docker + Kubernetes + Helm for deployment; Langfuse for production observability,evals; Postgres + pgvector for KSOR and database for data manipulation.
- When in doubt about a requirement not covered here, ask the user