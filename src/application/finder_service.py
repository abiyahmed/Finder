"""
Finder service - orchestrates issue finding workflow.
Application layer - use cases and business logic.
"""
from typing import Callable, Optional

from ..infrastructure.github_api import GitHubAPI
from ..infrastructure.database import (
    get_or_create_repository,
    create_issue,
    get_issues_by_repo,
)


class FinderService:
    """Service for finding and storing GitHub issues."""

    def __init__(self, github_api: GitHubAPI = None):
        self.github_api = github_api or GitHubAPI()

    def fetch_repo_info(self, repo_url: str) -> tuple[str, str, dict]:
        """
        Fetch repository metadata.
        
        Returns:
            (owner, repo_name, metadata_dict)
        """
        owner, repo = self.github_api.extract_repo_parts(repo_url)
        metadata = self.github_api.fetch_repo_metadata(owner, repo)
        return owner, repo, metadata

    def scan_and_store_issues(
        self,
        repo_url: str,
        log_callback: Callable[[str], None] = None,
    ) -> tuple[int, list, dict]:
        """
        Scan repository for issues and store them in database.
        
        Returns:
            (repo_id, list of issue records, analytics dict)
        """
        owner, repo, metadata = self.fetch_repo_info(repo_url)

        # Store/update repository
        repo_record = get_or_create_repository(owner, repo, metadata)

        # Scan for issues
        issues, analytics = self.github_api.scan_repository(owner, repo, log_callback)

        # Store issues
        stored_issues = []
        for issue_data in issues:
            issue_record = create_issue(repo_record.id, issue_data)
            stored_issues.append(issue_record)

        return repo_record.id, stored_issues, analytics

    def get_issues_for_repo(self, repo_id: int) -> list:
        """Get all stored issues for a repository."""
        return get_issues_by_repo(repo_id)

    def reset_scan_progress(self, repo_url: str):
        """Reset scan progress for a repository."""
        owner, repo = self.github_api.extract_repo_parts(repo_url)
        self.github_api.reset_scan_progress(f"{owner}/{repo}")

    # =========================
    # Validation helpers (exposed for UI)
    # =========================

    @staticmethod
    def extract_repo_parts(repo_url: str) -> tuple[str, str]:
        """Extract owner and repo from URL."""
        return GitHubAPI.extract_repo_parts(repo_url)

    @staticmethod
    def validate_issue_url(url: str) -> bool:
        """Validate issue URL is actually an issue."""
        return GitHubAPI.validate_issue_url_is_issue(url)

    @staticmethod
    def validate_issue_content(body: str) -> tuple[bool, str]:
        """Validate issue content meets criteria."""
        return GitHubAPI.validate_issue_content(body)

    @staticmethod
    def parse_issue_number(url: str) -> Optional[int]:
        """Parse issue number from URL."""
        return GitHubAPI.parse_issue_number_from_url(url)
