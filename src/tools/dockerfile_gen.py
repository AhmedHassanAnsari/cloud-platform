"""Dockerfile generation using multi-stage-dockerfile skill."""

import logging
from pathlib import Path
from typing import Optional
from src.tools.filesystem import DirectoryReview

logger = logging.getLogger(__name__)


class DockerfileGenerator:
    """Generates multi-stage Dockerfiles using the skill."""
    
    SKILL_PATH = Path(__file__).parent.parent.parent / ".agents" / "skill" / "multi-stage-dockerfile"
    
    def __init__(self):
        """Initialize generator with skill path."""
        self.skill_content = self._load_skill_from_local()
    
    def _load_skill_from_local(self) -> Optional[str]:
        """
        Load multi-stage-dockerfile skill from local .agents/skill directory.
        
        Returns:
            Skill content as string, or None if not found
        """
        if not self.SKILL_PATH.exists():
            logger.warning(f"Skill directory not found: {self.SKILL_PATH}")
            return None
        
        # Try to load SKILL.md or README.md from skill directory
        skill_file = self.SKILL_PATH / "SKILL.md"
        readme_file = self.SKILL_PATH / "README.md"
        
        if skill_file.exists():
            try:
                return skill_file.read_text()
            except Exception as e:
                logger.error(f"Failed to read skill file: {e}")
        
        if readme_file.exists():
            try:
                return readme_file.read_text()
            except Exception as e:
                logger.error(f"Failed to read README: {e}")
        
        logger.warning("No SKILL.md or README.md found in skill directory")
        return None
    
    def detect_project_framework(self, project_info: DirectoryReview) -> str:
        """
        Detect the project framework from review findings.
        
        Args:
            project_info: DirectoryReview with project information
            
        Returns:
            Framework name (e.g., "python", "nodejs", "rust")
        """
        # Check dependency files to determine framework
        for dep_file in project_info.dependency_files:
            # dep_file is a FileInfo object with .path attribute
            file_path = dep_file.path if hasattr(dep_file, 'path') else str(dep_file)
            if "pyproject.toml" in file_path or "requirements.txt" in file_path or "setup.py" in file_path:
                return "python"
            elif "package.json" in file_path:
                return "nodejs"
            elif "Cargo.toml" in file_path:
                return "rust"
            elif "go.mod" in file_path:
                return "go"
            elif "pom.xml" in file_path or "build.gradle" in file_path:
                return "java"
        
        # Default if no clear framework detected
        return "generic"
    
    def get_base_image_for_framework(self, framework: str) -> str:
        """
        Get recommended base image for framework.
        
        Args:
            framework: Framework name
            
        Returns:
            Base image reference
        """
        base_images = {
            "python": "python:3.12-alpine",
            "nodejs": "node:20-alpine",
            "rust": "rust:latest",
            "go": "golang:1.21-alpine",
            "java": "eclipse-temurin:21-jdk-alpine",
            "generic": "alpine:latest"
        }
        return base_images.get(framework, "alpine:latest")
    
    def generate_dockerfile(
        self,
        project_info: DirectoryReview,
        project_path: Path,
        base_image: Optional[str] = None,
        framework: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate a multi-stage Dockerfile for the project.
        
        Args:
            project_info: DirectoryReview with project information
            project_path: Path to project root
            base_image: Optional override for base image
            framework: Optional override for detected framework
            
        Returns:
            Generated Dockerfile content as string, or None if generation failed
        """
        # Detect framework if not provided
        if not framework:
            framework = self.detect_project_framework(project_info)
        
        # Determine base image
        if not base_image:
            base_image = self.get_base_image_for_framework(framework)
        
        logger.info(f"Generating {framework} Dockerfile with base image: {base_image}")
        
        # Generate framework-specific Dockerfile
        if framework == "python":
            return self._generate_python_dockerfile(project_path, base_image)
        elif framework == "nodejs":
            return self._generate_nodejs_dockerfile(project_path, base_image)
        elif framework == "rust":
            return self._generate_rust_dockerfile(project_path, base_image)
        elif framework == "go":
            return self._generate_go_dockerfile(project_path, base_image)
        else:
            return self._generate_generic_dockerfile(base_image)
    
    def _generate_python_dockerfile(self, project_path: Path, base_image: str) -> str:
        """Generate multi-stage Python Dockerfile."""
        return f"""# Multi-stage Python Dockerfile
# Generated by AI DevOps Employee (Sprint 2)

FROM {base_image} AS builder

WORKDIR /build

# Install build dependencies
RUN apk add --no-cache gcc musl-dev linux-headers

# Copy dependency files
COPY pyproject.toml* setup.py* setup.cfg* requirements.txt* ./

# Install Python dependencies
RUN if [ -f pyproject.toml ]; then \\
    pip install --no-cache-dir build && python -m build; \\
    elif [ -f requirements.txt ]; then \\
    pip install --no-cache-dir -r requirements.txt; \\
    elif [ -f setup.py ]; then \\
    pip install --no-cache-dir -e .; \\
    fi

# Runtime stage
FROM {base_image}

WORKDIR /app

# Install runtime dependencies only
RUN apk add --no-cache curl

# Copy only necessary files from builder
COPY --from=builder /build /app

# Copy application source code
COPY . .

# Create non-root user
RUN addgroup -g 1000 appuser && \\
    adduser -D -u 1000 -G appuser appuser
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \\
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Default command
CMD ["python", "main.py"]
"""
    
    def _generate_nodejs_dockerfile(self, project_path: Path, base_image: str) -> str:
        """Generate multi-stage Node.js Dockerfile."""
        return f"""# Multi-stage Node.js Dockerfile
# Generated by AI DevOps Employee (Sprint 2)

FROM {base_image} AS builder

WORKDIR /build

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production

# Runtime stage
FROM {base_image}

WORKDIR /app

# Install dumb-init to handle signals properly
RUN npm install -g dumb-init

# Copy node_modules from builder
COPY --from=builder /build/node_modules ./node_modules

# Copy application source code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && \\
    chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \\
    CMD node -e "require('http').get('http://localhost:3000', (r) => {{if (r.statusCode !== 200) throw new Error(r.statusCode)}}).on('error', (e) => {{throw e}});" || exit 1

# Use dumb-init to handle signals
ENTRYPOINT ["/usr/local/bin/dumb-init", "--"]

# Default command
CMD ["node", "server.js"]
"""
    
    def _generate_rust_dockerfile(self, project_path: Path, base_image: str) -> str:
        """Generate multi-stage Rust Dockerfile."""
        builder_image = base_image if "rust" in base_image else "rust:latest"
        runtime_image = "alpine:latest" if "alpine" not in base_image else base_image
        
        return f"""# Multi-stage Rust Dockerfile
# Generated by AI DevOps Employee (Sprint 2)

FROM {builder_image} AS builder

WORKDIR /build

# Copy Cargo files
COPY Cargo.toml Cargo.lock* ./

# Create dummy src to cache dependencies
RUN mkdir src && \\
    echo "fn main() {{}}" > src/main.rs && \\
    cargo build --release && \\
    rm -rf src

# Copy actual source code
COPY src ./src

# Build the application
RUN cargo build --release

# Runtime stage
FROM {runtime_image}

WORKDIR /app

# Install runtime dependencies
RUN apk add --no-cache ca-certificates

# Copy binary from builder
COPY --from=builder /build/target/release/* ./

# Create non-root user
RUN addgroup -g 1000 appuser && \\
    adduser -D -u 1000 -G appuser appuser
USER appuser

# Default command
CMD ["./application"]
"""
    
    def _generate_go_dockerfile(self, project_path: Path, base_image: str) -> str:
        """Generate multi-stage Go Dockerfile."""
        builder_image = "golang:1.21-alpine" if "alpine" not in base_image else base_image
        
        return f"""# Multi-stage Go Dockerfile
# Generated by AI DevOps Employee (Sprint 2)

FROM {builder_image} AS builder

WORKDIR /build

# Copy go mod files
COPY go.mod go.sum* ./

# Download dependencies
RUN go mod download

# Copy source code
COPY . .

# Build the application
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o application .

# Runtime stage
FROM alpine:latest

WORKDIR /app

# Install runtime dependencies
RUN apk add --no-cache ca-certificates

# Copy binary from builder
COPY --from=builder /build/application .

# Create non-root user
RUN addgroup -g 1000 appuser && \\
    adduser -D -u 1000 -G appuser appuser
USER appuser

# Expose port (adjust as needed)
EXPOSE 8080

# Default command
CMD ["./application"]
"""
    
    def _generate_generic_dockerfile(self, base_image: str) -> str:
        """Generate a generic minimal Dockerfile."""
        return f"""# Generic Dockerfile
# Generated by AI DevOps Employee (Sprint 2)

FROM {base_image}

WORKDIR /app

# Copy application files
COPY . .

# Create non-root user
RUN addgroup -g 1000 appuser && \\
    adduser -D -u 1000 -G appuser appuser
USER appuser

# Default command
CMD ["/bin/sh"]
"""
    
    def validate_dockerfile(self, content: str) -> bool:
        """
        Validate Dockerfile content.
        
        Args:
            content: Dockerfile content to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not content:
            return False
        
        # Basic validation: check for required keywords
        required_keywords = ["FROM"]
        return all(keyword in content for keyword in required_keywords)
    
    def save_generated_dockerfile(self, content: str, output_path: Path) -> bool:
        """
        Save generated Dockerfile to disk.
        
        Args:
            content: Dockerfile content
            output_path: Path to save Dockerfile
            
        Returns:
            True if successful, False otherwise
        """
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content)
            logger.info(f"Saved generated Dockerfile to: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save Dockerfile: {e}")
            return False
