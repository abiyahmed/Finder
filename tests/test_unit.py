"""
Unit tests for services and infrastructure.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.infrastructure.github_api import GitHubAPI
from src.application.command_service import CommandService
from src.application.bulk_issue_service import BulkIssueService


class TestGitHubAPIValidation:
    """Test GitHub API validation methods."""

    def test_extract_repo_parts_standard_url(self):
        owner, repo = GitHubAPI.extract_repo_parts("https://github.com/pallets/flask")
        assert owner == "pallets"
        assert repo == "flask"

    def test_extract_repo_parts_with_trailing_slash(self):
        owner, repo = GitHubAPI.extract_repo_parts("https://github.com/pallets/flask/")
        assert owner == "pallets"
        assert repo == "flask"

    def test_extract_repo_parts_with_extra_path(self):
        owner, repo = GitHubAPI.extract_repo_parts("https://github.com/pallets/flask/issues/123")
        assert owner == "pallets"
        assert repo == "flask"

    def test_extract_repo_parts_invalid_url(self):
        with pytest.raises(ValueError):
            GitHubAPI.extract_repo_parts("https://github.com/pallets")

    def test_parse_issue_number_valid(self):
        url = "https://github.com/pallets/flask/issues/123"
        assert GitHubAPI.parse_issue_number_from_url(url) == 123

    def test_parse_issue_number_pull_request(self):
        url = "https://github.com/pallets/flask/pull/123"
        assert GitHubAPI.parse_issue_number_from_url(url) is None

    def test_parse_issue_number_invalid(self):
        url = "https://github.com/pallets/flask"
        assert GitHubAPI.parse_issue_number_from_url(url) is None

    def test_validate_issue_url_is_issue_valid(self):
        assert GitHubAPI.validate_issue_url_is_issue("https://github.com/o/r/issues/1") is True

    def test_validate_issue_url_is_issue_pull(self):
        assert GitHubAPI.validate_issue_url_is_issue("https://github.com/o/r/pull/1") is False

    def test_validate_issue_closed_uppercase(self):
        assert GitHubAPI.validate_issue_closed("CLOSED") is True

    def test_validate_issue_closed_lowercase(self):
        assert GitHubAPI.validate_issue_closed("closed") is True

    def test_validate_issue_closed_open(self):
        assert GitHubAPI.validate_issue_closed("OPEN") is False

    def test_validate_issue_closed_none(self):
        assert GitHubAPI.validate_issue_closed(None) is False

    def test_validate_issue_content_valid(self):
        ok, reason = GitHubAPI.validate_issue_content("This is a bug report with code:\n```python\nprint('hello')\n```")
        assert ok is True
        assert reason == ""

    def test_validate_issue_content_empty(self):
        ok, reason = GitHubAPI.validate_issue_content("")
        assert ok is False
        assert "empty" in reason

    def test_validate_issue_content_none(self):
        ok, reason = GitHubAPI.validate_issue_content(None)
        assert ok is False

    def test_validate_issue_content_no_description(self):
        ok, reason = GitHubAPI.validate_issue_content("No description provided")
        assert ok is False

    def test_validate_issue_content_contains_url(self):
        ok, reason = GitHubAPI.validate_issue_content("Check this: https://example.com")
        assert ok is False
        assert "URL" in reason

    def test_validate_issue_content_contains_markdown_link(self):
        ok, reason = GitHubAPI.validate_issue_content("See [this link](https://example.com)")
        assert ok is False
        assert "markdown link" in reason

    def test_validate_issue_content_contains_image(self):
        ok, reason = GitHubAPI.validate_issue_content("Screenshot: ![img](https://example.com/img.png)")
        assert ok is False
        assert "image" in reason

    def test_categorize_file_includes_js_ts_as_code(self):
        assert GitHubAPI.categorize_file("src/app/index.js") == "python"
        assert GitHubAPI.categorize_file("src/app/index.ts") == "python"
        assert GitHubAPI.categorize_file("src/app/widget.tsx") == "python"

    def test_categorize_file_js_ts_tests(self):
        assert GitHubAPI.categorize_file("src/__tests__/app.test.tsx") == "test"
        assert GitHubAPI.categorize_file("specs/widget.spec.js") == "test"


class TestBulkIssueService:
    def test_parse_issue_url_normalizes_standard_issue(self):
        parsed = BulkIssueService.parse_issue_url("https://github.com/pallets/flask/issues/123")
        assert parsed == ("pallets", "flask", 123)

    def test_parse_issue_url_rejects_pull_request_url(self):
        parsed = BulkIssueService.parse_issue_url("https://github.com/pallets/flask/pull/123")
        assert parsed is None

    def test_extract_issue_urls_deduplicates_and_normalizes(self):
        text = """
https://github.com/pallets/flask/issues/100
https://github.com/pallets/flask/issues/100?utm=abc
https://github.com/psf/requests/issues/200,
"""
        out = BulkIssueService.extract_issue_urls(text)
        assert out["raw_url_count"] == 3
        assert out["duplicates_removed"] == 1
        assert out["valid_urls"] == [
            "https://github.com/pallets/flask/issues/100",
            "https://github.com/psf/requests/issues/200",
        ]

    def test_compute_quality_score_prefers_stronger_test_and_python_signal(self):
        weak_summary = {
            "python": {"count": 1, "additions": 20, "deletions": 5},
            "test": {"count": 0, "additions": 0, "deletions": 0},
            "doc": {"count": 0, "additions": 0, "deletions": 0},
            "other": {"count": 3, "additions": 10, "deletions": 5},
            "lock": {"count": 0, "additions": 0, "deletions": 0},
            "total_excluding_lock": {"count": 4, "additions": 30, "deletions": 10},
        }
        strong_summary = {
            "python": {"count": 4, "additions": 220, "deletions": 40},
            "test": {"count": 2, "additions": 80, "deletions": 15},
            "doc": {"count": 1, "additions": 10, "deletions": 0},
            "other": {"count": 1, "additions": 5, "deletions": 2},
            "lock": {"count": 1, "additions": 2, "deletions": 0},
            "total_excluding_lock": {"count": 8, "additions": 315, "deletions": 57},
        }
        weak_score = BulkIssueService.compute_quality_score(weak_summary, repo_has_tests=False, linked_merged_pr_count=1)
        strong_score = BulkIssueService.compute_quality_score(strong_summary, repo_has_tests=True, linked_merged_pr_count=1)
        assert strong_score > weak_score


class TestCommandService:
    """Test command generation service."""

    def test_wsl_path_c_drive(self):
        assert CommandService.wsl_path(r"C:\Users\test\project") == "/mnt/c/Users/test/project"

    def test_wsl_path_d_drive(self):
        assert CommandService.wsl_path(r"D:\work\repo") == "/mnt/d/work/repo"

    def test_wsl_path_forward_slashes(self):
        assert CommandService.wsl_path("C:/Users/test") == "/mnt/c/Users/test"

    def test_wsl_path_empty(self):
        assert CommandService.wsl_path("") == ""

    def test_windows_path_mnt_c(self):
        assert CommandService.windows_path("/mnt/c/Users/test") == r"C:\Users\test"

    def test_windows_path_mnt_d(self):
        assert CommandService.windows_path("/mnt/d/work") == r"D:\work"

    def test_windows_path_empty(self):
        assert CommandService.windows_path("") == ""

    def test_git_setup_commands(self):
        cmds = CommandService.git_setup_commands("/path/to/repo")
        assert any("cd" in cmd for cmd in cmds)
        assert any("fileMode" in cmd for cmd in cmds)
        assert any("reset" in cmd for cmd in cmds)

    def test_git_commit_command(self):
        cmd = CommandService.git_commit_command("Test commit")
        assert "PR writer" in cmd
        assert "Test commit" in cmd

    def test_docker_build_command(self):
        cmd = CommandService.docker_build_command("my-image")
        assert "docker build" in cmd
        assert "my-image" in cmd

    def test_docker_run_tests_command(self):
        cmd = CommandService.docker_run_tests_command("my-image", "pytest")
        assert "docker run" in cmd
        assert "my-image" in cmd
        assert cmd.endswith(" pytest")

    def test_tmux_attach_command(self):
        cmd = CommandService.tmux_attach_command("session-123")
        assert "tmux attach" in cmd
        assert "session-123" in cmd

    def test_hfi_start_command(self):
        cmd = CommandService.hfi_start_command()
        assert "claude-hfi" in cmd
        assert "--vscode" in cmd

    def test_dockerfile_template(self):
        template = CommandService.dockerfile_template("3.10")
        assert "python:3.10-slim" in template
        assert "COPY . ." in template
        assert 'CMD ["pytest"]' in template

    def test_dockerfile_template_normalizes_range_python_version(self):
        template = CommandService.dockerfile_template(">=3.7")
        assert "FROM python:3.13-slim" in template

    def test_normalize_python_version_for_docker_with_upper_bound(self):
        tag = CommandService.normalize_python_version_for_docker(">=3.8,<3.11")
        assert tag == "3.10"

    def test_readme_template(self):
        template = CommandService.readme_template("my-project")
        assert "my-project" in template
        assert "pip install" in template
        assert "python -m pytest -v" in template
        assert "To run all tests:" in template
        assert "To run a specific test:" in template
        assert "docker" not in template.lower()

    def test_readme_template_omits_run_section_when_no_entrypoint(self):
        template = CommandService.readme_template(
            "my-project",
            run_command="",
        )
        assert "To run the app:" not in template

    def test_readme_template_uses_repo_specific_test_target(self):
        template = CommandService.readme_template(
            "my-project",
            test_command="pytest",
            specific_test_target="tests/test_core.py",
        )
        assert "python -m pytest -v tests/test_core.py" in template

    def test_dockerfile_template_pipfile_avoids_lock_install(self):
        template = CommandService.dockerfile_template(
            python_version="3.11",
            dependency_files=["Pipfile"],
        )
        assert "--skip-lock" in template
        assert "--deploy" not in template

    def test_dockerfile_template_uses_dynamic_requirements_files(self):
        template = CommandService.dockerfile_template(
            dependency_files=["requirements.txt", "requirements-dev.txt"],
        )
        assert "pip install --no-cache-dir -r requirements.txt" in template
        assert "pip install --no-cache-dir -r requirements-dev.txt" in template

    def test_dockerfile_template_infers_system_packages(self):
        template = CommandService.dockerfile_template(
            dependency_entries=[
                {"name": "gitpython", "specifier": ""},
                {"name": "psycopg2", "specifier": ">=2.9"},
            ]
        )
        assert "git \\" in template
        assert "libpq-dev \\" in template

    def test_readme_template_uses_dynamic_install_commands(self):
        template = CommandService.readme_template(
            "my-project",
            dependency_files=["requirements.txt", "requirements-dev.txt"],
        )
        assert "pip install -r requirements.txt" in template
        assert "pip install -r requirements-dev.txt" in template

    def test_normalize_test_command_adds_python_prefix_and_verbose(self):
        assert CommandService.normalize_test_command("pytest") == "python -m pytest -v"
        assert CommandService.normalize_test_command("nosetests -x") == "python -m nose -x -v"
        assert CommandService.normalize_test_command("python -m pytest -q") == "python -m pytest -q"

    def test_normalize_test_command_for_docker_prefers_executable(self):
        assert CommandService.normalize_test_command_for_docker("pytest") == "pytest"
        assert CommandService.normalize_test_command_for_docker("python -m pytest -q") == "pytest -q"

    def test_normalize_run_command_web_frameworks(self):
        assert CommandService.normalize_run_command("flask --app app run") == "python -m flask --app app run"
        assert CommandService.normalize_run_command("uvicorn app:app") == "python -m uvicorn app:app"
        assert CommandService.normalize_run_command("python manage.py runserver") == "python manage.py runserver"

    def test_apply_pytest_exclusions(self):
        cmd = CommandService.apply_pytest_exclusions("pytest", exclusions=["live", "external"])
        assert "python -m pytest" in cmd
        assert '-k "not live and not external"' in cmd

    def test_dockerfile_template_with_test_exclusions(self):
        template = CommandService.dockerfile_template(
            test_command="python -m pytest -q",
            test_exclusions=["live", "external"],
        )
        assert 'CMD ["pytest", "-q", "-k", "not live and not external"]' in template

    def test_readme_template_with_test_exclusions_includes_reasons(self):
        template = CommandService.readme_template(
            "my-project",
            test_command="pytest",
            test_exclusions=["redis"],
        )
        assert "Ignored test categories and reasons:" in template
        assert "`redis`" in template
