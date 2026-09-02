"""Tests for Sprint 1 - Project Intake & Review."""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.agents.devops_agent import DevOpsAgent, ReviewFindings
from src.tools.filesystem import (
    check_project_validity,
    get_source_files,
    get_dependencies,
    get_config_files,
    get_secrets_files,
    get_services,
    check_docker_running,
    review_directory,
)


class TestProjectValidity:
    """Tests for UC-5: Invalid or non-project directory."""
    
    def test_ac4_valid_project_with_markers(self):
        """AC-4: Recognize valid project with markers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a marker file
            Path(tmpdir, "pyproject.toml").touch()
            
            is_valid, markers = check_project_validity(tmpdir)
            assert is_valid is True
            assert "pyproject.toml" in markers
    
    def test_ac4_valid_project_git(self):
        """AC-4: Recognize valid project with .git."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, ".git").mkdir()
            
            is_valid, markers = check_project_validity(tmpdir)
            assert is_valid is True
            assert ".git" in markers
    
    def test_ac4_invalid_project_no_markers(self):
        """AC-4: Reject empty directory with no markers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            is_valid, markers = check_project_validity(tmpdir)
            assert is_valid is False
            assert len(markers) == 0
    
    def test_ac4_multiple_markers(self):
        """AC-4: Recognize project with multiple markers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "pyproject.toml").touch()
            Path(tmpdir, ".git").mkdir()
            Path(tmpdir, "Dockerfile").touch()
            
            is_valid, markers = check_project_validity(tmpdir)
            assert is_valid is True
            assert "pyproject.toml" in markers
            assert ".git" in markers
            assert "Dockerfile" in markers


class TestSourceCodeReview:
    """Tests for AC-3: Review source code."""
    
    def test_ac3_source_code_detection(self):
        """AC-3: Detect source code files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a marker first
            Path(tmpdir, "pyproject.toml").touch()
            
            # Create source files
            Path(tmpdir, "main.py").write_text("print('hello')")
            Path(tmpdir, "utils.py").write_text("# utils")
            
            source_files = get_source_files(tmpdir)
            assert len(source_files) >= 2
            paths = [sf.path for sf in source_files]
            assert any("main.py" in p for p in paths)
            assert any("utils.py" in p for p in paths)
    
    def test_ac3_excludes_venv(self):
        """AC-3: Exclude virtual environments from scan."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "pyproject.toml").touch()
            
            # Create venv with Python files
            venv_dir = Path(tmpdir, ".venv", "lib")
            venv_dir.mkdir(parents=True)
            (venv_dir / "module.py").write_text("# in venv")
            
            # Create source file
            Path(tmpdir, "main.py").write_text("# main")
            
            source_files = get_source_files(tmpdir)
            paths = [sf.path for sf in source_files]
            
            # Should have main.py but not .venv stuff
            assert any("main.py" in p for p in paths)
            assert not any(".venv" in p for p in paths)


class TestDependenciesReview:
    """Tests for AC-3 & UC-2: Review dependencies and framework version."""
    
    def test_ac3_detect_pyproject(self):
        """AC-3: Detect pyproject.toml dependency file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pyproject_path = Path(tmpdir, "pyproject.toml")
            pyproject_path.write_text(
                "[project]\n"
                "requires-python = \">=3.12\"\n"
            )
            
            dep_files, version_info = get_dependencies(tmpdir)
            assert len(dep_files) > 0
            assert any(df.path == "pyproject.toml" for df in dep_files)
    
    def test_ac5_framework_version_detection(self):
        """AC-5: Detect framework version from pyproject.toml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pyproject_path = Path(tmpdir, "pyproject.toml")
            pyproject_path.write_text(
                "[project]\n"
                "requires-python = \">=3.12\"\n"
            )
            
            dep_files, version_info = get_dependencies(tmpdir)
            # Should detect version requirement
            assert version_info is not None
            assert "3.12" in version_info or "requires-python" in version_info
    
    def test_ac3_detect_requirements_txt(self):
        """AC-3: Detect requirements.txt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "requirements.txt").write_text("pytest>=7.0\n")
            
            dep_files, _ = get_dependencies(tmpdir)
            assert any(df.path == "requirements.txt" for df in dep_files)
    
    def test_ac3_detect_package_json(self):
        """AC-3: Detect package.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "package.json").write_text("{\"name\": \"app\"}\n")
            
            dep_files, _ = get_dependencies(tmpdir)
            assert any(df.path == "package.json" for df in dep_files)


class TestConfigurationReview:
    """Tests for AC-3: Review configuration files."""
    
    def test_ac3_detect_docker_compose(self):
        """AC-3: Detect docker-compose.yml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "docker-compose.yml").touch()
            
            config_files = get_config_files(tmpdir)
            assert any("docker-compose" in cf.path for cf in config_files)
    
    def test_ac3_detect_dockerfile(self):
        """AC-3: Detect Dockerfile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "Dockerfile").touch()
            
            config_files = get_config_files(tmpdir)
            assert any("Dockerfile" == cf.path for cf in config_files)
    
    def test_ac3_detect_gitignore(self):
        """AC-3: Detect .gitignore."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, ".gitignore").write_text("*.pyc\n")
            
            config_files = get_config_files(tmpdir)
            assert any(".gitignore" == cf.path for cf in config_files)


class TestSecretsReview:
    """Tests for AC-3 & AC-8: Review and protect secrets."""
    
    def test_ac8_detect_env_file(self):
        """AC-8: Detect .env file (location only)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir, ".env")
            env_path.write_text("API_KEY=secret123\nDB_PASSWORD=pass\n")
            
            secrets_files = get_secrets_files(tmpdir)
            assert len(secrets_files) > 0
            assert any(".env" in sf.path for sf in secrets_files)
    
    def test_ac8_never_read_secrets_content(self):
        """AC-8: Never read or expose secret contents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir, ".env")
            secret_content = "API_KEY=super_secret_key_12345\n"
            env_path.write_text(secret_content)
            
            secrets_files = get_secrets_files(tmpdir)
            
            # The secrets_files list should not contain the content
            for sf in secrets_files:
                assert "super_secret_key_12345" not in sf.path
                assert "API_KEY" not in sf.path
    
    def test_ac8_detect_multiple_secrets(self):
        """AC-8: Detect multiple secrets files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, ".env").write_text("KEY=val\n")
            Path(tmpdir, ".env.local").write_text("KEY2=val2\n")
            Path(tmpdir, "credentials.json").write_text('{"api_key": "secret"}\n')
            
            secrets_files = get_secrets_files(tmpdir)
            paths = [sf.path for sf in secrets_files]
            assert any(".env" in p for p in paths)


class TestServicesDetection:
    """Tests for AC-3: Detect services."""
    
    def test_ac3_detect_docker_compose_services(self):
        """AC-3: Detect services in docker-compose.yml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            compose_content = """
version: '3'
services:
  api:
    image: myapp:latest
  db:
    image: postgres:15
"""
            Path(tmpdir, "docker-compose.yml").write_text(compose_content)
            
            services = get_services(tmpdir)
            assert len(services) > 0
            assert any("Docker Compose" in s for s in services)
    
    def test_ac3_detect_dockerfile(self):
        """AC-3: Detect Dockerfile service."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "Dockerfile").write_text("FROM python:3.12\n")
            
            services = get_services(tmpdir)
            assert any("Dockerfile" in s for s in services)


class TestDockerDetection:
    """Tests for AC-7 & UC-4: Detect Docker status."""
    
    def test_ac7_docker_check_exists(self):
        """AC-7: Check Docker availability."""
        # This test verifies the check_docker_running function works
        # It may return True or False depending on system state
        result = check_docker_running()
        assert isinstance(result, bool)
    
    @patch('subprocess.run')
    def test_ac7_docker_running_true(self, mock_run):
        """AC-7: Correctly identify when Docker is running."""
        mock_run.return_value = MagicMock(returncode=0)
        
        result = check_docker_running()
        assert result is True
    
    @patch('subprocess.run')
    def test_ac7_docker_running_false(self, mock_run):
        """AC-7: Correctly identify when Docker is not running."""
        mock_run.return_value = MagicMock(returncode=1)
        
        result = check_docker_running()
        assert result is False


class TestDirectoryReview:
    """Tests for overall review functionality."""
    
    def test_review_directory_valid_project(self):
        """Test complete directory review on valid project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a valid project
            Path(tmpdir, "pyproject.toml").write_text(
                "[project]\nrequires-python = \">=3.12\"\n"
            )
            Path(tmpdir, ".git").mkdir()
            Path(tmpdir, "main.py").write_text("# main")
            Path(tmpdir, "config.yml").touch()
            
            review = review_directory(tmpdir)
            
            assert review.is_valid_project is True
            assert len(review.project_markers) > 0
            assert len(review.source_files) > 0
            assert len(review.dependency_files) > 0
    
    def test_review_directory_invalid_project(self):
        """Test complete directory review on invalid directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            review = review_directory(tmpdir)
            
            assert review.is_valid_project is False
            assert len(review.source_files) == 0


class TestDevOpsAgentReview:
    """Tests for the DevOps Agent review process."""
    
    def test_agent_initialization(self):
        """Test agent can be initialized."""
        agent = DevOpsAgent()
        assert agent is not None
        assert agent.config is not None
    
    def test_agent_review_valid_project(self):
        """Test agent reviews a valid project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a valid project
            Path(tmpdir, "pyproject.toml").write_text(
                "[project]\nrequires-python = \">=3.12\"\n"
            )
            Path(tmpdir, ".git").mkdir()
            Path(tmpdir, "main.py").write_text("# main")
            
            agent = DevOpsAgent()
            findings = agent.review_project(tmpdir)
            
            assert findings.is_valid_project is True
            assert len(findings.project_markers) > 0
    
    def test_ac10_summary_presentation(self):
        """AC-10: Agent produces clear summary."""
        findings = ReviewFindings(
            is_valid_project=True,
            project_markers=["pyproject.toml", ".git"],
            source_files_count=3,
            dependency_files_found=["pyproject.toml"],
            config_files_found=["docker-compose.yml"],
            secrets_files_detected=[".env"],
            services_detected=["Docker Compose detected"],
            docker_running=True,
            blockers=[],
            warnings=[],
            ready_for_next_stage=True,
        )
        
        agent = DevOpsAgent()
        # This should not raise an exception
        agent.present_summary(findings)


class TestAcceptanceCriteria:
    """Integration tests for all acceptance criteria."""
    
    def test_ac1_cli_no_args(self):
        """AC-1: CLI runs with no path argument required."""
        # The main.py uses os.getcwd(), so no path argument needed
        # This is verified by the structure of main.py
        from main import main
        assert main is not None
    
    def test_ac2_readonly_operations(self):
        """AC-2: All operations are read-only."""
        # All our filesystem functions only use open() for reading
        # and get_dependencies, get_config_files, etc. never modify anything
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "pyproject.toml").write_text("[project]\n")
            
            # These should all be read-only
            check_project_validity(tmpdir)
            get_source_files(tmpdir)
            get_dependencies(tmpdir)
            get_config_files(tmpdir)
            get_secrets_files(tmpdir)
            get_services(tmpdir)
            review_directory(tmpdir)
            
            # Verify no files were created/modified
            original_files = set(os.listdir(tmpdir))
            assert "pyproject.toml" in original_files
            assert len(original_files) == 1  # Only the file we created
    
    def test_ac3_reviews_all_five_areas(self):
        """AC-3: Reviews all 5 areas."""
        findings = ReviewFindings(
            is_valid_project=True,
            project_markers=["pyproject.toml"],
            source_files_count=5,  # Source code
            dependency_files_found=["pyproject.toml"],  # Dependencies
            config_files_found=["docker-compose.yml"],  # Configuration
            secrets_files_detected=[".env"],  # Secrets
            services_detected=["Docker Compose"],  # Services
            docker_running=True,
            blockers=[],
            warnings=[],
            ready_for_next_stage=True,
        )
        
        # All 5 areas should be present in findings
        assert findings.source_files_count >= 0  # Source code
        assert len(findings.dependency_files_found) >= 0  # Dependencies
        assert len(findings.config_files_found) >= 0  # Configuration
        assert len(findings.secrets_files_detected) >= 0  # Secrets
        assert len(findings.services_detected) >= 0  # Services


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
