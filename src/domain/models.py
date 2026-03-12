"""
Domain models - Pure data classes representing core business entities.
No dependencies on external libraries (except dataclasses).
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class RepoMetadata:
    """Repository metadata from GitHub."""
    owner: str
    name: str
    full_name: str
    description: Optional[str] = None
    stars: int = 0
    forks: int = 0
    language: Optional[str] = None
    default_branch: str = "main"
    url: Optional[str] = None


@dataclass
class IssueData:
    """Issue data from GitHub scan."""
    issue_url: str
    issue_number: int
    issue_title: str
    issue_body: Optional[str] = None
    issue_state: str = "CLOSED"
    issue_created_at: Optional[datetime] = None
    base_sha: Optional[str] = None
    pr_number: Optional[int] = None
    pr_title: Optional[str] = None
    pr_url: Optional[str] = None
    pr_files_changed: int = 0
    pr_additions: int = 0
    pr_deletions: int = 0
    pr_merged_at: Optional[datetime] = None


@dataclass
class TaskData:
    """Task created from an issue."""
    id: Optional[int] = None
    name: str = ""
    issue_id: Optional[int] = None
    local_path: Optional[str] = None
    status: str = "prep"
    hfi_session_id: Optional[str] = None
    trajectory_a_id: Optional[str] = None
    trajectory_b_id: Optional[str] = None
    prep_checklist: dict = field(default_factory=dict)
    created_at: Optional[datetime] = None


@dataclass
class IterationData:
    """Evaluation iteration data."""
    id: Optional[int] = None
    task_id: Optional[int] = None
    iteration_num: int = 1
    issue_context: Optional[str] = None
    model_a_response: Optional[str] = None
    model_b_response: Optional[str] = None
    ai_evaluation: Optional[str] = None
    next_instruction: Optional[str] = None
    created_at: Optional[datetime] = None
