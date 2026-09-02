"""Filesystem inspection tools for project review."""

import os
import subprocess
from pathlib import Path
from typing import Optional
from pydantic import BaseModel


class FileInfo(BaseModel):
    """Information about a file."""
    path: str
    size: int


class DirectoryReview(BaseModel):
    """Results from directory review."""
    is_valid_project: bool
    project_markers: list[str]
    source_files: list[FileInfo]
    dependency_files: list[FileInfo]
    config_files: list[FileInfo]
    secrets_files: list[FileInfo]
    services_detected: list[str]


def check_project_validity(cwd: str = ".") -> bool:
    """
    Check if the given directory looks like a valid project.
    
    Looks for project markers:
    - pyproject.toml, setup.py, setup.cfg, requirements.txt (Python)
    - package.json (Node.js)
    - Cargo.toml (Rust)
    - pom.xml (Java Maven)
    - build.gradle (Java Gradle)
    - go.mod (Go)
    - Dockerfile or docker-compose.yml
    - .git directory
    
    Args:
        cwd: Current working directory to check
        
    Returns:
        True if directory contains recognizable project markers
    """
    project_root = Path(cwd).resolve()
    
    markers = [
        "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
        "package.json", "Cargo.toml", "pom.xml", "build.gradle",
        "go.mod", "Dockerfile", "docker-compose.yml",
        ".git", "Makefile", ".gitignore"
    ]
    
    found_markers = []
    for marker in markers:
        if (project_root / marker).exists():
            found_markers.append(marker)
    
    return len(found_markers) > 0, found_markers


def get_source_files(cwd: str = ".", max_depth: int = 3) -> list[FileInfo]:
    """
    Get all source code files in the project.
    
    Args:
        cwd: Current working directory
        max_depth: Maximum directory depth to scan
        
    Returns:
        List of source file information
    """
    source_files = []
    project_root = Path(cwd).resolve()
    
    source_extensions = {
        ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs",
        ".java", ".cpp", ".c", ".h", ".cs", ".rb", ".php"
    }
    
    exclude_dirs = {".git", "node_modules", ".venv", "venv", "target", "__pycache__"}
    
    for root, dirs, files in os.walk(project_root):
        # Remove excluded directories from dirs in-place to prevent recursion
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        # Check depth
        depth = len(Path(root).relative_to(project_root).parts)
        if depth > max_depth:
            continue
        
        for file in files:
            if Path(file).suffix in source_extensions:
                file_path = Path(root) / file
                try:
                    size = file_path.stat().st_size
                    rel_path = str(file_path.relative_to(project_root))
                    source_files.append(FileInfo(path=rel_path, size=size))
                except (OSError, ValueError):
                    pass
    
    return source_files


def get_dependencies(cwd: str = ".") -> tuple[list[FileInfo], Optional[str]]:
    """
    Get dependency manifest files and detect framework/version info.
    
    Args:
        cwd: Current working directory
        
    Returns:
        Tuple of (dependency_files, detected_framework_version or error message)
    """
    project_root = Path(cwd).resolve()
    dependency_files = []
    
    # Check for Python dependencies
    pyproject_path = project_root / "pyproject.toml"
    requirements_path = project_root / "requirements.txt"
    
    if pyproject_path.exists():
        try:
            size = pyproject_path.stat().st_size
            dependency_files.append(FileInfo(path="pyproject.toml", size=size))
            
            # Try to parse version from pyproject.toml
            with open(pyproject_path) as f:
                content = f.read()
                if 'requires-python' in content:
                    # Extract Python version requirement
                    for line in content.split('\n'):
                        if 'requires-python' in line:
                            return dependency_files, f"Python version requirement found: {line.strip()}"
                return dependency_files, None
        except (OSError, ValueError):
            pass
    
    if requirements_path.exists():
        try:
            size = requirements_path.stat().st_size
            dependency_files.append(FileInfo(path="requirements.txt", size=size))
        except (OSError, ValueError):
            pass
    
    # Check for Node.js
    package_json = project_root / "package.json"
    if package_json.exists():
        try:
            size = package_json.stat().st_size
            dependency_files.append(FileInfo(path="package.json", size=size))
        except (OSError, ValueError):
            pass
    
    # Check for Go
    go_mod = project_root / "go.mod"
    if go_mod.exists():
        try:
            size = go_mod.stat().st_size
            dependency_files.append(FileInfo(path="go.mod", size=size))
        except (OSError, ValueError):
            pass
    
    # Check for Rust
    cargo_toml = project_root / "Cargo.toml"
    if cargo_toml.exists():
        try:
            size = cargo_toml.stat().st_size
            dependency_files.append(FileInfo(path="Cargo.toml", size=size))
        except (OSError, ValueError):
            pass
    
    return dependency_files, None


def get_config_files(cwd: str = ".") -> list[FileInfo]:
    """
    Get configuration files.
    
    Args:
        cwd: Current working directory
        
    Returns:
        List of configuration files
    """
    project_root = Path(cwd).resolve()
    config_files = []
    
    config_names = [
        "docker-compose.yml", "docker-compose.yaml",
        "Dockerfile", ".dockerignore",
        ".env.example", ".env.sample",
        "nginx.conf", "app.conf",
        ".github", "Makefile", ".gitignore",
        "pyproject.toml", "setup.cfg",
        "tsconfig.json", ".eslintrc.json",
    ]
    
    for name in config_names:
        path = project_root / name
        if path.exists():
            try:
                if path.is_file():
                    size = path.stat().st_size
                    config_files.append(FileInfo(path=name, size=size))
                elif path.is_dir():
                    # For directories like .github, just record existence
                    config_files.append(FileInfo(path=name, size=0))
            except (OSError, ValueError):
                pass
    
    return config_files


def get_secrets_files(cwd: str = ".") -> list[FileInfo]:
    """
    Get potential secrets files (location only, never read contents).
    
    Args:
        cwd: Current working directory
        
    Returns:
        List of potential secrets files (path and size only, no contents)
    """
    project_root = Path(cwd).resolve()
    secrets_files = []
    
    secrets_patterns = [
        ".env", ".env.local", ".env.*.local",
        "secrets.json", ".secrets",
        "credentials.json", ".aws", ".ssh",
        "known_hosts",
    ]
    
    for pattern in secrets_patterns:
        if "*" in pattern:
            # Handle glob patterns
            for path in project_root.glob(pattern):
                if path.is_file():
                    try:
                        size = path.stat().st_size
                        rel_path = str(path.relative_to(project_root))
                        secrets_files.append(FileInfo(path=rel_path, size=size))
                    except (OSError, ValueError):
                        pass
        else:
            path = project_root / pattern
            if path.exists():
                try:
                    if path.is_file():
                        size = path.stat().st_size
                        secrets_files.append(FileInfo(path=pattern, size=size))
                    elif path.is_dir():
                        secrets_files.append(FileInfo(path=pattern, size=0))
                except (OSError, ValueError):
                    pass
    
    return secrets_files


def get_services(cwd: str = ".") -> list[str]:
    """
    Detect services mentioned in project configuration.
    
    Args:
        cwd: Current working directory
        
    Returns:
        List of detected services
    """
    project_root = Path(cwd).resolve()
    services = []
    
    # Check docker-compose.yml
    docker_compose_path = project_root / "docker-compose.yml"
    if docker_compose_path.exists():
        try:
            with open(docker_compose_path) as f:
                content = f.read()
                # Simple detection: look for "services:" section
                if "services:" in content:
                    services.append("Docker Compose detected")
                    # Try to extract service names
                    in_services = False
                    for line in content.split('\n'):
                        if line.strip().startswith("services:"):
                            in_services = True
                            continue
                        if in_services and line.startswith("  ") and not line.startswith("    "):
                            service_name = line.strip().rstrip(":")
                            if service_name and not service_name.startswith("#"):
                                services.append(f"Service: {service_name}")
        except (OSError, ValueError, UnicodeDecodeError):
            pass
    
    # Check for Dockerfile
    if (project_root / "Dockerfile").exists():
        services.append("Dockerfile detected")
    
    return services


def check_docker_running() -> bool:
    """
    Check if Docker daemon is running.
    
    Returns:
        True if Docker is accessible, False otherwise
    """
    try:
        result = subprocess.run(
            ["docker", "ps"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def review_directory(cwd: str = ".") -> DirectoryReview:
    """
    Perform a complete directory review.
    
    Args:
        cwd: Current working directory to review
        
    Returns:
        DirectoryReview with all collected information
    """
    is_valid, markers = check_project_validity(cwd)
    source_files = get_source_files(cwd) if is_valid else []
    dependency_files, version_info = get_dependencies(cwd) if is_valid else ([], None)
    config_files = get_config_files(cwd) if is_valid else []
    secrets_files = get_secrets_files(cwd) if is_valid else []
    services = get_services(cwd) if is_valid else []
    
    return DirectoryReview(
        is_valid_project=is_valid,
        project_markers=markers,
        source_files=source_files,
        dependency_files=dependency_files,
        config_files=config_files,
        secrets_files=secrets_files,
        services_detected=services,
    )
