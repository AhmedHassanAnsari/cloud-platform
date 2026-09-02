"""GHCR push operations with secure credential handling."""

import logging
import getpass
import subprocess
from typing import Optional, Tuple
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PushResult(BaseModel):
    """Result from a GHCR push operation."""
    success: bool
    image_reference: Optional[str] = None
    push_output: Optional[str] = None
    error_message: Optional[str] = None


class GHCRPushTool:
    """Orchestrates GHCR push operations with secure credential handling."""
    
    GHCR_REGISTRY = "ghcr.io"
    
    def prompt_for_credentials(self) -> Optional[Tuple[str, str]]:
        """
        Prompt user for GHCR credentials with masked input.
        
        Returns:
            Tuple of (username, token) if successful, None if user cancels
        """
        print("\n🔑 GHCR Authentication Required")
        print("=" * 60)
        
        try:
            username = input("GitHub Username: ").strip()
            if not username:
                print("❌ Username cannot be empty")
                return None
            
            # Masked input for token (not echoed to terminal)
            token = getpass.getpass("GitHub Personal Access Token (hidden): ").strip()
            if not token:
                print("❌ Token cannot be empty")
                return None
            
            return (username, token)
        
        except KeyboardInterrupt:
            print("\n❌ Authentication cancelled by user")
            return None
        except Exception as e:
            logger.error(f"Error during credential prompt: {e}")
            print(f"❌ Error: {e}")
            return None
    
    def prompt_for_image_tag(self, default_tag: str = "latest") -> str:
        """
        Prompt user for image tag.
        
        Args:
            default_tag: Default tag if user doesn't specify one
            
        Returns:
            Image tag chosen by user
        """
        print(f"\n🏷️  Image Tag (default: {default_tag}):")
        try:
            tag = input("Enter tag (or press Enter for default): ").strip()
            return tag if tag else default_tag
        except KeyboardInterrupt:
            print(f"Using default tag: {default_tag}")
            return default_tag
    
    def build_image_reference(
        self,
        registry: str,
        username: str,
        project_name: str,
        tag: str
    ) -> str:
        """
        Build full image reference in Docker registry format.
        
        Args:
            registry: Registry host (e.g., ghcr.io)
            username: Registry username/namespace
            project_name: Project/repository name
            tag: Image tag
            
        Returns:
            Full image reference (e.g., ghcr.io/username/project-name:tag)
        """
        # Normalize project name (lowercase, replace underscores)
        normalized_name = project_name.lower().replace("_", "-")
        return f"{registry}/{username}/{normalized_name}:{tag}"
    
    def validate_credentials(self, username: str, token: str) -> bool:
        """
        Validate GHCR credentials.
        
        Args:
            username: GitHub username
            token: GitHub personal access token
            
        Returns:
            True if credentials appear valid, False otherwise
        """
        # Basic validation
        if not username or len(username) < 2:
            logger.error("Invalid username")
            return False
        
        if not token or len(token) < 20:
            logger.error("Invalid token (too short)")
            return False
        
        # Token should be a personal access token format
        if not (token.startswith("ghp_") or token.startswith("github_pat_")):
            logger.warning("Token doesn't appear to be a GitHub PAT, but proceeding")
        
        return True
    
    def authenticate_ghcr(self, username: str, token: str) -> bool:
        """
        Authenticate with GHCR using Docker login.
        
        Args:
            username: GitHub username
            token: GitHub personal access token
            
        Returns:
            True if authentication successful, False otherwise
        """
        try:
            # Use 'docker login' with credentials
            # Note: Token is used as password
            cmd = ["docker", "login", "-u", username, "-p", token, self.GHCR_REGISTRY]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                error = result.stderr if result.stderr else result.stdout
                logger.error(f"Docker login failed: {error}")
                return False
            
            logger.info("Successfully authenticated with GHCR")
            return True
        
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False
    
    def push_image(
        self,
        local_image: str,
        remote_image: str,
        username: str,
        token: str
    ) -> PushResult:
        """
        Push Docker image to GHCR.
        
        Args:
            local_image: Local image reference (e.g., "myapp:latest")
            remote_image: Remote GHCR image reference (e.g., "ghcr.io/user/myapp:v1")
            username: GitHub username for authentication
            token: GitHub personal access token
            
        Returns:
            PushResult with success status and output/error
        """
        # Validate credentials
        if not self.validate_credentials(username, token):
            return PushResult(
                success=False,
                error_message="Invalid credentials provided"
            )
        
        # Authenticate with GHCR
        if not self.authenticate_ghcr(username, token):
            return PushResult(
                success=False,
                error_message="Failed to authenticate with GHCR. Check your username and token."
            )
        
        try:
            # Tag the local image with remote reference
            tag_cmd = ["docker", "tag", local_image, remote_image]
            tag_result = subprocess.run(
                tag_cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if tag_result.returncode != 0:
                return PushResult(
                    success=False,
                    error_message=f"Failed to tag image: {tag_result.stderr}"
                )
            
            # Push the image
            push_cmd = ["docker", "push", remote_image]
            logger.info(f"Pushing: {' '.join(push_cmd)}")
            
            push_result = subprocess.run(
                push_cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout for push
            )
            
            if push_result.returncode != 0:
                error_output = push_result.stderr if push_result.stderr else push_result.stdout
                
                # Categorize error
                if "unauthorized" in error_output.lower() or "authentication" in error_output.lower():
                    error_msg = "Authentication failed. Check your GHCR credentials."
                elif "connection" in error_output.lower() or "network" in error_output.lower():
                    error_msg = "Network error. Check your internet connection."
                elif "not found" in error_output.lower():
                    error_msg = "Image not found locally. Build may have failed."
                else:
                    error_msg = f"Push failed: {error_output[-500:] if len(error_output) > 500 else error_output}"
                
                return PushResult(
                    success=False,
                    image_reference=remote_image,
                    error_message=error_msg,
                    push_output=push_result.stdout[-300:] if len(push_result.stdout) > 300 else push_result.stdout
                )
            
            logger.info(f"Successfully pushed image to GHCR: {remote_image}")
            
            return PushResult(
                success=True,
                image_reference=remote_image,
                push_output=push_result.stdout[-300:] if len(push_result.stdout) > 300 else push_result.stdout
            )
        
        except subprocess.TimeoutExpired:
            return PushResult(
                success=False,
                image_reference=remote_image,
                error_message="Push operation timed out (>5 minutes). The image may be too large."
            )
        
        except Exception as e:
            return PushResult(
                success=False,
                image_reference=remote_image,
                error_message=f"Unexpected error during push: {str(e)}"
            )
    
    def cleanup_credentials(self) -> None:
        """Clear any cached credentials (if implemented)."""
        # Note: docker login caches credentials in ~/.docker/config.json
        # This is handled by Docker itself, but we could implement logout if needed
        logger.debug("Credential cleanup (handled by Docker daemon)")
