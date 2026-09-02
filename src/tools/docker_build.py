"""Docker build operations for Sprint 2."""

import subprocess
import json
import logging
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ImageInfo(BaseModel):
    """Information about a built Docker image."""
    image_id: str
    image_name: str
    image_tag: str
    size: Optional[int] = None  # Size in bytes
    base_image: Optional[str] = None
    layers: int = 0
    created_at: Optional[str] = None


class BuildResult(BaseModel):
    """Result from a Docker build operation."""
    success: bool
    image_info: Optional[ImageInfo] = None
    error_message: Optional[str] = None
    build_output: Optional[str] = None
    dockerfile_path: Optional[str] = None


class DockerBuildTool:
    """Orchestrates Docker build operations."""
    
    def check_docker_running(self) -> bool:
        """
        Check if Docker daemon is running.
        
        Returns:
            True if Docker is accessible and running
        """
        try:
            result = subprocess.run(
                ["docker", "ps"],
                capture_output=True,
                timeout=5,
                text=True
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def get_dockerfile_path(self, cwd: Path) -> Optional[Path]:
        """
        Find Dockerfile in the project.
        
        Args:
            cwd: Current working directory (project root)
            
        Returns:
            Path to Dockerfile if found, None otherwise
        """
        project_root = Path(cwd).resolve()
        
        dockerfile_names = ["Dockerfile", "dockerfile", "Dockerfile.prod"]
        for name in dockerfile_names:
            dockerfile_path = project_root / name
            if dockerfile_path.exists() and dockerfile_path.is_file():
                return dockerfile_path
        
        return None
    
    def get_build_context(
        self,
        cwd: Path,
        custom_context: Optional[Path] = None
    ) -> Path:
        """
        Determine the build context directory.
        
        Args:
            cwd: Current working directory (project root)
            custom_context: Optional custom context directory
            
        Returns:
            Path to build context directory
        """
        if custom_context:
            context_path = Path(custom_context).resolve()
            if context_path.exists() and context_path.is_dir():
                return context_path
            logger.warning(f"Custom context not found: {custom_context}, using project root")
        
        return Path(cwd).resolve()
    
    def build_image(
        self,
        dockerfile_path: Path,
        context_path: Path,
        image_name: str,
        image_tag: str,
        build_args: Optional[dict] = None
    ) -> BuildResult:
        """
        Build a Docker image.
        
        Args:
            dockerfile_path: Path to Dockerfile
            context_path: Build context directory
            image_name: Image name (e.g., "cloud-platform")
            image_tag: Image tag (e.g., "latest", "v1.0.0")
            build_args: Optional build arguments (--build-arg key=value)
            
        Returns:
            BuildResult with success status and image info or error
        """
        # Check Docker is running first
        if not self.check_docker_running():
            return BuildResult(
                success=False,
                error_message="Docker daemon is not running. Please start Docker and try again."
            )
        
        # Validate paths
        if not dockerfile_path.exists():
            return BuildResult(
                success=False,
                error_message=f"Dockerfile not found: {dockerfile_path}"
            )
        
        if not context_path.exists():
            return BuildResult(
                success=False,
                error_message=f"Build context not found: {context_path}"
            )
        
        # Build the image reference
        image_ref = f"{image_name}:{image_tag}"
        
        # Prepare docker build command
        cmd = [
            "docker", "build",
            "-t", image_ref,
            "-f", str(dockerfile_path),
        ]
        
        # Add build args if provided
        if build_args:
            for key, value in build_args.items():
                cmd.extend(["--build-arg", f"{key}={value}"])
        
        # Add context
        cmd.append(str(context_path))
        
        logger.info(f"Running: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=600,  # 10 minute timeout
                text=True,
                cwd=context_path
            )
            
            if result.returncode != 0:
                # Build failed
                error_output = result.stderr if result.stderr else result.stdout
                return BuildResult(
                    success=False,
                    error_message="Docker build failed",
                    build_output=error_output[-1000:] if len(error_output) > 1000 else error_output,  # Last 1000 chars
                    dockerfile_path=str(dockerfile_path)
                )
            
            # Build succeeded, get image info
            image_info = self.get_image_info(image_name, image_tag)
            
            return BuildResult(
                success=True,
                image_info=image_info,
                build_output=result.stdout[-500:] if len(result.stdout) > 500 else result.stdout,
                dockerfile_path=str(dockerfile_path)
            )
        
        except subprocess.TimeoutExpired:
            return BuildResult(
                success=False,
                error_message="Docker build timed out (>10 minutes). Build may be taking too long.",
                dockerfile_path=str(dockerfile_path)
            )
        except Exception as e:
            return BuildResult(
                success=False,
                error_message=f"Unexpected error during build: {str(e)}",
                dockerfile_path=str(dockerfile_path)
            )
    
    def get_image_info(self, image_name: str, image_tag: str) -> Optional[ImageInfo]:
        """
        Get information about a built image.
        
        Args:
            image_name: Image name
            image_tag: Image tag
            
        Returns:
            ImageInfo with image metadata
        """
        image_ref = f"{image_name}:{image_tag}"
        
        try:
            # Get image info in JSON format
            result = subprocess.run(
                ["docker", "inspect", image_ref],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return None
            
            image_data = json.loads(result.stdout)
            if not image_data:
                return None
            
            image_obj = image_data[0]
            
            # Extract size (virtual size in bytes)
            size = image_obj.get("VirtualSize")
            
            # Extract base image from config
            base_image = None
            if "Config" in image_obj and "Image" in image_obj["Config"]:
                base_image = image_obj["Config"]["Image"]
            
            # Count layers
            layers = len(image_obj.get("RootFS", {}).get("Layers", []))
            
            # Get creation timestamp
            created_at = image_obj.get("Created")
            
            # Get image ID (short form)
            image_id = image_obj["Id"].split(":")[-1][:12]
            
            return ImageInfo(
                image_id=image_id,
                image_name=image_name,
                image_tag=image_tag,
                size=size,
                base_image=base_image,
                layers=layers,
                created_at=created_at
            )
        
        except Exception as e:
            logger.error(f"Failed to get image info: {e}")
            return None
    
    def tag_image(self, source_image: str, target_image: str) -> bool:
        """
        Tag an image with a new name/tag.
        
        Args:
            source_image: Source image reference (e.g., "myimage:latest")
            target_image: Target image reference (e.g., "ghcr.io/user/myimage:v1.0")
            
        Returns:
            True if successful, False otherwise
        """
        try:
            result = subprocess.run(
                ["docker", "tag", source_image, target_image],
                capture_output=True,
                timeout=10,
                text=True
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to tag image: {e}")
            return False
