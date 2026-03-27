"""
Bulk issue suggestion service.
Evaluates pasted GitHub issue URLs across many repos using Issue Finder-like filters.
"""
from __future__ import annotations

import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Callable, Optional
from urllib.parse import urlparse

from ..infrastructure.github_api import GitHubAPI


@dataclass
class BulkIssueFilters:
    """Filtering controls for bulk issue suggestions."""

    min_files_changed: int = 4
    min_lines_changed: int = 50
    max_lines_changed: int = 700
    min_python_files: int = 1  # Code files (Python + JS/TS)
    min_python_lines: int = 50
    min_test_files: int = 1
    min_doc_files: int = 0
    min_total_python_files: int = 4  # Code + test files
    strict_links: bool = False
    require_repo_tests: bool = True
    require_single_merged_pr: bool = True


class BulkIssueService:
    """Service for bulk issue URL qualification and suggestion ranking."""

    URL_PATTERN = re.compile(r"https?://github\.com/[^\s]+", re.IGNORECASE)

    def __init__(self, github_api: GitHubAPI):
        self.github_api = github_api
        self._cache_lock = Lock()
        self._repo_test_cache: dict[str, tuple[bool, list[str]]] = {}
        self._repo_meta_cache: dict[str, dict] = {}

    @classmethod
    def parse_issue_url(cls, url: str) -> Optional[tuple[str, str, int]]:
        """Parse and normalize a GitHub issue URL into owner, repo, issue_number."""
        if not url:
            return None
        cleaned = cls._clean_token(url)
        parsed = urlparse(cleaned)
        if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
            return None
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) < 4:
            return None
        owner, repo, kind, issue_str = parts[0], parts[1], parts[2].lower(), parts[3]
        if kind != "issues":
            return None
        if not issue_str.isdigit():
            return None
        return owner, repo, int(issue_str)

    @classmethod
    def normalize_issue_url(cls, url: str) -> Optional[str]:
        parsed = cls.parse_issue_url(url)
        if not parsed:
            return None
        owner, repo, issue_number = parsed
        return f"https://github.com/{owner}/{repo}/issues/{issue_number}"

    @classmethod
    def extract_issue_urls(cls, raw_text: str) -> dict:
        """
        Extract and normalize issue URLs from free-form text.
        Returns valid list + invalid snippets + duplicate stats.
        """
        raw_text = raw_text or ""
        raw_candidates = [cls._clean_token(token) for token in cls.URL_PATTERN.findall(raw_text)]

        valid_urls = []
        invalid_entries = []
        for token in raw_candidates:
            normalized = cls.normalize_issue_url(token)
            if normalized:
                valid_urls.append(normalized)
            elif token:
                invalid_entries.append(token)

        seen = set()
        unique_urls = []
        for url in valid_urls:
            if url in seen:
                continue
            seen.add(url)
            unique_urls.append(url)

        return {
            "valid_urls": unique_urls,
            "invalid_entries": invalid_entries,
            "raw_url_count": len(raw_candidates),
            "duplicates_removed": len(valid_urls) - len(unique_urls),
        }

    def suggest_from_issue_urls(
        self,
        issue_urls: list[str],
        filters: BulkIssueFilters,
        max_workers: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> dict:
        """
        Evaluate issue URLs and return ranked suggestions + rejection analytics.
        """
        normalized_urls = []
        seen = set()
        for issue_url in issue_urls:
            normalized = self.normalize_issue_url(issue_url)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            normalized_urls.append(normalized)

        total = len(normalized_urls)
        if total == 0:
            return {
                "suggestions": [],
                "rejected": [],
                "summary": {
                    "processed": 0,
                    "qualified": 0,
                    "rejected": 0,
                    "rejection_reasons": {},
                },
            }

        if max_workers is None:
            token_count = max(1, self.github_api.pool.token_count)
            max_workers = max(2, min(24, token_count * 3))

        suggestions = []
        rejected = []
        rejection_counter = Counter()
        processed = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {
                executor.submit(self._evaluate_single_issue, issue_url, filters): issue_url
                for issue_url in normalized_urls
            }

            for future in as_completed(future_to_url):
                issue_url = future_to_url[future]
                try:
                    result = future.result()
                except Exception as exc:  # Defensive: never crash bulk run for one issue.
                    result = {
                        "qualified": False,
                        "issue_url": issue_url,
                        "reason": f"Unhandled error: {exc}",
                    }

                processed += 1
                if result.get("qualified"):
                    suggestions.append(result["suggestion"])
                    status_msg = f"Qualified {processed}/{total}: {result['suggestion']['issue_url']}"
                else:
                    reason = result.get("reason", "Rejected")
                    rejected.append(
                        {
                            "issue_url": result.get("issue_url", issue_url),
                            "owner": result.get("owner"),
                            "repo": result.get("repo"),
                            "issue_number": result.get("issue_number"),
                            "reason": reason,
                        }
                    )
                    rejection_counter[reason] += 1
                    status_msg = f"Rejected {processed}/{total}: {issue_url} ({reason})"

                if progress_callback:
                    progress_callback(processed, total, status_msg)

        suggestions.sort(
            key=lambda row: (
                row.get("quality_score", 0.0),
                row.get("pr_python_additions", 0) + row.get("pr_python_deletions", 0),
                row.get("pr_test_files", 0),
            ),
            reverse=True,
        )

        return {
            "suggestions": suggestions,
            "rejected": rejected,
            "summary": {
                "processed": processed,
                "qualified": len(suggestions),
                "rejected": len(rejected),
                "rejection_reasons": dict(rejection_counter),
            },
        }

    @staticmethod
    def compute_quality_score(
        file_summary: dict,
        repo_has_tests: Optional[bool],
        linked_merged_pr_count: int,
    ) -> float:
        """Compute a simple ranking score for suggestion ordering."""
        py_count = file_summary["python"]["count"]
        test_count = file_summary["test"]["count"]
        py_lines = file_summary["python"]["additions"] + file_summary["python"]["deletions"]
        total_files = file_summary["total_excluding_lock"]["count"]

        score = 0.0
        score += min(60.0, py_count * 12.0)
        score += min(45.0, test_count * 9.0)
        score += min(40.0, py_lines / 8.0)
        score += min(25.0, total_files * 2.0)

        if repo_has_tests is True:
            score += 10.0
        if linked_merged_pr_count == 1:
            score += 5.0
        elif linked_merged_pr_count > 1:
            score -= min(8.0, float(linked_merged_pr_count - 1))

        return round(score, 2)

    def _evaluate_single_issue(self, issue_url: str, filters: BulkIssueFilters) -> dict:
        parsed = self.parse_issue_url(issue_url)
        if not parsed:
            return {"qualified": False, "issue_url": issue_url, "reason": "Invalid issue URL"}

        owner, repo, issue_number = parsed
        full_name = f"{owner}/{repo}"

        issue = self.github_api.fetch_issue_full_details(owner, repo, issue_number)
        if not issue:
            return self._reject(issue_url, owner, repo, issue_number, "Could not fetch issue")

        if not self.github_api.validate_issue_closed(issue.get("state")):
            return self._reject(issue_url, owner, repo, issue_number, "Issue not closed")

        content_ok, content_reason = self.github_api.validate_issue_content(
            issue.get("body"),
            strict_links=filters.strict_links,
        )
        if not content_ok:
            return self._reject(issue_url, owner, repo, issue_number, content_reason)

        linked_pr, linked_merged_pr_count = self._select_merged_pr(issue)
        if not linked_pr:
            return self._reject(issue_url, owner, repo, issue_number, "No merged PR linked to issue")

        if filters.require_single_merged_pr and linked_merged_pr_count != 1:
            return self._reject(
                issue_url,
                owner,
                repo,
                issue_number,
                f"Issue linked to {linked_merged_pr_count} merged PRs",
            )

        pr_number = linked_pr.get("number")
        if not pr_number:
            return self._reject(issue_url, owner, repo, issue_number, "Linked PR has no number")

        pr_files = self.github_api.fetch_pr_files(owner, repo, pr_number)
        if not pr_files:
            return self._reject(issue_url, owner, repo, issue_number, "Could not fetch PR files")

        file_summary = self.github_api.summarize_file_changes(pr_files)
        effective_files = file_summary["total_excluding_lock"]["count"]
        effective_lines = (
            file_summary["total_excluding_lock"]["additions"]
            + file_summary["total_excluding_lock"]["deletions"]
        )
        py_lines = file_summary["python"]["additions"] + file_summary["python"]["deletions"]
        total_python_files = file_summary["python"]["count"] + file_summary["test"]["count"]

        if effective_files < filters.min_files_changed:
            return self._reject(
                issue_url,
                owner,
                repo,
                issue_number,
                f"PR has < {filters.min_files_changed} non-lock files",
            )

        if effective_lines < filters.min_lines_changed:
            return self._reject(
                issue_url,
                owner,
                repo,
                issue_number,
                f"PR has < {filters.min_lines_changed} changed lines",
            )

        if effective_lines > filters.max_lines_changed:
            return self._reject(
                issue_url,
                owner,
                repo,
                issue_number,
                f"PR has > {filters.max_lines_changed} changed lines",
            )

        if file_summary["python"]["count"] < filters.min_python_files:
            return self._reject(
                issue_url,
                owner,
                repo,
                issue_number,
                f"< {filters.min_python_files} Code (Py/JS/TS) files",
            )

        if py_lines < filters.min_python_lines:
            return self._reject(
                issue_url,
                owner,
                repo,
                issue_number,
                f"< {filters.min_python_lines} Code (Py/JS/TS) lines",
            )

        if file_summary["test"]["count"] < filters.min_test_files:
            return self._reject(
                issue_url,
                owner,
                repo,
                issue_number,
                f"< {filters.min_test_files} test files",
            )

        if total_python_files < filters.min_total_python_files:
            return self._reject(
                issue_url,
                owner,
                repo,
                issue_number,
                f"< {filters.min_total_python_files} total code+test files",
            )

        if file_summary["doc"]["count"] < filters.min_doc_files:
            return self._reject(
                issue_url,
                owner,
                repo,
                issue_number,
                f"< {filters.min_doc_files} doc files",
            )

        repo_has_tests = None
        test_indicators: list[str] = []
        if filters.require_repo_tests:
            repo_has_tests, test_indicators = self._repo_has_tests_cached(owner, repo)
            if not repo_has_tests:
                return self._reject(issue_url, owner, repo, issue_number, "Repository has no tests")

        issue_created_at = self._parse_github_datetime(issue.get("createdAt"))
        pr_merged_at = self._parse_github_datetime(linked_pr.get("mergedAt"))

        base_sha = linked_pr.get("baseRefOid")
        base_sha_source = "linked_pr_base"
        if not base_sha and issue.get("createdAt"):
            default_branch = self._repo_default_branch_cached(owner, repo)
            base_sha = self.github_api.get_base_sha_at_date(
                owner,
                repo,
                issue.get("createdAt"),
                default_branch=default_branch,
            )
            base_sha_source = "default_branch_at_issue_creation"

        if not base_sha:
            return self._reject(issue_url, owner, repo, issue_number, "Could not resolve base SHA")

        quality_score = self.compute_quality_score(file_summary, repo_has_tests, linked_merged_pr_count)

        suggestion = {
            "owner": owner,
            "repo": repo,
            "full_name": full_name,
            "issue_url": issue_url,
            "issue_number": issue_number,
            "issue_title": issue.get("title", ""),
            "issue_body": issue.get("body"),
            "issue_state": issue.get("state", "CLOSED"),
            "issue_created_at": issue_created_at,
            "base_sha": base_sha,
            "base_sha_source": base_sha_source,
            "pr_number": linked_pr.get("number"),
            "pr_title": linked_pr.get("title"),
            "pr_url": linked_pr.get("url"),
            "pr_files_changed": file_summary["total_excluding_lock"]["count"],
            "pr_additions": file_summary["total_excluding_lock"]["additions"],
            "pr_deletions": file_summary["total_excluding_lock"]["deletions"],
            "pr_merged_at": pr_merged_at,
            "pr_python_files": file_summary["python"]["count"],
            "pr_python_additions": file_summary["python"]["additions"],
            "pr_python_deletions": file_summary["python"]["deletions"],
            "pr_test_files": file_summary["test"]["count"],
            "pr_test_additions": file_summary["test"]["additions"],
            "pr_test_deletions": file_summary["test"]["deletions"],
            "pr_doc_files": file_summary["doc"]["count"],
            "pr_doc_additions": file_summary["doc"]["additions"],
            "pr_doc_deletions": file_summary["doc"]["deletions"],
            "pr_other_files": file_summary["other"]["count"],
            "pr_lock_files_ignored": file_summary["lock"]["count"],
            "repo_has_tests": repo_has_tests,
            "repo_test_indicators": test_indicators,
            "linked_merged_pr_count": linked_merged_pr_count,
            "quality_score": quality_score,
        }

        return {"qualified": True, "suggestion": suggestion}

    @staticmethod
    def _reject(
        issue_url: str,
        owner: str,
        repo: str,
        issue_number: int,
        reason: str,
    ) -> dict:
        return {
            "qualified": False,
            "issue_url": issue_url,
            "owner": owner,
            "repo": repo,
            "issue_number": issue_number,
            "reason": reason,
        }

    @staticmethod
    def _clean_token(token: str) -> str:
        token = (token or "").strip()
        token = token.strip("`'\"<>[]()")
        token = token.rstrip(".,;")
        return token

    @staticmethod
    def _parse_github_datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def _select_merged_pr(issue_data: dict) -> tuple[Optional[dict], int]:
        merged_by_number = {}
        timeline = issue_data.get("timelineItems", {}).get("nodes", []) or []
        for event in timeline:
            source = (event or {}).get("source", {})
            if source.get("__typename") != "PullRequest":
                continue
            if not source.get("merged"):
                continue
            pr_number = source.get("number")
            if not pr_number:
                continue
            merged_by_number[pr_number] = source

        if not merged_by_number:
            return None, 0

        merged_prs = list(merged_by_number.values())
        merged_prs.sort(
            key=lambda pr: (
                pr.get("changedFiles", 0) or 0,
                pr.get("additions", 0) + pr.get("deletions", 0),
                pr.get("mergedAt") or "",
            ),
            reverse=True,
        )
        return merged_prs[0], len(merged_prs)

    def _repo_has_tests_cached(self, owner: str, repo: str) -> tuple[bool, list[str]]:
        full_name = f"{owner}/{repo}"
        with self._cache_lock:
            if full_name in self._repo_test_cache:
                return self._repo_test_cache[full_name]

        has_tests, indicators = self.github_api.repo_has_tests(owner, repo)
        value = (has_tests, indicators or [])
        with self._cache_lock:
            self._repo_test_cache[full_name] = value
        return value

    def _repo_default_branch_cached(self, owner: str, repo: str) -> str:
        full_name = f"{owner}/{repo}"
        with self._cache_lock:
            cached = self._repo_meta_cache.get(full_name)
            if cached and cached.get("default_branch"):
                return cached["default_branch"]

        default_branch = self.github_api.get_default_branch(owner, repo) or "main"
        with self._cache_lock:
            self._repo_meta_cache.setdefault(full_name, {})
            self._repo_meta_cache[full_name]["default_branch"] = default_branch
        return default_branch
