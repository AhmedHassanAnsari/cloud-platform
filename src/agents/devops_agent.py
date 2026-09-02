"""AI DevOps Employee Agent using OpenAI Agents SDK with Gemini."""

import os
import json
import logging
import subprocess
from typing import Optional
from pathlib import Path
from pydantic import BaseModel

# OpenAI SDK with Gemini support
from openai import AsyncOpenAI, RateLimitError

# OpenAI Agents SDK - try multiple import locations for compatibility
try:
    from agents import (
        Agent,
        OpenAIChatCompletionsModel,
        RunConfig,
        Runner,
    )
except ImportError:
    try:
        from openai.agents import (
            Agent,
            OpenAIChatCompletionsModel,
            RunConfig,
            Runner,
        )
    except ImportError:
        # Fallback for development - will show error at runtime
        Agent = None
        OpenAIChatCompletionsModel = None
        RunConfig = None
        Runner = None

# Filesystem tools
from src.tools.filesystem import (
    check_project_validity,
    get_source_files,
    get_dependencies,
    get_config_files,
    get_secrets_files,
    get_services,
    check_docker_running,
    DirectoryReview,
    review_directory,
)
from src.config import GEMINI_API_KEY, GEMINI_MODEL

# Sprint 2 tools
from src.tools.docker_build import DockerBuildTool, BuildResult, ImageInfo
from src.tools.dockerfile_gen import DockerfileGenerator
from src.tools.ghcr_push import GHCRPushTool, PushResult
from src.tools.k8s_manifest_generator import K8sManifestGenerator
from src.tools.dapr_client import invoke_aiops_deployment_notification

logger = logging.getLogger(__name__)


class ReviewFindings(BaseModel):
    """Findings from the DevOps review."""
    is_valid_project: bool
    project_markers: list[str]
    source_files_count: int
    dependency_files_found: list[str]
    config_files_found: list[str]
    secrets_files_detected: list[str]
    services_detected: list[str]
    docker_running: bool
    blockers: list[str]
    warnings: list[str]
    ready_for_next_stage: bool


class DevOpsAgentConfig:
    """Configuration for the DevOps Agent using OpenAI Agents SDK with Gemini."""
    
    def __init__(self):
        """Initialize Gemini client and models."""
        self.gemini_api_key = GEMINI_API_KEY
        self.model_name = GEMINI_MODEL
        
        # Initialize AsyncOpenAI client pointing to Gemini's OpenAI-compatible endpoint
        self.client = AsyncOpenAI(
            api_key=self.gemini_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        
        # Wrap the client in an OpenAI ChatCompletions model (if available)
        if OpenAIChatCompletionsModel is not None:
            self.model = OpenAIChatCompletionsModel(
                model=self.model_name,
                openai_client=self.client,
            )
        else:
            self.model = None
    
    def get_run_config(self) -> Optional[RunConfig]:
        """Get the run configuration for agent execution."""
        if RunConfig is None or self.model is None:        return RunConfig(
            model=self.model,
            model_provider=self.client,
        )


class DevOpsAgent:
    """AI DevOps Employee Agent for project review and deployment preparation."""
    
    def __init__(self):
        """Initialize the agent with Gemini via OpenAI Agents SDK."""
        self.config = DevOpsAgentConfig()
        self._setup_agents()
    
    def _setup_agents(self):
        """Set up the specialized agents for different review tasks."""
        if Agent is None:
            logger.warning("Agents SDK not available - using fallback mode")
            return
        
        # Agent for project validation
        self.validator_agent = Agent(
            name="Project Validator",
            instructions=(
                "You are a project structure validator. Review the provided project "
                "information and determine if it appears to be a valid project directory. "
                "Look for key markers like source files, configuration files, and "
                "dependency manifests. Report your findings clearly."
            ),
            model=self.config.model,
        )
        
        # Agent for dependency analysis
        self.dependency_agent = Agent(
            name="Dependency Analyzer",
            instructions=(
                "You are a dependency and framework expert. Analyze the project's "
                "dependency manifests (pyproject.toml, requirements.txt, package.json, etc). "
                "Identify the framework, runtime, and key dependencies. Alert on any "
                "version conflicts or unclear versioning. Be specific about what you find."
            ),
            model=self.config.model,
        )
        
        # Agent for configuration reviewer
        self.config_agent = Agent(
            name="Configuration Reviewer",
            instructions=(
                "You are a configuration expert. Review Docker, CI/CD, and application "
                "configuration files. Look for docker-compose.yml, Dockerfile, deployment "
                "configs, and environment setup. Identify any missing or incomplete configs "
                "that might block deployment."
            ),
            model=self.config.model,
        )
        
        # Agent for blocker detection and summary
        self.summary_agent = Agent(
            name="Review Summarizer",
            instructions=(
                "You are a technical review summarizer. Given a complete project review, "
                "synthesize all findings into a clear, actionable summary. Identify and "
                "prioritize any blockers that must be resolved before the next stage. "
                "Be concise and specific."
            ),
            model=self.config.model,
        )
    
    async def _run_agent(self, agent: Agent, prompt: str) -> str:
        """
        Run an agent and return its text response.
        
        Args:
            agent: The agent to run
            prompt: The input prompt
            
        Returns:
            The agent's response as text
        """
        if Runner is None:
            logger.warning("Runner not available")
            return ""
        
        try:
            run_config = self.config.get_run_config()
            if run_config is None:
                return ""
            
            result = await Runner.run(
                agent,
                prompt,
                run_config=run_config,
            )
            return result.final_output or ""
        except Exception as e:
            logger.error(f"Agent run failed: {e}")
            return ""
    
    def _ask_user(self, question: str, choices: Optional[list[str]] = None) -> str:
        """
        Ask the user a question interactively.
        
        Args:
            question: The question to ask
            choices: Optional list of choices
            
        Returns:
            User's response
        """
        print(f"\n❓ {question}")
        if choices:
            for i, choice in enumerate(choices, 1):
                print(f"  {i}. {choice}")
            while True:
                try:
                    response = input("Your choice (number): ").strip()
                    idx = int(response) - 1
                    if 0 <= idx < len(choices):
                        return choices[idx]
                    print("Invalid choice. Try again.")
                except ValueError:
                    print("Please enter a number.")
        else:
            return input("Your answer: ").strip()
    
    def _handle_invalid_project(self, cwd: str) -> None:
        """Handle case where directory doesn't look like a project."""
        print("\n⚠️  This directory doesn't appear to be a valid project.")
        print("   (No project markers found: no package.json, pyproject.toml, Dockerfile, .git, etc.)")
        
        confirm = self._ask_user(
            "Do you want to continue anyway?",
            ["Yes, continue", "No, stop"]
        )
        
        if confirm == "No, stop":
            print("\n❌ Review halted by user.\n")
            raise SystemExit(1)
    
    def _handle_framework_version_unclear(self) -> str:
        """Handle case where framework version cannot be determined."""
        print("\n⚠️  Framework version could not be automatically determined.")
        print("   (No clear version pin found in dependency manifests.)")
        
        version = self._ask_user(
            "Please specify the Python/framework version you're using:",
            None  # Free text input
        )
        
        return version
    
    def _handle_missing_dependency(self, dep_name: str) -> str:
        """Handle case where a dependency cannot be resolved."""
        print(f"\n⚠️  Dependency '{dep_name}' referenced but cannot be resolved.")
        
        action = self._ask_user(
            "What should we do?",
            ["Install it now", "Skip this", "Correct the manifest", "Stop"]
        )
        
        if action == "Stop":
            print("\n❌ Review halted by user.\n")
            raise SystemExit(1)
        
        return action
    
    def _handle_docker_not_running(self) -> str:
        """Handle case where Docker is not running."""
        print("\n⚠️  Docker is not running or not accessible.")
        print("   (This will block the build step in the next sprint.)")
        
        action = self._ask_user(
            "What should we do?",
            ["Start Docker and continue", "Continue review only (skip Docker steps)", "Stop"]
        )
        
        if action == "Stop":
            print("\n❌ Review halted by user.\n")
            raise SystemExit(1)
        
        return action
    
    def _handle_general_error(self, error_msg: str) -> str:
        """Handle general/unexpected errors during review."""
        print(f"\n❌ Error during review: {error_msg}")
        
        action = self._ask_user(
            "How should we proceed?",
            ["Retry", "Continue anyway", "Stop"]
        )
        
        if action == "Stop":
            print("\n❌ Review halted by user.\n")
            raise SystemExit(1)
        
        return action
    
    def review_project(self, cwd: str = ".") -> ReviewFindings:
        """
        Perform a complete project review.
        
        This implements the review logic from Sprint 1:
        - Check project validity
        - Review source code
        - Review services
        - Review dependencies
        - Review configuration
        - Review secrets (location only, never read)
        - Detect and handle blockers
        - Ask user when blockers found
        
        Args:
            cwd: Current working directory to review
            
        Returns:
            ReviewFindings with all review results
        """
        print("\n🔍 Starting AI DevOps Employee Review...\n")
        
        blockers = []
        warnings = []
        
        # Step 1: Check project validity (UC-5)
        print("📋 Checking project structure...")
        is_valid, markers = check_project_validity(cwd)
        
        if not is_valid:
            self._handle_invalid_project(cwd)
            return ReviewFindings(
                is_valid_project=False,
                project_markers=[],
                source_files_count=0,
                dependency_files_found=[],
                config_files_found=[],
                secrets_files_detected=[],
                services_detected=[],
                docker_running=False,
                blockers=["Invalid project directory"],
                warnings=[],
                ready_for_next_stage=False,
            )
        
        print(f"   ✓ Project markers found: {', '.join(markers)}")
        
        # Step 2: Review source code
        print("\n📝 Reviewing source code...")
        source_files = get_source_files(cwd)
        print(f"   ✓ Found {len(source_files)} source files")
        for sf in source_files[:5]:  # Show first 5
            print(f"     - {sf.path} ({sf.size} bytes)")
        if len(source_files) > 5:
            print(f"     ... and {len(source_files) - 5} more files")
        
        # Step 3: Review services
        print("\n🔧 Reviewing services configuration...")
        services = get_services(cwd)
        if services:
            for service in services:
                print(f"   ✓ {service}")
        else:
            print("   ℹ️  No Docker Compose or service configuration found")
        
        # Step 4: Review dependencies (UC-2, UC-3)
        print("\n📦 Reviewing dependencies...")
        dependency_files, version_info = get_dependencies(cwd)
        
        if dependency_files:
            for df in dependency_files:
                print(f"   ✓ Dependency file: {df.path}")
            
            if version_info is None:
                # Try to ask user for framework version if unclear
                version = self._handle_framework_version_unclear()
                blockers.append(f"Framework version clarified by user: {version}")
        else:
            warnings.append("No dependency manifest found (pyproject.toml, package.json, etc.)")
        
        # Step 5: Review configuration
        print("\n⚙️  Reviewing configuration files...")
        config_files = get_config_files(cwd)
        if config_files:
            for cf in config_files[:5]:
                print(f"   ✓ Config file: {cf.path}")
            if len(config_files) > 5:
                print(f"   ... and {len(config_files) - 5} more config files")
        else:
            warnings.append("No configuration files found")
        
        # Step 6: Review secrets (UC-6 - location only, never read)
        print("\n🔐 Checking for secrets files...")
        secrets_files = get_secrets_files(cwd)
        if secrets_files:
            for sf in secrets_files:
                print(f"   ⚠️  Secrets file detected (location only): {sf.path}")
                print("     (Contents not read or exposed)")
        else:
            print("   ℹ️  No obvious secrets files detected")
        
        # Step 7: Check Docker (UC-4)
        print("\n🐳 Checking Docker availability...")
        docker_running = check_docker_running()
        if docker_running:
            print("   ✓ Docker is running")
        else:
            print("   ⚠️  Docker is not running")
            action = self._handle_docker_not_running()
            if action != "Continue review only (skip Docker steps)":
                blockers.append("Docker not running - user will start it")
            else:
                warnings.append("Docker not available - build step will need attention")
        
        # Prepare findings
        findings = ReviewFindings(
            is_valid_project=True,
            project_markers=markers,
            source_files_count=len(source_files),
            dependency_files_found=[df.path for df in dependency_files],
            config_files_found=[cf.path for cf in config_files],
            secrets_files_detected=[sf.path for sf in secrets_files],
            services_detected=services,
            docker_running=docker_running,
            blockers=blockers,
            warnings=warnings,
            ready_for_next_stage=len(blockers) == 0,
        )
        
        return findings
    
    def present_summary(self, findings: ReviewFindings) -> None:
        """
        Present a clear summary of review findings to the user.
        
        Args:
            findings: ReviewFindings from the review
        """
        print("\n" + "="*60)
        print("📊 REVIEW SUMMARY")
        print("="*60)
        
        print("\n✅ Project Structure:")
        print(f"  - Valid project: {'Yes' if findings.is_valid_project else 'No'}")
        print(f"  - Project markers: {', '.join(findings.project_markers)}")
        
        print("\n📝 Source Code:")
        print(f"  - Source files found: {findings.source_files_count}")
        
        print("\n🔧 Services:")
        if findings.services_detected:
            for service in findings.services_detected:
                print(f"  - {service}")
        else:
            print("  - No services detected")
        
        print("\n📦 Dependencies:")
        if findings.dependency_files_found:
            for dep in findings.dependency_files_found:
                print(f"  - {dep}")
        else:
            print("  - No dependency files found")
        
        print("\n⚙️  Configuration:")
        if findings.config_files_found:
            for cfg in findings.config_files_found[:5]:
                print(f"  - {cfg}")
            if len(findings.config_files_found) > 5:
                print(f"  - ... and {len(findings.config_files_found) - 5} more")
        else:
            print("  - No config files found")
        
        print("\n🔐 Secrets:")
        if findings.secrets_files_detected:
            for secret in findings.secrets_files_detected:
                print(f"  - {secret} (location noted, contents not read)")
        else:
            print("  - No secrets files detected")
        
        print("\n🐳 Docker:")
        print(f"  - Docker running: {'Yes' if findings.docker_running else 'No'}")
        
        if findings.blockers:
            print("\n⚠️  Blockers Encountered:")
            for blocker in findings.blockers:
                print(f"  - {blocker}")
        else:
            print("\n✅ No blockers encountered!")
        
        if findings.warnings:
            print("\n⚡ Warnings:")
            for warning in findings.warnings:
                print(f"  - {warning}")
        
        print("\n" + "="*60)
        if findings.ready_for_next_stage:
            print("✅ PROJECT IS READY FOR THE NEXT STAGE (BUILD)")
            print("="*60 + "\n")
        else:
            print("⚠️  BLOCKERS PRESENT - RESOLVE BEFORE PROCEEDING")
            print("="*60 + "\n")
    
    # Sprint 2: Build and Push Methods
    
    def build_phase(
        self,
        cwd: str,
        review_findings: ReviewFindings
    ) -> Optional[BuildResult]:
        """
        Perform the build phase (Sprint 2).
        
        Args:
            cwd: Current working directory (project root)
            review_findings: Findings from Sprint 1 review
            
        Returns:
            BuildResult with build status and image info, or None if build was skipped
        """
        # AC-1: Verify Sprint 1 review has no blockers
        if not review_findings.ready_for_next_stage:
            print("\n⚠️  Cannot proceed with build - Review blockers must be resolved first")
            print("Blockers:")
            for blocker in review_findings.blockers:
                print(f"  - {blocker}")        
        print("\n" + "="*60)
        print("🔨 STARTING BUILD PHASE (Sprint 2)")
        print("="*60 + "\n")
        
        # Initialize build tool
        build_tool = DockerBuildTool()
        
        # AC-3: Check Docker is running
        if not build_tool.check_docker_running():
            print("\n❌ Docker is not running")
            action = self._ask_user(
                "What should we do?",
                ["Start Docker and retry", "Stop"]
            )
            if action == "Stop":
                return None
            # User will start Docker - we could retry here
            if not build_tool.check_docker_running():
                print("❌ Docker still not running after waiting. Cannot proceed.")
                return None
        
        print("✓ Docker is running\n")
        
        # Get Dockerfile path or generate one
        from pathlib import Path
        project_path = Path(cwd).resolve()
        dockerfile_path = build_tool.get_dockerfile_path(project_path)
        
        # AC-4/UC-4: Handle missing Dockerfile
        if not dockerfile_path:
            print("⚠️  No Dockerfile found in project")
            dockerfile_path = self._handle_dockerfile_generation(
                project_path,
                review_findings
            )
            if not dockerfile_path:
                print("❌ Build aborted - no Dockerfile available")
                return None
        else:
            print(f"✓ Found Dockerfile: {dockerfile_path}")
        
        # Get build context
        build_context = build_tool.get_build_context(project_path)
        
        # Run build
        print(f"\n📦 Building Docker image...")
        print(f"   Context: {build_context}")
        print(f"   Dockerfile: {dockerfile_path}\n")
        
        from src.config import PROJECT_NAME
        image_tag = "latest"
        build_result = build_tool.build_image(
            dockerfile_path=dockerfile_path,
            context_path=build_context,
            image_name=PROJECT_NAME,
            image_tag=image_tag
        )
        
        # Handle build failure (UC-3)
        if not build_result.success:
            print(f"❌ Build failed: {build_result.error_message}")
            if build_result.build_output:
                print(f"\nBuild error details:\n{build_result.build_output}")
            
            action = self._ask_user(
                "How should we proceed?",
                ["Retry", "Stop"]
            )
            if action == "Retry":
                return self.build_phase(cwd, review_findings)        
        # Build succeeded (UC-1)
        print("✓ Build completed successfully!")
        self.present_image_details(build_result)
        
        return build_result
    
    def _handle_dockerfile_generation(
        self,
        project_path: Path,
        review_findings: ReviewFindings
    ) -> Optional[Path]:
        """
        Handle Dockerfile generation when none exists.
        
        Args:
            project_path: Path to project root
            review_findings: Findings from Sprint 1 review
            
        Returns:
            Path to generated Dockerfile, or None if generation failed
        """
        print("\n🔧 Generating Dockerfile using multi-stage-dockerfile skill...\n")
        
        generator = DockerfileGenerator()
        
        # Generate Dockerfile
        dockerfile_content = generator.generate_dockerfile(
            project_info=review_directory(str(project_path)),
            project_path=project_path
        )
        
        if not dockerfile_content:
            print("❌ Failed to generate Dockerfile - skill may not support this framework")
            action = self._ask_user(
                "What would you like to do?",
                ["Provide your own Dockerfile", "Stop"]
            )
            if action == "Provide your own Dockerfile":
                dockerfile_path = project_path / "Dockerfile"
                print(f"\nPlease create a Dockerfile at: {dockerfile_path}")
                print("Then run the build again.")
                return None        
        # Validate generated Dockerfile
        if not generator.validate_dockerfile(dockerfile_content):
            print("❌ Generated Dockerfile is invalid")        
        # Present to user before proceeding (AC-5)
        print("📄 Generated Dockerfile:")
        print("-" * 60)
        print(dockerfile_content)
        print("-" * 60 + "\n")
        
        confirm = self._ask_user(
            "Does this Dockerfile look correct?",
            ["Yes, use it", "No, stop"]
        )
        
        if confirm == "No, stop":        
        # Save the generated Dockerfile
        dockerfile_path = project_path / "Dockerfile"
        if generator.save_generated_dockerfile(dockerfile_content, dockerfile_path):
            print(f"✓ Saved Dockerfile to: {dockerfile_path}\n")
            return dockerfile_path
        else:
            print("❌ Failed to save generated Dockerfile")    
    def present_image_details(self, build_result: BuildResult) -> None:
        """
        Present image details to user before push approval.
        
        Args:
            build_result: BuildResult from successful build
        """
        if not build_result.image_info:
            return
        
        info = build_result.image_info
        
        print("\n" + "="*60)
        print("🎯 IMAGE BUILD DETAILS")
        print("="*60)
        
        print(f"\n📦 Image Information:")
        print(f"  - Name: {info.image_name}")
        print(f"  - Tag: {info.image_tag}")
        print(f"  - Full Reference: {info.image_name}:{info.image_tag}")
        print(f"  - Image ID: {info.image_id}")
        
        if info.size:
            size_mb = info.size / (1024 * 1024)
            print(f"  - Size: {size_mb:.2f} MB")
        
        if info.base_image:
            print(f"  - Base Image: {info.base_image}")
        
        if info.layers > 0:
            print(f"  - Layers: {info.layers}")
        
        print("\n" + "="*60 + "\n")
    
    def push_approval(self) -> bool:
        """
        Request user approval to push image to GHCR.
        
        Returns:
            True if user approves push, False otherwise
        """
        confirm = self._ask_user(
            "Do you want to push this image to GHCR?",
            ["Yes, push to GHCR", "No, keep local only"]
        )
        
        return confirm == "Yes, push to GHCR"
    
    def push_to_ghcr(
        self,
        build_result: BuildResult,
        project_name: Optional[str] = None
    ) -> Optional[PushResult]:
        """
        Push built image to GHCR.
        
        Args:
            build_result: BuildResult from successful build
            project_name: Optional project name for image reference
            
        Returns:
            PushResult with push status, or None if cancelled
        """
        if not build_result.image_info:        
        print("\n" + "="*60)
        print("🚀 PUSHING TO GHCR")
        print("="*60 + "\n")
        
        push_tool = GHCRPushTool()
        local_image = f"{build_result.image_info.image_name}:{build_result.image_info.image_tag}"
        
        # Prompt for credentials (AC-9)
        creds = push_tool.prompt_for_credentials()
        if not creds:
            print("❌ Push cancelled - no credentials provided")        
        username, token = creds
        
        # Prompt for image tag (AC-6)
        image_tag = push_tool.prompt_for_image_tag(default_tag="latest")
        
        # Build remote image reference
        from src.config import GHCR_REGISTRY, PROJECT_NAME
        remote_image = push_tool.build_image_reference(
            registry=GHCR_REGISTRY,
            username=username,
            project_name=project_name or PROJECT_NAME,
            tag=image_tag
        )
        
        # Confirm before push
        print(f"\n📤 Pushing image:")
        print(f"  From: {local_image}")
        print(f"  To:   {remote_image}\n")
        
        confirm = self._ask_user(
            "Confirm push?",
            ["Yes, push", "No, cancel"]
        )
        
        if confirm == "No, cancel":
            print("❌ Push cancelled by user")        
        # Push the image
        push_result = push_tool.push_image(
            local_image=local_image,
            remote_image=remote_image,
            username=username,
            token=token
        )
        
        # Handle push result (AC-8, UC-6)
        if push_result.success:
            print(f"\n✅ Successfully pushed to GHCR!")
            print(f"   Image: {push_result.image_reference}")
            if push_result.push_output:
                print(f"\n   Details: {push_result.push_output}")
            print("\n✅ GATE 1 (GHCR Push) COMPLETE")
            return push_result
        else:
            print(f"\n❌ Push failed: {push_result.error_message}")
            if push_result.push_output:
                print(f"\nDetails:\n{push_result.push_output}")
            
            action = self._ask_user(
                "How should we proceed?",
                ["Retry", "Stop"]
            )
            
            if action == "Retry":
                return self.push_to_ghcr(build_result, project_name)

    def deployment_phase(self, push_result: PushResult) -> bool:
        """Generate manifests, apply them, verify, and hand over to AIOps.

        This implements Sprint 3 responsibilities:
        * Write Kubernetes manifests into the ``deployment/`` directory (only location
          written in this sprint).
        * Reference the exact GHCR image that was pushed.
        * Prompt for any missing cluster‑specific information.
        * Present the manifests for user approval (Gate 2).
        * Apply the manifests with ``kubectl`` and verify a successful rollout.
        * Notify the AI AIOps Employee via Dapr Service Invocation.
        """
        # ---------------------------------------------------------------------
        # Basic pre‑flight checks
        # ---------------------------------------------------------------------
        if not push_result:
            print("❌ No push result – cannot generate manifests.")
            return False
        if not push_result.success or not push_result.image_reference:
            print("❌ Push was not successful – aborting deployment phase.")
            return False

        image_ref = push_result.image_reference
        # ---------------------------------------------------------------------
        # Gather cluster‑specific info from the user
        # ---------------------------------------------------------------------
        # Deployment (app) name – default to project name if not overridden
        default_app_name = os.getenv("PROJECT_NAME", "cloud-platform")
        app_name = self._ask_user(
            f"Enter the deployment name (default: {default_app_name})"
        ).strip()
        if not app_name:
            app_name = default_app_name

        namespace = self._ask_user(
            "Enter the target Kubernetes namespace (default: default)"
        ).strip()
        if not namespace:
            namespace = "default"

        replicas_input = self._ask_user(
            "Number of replicas (default: 1)"
        ).strip()
        try:
            replicas = int(replicas_input) if replicas_input else 1
            if replicas < 1:
                raise ValueError
        except ValueError:
            print("❌ Invalid replica count – using 1.")
            replicas = 1

        container_port_input = self._ask_user(
            "Container port to expose (default: 80)"
        ).strip()
        try:
            container_port = int(container_port_input) if container_port_input else 80
        except ValueError:
            print("❌ Invalid port – using 80.")
            container_port = 80

        # Resource requests / limits – optional
        resources = (None, None)
        want_resources = self._ask_user(
            "Do you want to specify resource requests/limits?",
            ["Yes, specify", "No, use defaults"]
        )
        if want_resources == "Yes, specify":
            cpu_req = self._ask_user("CPU request (e.g., 250m) ")
            mem_req = self._ask_user("Memory request (e.g., 256Mi) ")
            cpu_lim = self._ask_user("CPU limit (e.g., 500m) ")
            mem_lim = self._ask_user("Memory limit (e.g., 512Mi) ")
            requests = {"cpu": cpu_req, "memory": mem_req} if cpu_req or mem_req else None
            limits = {"cpu": cpu_lim, "memory": mem_lim} if cpu_lim or mem_lim else None
            resources = (requests, limits)

        service_type = self._ask_user(
            "Service type (ClusterIP, NodePort, LoadBalancer)",
            ["ClusterIP", "NodePort", "LoadBalancer"]
        )
        service_port_input = self._ask_user(
            "Service port (default: 80)"
        ).strip()
        try:
            service_port = int(service_port_input) if service_port_input else 80
        except ValueError:
            print("❌ Invalid service port – using 80.")
            service_port = 80

        # ---------------------------------------------------------------------
        # Generate manifests
        # ---------------------------------------------------------------------
        generator = K8sManifestGenerator()
        manifests = generator.generate_all(
            app_name=app_name,
            namespace=namespace,
            image=image_ref,
            replicas=replicas,
            container_port=container_port,
            service_type=service_type,
            service_port=service_port,
            target_port=container_port,
            resources=resources,
        )

        # Present manifests for review
        print("\n" + "=" * 60)
        print("📄 GENERATED KUBERNETES MANIFESTS")
        print("=" * 60)
        for fname, content in manifests.items():
            print(f"--- {fname} ---")
            print(content)
            print("-" * 30 + "\n")

        approve = self._ask_user(
            "Deploy these manifests to the cluster?",
            ["Yes, deploy", "No, abort"]
        )
        if approve != "Yes, deploy":
            print("⚠️  Deployment aborted by user.")
            return False

        # ---------------------------------------------------------------------
        # Write files to deployment/ directory (AC‑1)
        # ---------------------------------------------------------------------
        deployment_dir = Path("deployment")
        deployment_dir.mkdir(parents=True, exist_ok=True)
        for fname, content in manifests.items():
            file_path = deployment_dir / fname
            try:
                file_path.write_text(content)
                print(f"✓ Wrote {file_path}")
            except Exception as e:
                print(f"❌ Failed to write {file_path}: {e}")
                return False

        # ---------------------------------------------------------------------
        # Apply manifests with kubectl
        # ---------------------------------------------------------------------
        apply_cmd = ["kubectl", "apply", "-f", str(deployment_dir)]
        result = subprocess.run(apply_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ kubectl apply failed: {result.stderr or result.stdout}")
            return False
        else:
            print(result.stdout)

        # ---------------------------------------------------------------------
        # Verify rollout success
        # ---------------------------------------------------------------------
        rollout_cmd = [
            "kubectl",
            "rollout",
            "status",
            f"deployment/{app_name}",
            "-n",
            namespace,
            "--timeout=60s",
        ]
        rollout = subprocess.run(rollout_cmd, capture_output=True, text=True)
        if rollout.returncode != 0:
            print(f"❌ Deployment verification failed: {rollout.stderr or rollout.stdout}")
            return False
        else:
            print(rollout.stdout)

        # ---------------------------------------------------------------------
        # Notify AIOps via Dapr
        # ---------------------------------------------------------------------
        handover_success = invoke_aiops_deployment_notification(
            image_reference=image_ref,
            deployment_name=app_name,
            namespace=namespace,
            manifests_dir=str(deployment_dir),
        )
        if handover_success:
            print("✅ Deployment handover to AI AIOps Employee completed successfully.")
        else:
            print("⚠️  Deployment succeeded but handover notification failed.")
        return True