# Sprint 2 Implementation Plan

## Overview
**Sprint 2: Image Build & GHCR Push** - Build container image from reviewed project, request user approval, push to GHCR (Gate 1)

Depends on: Sprint 1 completion with no unresolved blockers

---

## User Stories (Confirmed)

1. Agent builds container image automatically after review passes
2. Image stays in local Docker only until approval
3. Explicit approval required before GHCR push (Gate 1)
4. Clear error reporting on build/push failures
5. Exact image name/tag shown before approval
6. User can reject the push

---

## Use Cases Summary

| UC | Scenario | Key Action |
|---|---|---|
| **UC-1** | Happy path | Build → Show details → Approve → Push → Confirm |
| **UC-2** | Docker not running | Halt, ask user to start Docker |
| **UC-3** | Build fails | Surface error verbatim, ask how to proceed |
| **UC-4** | No Dockerfile | Use skill to generate multi-stage Dockerfile, present, then build |
| **UC-5** | User rejects push | Confirm image stays local, offer next steps |
| **UC-6** | Push to GHCR fails | Report specific error, ask how to proceed |
| **UC-7** | No GHCR auth | Ask user to configure auth before push |

---

## Acceptance Criteria (11 total)

### AC-1: Build only after Sprint 1 passes
- [ ] Agent verifies Sprint 1 review completed with no blockers before starting build
- [ ] If blockers present, halt and refuse to build

### AC-2: Local-only until approval
- [ ] Successful build → image in local Docker only
- [ ] No push without explicit separate approval step

### AC-3: Docker not running detection (UC-2)
- [ ] Halt and report clearly
- [ ] Ask user to start Docker
- [ ] Don't fail silently or hang

### AC-4: Build errors surfaced (UC-3)
- [ ] Surface actual build error output to user
- [ ] Don't attempt automatic fixes
- [ ] Don't retry without asking

### AC-5: Dockerfile generation using skill (UC-4)
- [ ] If no Dockerfile: use multi-stage-dockerfile skill
- [ ] Generate multi-stage Dockerfile appropriate to project framework
- [ ] Present to user before building
- [ ] Only proceed after user sees it

### AC-5b: Generated Dockerfile quality
- [ ] Multi-stage (build vs. runtime)
- [ ] No unnecessary layers
- [ ] No build-time dependencies in final image

### AC-5c: Skill fallback
- [ ] If skill can't produce valid Dockerfile
- [ ] Halt and ask user (don't use generic template)

### AC-6: Image details before approval
- [ ] Show exact image name and tag
- [ ] Show image size (if available)
- [ ] Show base image info
- [ ] No ambiguity about what's approved

### AC-7: Rejection path (UC-5)
- [ ] If user rejects push
- [ ] No push occurs
- [ ] Confirm image remains local

### AC-8: Push failures handled (UC-6)
- [ ] Report specific failure (auth/network/registry)
- [ ] Don't silently retry
- [ ] Don't treat as success

### AC-9: GHCR auth check (UC-7)
- [ ] If no credentials configured
- [ ] Ask user to configure auth
- [ ] Don't attempt unauthenticated push

### AC-10: Separate approval gates
- [ ] Build approval (Gate 1) independent from deployment approval (Gate 2)
- [ ] Don't combine approval steps

### AC-11: Comprehensive test coverage
- [ ] All UC and AC covered by automated tests
- [ ] Test against real Docker/GHCR interactions (not mocked)
- [ ] Include: broken Dockerfile, stopped Docker, invalid credentials

---

## Implementation Breakdown

### Phase 1: Project Structure & Dependencies
**Files to create/modify:**
- `src/tools/docker_build.py` — Docker build operations
- `src/tools/ghcr_push.py` — GHCR push operations
- `src/tools/dockerfile_gen.py` — Dockerfile generation (skill integration from `.agents/skill/`)
- `src/agents/devops_agent.py` — Add build/push logic to existing agent
- `src/config.py` — Add build/push config (project name, registry, base images)
- `pyproject.toml` — Add docker SDK if needed
- `tests/test_sprint2.py` — Comprehensive test suite

**Skill location:**
- `.agents/skill/multi-stage-dockerfile/` — Local skill directory for Dockerfile generation

**Dependencies to add:**
```toml
docker>=7.0.0  # Docker SDK for Python
```

**Configuration needed:**
```
PROJECT_NAME=cloud-platform  # Used for image naming
REGISTRY=ghcr.io  # GHCR registry host
DEFAULT_BASE_IMAGE_PYTHON=python:3.12-alpine
DEFAULT_BASE_IMAGE_NODEJS=node:20-alpine
DEFAULT_BASE_IMAGE_RUST=rust:latest
DEFAULT_BASE_IMAGE_GO=golang:1.21-alpine
```

**Sensitive credentials (collected at runtime via interactive CLI with masked input):**
- `GHCR_USERNAME` — Asked interactively when push approval is requested
- `GHCR_TOKEN` — Asked interactively with masked input (input hidden, not echoed to terminal)
- Never stored in `.env` or code — only in memory for the current session

### Phase 2: Docker Build Operations (`src/tools/docker_build.py`)

**Classes:**
- `BuildConfig` — Build configuration (Dockerfile path, context, tag, build args)
- `BuildResult` — Build result (success, image ID, size, error, base image info)
- `DockerBuildTool` — Orchestrates build operations

**Methods:**
```python
class DockerBuildTool:
    def check_docker_running() -> bool
    def get_dockerfile_path(cwd: Path) -> Path | None
    def get_build_context(cwd: Path, custom_context: Optional[Path] = None) -> Path
    def build_image(
        dockerfile_path: Path,
        context_path: Path,
        image_name: str,
        image_tag: str,
        build_args: Optional[dict] = None
    ) -> BuildResult
    def get_image_info(image_name: str, image_tag: str) -> ImageInfo
    def tag_image(source_image: str, target_image: str) -> bool
```

**Key behaviors:**
- Check Docker daemon is running before attempting build
- Support custom build context (default: project root)
- Respect `.dockerignore` for excluding files
- Run `docker build` with proper error capture
- Return stderr/stdout on failure
- Extract image metadata (size, layers, base image)
- Support build args (e.g., for customizing base images)

**Build context support:**
- Default: project root directory
- Allow user to specify custom context (subdirectory)
- Validate context exists before build
- Support `.dockerignore` file in context

### Phase 3: Dockerfile Generation (`src/tools/dockerfile_gen.py`)

**Key requirements:**
1. Load multi-stage-dockerfile skill from local `.agents/skill/` directory
2. Make skill content available to agent via local file context
3. Use skill to generate Dockerfile based on project framework
4. Handle skill failures gracefully

**Methods:**
```python
class DockerfileGenerator:
    def load_skill_from_local(skill_path: Path) -> str  # Load from .agents/skill/
    def detect_project_framework(project_info: DirectoryReview) -> str
    def generate_dockerfile(
        project_info: DirectoryReview,
        project_path: Path,
        base_image: Optional[str] = None
    ) -> str | None  # Generated Dockerfile content or None if failed
    def validate_dockerfile(content: str) -> bool
    def save_generated_dockerfile(content: str, path: Path) -> None
```

**Decision logic (framework detection):**
- If `pyproject.toml` exists → Python project (base: `python:3.12-alpine`)
- If `package.json` exists → Node.js project (base: `node:20-alpine`)
- If `Cargo.toml` exists → Rust project (base: `rust:latest as builder` → `alpine:latest`)
- If `go.mod` exists → Go project (base: `golang:1.21-alpine as builder` → `alpine:latest`)
- If `pom.xml` or `build.gradle` exists → Java project
- Etc.

**Skill context:**
```
.agents/skill/multi-stage-dockerfile/
├── README.md
├── SKILL.md
└── templates/  # Framework-specific templates
    ├── python.dockerfile
    ├── nodejs.dockerfile
    ├── rust.dockerfile
    └── go.dockerfile
```

**Usage in agent:**
- Load skill content as local context when generating Dockerfile
- Pass to agent as reference/template
- Agent uses skill guidelines to generate appropriate multi-stage Dockerfile
- Present generated Dockerfile to user before building

### Phase 4: GHCR Push Operations (`src/tools/ghcr_push.py`)

**Classes:**
- `GHCRConfig` — GHCR authentication and registry config (built at runtime from user input)
- `PushResult` — Push result (success, image ref, error)
- `GHCRPushTool` — Orchestrates GHCR push and image naming

**Methods:**
```python
class GHCRPushTool:
    def prompt_for_credentials() -> tuple[str, str]  # Interactive prompts with masked token input
    def prompt_for_image_tag() -> str  # Ask user for tag (default: timestamp)
    def validate_credentials(username: str, token: str) -> bool
    def authenticate_ghcr(username: str, token: str) -> bool
    def build_image_reference(
        registry: str,
        username: str,
        project_name: str,
        tag: str
    ) -> str  # Format: ghcr.io/username/project-name:tag
    def push_image(
        local_image: str,
        remote_image: str,
        username: str,
        token: str
    ) -> PushResult
```

**Image naming:**
- Format: `[REGISTRY_HOST[:REGISTRY_PORT]/][NAMESPACE/]REPOSITORY_NAME[:TAG]`
- GHCR example: `ghcr.io/ahmedhassan/cloud-platform:latest`
- Tag options: `latest`, `v1.0.0`, custom string, or timestamp
- User can choose tag or use default (current timestamp)

**Credential handling:**
- Credentials prompted only when push approval is requested
- Username prompted normally (not sensitive)
- Token prompted with masked input using `getpass.getpass()` (input hidden)
- Credentials stored only in memory for current session
- Never written to .env, logs, or persistent storage
- Cleared after push attempt

**Error handling:**
- Catch auth errors specifically
- Catch network errors
- Catch registry rejection errors
- Report exact error to user

### Phase 5: Agent Build/Push Logic

**Update `DevOpsAgent` in `src/agents/devops_agent.py`:**

```python
class DevOpsAgent:
    def build_phase(self, cwd: str, review_findings: ReviewFindings) -> BuildResult
    def push_approval(self, build_result: BuildResult) -> bool
    def push_to_ghcr(self, build_result: BuildResult) -> PushResult
    def handle_build_failure(self, error: str) -> str
    def present_image_details(self, build_result: BuildResult) -> None
```

**Flow:**
1. Verify Sprint 1 review has no blockers
2. Check Docker running (halt if not)
3. Check for Dockerfile:
   - If exists: use it
   - If missing: generate using skill, present to user, ask to proceed
4. Run build (capture stderr, report on failure)
5. Get image info
6. Present image details to user
7. Ask for push approval
8. If approved:
   - Prompt user for GHCR username (normal input)
   - Prompt user for GHCR token (masked input via `getpass`)
   - Validate credentials
   - Push to GHCR
   - Report success or specific error
9. If failed push: report error, ask how to proceed
10. If rejected: confirm image stays local, offer next steps
11. Clear credentials from memory after push attempt

### Phase 6: Test Suite (`tests/test_sprint2.py`)

**Test Categories:**

#### Build Tests
```python
class TestDockerBuild:
    test_ac3_docker_not_running()  # UC-2
    test_ac3_docker_error_message()
    test_ac4_build_fails_bad_dockerfile()  # UC-3
    test_ac4_build_error_surfaced()
    test_ac1_no_build_if_blockers()  # AC-1
```

#### Dockerfile Generation Tests
```python
class TestDockerfileGeneration:
    test_ac5_generate_python_dockerfile()  # UC-4
    test_ac5_generate_nodejs_dockerfile()
    test_ac5_generate_rust_dockerfile()
    test_ac5_present_dockerfile_to_user()
    test_ac5b_generated_dockerfile_multistage()
    test_ac5c_skill_fallback_no_generic()
```

#### Image Info Tests
```python
class TestImageInfo:
    test_ac6_show_image_name_tag()
    test_ac6_show_image_size()
    test_ac6_show_base_image()
```

#### GHCR Push Tests
```python
class TestGHCRPush:
    test_ac7_user_rejects_push()  # UC-5
    test_ac7_image_stays_local()
    test_ac8_push_auth_failure()  # UC-6
    test_ac8_push_network_error()
    test_ac8_error_specific()
    test_ac9_no_credentials()  # UC-7
    test_ac9_ask_user_configure_auth()
    test_ac10_separate_approval_gates()
```

#### Integration Tests
```python
class TestSprint2Integration:
    test_uc1_happy_path()  # Build → approve → push
    test_uc1_success_confirmation()
```

**Test approach:**
- Use real Docker for build tests (or skip if Docker not available)
- Use mocked GHCR client for push tests (or test with invalid credentials)
- Test both success and failure paths

---

## Implementation Sequence

1. **Week 1 - Foundation:**
   - Add dependencies to `pyproject.toml`
   - Create `src/tools/docker_build.py` with Docker operations
   - Create `src/tools/dockerfile_gen.py` with skill integration
   - Create `src/tools/ghcr_push.py` with GHCR operations

2. **Week 1-2 - Agent Integration:**
   - Integrate build/push logic into `DevOpsAgent`
   - Implement approval gates
   - Add user prompts for each decision point

3. **Week 2 - Testing:**
   - Create `tests/test_sprint2.py`
   - Write unit tests for each component
   - Write integration tests for full workflows

4. **Week 2 - Validation:**
   - Run full test suite
   - Verify all AC pass
   - Test against real Docker/GHCR (with credentials)

---

## Key Decision Points

1. **Dockerfile generation skill source:**
   - ✅ **DECIDED:** Located in `.agents/skill` directory (local context)
   - Load skill content from local `.agents/skill/multi-stage-dockerfile/` directory
   - Skill content made available to agent via local file context
   - Fetched at build time, not from GitHub

2. **GHCR credentials handling:**
   - ✅ **DECIDED:** Collect interactively at runtime (not in `.env`)
   - Username: normal text input
   - Token: masked input using `getpass.getpass()` (input hidden)
   - Credentials stored only in memory for session
   - Never persisted to disk

3. **Image naming convention:**
   - ✅ **DECIDED:** Docker registry format standard
   - Format: `[REGISTRY_HOST[:REGISTRY_PORT]/][NAMESPACE/]REPOSITORY_NAME[:TAG]`
   - For GHCR: `ghcr.io/{username}/{project-name}:{tag}`
   - Tag examples: `latest`, `v1.0.0`, `{git-sha}`, `{timestamp}`
   - Allow user to specify tag or use default (timestamp)

4. **Build context:**
   - ✅ **DECIDED:** Support custom build context
   - Default: project root
   - Allow user to specify custom context directory
   - Support `.dockerignore` for excluding files

5. **Base images:**
   - ✅ **DECIDED:** Python-alpine recommended
   - Python projects: `python:3.12-alpine` (lightweight)
   - Node projects: `node:20-alpine`
   - Go projects: `golang:1.21-alpine as builder` + `alpine:latest` for runtime
   - Rust projects: `rust:latest as builder` + `alpine:latest` for runtime

---

## Security Practices

### Credential Management
- **No `.env` storage:** GHCR credentials NOT stored in `.env` or committed to git
- **Runtime collection:** Credentials collected interactively when needed (at push approval step)
- **Masked input:** Token input hidden using Python's `getpass.getpass()` module
- **Memory-only:** Credentials stored only in memory for the current session
- **Cleanup:** Credentials cleared after push attempt (success or failure)
- **No logging:** Credentials never logged, printed, or exposed in error messages

### Implementation Example
```python
import getpass

# When push approval requested:
username = input("GHCR Username: ")
token = getpass.getpass("GHCR Token (will be hidden): ")
# User types password - nothing shown on screen, not even dots

# After push:
del token  # Clear from memory
```

### Acceptance Criterion AC-9 Alignment
"If GHCR authentication is not configured at all, the agent asks the user to configure it"
- **Implementation:** Interactive prompts are the "configuration at runtime"
- **No pre-configuration needed:** User provides credentials only when approving push

---

## All Decision Points Resolved ✅

All key decisions have been clarified and documented in the plan:
1. ✅ Skill location: `.agents/skill/multi-stage-dockerfile/` (local context)
2. ✅ Credentials: Interactive prompts with masked input at push time
3. ✅ Image naming: Docker registry format standard
4. ✅ Build context: Support custom context + .dockerignore
5. ✅ Base images: Python-alpine + framework-specific recommendations

**Ready to proceed with implementation.**

