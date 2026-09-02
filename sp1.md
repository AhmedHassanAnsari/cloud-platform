# Sprint 2 — Image Build & GHCR Push (AI DevOps Employee)

**Depends on:** Sprint 1 (project intake & review) completed with no unresolved blockers.

**Scope:** Build the container image from the reviewed project, keep it in local Docker, then gate on user approval before pushing to GHCR (Gate 1). No manifest generation or deployment in this sprint — those are later sprints.

---

## User Stories

1. **As a user**, I want the agent to build my container image automatically once review passes, so that I don't have to run the Docker build myself.

2. **As a user**, I want the built image to stay in my local Docker only, so that nothing reaches a remote registry without my explicit say-so.

3. **As a user**, I want to be asked for explicit approval before the image is pushed to GHCR, so that I control what gets published and when.

4. **As a user**, I want to be told clearly if the build fails (e.g. Docker not running, a bad Dockerfile step, build error), so that I can fix the problem instead of the agent guessing a workaround.

5. **As a user**, I want to know exactly what image (name, tag) was built and what will be pushed, so that there's no ambiguity about what I'm approving.

6. **As a user**, I want to be able to reject the push, so that a bad or premature build never reaches GHCR.

---

## Use Cases

### UC-1: Happy path — build succeeds, user approves push
- Sprint 1 review completed with no blockers.
- Agent builds the container image using Docker.
- Build succeeds; image is tagged and stored in local Docker only.
- Agent presents the image details (name, tag, size, base image) and asks for approval to push to GHCR.
- User approves.
- Agent pushes the image to GHCR.
- Agent confirms the push succeeded and reports the GHCR image reference.

### UC-2: Docker not running at build time
- Agent attempts to start the build.
- Docker daemon is not running.
- Agent stops, tells the user Docker is not running, and asks them to start it before proceeding. Does not retry silently or wait/poll indefinitely without telling the user.

### UC-3: Build fails (bad Dockerfile / build error)
- Docker is running, but the build fails (e.g. syntax error in Dockerfile, missing build context file, failed dependency install inside the image).
- Agent stops, surfaces the actual build error output to the user, and asks how to proceed. Does not attempt automatic fixes to the Dockerfile or retry with modified build args without asking first.

### UC-4: No Dockerfile found
- Project has no Dockerfile (and Sprint 1's review didn't already catch this as a blocker).
- Agent uses the **multi-stage-dockerfile skill** (`github.com/AhmedHassanAnsari/skill/tree/main/multi-stage-dockerfile`) to generate a multi-stage Dockerfile appropriate to the reviewed project (per Sprint 1's detected framework/dependencies), rather than writing an ad-hoc single-stage Dockerfile from scratch or assuming a generic template outside that skill.This skill content should be placed in a file for the agent to read in local envionment. so at implemetation time fetch the content and place in local file for agent and pass it as local context to agent when it requires it for building multi stage docker file.
- Agent does **not** silently write and build with a freshly generated Dockerfile without surfacing it first — it presents the generated Dockerfile to the user before proceeding to build, since this is new code being introduced into the project that the user didn't write.
- If the skill itself can't produce a valid Dockerfile for the project (e.g. unsupported framework/language), the agent stops and asks the user how to proceed — this fallback matches the original "ask, don't assume" behavior.

### UC-5: User rejects the push
- Build succeeds, agent presents image details, asks for approval.
- User rejects.
- Agent does not push anything to GHCR.
- Agent confirms the image remains local only and asks whether the user wants to stop here, rebuild, or take another action.

### UC-6: Push to GHCR fails
- User approves the push.
- Push attempt fails (e.g. auth error, network error, registry rejects the image).
- Agent stops, reports the specific failure to the user, and asks how to proceed (e.g. re-check credentials) rather than retrying blindly or treating it as a soft failure.

### UC-7: GHCR authentication not configured
- Agent reaches the push step but has no valid GHCR credentials/token available.
- Agent stops and asks the user to provide/configure GHCR authentication rather than attempting to push anonymously or guessing a token location.

---

## Acceptance Criteria

- [ ] AC-1: The build step only runs after Sprint 1's review has completed with no unresolved blockers — verified by confirming the agent will not attempt a build if invoked with review still pending/blocked.
- [ ] AC-2: A successful build results in an image that exists in local Docker only — no push occurs without a separate, explicit approval step (UC-1).
- [ ] AC-3: If Docker is not running when the build step starts, the agent halts and reports this clearly rather than failing silently or hanging (UC-2) — verified by running with Docker stopped.
- [ ] AC-4: If the build fails for any reason, the actual build error is surfaced to the user verbatim (or a clear excerpt of it), and the agent does not attempt an automatic fix or retry without asking (UC-3) — verified with a test project containing an intentionally broken Dockerfile.
- [ ] AC-5: If no Dockerfile is present, the agent uses the multi-stage-dockerfile skill to generate one appropriate to the project, presents it to the user before building, and only proceeds to build after that generated Dockerfile has been shown (UC-4) — verified with a test project with no Dockerfile.
- [ ] AC-5b: The generated Dockerfile is multi-stage and avoids bloat (no unnecessary layers, no build-time-only dependencies carried into the final image) — verified by inspecting the generated Dockerfile and the resulting image size/layer count against a naive single-stage equivalent.
- [ ] AC-5c: If the multi-stage-dockerfile skill cannot produce a valid Dockerfile for the project (e.g. unsupported framework), the agent halts and asks the user rather than falling back to a generic template on its own (UC-4 fallback).
- [ ] AC-6: Before requesting push approval, the agent presents the exact image name and tag that will be pushed — no ambiguity about what's being approved (UC-1, User Story 5).
- [ ] AC-7: If the user rejects the push, no push occurs, and the agent confirms the image remains local (UC-5) — verified by testing the rejection path explicitly.
- [ ] AC-8: If the push itself fails (auth, network, registry error), the agent reports the specific failure and does not silently retry or treat it as success (UC-6) — verified with a test using invalid/missing GHCR credentials.
- [ ] AC-9: If GHCR authentication is not configured at all, the agent asks the user to configure it rather than attempting an unauthenticated push (UC-7).
- [ ] AC-10: The GHCR push approval gate (Gate 1) is implemented as a distinct, separate approval step — it does not implicitly grant or combine with the deployment approval gate (Gate 2), consistent with the confirmed system design.
- [ ] AC-11: All of the above are covered by automated tests (per CLAUDE.md §2) before this sprint is considered done. Docker/GHCR interactions should be tested against a real or realistic test registry/build context, not mocked in a way that would hide real failures (e.g. a genuinely broken Dockerfile, genuinely stopped Docker daemon, genuinely invalid credentials).

---

## Explicitly Out of Scope for Sprint 2
- Kubernetes manifest generation
- Creating/writing to the `deployment/` directory
- Deployment itself (Gate 2)
- Dapr handover to AI AIOps Employee
- Anything related to the AI AIOps Employee itself
- Re-running review logic from Sprint 1 (assumed already passed)