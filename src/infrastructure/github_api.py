"""
GitHub API client.
Infrastructure layer - handles external API communication.
"""
import os
import re
import json
import time
import threading
import requests
from datetime import datetime
from typing import Optional, Callable, List
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

load_dotenv()


class TokenPoolManager:
    """Manages a pool of GitHub tokens with rate limit tracking and rotation."""
    def __init__(self, tokens: List[str] = None):
        self._tokens = [] # List of dicts with 'token', 'remaining', 'reset'
        self._lock = threading.Lock()
        self._current_index = 0
        if tokens:
            self.set_tokens(tokens)
        else:
            env_token = os.getenv("GITHUB_TOKEN", "")
            if env_token:
                self.set_tokens([env_token])

    def set_tokens(self, tokens: List[str]):
        with self._lock:
            # Ignore empty/invalid tokens
            tokens = [t for t in (tokens or []) if t and str(t).strip()]
            # Keep existing rate limit info if token still present
            existing_map = {t["token"]: t for t in self._tokens}
            new_tokens = []
            for t in tokens:
                if t in existing_map:
                    new_tokens.append(existing_map[t])
                else:
                    new_tokens.append({
                        "token": t,
                        "remaining": 5000,
                        "reset": datetime.utcnow()
                    })
            self._tokens = new_tokens
            self._current_index = 0

    def get_next_token(self) -> str:
        with self._lock:
            if not self._tokens:
                env = (os.getenv("GITHUB_TOKEN") or "").strip()
                return env if env else ""
            
            # Try to find a token that isn't rate limited
            for _ in range(len(self._tokens)):
                token_data = self._tokens[self._current_index]
                self._current_index = (self._current_index + 1) % len(self._tokens)
                
                if token_data["remaining"] > 5 or token_data["reset"] < datetime.utcnow():
                    return token_data["token"]
            
            # If all are exhausted, return the one with the earliest reset
            best_token = min(self._tokens, key=lambda x: x["reset"])
            return best_token["token"]

    def update_limit(self, token: str, remaining: int, reset_at: float):
        reset_dt = datetime.fromtimestamp(reset_at)
        with self._lock:
            for t in self._tokens:
                if t["token"] == token:
                    t["remaining"] = remaining
                    t["reset"] = reset_dt
                    break
    
    @property
    def token_count(self) -> int:
        return len(self._tokens)

# Repo metadata cache: key (owner, repo) -> (expiry_ts, data). TTL 5 min.
_REPO_METADATA_CACHE: dict = {}
_REPO_CACHE_TTL = 300

class GitHubAPI:
    """GitHub API client for fetching repository and issue data."""

    # Validation patterns
    RE_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]+\)")
    RE_BARE_URL = re.compile(r"https?://[^\s)\]\"]+")
    RE_IMAGE_MD = re.compile(r"!\[.*?\]\([^)]+\)")
    RE_IMG_TAG = re.compile(r"<img\s", re.I)
    # GitHub issue/PR references like #88, #123 (not inside code blocks)
    RE_GITHUB_REF = re.compile(r"(?<![`\w])#\d+(?![`\w])")

    # File categorization patterns
    LOCK_FILES = {
        "poetry.lock", "Pipfile.lock", "package-lock.json", "yarn.lock",
        "uv.lock", "pdm.lock", "pnpm-lock.yaml", "Gemfile.lock", "composer.lock"
    }
    DOC_EXTENSIONS = {".md", ".rst", ".txt", ".adoc", ".rdoc"}
    DOC_DIRS = {"docs", "doc", "documentation", "wiki"}
    TEST_PATTERNS = {"test_", "_test.py", "tests/", "test/", "testing/", "spec/", "_spec.py"}

    def __init__(
        self,
        token: str = None,
        tokens: List[str] = None,
        min_files_changed: int = 5,
        min_lines_changed: int = 150,
        max_lines_changed: int = 700,
        per_page: int = 50,
        max_pages: int = 10,
        request_delay: float = 1.0,
        request_timeout: float = 30.0,
        strict_links: bool = False,  # If False, ignore URLs inside code blocks
        # Minimum requirements by category (0 = no requirement)
        min_python_files: int = 1,
        min_python_lines: int = 50,  # Minimum lines changed in Python files
        min_test_files: int = 0,
        min_doc_files: int = 0,
        # Combined Python requirement (py + test files total)
        min_total_python_files: int = 0,  # e.g., 4 = at least 4 py files (including tests)
        # Repo-level requirements
        require_repo_tests: bool = False,  # Require repo to have test infrastructure
        # Target mode
        target_issues: int = 0,  # Keep scanning until this many issues found (0 = disabled)
        relax_lines_for_target: bool = True,  # In target mode, relax line requirements
        # Blacklist
        blacklist_urls: set = None,  # Set of issue URLs to skip
        blacklist_repos: set = None,  # Set of repo full names to skip
        # Multi-PR/Issue filters
        exclude_multi_issue_prs: bool = False,  # Skip PRs that close multiple issues
        exclude_multi_pr_issues: bool = False,  # Skip issues closed by multiple PRs
    ):
        if tokens:
            self.pool = TokenPoolManager(tokens)
        elif token:
            self.pool = TokenPoolManager([token])
        else:
            self.pool = TokenPoolManager()
            
        self.token = self.pool.get_next_token() # Current token for simple calls
        self.blacklist_urls = blacklist_urls or set()
        self.blacklist_repos = blacklist_repos or set()
        self.exclude_multi_issue_prs = exclude_multi_issue_prs
        self.exclude_multi_pr_issues = exclude_multi_pr_issues
        self.min_files_changed = min_files_changed
        self.min_lines_changed = min_lines_changed
        self.max_lines_changed = max_lines_changed
        self.per_page = per_page
        self.max_pages = max_pages
        self.request_delay = request_delay
        self.request_timeout = request_timeout
        self.strict_links = strict_links
        self.min_python_files = min_python_files
        self.min_python_lines = min_python_lines
        self.min_test_files = min_test_files
        self.min_doc_files = min_doc_files
        self.min_total_python_files = min_total_python_files
        self.require_repo_tests = require_repo_tests
        self.target_issues = target_issues
        self.relax_lines_for_target = relax_lines_for_target
        self._rate_limit_info = None
        
        # Concurrency control
        # "twice as many as the github tokens cuncurent requests"
        limit = max(1, self.pool.token_count * 2)
        self._semaphore = threading.Semaphore(limit)

    @classmethod
    def categorize_file(cls, filepath: str) -> str:
        """
        Categorize a file path into: lock, doc, test, python, other.
        """
        filename = filepath.split("/")[-1].lower()
        filepath_lower = filepath.lower()
        
        # Lock files - ignore these
        if filename in cls.LOCK_FILES or filename.endswith(".lock"):
            return "lock"
        
        # Documentation
        ext = "." + filename.split(".")[-1] if "." in filename else ""
        if ext in cls.DOC_EXTENSIONS:
            return "doc"
        for doc_dir in cls.DOC_DIRS:
            if f"/{doc_dir}/" in f"/{filepath_lower}/" or filepath_lower.startswith(f"{doc_dir}/"):
                return "doc"
        
        # Python files
        if filepath_lower.endswith(".py"):
            # Test files
            for pattern in cls.TEST_PATTERNS:
                if pattern in filepath_lower:
                    return "test"
            return "python"
        
        return "other"

    def fetch_pr_files(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        """
        Fetch the list of files changed in a PR with additions/deletions.
        Returns list of {filename, additions, deletions, status, category}.
        """
        # Use REST API for file list (GraphQL doesn't provide this easily)
        files = []
        page = 1
        while True:
            data = self._rest_get(f"/repos/{owner}/{repo}/pulls/{pr_number}/files?per_page=100&page={page}")
            if not data:
                break
            for f in data:
                filename = f.get("filename", "")
                files.append({
                    "filename": filename,
                    "additions": f.get("additions", 0),
                    "deletions": f.get("deletions", 0),
                    "status": f.get("status", "modified"),
                    "category": self.categorize_file(filename),
                })
            if len(data) < 100:
                break
            page += 1
        return files

    @staticmethod
    def summarize_file_changes(files: list[dict]) -> dict:
        """
        Summarize file changes by category.
        Returns dict with counts and line changes per category.
        """
        summary = {
            "python": {"count": 0, "additions": 0, "deletions": 0},
            "test": {"count": 0, "additions": 0, "deletions": 0},
            "doc": {"count": 0, "additions": 0, "deletions": 0},
            "lock": {"count": 0, "additions": 0, "deletions": 0},
            "other": {"count": 0, "additions": 0, "deletions": 0},
            "total_excluding_lock": {"count": 0, "additions": 0, "deletions": 0},
        }
        
        for f in files:
            cat = f.get("category", "other")
            summary[cat]["count"] += 1
            summary[cat]["additions"] += f.get("additions", 0)
            summary[cat]["deletions"] += f.get("deletions", 0)
            
            if cat != "lock":
                summary["total_excluding_lock"]["count"] += 1
                summary["total_excluding_lock"]["additions"] += f.get("additions", 0)
                summary["total_excluding_lock"]["deletions"] += f.get("deletions", 0)
        
        return summary

    def _headers(self, token: str = None) -> dict:
        t = token or self.pool.get_next_token()
        return {
            "Authorization": f"Bearer {t}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "issue-finder-script",
        }

    def get_rate_limit(self) -> dict:
        """
        Get current GitHub API rate limit status.
        
        Returns:
            Dict with rate limit info:
            - core_remaining: REST API calls remaining
            - core_limit: REST API total limit
            - core_reset: UTC timestamp when limit resets
            - graphql_remaining: GraphQL calls remaining
            - graphql_limit: GraphQL total limit
            - graphql_reset: UTC timestamp when limit resets
        """
        url = "https://api.github.com/rate_limit"
        try:
            res = requests.get(url, headers=self._headers(), timeout=self.request_timeout)
        except requests.exceptions.RequestException as e:
            return {"error": f"Failed to fetch rate limit: {e}"}
        if res.status_code != 200:
            return {"error": f"Failed to fetch rate limit: {res.status_code}"}
        
        data = res.json()
        resources = data.get("resources", {})
        core = resources.get("core", {})
        graphql = resources.get("graphql", {})
        
        self._rate_limit_info = {
            "core_remaining": core.get("remaining", 0),
            "core_limit": core.get("limit", 0),
            "core_reset": datetime.fromtimestamp(core.get("reset", 0)).isoformat(),
            "graphql_remaining": graphql.get("remaining", 0),
            "graphql_limit": graphql.get("limit", 0),
            "graphql_reset": datetime.fromtimestamp(graphql.get("reset", 0)).isoformat(),
        }
        return self._rate_limit_info

    def is_rate_limited(self) -> tuple[bool, str]:
        """
        Check if we're rate limited.
        
        Returns:
            (is_limited: bool, message: str)
        """
        info = self.get_rate_limit()
        if "error" in info:
            return False, info["error"]
        
        if info["core_remaining"] < 10:
            return True, f"REST API nearly exhausted: {info['core_remaining']}/{info['core_limit']}. Resets at {info['core_reset']}"
        if info["graphql_remaining"] < 10:
            return True, f"GraphQL API nearly exhausted: {info['graphql_remaining']}/{info['graphql_limit']}. Resets at {info['graphql_reset']}"
        
        return False, f"OK - REST: {info['core_remaining']}/{info['core_limit']}, GraphQL: {info['graphql_remaining']}/{info['graphql_limit']}"

    def _rest_get(self, path: str) -> Optional[dict]:
        """GET GitHub REST API. Returns JSON or None."""
        url = f"https://api.github.com{path}"
        
        with self._semaphore:
            token = self.pool.get_next_token()
            try:
                res = requests.get(url, headers=self._headers(token), timeout=self.request_timeout)
            except requests.exceptions.RequestException:
                return None
            
            # Update rate limit info
            remaining = res.headers.get("X-RateLimit-Remaining")
            reset = res.headers.get("X-RateLimit-Reset")
            if remaining is not None and reset is not None:
                self.pool.update_limit(token, int(remaining), float(reset))
                
            if res.status_code != 200:
                if res.status_code == 403 and "rate limit" in res.text.lower():
                    # If this token is exhausted, try one more time with a different token
                    token = self.pool.get_next_token()
                    try:
                        res = requests.get(url, headers=self._headers(token), timeout=self.request_timeout)
                    except requests.exceptions.RequestException:
                        return None
                    if res.status_code != 200:
                        return None
                else:
                    return None
            return res.json()

    def _graphql_query(self, query: str, variables: dict = None) -> dict:
        """Execute a GraphQL query on GitHub's public API."""
        url = "https://api.github.com/graphql"
        
        with self._semaphore:
            token = self.pool.get_next_token()
            try:
                res = requests.post(
                    url,
                    json={"query": query, "variables": variables or {}},
                    headers=self._headers(token),
                    timeout=self.request_timeout,
                )
            except requests.exceptions.RequestException as e:
                raise Exception(f"GraphQL request failed: {e}")
            
            # Update rate limit info
            remaining = res.headers.get("X-RateLimit-Remaining")
            reset = res.headers.get("X-RateLimit-Reset")
            if remaining is not None and reset is not None:
                self.pool.update_limit(token, int(remaining), float(reset))

            if res.status_code != 200:
                raise Exception(f"GraphQL query failed with status {res.status_code}: {res.text}")
            data = res.json()
            if "errors" in data:
                raise Exception(f"GraphQL query error: {data['errors']}")
            return data["data"]

    # =========================
    # Validation Methods
    # =========================

    @staticmethod
    def extract_repo_parts(repo_url: str) -> tuple[str, str]:
        """Extract owner and repo name from a GitHub repository URL."""
        parsed = urlparse(repo_url)
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 2:
            raise ValueError("Invalid GitHub repository URL. Example: https://github.com/pallets/flask")
        return parts[0], parts[1]

    @staticmethod
    def parse_issue_number_from_url(issue_url: str) -> Optional[int]:
        """Extract issue number from GitHub issue URL (must be /issues/N, not /pull/N)."""
        parsed = urlparse(issue_url)
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 4:
            return None
        if parts[2].lower() != "issues":
            return None
        try:
            return int(parts[3])
        except ValueError:
            return None

    @staticmethod
    def validate_issue_url_is_issue(issue_url: str) -> bool:
        """URL must be an Issue (/issues/), not a Pull Request (/pull/)."""
        return "/issues/" in issue_url and "/pull/" not in issue_url

    @staticmethod
    def validate_issue_closed(state: str) -> bool:
        """Issue status must be Closed."""
        return (state or "").upper() == "CLOSED"

    # Pattern to match fenced code blocks (```...```) and inline code (`...`)
    RE_FENCED_CODE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
    RE_INLINE_CODE = re.compile(r"`[^`]+`")
    # Indented code blocks (4+ spaces or tab at start of line)
    RE_INDENTED_CODE = re.compile(r"^(?:    |\t).+$", re.MULTILINE)

    @classmethod
    def strip_code_blocks(cls, text: str) -> str:
        """Remove code blocks from text (fenced, inline, indented)."""
        result = cls.RE_FENCED_CODE.sub("", text)
        result = cls.RE_INLINE_CODE.sub("", result)
        result = cls.RE_INDENTED_CODE.sub("", result)
        return result

    @classmethod
    def validate_issue_content(cls, body: str, strict_links: bool = True) -> tuple[bool, str]:
        """
        Issue content: no links, no images, non-empty, not 'No description provided'.
        Returns (ok: bool, reason: str).
        
        If strict_links=False, URLs inside code blocks are ignored.
        """
        if body is None:
            return False, "empty body"
        text = (body or "").strip()
        if not text:
            return False, "empty body"
        lower = text.lower()
        if "no description provided" in lower or lower == "no description":
            return False, "no description provided"
        
        # For link/URL detection, optionally strip code blocks first
        text_for_links = cls.strip_code_blocks(text) if not strict_links else text
        
        if cls.RE_IMAGE_MD.search(text):
            return False, "contains image (markdown)"
        if cls.RE_IMG_TAG.search(text):
            return False, "contains image (html)"
        if cls.RE_MD_LINK.search(text_for_links):
            return False, "contains markdown link"
        if cls.RE_BARE_URL.search(text_for_links):
            return False, "contains URL"
        if cls.RE_GITHUB_REF.search(text_for_links):
            return False, "contains GitHub reference (#issue)"
        return True, ""
    
    @classmethod
    def check_content_flags(cls, body: str) -> dict:
        """
        Return individual content flags without failing validation.
        Useful for UI display.
        """
        text = (body or "").strip()
        text_no_code = cls.strip_code_blocks(text)
        
        return {
            "is_empty": not text,
            "has_md_link": bool(cls.RE_MD_LINK.search(text)),
            "has_md_link_outside_code": bool(cls.RE_MD_LINK.search(text_no_code)),
            "has_url": bool(cls.RE_BARE_URL.search(text)),
            "has_url_outside_code": bool(cls.RE_BARE_URL.search(text_no_code)),
            "has_github_ref": bool(cls.RE_GITHUB_REF.search(text)),
            "has_github_ref_outside_code": bool(cls.RE_GITHUB_REF.search(text_no_code)),
            "has_image_md": bool(cls.RE_IMAGE_MD.search(text)),
            "has_image_html": bool(cls.RE_IMG_TAG.search(text)),
        }

    # =========================
    # Repository Methods
    # =========================

    def fetch_repo_metadata(self, owner: str, repo: str) -> dict:
        """Fetch repository metadata (stars, forks, language, description, topics, discussions)."""
        global _REPO_METADATA_CACHE
        key = (owner.lower(), repo.lower())
        now = time.time()
        if key in _REPO_METADATA_CACHE:
            expiry, data = _REPO_METADATA_CACHE[key]
            if now < expiry:
                return data
            del _REPO_METADATA_CACHE[key]
        # We'll use GraphQL to get everything in one call more efficiently
        query = """
        query($owner: String!, $repo: String!) {
          repository(owner: $owner, name: $repo) {
            description
            stargazerCount
            forkCount
            primaryLanguage { name }
            defaultBranchRef { name }
            url
            hasDiscussionsEnabled
            repositoryTopics(first: 20) {
              nodes {
                topic { name }
              }
            }
            issues(states: CLOSED) { totalCount }
            openIssues: issues(states: OPEN) { totalCount }
          }
        }
        """
        try:
            data = self._graphql_query(query, {"owner": owner, "repo": repo})
            r = data.get("repository")
            if r:
                out = {
                    "owner": owner,
                    "name": repo,
                    "full_name": f"{owner}/{repo}",
                    "description": r.get("description"),
                    "stars": r.get("stargazerCount", 0),
                    "forks": r.get("forkCount", 0),
                    "language": r.get("primaryLanguage", {}).get("name") if r.get("primaryLanguage") else None,
                    "default_branch": r.get("defaultBranchRef", {}).get("name", "main") if r.get("defaultBranchRef") else "main",
                    "url": r.get("url"),
                    "has_discussions": 1 if r.get("hasDiscussionsEnabled") else 0,
                    "topics": json.dumps([n["topic"]["name"] for n in r.get("repositoryTopics", {}).get("nodes", [])]),
                    "closed_issues": r.get("issues", {}).get("totalCount", 0),
                    "open_issues": r.get("openIssues", {}).get("totalCount", 0),
                }
                _REPO_METADATA_CACHE[key] = (now + _REPO_CACHE_TTL, out)
                return out
        except Exception:
            pass

        # Fallback to REST if GraphQL fails
        data = self._rest_get(f"/repos/{owner}/{repo}")
        
        # Fetch issue counts separately
        closed_issues = 0
        open_issues = 0
        try:
            search_closed = self._rest_get(f"/search/issues?q=repo:{owner}/{repo}+type:issue+state:closed&per_page=1")
            if search_closed:
                closed_issues = search_closed.get("total_count", 0)
            
            search_open = self._rest_get(f"/search/issues?q=repo:{owner}/{repo}+type:issue+state:open&per_page=1")
            if search_open:
                open_issues = search_open.get("total_count", 0)
        except Exception:
            pass
        
        if not data:
            return {
                "owner": owner,
                "name": repo,
                "full_name": f"{owner}/{repo}",
                "description": None,
                "stars": 0,
                "forks": 0,
                "language": None,
                "default_branch": "main",
                "url": f"https://github.com/{owner}/{repo}",
                "closed_issues": closed_issues,
                "open_issues": open_issues,
                "has_discussions": 0,
                "topics": "[]",
            }
        out = {
            "owner": owner,
            "name": repo,
            "full_name": data.get("full_name", f"{owner}/{repo}"),
            "description": data.get("description"),
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "language": (data.get("language") or {}).get("name") if isinstance(data.get("language"), dict) else data.get("language"),
            "default_branch": data.get("default_branch", "main"),
            "url": data.get("html_url", f"https://github.com/{owner}/{repo}"),
            "closed_issues": closed_issues,
            "open_issues": open_issues,
            "has_discussions": 0,
            "topics": "[]",
        }
        _REPO_METADATA_CACHE[key] = (now + _REPO_CACHE_TTL, out)
        return out

    def get_default_branch(self, owner: str, repo: str) -> Optional[str]:
        """Return default branch name (e.g. main) or None."""
        data = self._rest_get(f"/repos/{owner}/{repo}")
        if not data:
            return None
        return data.get("default_branch")

    def get_issue_counts(self, owner: str, repo: str) -> dict:
        """Fetch linked, closed, and open issue counts for a repo."""
        linked_count = 0
        closed_count = 0
        open_count = 0
        try:
            linked_search = self._rest_get(
                f"/search/issues?q=repo:{owner}/{repo}+type:issue+state:closed+linked:pr&per_page=1"
            )
            if linked_search:
                linked_count = linked_search.get("total_count", 0)
            closed_search = self._rest_get(
                f"/search/issues?q=repo:{owner}/{repo}+type:issue+state:closed&per_page=1"
            )
            if closed_search:
                closed_count = closed_search.get("total_count", 0)
            open_search = self._rest_get(
                f"/search/issues?q=repo:{owner}/{repo}+type:issue+state:open&per_page=1"
            )
            if open_search:
                open_count = open_search.get("total_count", 0)
        except Exception:
            pass
        return {
            "linked": linked_count,
            "closed": closed_count,
            "open": open_count,
        }

    def _get_merged_pr_count(self, owner: str, repo: str) -> int:
        """Get total count of merged PRs in the repository."""
        query = """
        query($owner: String!, $repo: String!) {
          repository(owner: $owner, name: $repo) {
            pullRequests(states: MERGED) {
              totalCount
            }
          }
        }
        """
        try:
            data = self._graphql_query(query, {"owner": owner, "repo": repo})
            return data.get("repository", {}).get("pullRequests", {}).get("totalCount", 0)
        except Exception:
            return 0

    def repo_has_tests(self, owner: str, repo: str) -> tuple[bool, list[str]]:
        """
        Check if the repository has test infrastructure.
        
        Returns:
            (has_tests: bool, found_indicators: list[str])
        """
        # Common test directories and files to look for
        test_indicators = [
            "tests",
            "test", 
            "testing",
            "spec",
            "pytest.ini",
            "setup.cfg",  # Often contains pytest config
            "tox.ini",
            "conftest.py",
            ".pytest_cache",
            "test_requirements.txt",
            "requirements-test.txt",
            "requirements-dev.txt",
        ]
        
        found = []
        
        # Check root directory for test indicators
        data = self._rest_get(f"/repos/{owner}/{repo}/contents")
        if data:
            for item in data:
                name = item.get("name", "").lower()
                item_type = item.get("type", "")
                
                # Check for test directories
                if item_type == "dir" and name in ["tests", "test", "testing", "spec"]:
                    found.append(f"{name}/ directory")
                
                # Check for test config files
                if item_type == "file" and name in ["pytest.ini", "tox.ini", "conftest.py", 
                                                      "test_requirements.txt", "requirements-test.txt"]:
                    found.append(name)
                
                # Check setup.cfg for pytest section (we'll just note it exists)
                if item_type == "file" and name == "setup.cfg":
                    found.append("setup.cfg (may contain test config)")
                
                # Check pyproject.toml for pytest config
                if item_type == "file" and name == "pyproject.toml":
                    found.append("pyproject.toml (may contain test config)")
        
        return len(found) > 0, found

    def get_base_sha_at_date(
        self, owner: str, repo: str, until_iso8601: str, default_branch: str = None
    ) -> Optional[str]:
        """
        Return the default branch tip at or before until_iso8601 (REST commits?until=).
        Use as fallback when PR base_sha (baseRefOid) is not available. For true PR base,
        prefer the API's base.sha / baseRefOid (target branch at PR create/update).
        """
        if default_branch is None:
            default_branch = self.get_default_branch(owner, repo)
        if not default_branch:
            return None
        data = self._rest_get(
            f"/repos/{owner}/{repo}/commits?sha={default_branch}&until={until_iso8601}&per_page=1"
        )
        if not data or not isinstance(data, list) or len(data) == 0:
            return None
        return data[0].get("sha")

    # =========================
    # Issue Methods
    # =========================

    def fetch_issue_details(self, owner: str, repo: str, issue_number: int) -> Optional[dict]:
        """Fetch issue state, body, createdAt via GraphQL. Returns dict or None."""
        query = """
        query($owner: String!, $repo: String!, $num: Int!) {
          repository(owner: $owner, name: $repo) {
            issue(number: $num) {
              state
              body
              createdAt
            }
          }
        }
        """
        try:
            data = self._graphql_query(query, {"owner": owner, "repo": repo, "num": issue_number})
            repo_data = data.get("repository")
            if not repo_data:
                return None
            issue = repo_data.get("issue")
            if not issue:
                return None
            return {
                "state": issue.get("state"),
                "body": issue.get("body"),
                "createdAt": issue.get("createdAt"),
            }
        except Exception:
            return None

    def fetch_issue_full_details(self, owner: str, repo: str, issue_number: int) -> Optional[dict]:
        """Fetch comprehensive issue details including title and linked PR. Returns dict or None."""
        query = """
        query($owner: String!, $repo: String!, $num: Int!) {
          repository(owner: $owner, name: $repo) {
            issue(number: $num) {
              number
              title
              state
              body
              createdAt
              closedAt
              author {
                login
              }
              timelineItems(first: 50, itemTypes: [CROSS_REFERENCED_EVENT]) {
                nodes {
                  ... on CrossReferencedEvent {
                    source {
                      __typename
                      ... on PullRequest {
                        number
                        title
                        url
                        state
                        merged
                        mergedAt
                        baseRefOid
                        additions
                        deletions
                        changedFiles
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        try:
            data = self._graphql_query(query, {"owner": owner, "repo": repo, "num": issue_number})
            repo_data = data.get("repository")
            if not repo_data:
                return None
            issue = repo_data.get("issue")
            if not issue:
                return None
            return issue
        except Exception:
            return None

    def get_issue_closing_prs_count(self, owner: str, repo: str, issue_number: int) -> int:
        """
        Count how many merged PRs are linked to this issue.
        Uses multiple methods to ensure accurate detection:
        1. GraphQL timeline events (primary)
        2. Search for merged PRs mentioning this issue (fallback)
        """
        merged_prs = set()
        
        # Method 1: GraphQL timeline events
        try:
            gql_prs = self._get_closing_prs_graphql(owner, repo, issue_number)
            merged_prs.update(gql_prs)
        except Exception as e:
            print(f"    GraphQL failed for issue #{issue_number}: {e}")
        
        # Method 2: Search for merged PRs that mention this issue
        # This catches PRs that might not show up in timeline events
        try:
            search_prs = self._search_merged_prs_for_issue(owner, repo, issue_number)
            if search_prs:
                print(f"    Search found additional PRs: {search_prs - merged_prs}")
                merged_prs.update(search_prs)
        except Exception as e:
            print(f"    Search failed for issue #{issue_number}: {e}")
        
        print(f"    Issue #{issue_number}: TOTAL {len(merged_prs)} merged PRs -> {sorted(merged_prs)}")
        return len(merged_prs)
    
    def _search_merged_prs_for_issue(self, owner: str, repo: str, issue_number: int) -> set:
        """Search for merged PRs that reference this issue number."""
        merged_prs = set()
        
        # Search query: merged PRs in this repo that mention this issue
        search_query = f"repo:{owner}/{repo} is:pr is:merged #{issue_number}"
        url = f"https://api.github.com/search/issues?q={requests.utils.quote(search_query)}&per_page=20"
        
        try:
            res = requests.get(url, headers=self._headers(), timeout=self.request_timeout)
            if res.status_code != 200:
                return merged_prs
            
            data = res.json()
            for item in data.get("items", []):
                pr_number = item.get("number")
                # Verify it's actually linked (not just a mention in comments)
                # by checking if the PR body or title contains issue reference
                body = (item.get("body") or "").lower()
                title = (item.get("title") or "").lower()
                
                # Check for closing keywords or direct reference
                issue_ref = f"#{issue_number}"
                if issue_ref in body or issue_ref in title:
                    merged_prs.add(pr_number)
                    print(f"      Search: Found merged PR #{pr_number} mentioning {issue_ref}")
            
            return merged_prs
        except Exception:
            return merged_prs
    
    def _get_closing_prs_graphql(self, owner: str, repo: str, issue_number: int) -> set:
        """
        Use GraphQL to get merged PRs linked to this issue.
        Checks multiple sources:
        1. ClosedEvent - PR that closed the issue via "fixes #X" keywords
        2. ConnectedEvent - PR linked via GitHub's Development panel  
        3. CrossReferencedEvent - PR that mentioned this issue
        
        Returns set of PR numbers.
        """
        query = """
        query($owner: String!, $repo: String!, $num: Int!) {
          repository(owner: $owner, name: $repo) {
            issue(number: $num) {
              timelineItems(first: 100, itemTypes: [CLOSED_EVENT, CONNECTED_EVENT, CROSS_REFERENCED_EVENT]) {
                nodes {
                  __typename
                  ... on ClosedEvent {
                    closer {
                      __typename
                      ... on PullRequest {
                        number
                        merged
                        state
                      }
                    }
                  }
                  ... on ConnectedEvent {
                    subject {
                      __typename
                      ... on PullRequest {
                        number
                        merged
                        state
                      }
                    }
                  }
                  ... on CrossReferencedEvent {
                    source {
                      __typename
                      ... on PullRequest {
                        number
                        merged
                        state
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        merged_prs = set()
        
        try:
            data = self._graphql_query(query, {"owner": owner, "repo": repo, "num": issue_number})
            issue = data.get("repository", {}).get("issue")
            if not issue:
                print(f"    GQL: Issue #{issue_number} not found")
                return merged_prs
            
            timeline_nodes = issue.get("timelineItems", {}).get("nodes", [])
            print(f"    GQL: Issue #{issue_number} has {len(timeline_nodes)} timeline events")
            
            for node in timeline_nodes:
                if not node:
                    continue
                
                node_type = node.get("__typename")
                
                # ClosedEvent - PR that directly closed the issue via keywords like "fixes #123"
                if node_type == "ClosedEvent":
                    closer = node.get("closer")
                    if closer and closer.get("__typename") == "PullRequest":
                        pr_num = closer.get("number")
                        is_merged = closer.get("merged", False)
                        state = closer.get("state", "")
                        print(f"      GQL ClosedEvent: PR #{pr_num} merged={is_merged} state={state}")
                        if is_merged:
                            merged_prs.add(pr_num)
                
                # ConnectedEvent - issue linked to PR via GitHub's Development panel
                if node_type == "ConnectedEvent":
                    subject = node.get("subject")
                    if subject and subject.get("__typename") == "PullRequest":
                        pr_num = subject.get("number")
                        is_merged = subject.get("merged", False)
                        state = subject.get("state", "")
                        print(f"      GQL ConnectedEvent: PR #{pr_num} merged={is_merged} state={state}")
                        if is_merged:
                            merged_prs.add(pr_num)
                
                # CrossReferencedEvent - ANY PR that references this issue  
                if node_type == "CrossReferencedEvent":
                    source = node.get("source")
                    if source and source.get("__typename") == "PullRequest":
                        pr_num = source.get("number")
                        is_merged = source.get("merged", False)
                        state = source.get("state", "")
                        print(f"      GQL CrossReferencedEvent: PR #{pr_num} merged={is_merged} state={state}")
                        if is_merged:
                            merged_prs.add(pr_num)
            
            print(f"    GQL: Issue #{issue_number} found {len(merged_prs)} merged PRs -> {sorted(merged_prs)}")
            return merged_prs
            
        except Exception as e:
            print(f"    GQL error for issue #{issue_number}: {e}")
            return merged_prs

    # =========================
    # Scan Methods
    # =========================

    def scan_repository(
        self,
        owner: str,
        repo: str,
        log_callback: Callable[[str], None] = None,
    ) -> tuple[list[dict], dict]:
        """
        Scan repository for qualifying issues.
        Returns (list of issue dicts, analytics dict).
        
        Analytics dict contains:
        - total_prs: Total PRs scanned
        - total_issues_examined: Issues linked to PRs that were examined
        - qualified: Count of qualifying issues
        - rejection_reasons: Dict of reason -> count
        - pages_scanned: Number of pages scanned this run
        """

        def _log(msg: str):
            print(msg)
            if log_callback:
                log_callback(msg)

        # Check repo-level blacklist FIRST - don't waste any API calls
        full_name = f"{owner}/{repo}"
        if full_name in self.blacklist_repos:
            _log(f"Repository {full_name} is blacklisted - skipping entirely")
            return [], {"repo_blacklisted": True, "qualified": 0}

        def _log(msg: str):
            print(msg)
            if log_callback:
                log_callback(msg)

        # Analytics tracking
        analytics = {
            "total_prs": 0,
            "total_issues_examined": 0,
            "qualified": 0,
            "rejection_reasons": {},
            "pages_scanned": 0,
            "pages_previously_scanned": 0,
            "pages_target": 0,
            "repo_total_prs": 0,
            "estimated_prs_remaining": 0,
            "repo_has_tests": False,
            "repo_test_indicators": [],
            "near_misses": [],  # Issues that almost qualify
            "blacklisted_skipped": 0,  # Count of blacklisted issues skipped
            "multi_issue_prs_skipped": 0,  # PRs that close multiple issues
            "multi_pr_issues_skipped": 0,  # Issues resolved by multiple PRs
        }

        # Check if repo has tests (if required)
        if self.require_repo_tests:
            has_tests, test_indicators = self.repo_has_tests(owner, repo)
            analytics["repo_has_tests"] = has_tests
            analytics["repo_test_indicators"] = test_indicators
            
            if has_tests:
                _log(f"Repo has tests: {', '.join(test_indicators)}")
            else:
                _log("Repo has NO test infrastructure - skipping (require_repo_tests=True)")
                return [], analytics
        else:
            # Still check for informational purposes
            has_tests, test_indicators = self.repo_has_tests(owner, repo)
            analytics["repo_has_tests"] = has_tests
            analytics["repo_test_indicators"] = test_indicators
            _log(f"Repo test status: {'Yes - ' + ', '.join(test_indicators) if has_tests else 'No tests found'}")

        # Load progress
        progress = self._load_scan_progress(f"{owner}/{repo}")
        scanned_pages = progress.get("scanned_pages", [])
        after_cursor = progress.get("last_cursor")
        
        analytics["pages_previously_scanned"] = len(scanned_pages)

        # Get total merged PR count for progress estimation
        total_pr_count = self._get_merged_pr_count(owner, repo)
        analytics["repo_total_prs"] = total_pr_count
        estimated_total_pages = (total_pr_count // self.per_page) + 1 if total_pr_count > 0 else 0

        # max_pages is a HARD LIMIT on total pages ever scanned (not per-run)
        # If we've already scanned some pages, only scan up to max_pages total
        pages_already_done = len(scanned_pages)
        pages_left_in_budget = max(0, self.max_pages - pages_already_done)
        
        # dynamic_max_pages = the absolute page number we'll stop at
        dynamic_max_pages = pages_already_done + pages_left_in_budget
        analytics["pages_target"] = self.max_pages  # User's hard limit
        
        _log(f"Repository has ~{total_pr_count:,} merged PRs (~{estimated_total_pages} pages)")
        _log(f"Previously scanned: {pages_already_done} pages | Hard limit: {self.max_pages} | Budget remaining: {pages_left_in_budget}")
        
        # Check if we've hit the hard limit
        if pages_left_in_budget == 0:
            _log(f"Hard limit reached! Already scanned {pages_already_done}/{self.max_pages} pages. Increase limit to scan more.")
        elif estimated_total_pages > 0 and pages_already_done >= estimated_total_pages:
            _log(f"Repo fully scanned! All ~{total_pr_count:,} PRs have been examined.")
        else:
            pages_in_repo_remaining = max(0, estimated_total_pages - pages_already_done) if estimated_total_pages > 0 else pages_left_in_budget
            actual_pages_to_scan = min(pages_left_in_budget, pages_in_repo_remaining)
            _log(f"This run: up to {actual_pages_to_scan} new pages (pages {pages_already_done + 1}+)")
        
        prs_already_scanned = len(scanned_pages) * self.per_page
        analytics["estimated_prs_remaining"] = max(0, total_pr_count - prs_already_scanned)

        all_issues = []
        default_branch = self.get_default_branch(owner, repo)

        for page in range(1, dynamic_max_pages + 1):
            if page in scanned_pages:
                _log(f"Skipping page {page} (already scanned)")
                continue

            _log(f"Fetching PRs page {page}...")
            query = """
            query($owner: String!, $repo: String!, $per_page: Int!, $after: String) {
              repository(owner: $owner, name: $repo) {
                pullRequests(first: $per_page, after: $after, states: MERGED, orderBy: {field: UPDATED_AT, direction: DESC}) {
                  pageInfo {
                    hasNextPage
                    endCursor
                  }
                  nodes {
                    number
                    title
                    url
                    additions
                    deletions
                    changedFiles
                    mergedAt
                    baseRefOid
                    closingIssuesReferences(first: 10) {
                      totalCount
                      nodes {
                        number
                        title
                        url
                      }
                    }
                  }
                }
              }
            }
            """
            variables = {
                "owner": owner,
                "repo": repo,
                "per_page": self.per_page,
                "after": after_cursor,
            }
            data = self._graphql_query(query, variables)
            prs_data = data["repository"]["pullRequests"]
            prs = prs_data["nodes"]

            analytics["total_prs"] += len(prs)
            page_issues, page_analytics = self._filter_prs(owner, repo, prs, default_branch, _log)
            all_issues.extend(page_issues)
            
            # Merge page analytics
            analytics["total_issues_examined"] += page_analytics["examined"]
            analytics["qualified"] += len(page_issues)
            analytics["blacklisted_skipped"] += page_analytics.get("blacklisted_skipped", 0)
            analytics["multi_issue_prs_skipped"] += page_analytics.get("multi_issue_prs_skipped", 0)
            analytics["multi_pr_issues_skipped"] += page_analytics.get("multi_pr_issues_skipped", 0)
            for reason, count in page_analytics["rejections"].items():
                analytics["rejection_reasons"][reason] = analytics["rejection_reasons"].get(reason, 0) + count
            
            # Collect near-misses
            analytics["near_misses"].extend(page_analytics.get("near_misses", []))

            # Progress info
            pages_done = analytics["pages_previously_scanned"] + analytics["pages_scanned"] + 1
            prs_scanned_total = pages_done * self.per_page
            pct = min(100, (prs_scanned_total / max(total_pr_count, 1)) * 100) if total_pr_count > 0 else 0
            _log(f"Page {page}: {len(prs)} PRs, {len(page_issues)} qualifying | Progress: ~{pct:.0f}% of repo PRs")

            scanned_pages.append(page)
            analytics["pages_scanned"] += 1
            after_cursor = prs_data["pageInfo"]["endCursor"]
            self._save_scan_progress(f"{owner}/{repo}", scanned_pages, after_cursor)

            if not prs_data["pageInfo"]["hasNextPage"]:
                _log("No more pages.")
                break
            
            # Check if target reached
            if self.target_issues > 0 and len(all_issues) >= self.target_issues:
                _log(f"Target reached: found {len(all_issues)} issues (target: {self.target_issues})")
                break

            time.sleep(self.request_delay)
        
        # If target mode enabled and not reached, continue scanning more pages
        # BUT respect max_pages as a hard limit (total pages = previously scanned + this run)
        total_pages_so_far = analytics["pages_previously_scanned"] + analytics["pages_scanned"]
        pages_remaining = max(0, self.max_pages - total_pages_so_far)
        
        if self.target_issues > 0 and len(all_issues) < self.target_issues:
            if pages_remaining == 0:
                _log(f"Target not met ({len(all_issues)}/{self.target_issues}) but hard limit of {self.max_pages} pages reached. Increase limit to continue.")
            else:
                extra_pages = 0
                
                while (len(all_issues) < self.target_issues and 
                       extra_pages < pages_remaining and 
                       after_cursor is not None):
                    extra_pages += 1
                    page = dynamic_max_pages + extra_pages
                    
                    _log(f"Target not met ({len(all_issues)}/{self.target_issues}), fetching page {page} ({extra_pages}/{pages_remaining} remaining)...")
                    
                    query = """
                    query($owner: String!, $repo: String!, $per_page: Int!, $after: String) {
                      repository(owner: $owner, name: $repo) {
                        pullRequests(first: $per_page, after: $after, states: MERGED, orderBy: {field: UPDATED_AT, direction: DESC}) {
                          pageInfo { hasNextPage endCursor }
                          nodes {
                            number title url additions deletions changedFiles mergedAt baseRefOid
                            closingIssuesReferences(first: 10) {
                              totalCount
                              nodes { number title url }
                            }
                          }
                        }
                      }
                    }
                    """
                    try:
                        data = self._graphql_query(query, {
                            "owner": owner, "repo": repo, 
                            "per_page": self.per_page, "after": after_cursor
                        })
                        prs_data = data["repository"]["pullRequests"]
                        prs = prs_data["nodes"]
                        
                        if len(prs) == 0:
                            _log("No more PRs.")
                            break
                        
                        analytics["total_prs"] += len(prs)
                        page_issues, page_analytics = self._filter_prs(owner, repo, prs, default_branch, _log)
                        all_issues.extend(page_issues)
                        
                        analytics["total_issues_examined"] += page_analytics["examined"]
                        analytics["qualified"] += len(page_issues)
                        analytics["pages_scanned"] += 1
                        analytics["blacklisted_skipped"] += page_analytics.get("blacklisted_skipped", 0)
                        analytics["multi_issue_prs_skipped"] += page_analytics.get("multi_issue_prs_skipped", 0)
                        analytics["multi_pr_issues_skipped"] += page_analytics.get("multi_pr_issues_skipped", 0)
                        analytics["near_misses"].extend(page_analytics.get("near_misses", []))
                        
                        for reason, count in page_analytics["rejections"].items():
                            analytics["rejection_reasons"][reason] = analytics["rejection_reasons"].get(reason, 0) + count
                        
                        scanned_pages.append(page)
                        after_cursor = prs_data["pageInfo"]["endCursor"]
                        self._save_scan_progress(f"{owner}/{repo}", scanned_pages, after_cursor)
                        
                        _log(f"Extra page {page}: {len(prs)} PRs, {len(page_issues)} qualifying | Total: {len(all_issues)}")
                        
                        if not prs_data["pageInfo"]["hasNextPage"]:
                            _log("No more pages in repo.")
                            break
                        
                        time.sleep(self.request_delay)
                    except Exception as e:
                        _log(f"Error fetching extra page: {e}")
                        break

        _log(f"Scan complete. Found {len(all_issues)} qualifying issues.")
        
        # Sort and limit near-misses
        analytics["near_misses"].sort(key=lambda x: x.get("python_lines", 0), reverse=True)
        analytics["near_misses"] = analytics["near_misses"][:10]
        
        if len(all_issues) == 0 and len(analytics["near_misses"]) > 0:
            _log(f"No qualifying issues, but found {len(analytics['near_misses'])} near-misses")
        
        return all_issues, analytics

    def _filter_prs(
        self,
        owner: str,
        repo: str,
        prs: list,
        default_branch: str,
        log: Callable,
    ) -> tuple[list[dict], dict]:
        """Filter PRs and return (qualifying issues, analytics)."""
        results = []
        near_misses = []  # Issues that almost qualify
        analytics = {
            "examined": 0, 
            "rejections": {}, 
            "near_misses": [], 
            "blacklisted_skipped": 0,
            "multi_issue_prs_skipped": 0,
            "multi_pr_issues_skipped": 0,
        }
        
        def reject(reason: str):
            analytics["rejections"][reason] = analytics["rejections"].get(reason, 0) + 1
        
        for pr in prs:
            pr_number = pr.get("number")
            
            # Quick pre-filter on total files (avoid API call if obviously too small)
            files_changed = pr.get("changedFiles", 0)
            if files_changed < self.min_files_changed:
                reject(f"PR < {self.min_files_changed} files")
                continue

            # Quick pre-filter on total lines
            total_lines = pr.get("additions", 0) + pr.get("deletions", 0)
            if total_lines < self.min_lines_changed:
                reject(f"PR < {self.min_lines_changed} lines")
                continue
            if total_lines > self.max_lines_changed:
                reject(f"PR > {self.max_lines_changed} lines")
                continue

            # Fetch detailed file breakdown
            pr_files = self.fetch_pr_files(owner, repo, pr_number)
            file_summary = self.summarize_file_changes(pr_files)
            
            # Apply category-based filters (excluding lock files)
            effective_files = file_summary["total_excluding_lock"]["count"]
            effective_lines = file_summary["total_excluding_lock"]["additions"] + file_summary["total_excluding_lock"]["deletions"]
            
            # Determine if we should relax line requirements (target mode)
            relaxed_mode = self.target_issues > 0 and self.relax_lines_for_target
            
            if effective_files < self.min_files_changed:
                reject(f"< {self.min_files_changed} non-lock files")
                continue
            
            # Line requirements - skip if in relaxed mode
            if not relaxed_mode:
                if effective_lines < self.min_lines_changed:
                    reject(f"< {self.min_lines_changed} lines (excl. lock)")
                    continue
                
                if effective_lines > self.max_lines_changed:
                    reject(f"> {self.max_lines_changed} lines (excl. lock)")
                    continue
            
            # Check minimum Python files
            if self.min_python_files > 0 and file_summary["python"]["count"] < self.min_python_files:
                reject(f"< {self.min_python_files} Python files")
                continue
            
            # Check minimum Python lines (substantial code changes) - skip if relaxed
            python_lines = file_summary["python"]["additions"] + file_summary["python"]["deletions"]
            if not relaxed_mode and self.min_python_lines > 0 and python_lines < self.min_python_lines:
                reject(f"< {self.min_python_lines} Python lines ({python_lines} found)")
                continue
            
            # Check minimum test files
            if self.min_test_files > 0 and file_summary["test"]["count"] < self.min_test_files:
                reject(f"< {self.min_test_files} test files")
                continue
            
            # Check combined Python + Test files (hard requirement even in relaxed mode)
            total_py_files = file_summary["python"]["count"] + file_summary["test"]["count"]
            if self.min_total_python_files > 0 and total_py_files < self.min_total_python_files:
                reject(f"< {self.min_total_python_files} total py files ({total_py_files} found: {file_summary['python']['count']} py + {file_summary['test']['count']} test)")
                continue
            
            # Check minimum doc files
            if self.min_doc_files > 0 and file_summary["doc"]["count"] < self.min_doc_files:
                reject(f"< {self.min_doc_files} doc files")
                continue

            # Check linked issues
            linked = pr.get("closingIssuesReferences", {})
            linked_count = linked.get("totalCount", 0)
            if linked_count == 0:
                reject("No linked issues")
                continue
            
            # Filter: Exclude PRs that close multiple issues
            if self.exclude_multi_issue_prs and linked_count > 1:
                log(f"  Skip PR #{pr_number}: closes {linked_count} issues (multi-issue PR filter)")
                reject(f"PR closes {linked_count} issues (multi-issue PR)")
                analytics["multi_issue_prs_skipped"] += 1
                continue

            # Track PR-level failure reasons for near-miss scoring
            pr_fail_reasons = []
            if effective_files < self.min_files_changed:
                pr_fail_reasons.append(f"files:{effective_files}/{self.min_files_changed}")
            if effective_lines < self.min_lines_changed:
                pr_fail_reasons.append(f"lines:{effective_lines}/{self.min_lines_changed}")
            if effective_lines > self.max_lines_changed:
                pr_fail_reasons.append(f"lines:{effective_lines}>{self.max_lines_changed}")
            if self.min_python_files > 0 and file_summary["python"]["count"] < self.min_python_files:
                pr_fail_reasons.append(f"py_files:{file_summary['python']['count']}/{self.min_python_files}")
            if self.min_python_lines > 0 and python_lines < self.min_python_lines:
                pr_fail_reasons.append(f"py_lines:{python_lines}/{self.min_python_lines}")
            
            for issue_ref in linked.get("nodes", []):
                issue_url = issue_ref.get("url", "")
                analytics["examined"] += 1

                # Check blacklist first
                if issue_url in self.blacklist_urls:
                    log(f"  Skip issue (blacklisted): {issue_url}")
                    reject("Blacklisted")
                    analytics["blacklisted_skipped"] += 1
                    continue

                # Must be /issues/, not /pull/
                if not self.validate_issue_url_is_issue(issue_url):
                    reject("Is PR, not issue")
                    continue

                issue_number = self.parse_issue_number_from_url(issue_url)
                if issue_number is None:
                    reject("Invalid issue URL")
                    continue

                # Fetch issue details
                details = self.fetch_issue_details(owner, repo, issue_number)
                if not details:
                    reject("Could not fetch issue")
                    continue

                # Validate closed
                if not self.validate_issue_closed(details.get("state")):
                    reject("Issue not closed")
                    continue

                # Validate content - track as near-miss if issue is good but PR fails
                ok, reason = self.validate_issue_content(details.get("body"), strict_links=self.strict_links)
                issue_quality_ok = ok
                issue_fail_reason = reason if not ok else None
                
                if not ok:
                    log(f"  Skip issue #{issue_number}: {reason}")
                    reject(reason)
                    # Still track as near-miss if close
                    if reason in ["contains URL", "contains markdown link"] and len(pr_fail_reasons) == 0:
                        near_misses.append({
                            "issue_number": issue_number,
                            "issue_title": issue_ref.get("title", ""),
                            "issue_url": issue_url,
                            "pr_number": pr.get("number"),
                            "fail_reasons": [reason],
                            "python_lines": python_lines,
                            "python_files": file_summary["python"]["count"],
                        })
                    continue

                # Filter: Exclude issues resolved by multiple PRs
                if self.exclude_multi_pr_issues:
                    log(f"  Checking issue #{issue_number} for multi-PR...")
                    closing_prs_count = self.get_issue_closing_prs_count(owner, repo, issue_number)
                    log(f"  Issue #{issue_number} has {closing_prs_count} merged PRs linked")
                    if closing_prs_count > 1:
                        log(f"  SKIP issue #{issue_number}: resolved by {closing_prs_count} PRs (multi-PR issue filter)")
                        reject(f"Issue resolved by {closing_prs_count} PRs")
                        analytics["multi_pr_issues_skipped"] += 1
                        continue
                    else:
                        log(f"  PASS issue #{issue_number}: only {closing_prs_count} PR(s)")

                # Get base SHA: PR's base branch tip (baseRefOid) when available, else default branch at issue creation
                created_at = details.get("createdAt")
                base_sha = pr.get("baseRefOid")
                if not base_sha and created_at:
                    base_sha = self.get_base_sha_at_date(owner, repo, created_at, default_branch)

                # Parse dates
                issue_created_at = None
                if created_at:
                    try:
                        issue_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    except Exception:
                        pass

                pr_merged_at = None
                if pr.get("mergedAt"):
                    try:
                        pr_merged_at = datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))
                    except Exception:
                        pass

                issue_data = {
                    "issue_url": issue_url,
                    "issue_number": issue_number,
                    "issue_title": issue_ref.get("title", ""),
                    "issue_body": details.get("body"),
                    "issue_state": details.get("state", "CLOSED"),
                    "issue_created_at": issue_created_at,
                    "base_sha": base_sha,
                    "pr_number": pr.get("number"),
                    "pr_title": pr.get("title"),
                    "pr_url": pr.get("url"),
                    "pr_files_changed": effective_files,
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
                }
                
                results.append(issue_data)
                py_info = f"py:{file_summary['python']['count']}"
                test_info = f"test:{file_summary['test']['count']}"
                doc_info = f"doc:{file_summary['doc']['count']}"
                log(f"  Found: Issue #{issue_number} -> PR #{pr.get('number')} ({py_info}, {test_info}, {doc_info})")
        
        # Sort near-misses by Python lines (closest to qualifying)
        near_misses.sort(key=lambda x: x.get("python_lines", 0), reverse=True)
        analytics["near_misses"] = near_misses[:10]  # Keep top 10

        return results, analytics

    # =========================
    # Progress Persistence
    # =========================

    def _get_config_hash(self) -> str:
        """Generate a hash of current filter configuration."""
        import hashlib
        config = f"{self.min_files_changed}|{self.min_lines_changed}|{self.max_lines_changed}|" \
                 f"{self.min_python_files}|{self.min_python_lines}|{self.min_test_files}|" \
                 f"{self.min_doc_files}|{self.strict_links}|{self.require_repo_tests}"
        return hashlib.md5(config.encode()).hexdigest()[:8]

    def _load_scan_progress(self, repo_key: str) -> dict:
        """Load scanning progress for a repository. Returns empty if config changed."""
        progress_file = "scan_progress.json"
        current_hash = self._get_config_hash()
        
        if os.path.exists(progress_file):
            try:
                with open(progress_file, "r") as f:
                    progress = json.load(f)
                    repo_progress = progress.get(repo_key, {})
                    
                    # Check if config changed - if so, reset
                    stored_hash = repo_progress.get("config_hash", "")
                    if stored_hash and stored_hash != current_hash:
                        print(f"  Config changed (was {stored_hash}, now {current_hash}) - resetting progress")
                        return {"scanned_pages": [], "last_cursor": None, "config_hash": current_hash}
                    
                    return repo_progress if repo_progress else {"scanned_pages": [], "last_cursor": None}
            except (json.JSONDecodeError, KeyError):
                pass
        return {"scanned_pages": [], "last_cursor": None}

    def _save_scan_progress(self, repo_key: str, scanned_pages: list, last_cursor: str):
        """Save scanning progress for a repository with config hash."""
        progress_file = "scan_progress.json"
        progress = {}
        if os.path.exists(progress_file):
            try:
                with open(progress_file, "r") as f:
                    progress = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                pass

        progress[repo_key] = {
            "scanned_pages": scanned_pages,
            "last_cursor": last_cursor,
            "config_hash": self._get_config_hash(),
        }

        with open(progress_file, "w") as f:
            json.dump(progress, f, indent=2)

    @staticmethod
    def reset_scan_progress(repo_key: str):
        """Reset scanning progress for a repository."""
        progress_file = "scan_progress.json"
        if os.path.exists(progress_file):
            try:
                with open(progress_file, "r") as f:
                    progress = json.load(f)
                if repo_key in progress:
                    del progress[repo_key]
                    with open(progress_file, "w") as f:
                        json.dump(progress, f, indent=2)
            except (json.JSONDecodeError, FileNotFoundError):
                pass
