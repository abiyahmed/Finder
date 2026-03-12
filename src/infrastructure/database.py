"""
Database models and CRUD helpers using SQLAlchemy.
Infrastructure layer - handles persistence concerns.
"""
import os
import json
import hashlib
import threading
from datetime import datetime, timedelta
from typing import Any, Optional
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, joinedload

from dotenv import load_dotenv
load_dotenv()

if os.environ.get("TEST_MODE"):
    DATABASE_URL = "sqlite:///:memory:"
elif os.environ.get("DATABASE_URL"):
    DATABASE_URL = os.environ.get("DATABASE_URL")
else:
    _db_user = os.environ.get("SUPABASE_DB_USER")
    _db_pass = os.environ.get("SUPABASE_DB_PASSWORD")
    _db_host = os.environ.get("SUPABASE_DB_HOST")
    _db_port = os.environ.get("SUPABASE_DB_PORT", "5432")
    _db_name = os.environ.get("SUPABASE_DB_NAME", "postgres")
    if _db_user and _db_host:
        _encoded_pass = (_db_pass or "").replace("@", "%40").replace("#", "%23")
        DATABASE_URL = f"postgresql://{_db_user}:{_encoded_pass}@{_db_host}:{_db_port}/{_db_name}"
    else:
        _persistent_dir = "/home/app-user/data"
        if os.path.exists(_persistent_dir):
            DATABASE_URL = "sqlite:////home/app-user/data/tasks.db"
        else:
            DATABASE_URL = "sqlite:///tasks.db"

_connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}

def _create_engine_with_fallback():
    """Create engine, falling back to SQLite if Supabase Postgres is unreachable."""
    try:
        kwargs = {"echo": False, "connect_args": _connect_args, "pool_pre_ping": True}
        if "postgresql" in DATABASE_URL:
            # Recycle connections before server idle timeout (e.g. Supabase ~5–10 min)
            kwargs["pool_recycle"] = 300
        eng = create_engine(DATABASE_URL, **kwargs)
        if "postgresql" in DATABASE_URL:
            with eng.connect() as conn:
                conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return eng
    except Exception as exc:
        if "sqlite" in DATABASE_URL:
            raise
        import warnings
        warnings.warn(f"Supabase Postgres unreachable ({exc}), falling back to local SQLite.")
        fallback_url = "sqlite:///tasks.db"
        return create_engine(
            fallback_url,
            echo=False,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )

engine = _create_engine_with_fallback()
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()
_DB_INIT_LOCK = threading.Lock()
_DB_INITIALIZED = False


class User(Base):
    """User accounts for the platform"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(256), nullable=False)
    email = Column(String(255), nullable=True)
    supabase_uid = Column(String(255), nullable=True, unique=True)
    github_token = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    last_active_at = Column(DateTime, nullable=True)
    last_seen_ip = Column(String(64), nullable=True)
    last_seen_device = Column(String(128), nullable=True)
    last_seen_country = Column(String(100), nullable=True)
    last_seen_location = Column(String(255), nullable=True)
    
    # Admin & Verification
    is_admin = Column(Integer, default=0)  # 1 = admin
    is_verified = Column(Integer, default=0)  # 1 = verified by admin
    role = Column(String(50), default="user")  # user, admin, role_manager
    
    # Stats
    issues_submitted = Column(Integer, default=0)
    issues_reserved = Column(Integer, default=0)
    issues_completed = Column(Integer, default=0)

    # Access restrictions
    max_ip_addresses = Column(Integer, nullable=True)
    max_device_fingerprints = Column(Integer, nullable=True)
    allowed_countries = Column(Text, nullable=True)  # JSON array
    allowed_locations = Column(Text, nullable=True)  # JSON array


class UserSession(Base):
    """Session and access history for a user."""
    __tablename__ = "user_sessions"
    __table_args__ = (
        UniqueConstraint("user_id", "session_key", name="uq_user_sessions_user_session_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_key = Column(String(128), nullable=False)
    ip_address = Column(String(64), nullable=True)
    device_fingerprint = Column(String(128), nullable=True)
    mac_address = Column(String(128), nullable=True)
    country = Column(String(100), nullable=True)
    location = Column(String(255), nullable=True)
    user_agent = Column(String(512), nullable=True)
    signed_in_at = Column(DateTime, default=datetime.utcnow)
    last_active_at = Column(DateTime, default=datetime.utcnow)
    signed_out_at = Column(DateTime, nullable=True)
    is_active = Column(Integer, default=1)


class UserActivity(Base):
    """Audit log of user actions and feature usage."""
    __tablename__ = "user_activities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    username_snapshot = Column(String(100), nullable=True)
    action = Column(String(100), nullable=False)
    feature = Column(String(100), nullable=True)
    repo_full_name = Column(String(512), nullable=True)
    issue_url = Column(String(512), nullable=True)
    issue_number = Column(Integer, nullable=True)
    task_id = Column(Integer, nullable=True)
    ip_address = Column(String(64), nullable=True)
    device_fingerprint = Column(String(128), nullable=True)
    mac_address = Column(String(128), nullable=True)
    country = Column(String(100), nullable=True)
    location = Column(String(255), nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class GoodIssue(Base):
    """Curated good-quality issues shared among users"""
    __tablename__ = "good_issues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    issue_url = Column(String(512), nullable=False, unique=True)
    owner = Column(String(255), nullable=True)
    repo = Column(String(255), nullable=True)
    issue_number = Column(Integer, nullable=True)
    issue_title = Column(String(512), nullable=True)
    pr_url = Column(String(512), nullable=True)
    pr_number = Column(Integer, nullable=True)
    base_sha = Column(String(64), nullable=True)
    
    # File breakdown
    python_files = Column(Integer, default=0)
    test_files = Column(Integer, default=0)
    total_lines = Column(Integer, default=0)
    
    # Submission info
    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)  # Why it's good
    is_public = Column(Integer, default=1)  # 1 = community-visible, 0 = personal/private
    
    # Reservation
    reserved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reserved_at = Column(DateTime, nullable=True)
    status = Column(String(50), default="available")  # available, reserved, completed


class Blacklist(Base):
    """Blacklisted issues that should be skipped during scanning"""
    __tablename__ = "blacklist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    issue_url = Column(String(512), nullable=False, unique=True)
    owner = Column(String(255), nullable=True)
    repo = Column(String(255), nullable=True)
    issue_number = Column(Integer, nullable=True)
    reason = Column(String(255), nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)


class BlacklistRepo(Base):
    """Blacklisted repositories - all issues from these repos are skipped"""
    __tablename__ = "blacklist_repos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(512), nullable=False, unique=True)  # owner/repo
    owner = Column(String(255), nullable=True)
    repo = Column(String(255), nullable=True)
    reason = Column(String(255), nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)


class RepoWhitelist(Base):
    """Whitelisted repositories - known good repos from search results."""
    __tablename__ = "repo_whitelist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(512), nullable=False, unique=True)  # owner/repo
    owner = Column(String(255), nullable=True)
    repo = Column(String(255), nullable=True)
    reason = Column(String(255), nullable=True)
    source = Column(String(100), nullable=True)  # e.g. repo-search-auto, manual
    added_at = Column(DateTime, default=datetime.utcnow)


class GitHubToken(Base):
    """GitHub Personal Access Tokens for the pool"""
    __tablename__ = "github_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(255), nullable=False, unique=True)
    description = Column(String(255), nullable=True)
    is_active = Column(Integer, default=1)
    rate_limit_remaining = Column(Integer, nullable=True)
    rate_limit_reset = Column(DateTime, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)


class Repository(Base):
    """Cached repository metadata"""
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    full_name = Column(String(512), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    stars = Column(Integer, default=0)
    forks = Column(Integer, default=0)
    language = Column(String(100), nullable=True)
    default_branch = Column(String(100), default="main")
    url = Column(String(512), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)

    # Analysis
    saved_dockerfile = Column(Text, nullable=True)
    saved_dependencies = Column(Text, nullable=True)  # Frozen deps content
    saved_readme_section = Column(Text, nullable=True)  # Install/test section
    setup_notes = Column(Text, nullable=True)  # User notes for this repo

    # GraphQL Indicators
    topics = Column(Text, nullable=True)  # JSON list of strings
    has_discussions = Column(Integer, default=0)
    primary_language = Column(String(100), nullable=True)
    stars_count = Column(Integer, default=0)
    forks_count = Column(Integer, default=0)

    issues = relationship("Issue", back_populates="repository")


class RepoHistory(Base):
    """History of repo preparations for reuse"""
    __tablename__ = "repo_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    
    # What was saved
    dockerfile_content = Column(Text, nullable=True)
    dependencies_content = Column(Text, nullable=True)
    readme_section = Column(Text, nullable=True)
    python_version = Column(String(20), nullable=True)
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class RepoSearchRun(Base):
    """History of repo search runs (star range, criteria, results)."""
    __tablename__ = "repo_search_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    min_stars = Column(Integer, nullable=False)
    max_stars = Column(Integer, nullable=True)  # None = no upper bound
    language = Column(String(100), nullable=True)
    min_closed_issues = Column(Integer, default=0)
    max_results = Column(Integer, default=30)
    sort_by = Column(String(50), default="stars")
    results_count = Column(Integer, default=0)
    results_json = Column(Text, nullable=True)  # JSON array of repo summaries


class Issue(Base):
    """Found issues from scanning repositories"""
    __tablename__ = "issues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)

    # Issue info
    issue_url = Column(String(512), nullable=False, unique=True)
    issue_number = Column(Integer, nullable=False)
    issue_title = Column(String(512), nullable=False)
    issue_body = Column(Text, nullable=True)
    issue_state = Column(String(50), default="CLOSED")
    issue_created_at = Column(DateTime, nullable=True)

    # Base SHA (repo state when issue was created)
    base_sha = Column(String(64), nullable=True)

    # Linked PR info
    pr_number = Column(Integer, nullable=True)
    pr_title = Column(String(512), nullable=True)
    pr_url = Column(String(512), nullable=True)
    pr_files_changed = Column(Integer, default=0)
    pr_additions = Column(Integer, default=0)
    pr_deletions = Column(Integer, default=0)
    pr_merged_at = Column(DateTime, nullable=True)
    
    # Detailed file breakdown
    pr_python_files = Column(Integer, default=0)
    pr_python_additions = Column(Integer, default=0)
    pr_python_deletions = Column(Integer, default=0)
    pr_test_files = Column(Integer, default=0)
    pr_test_additions = Column(Integer, default=0)
    pr_test_deletions = Column(Integer, default=0)
    pr_doc_files = Column(Integer, default=0)
    pr_doc_additions = Column(Integer, default=0)
    pr_doc_deletions = Column(Integer, default=0)
    pr_other_files = Column(Integer, default=0)
    pr_lock_files_ignored = Column(Integer, default=0)

    # Dependency Analysis
    dependencies_json = Column(Text, nullable=True)
    usage_analysis_json = Column(Text, nullable=True)
    dependency_workflow_json = Column(Text, nullable=True)  # UV/import resolution workflow state

    scanned_at = Column(DateTime, default=datetime.utcnow)

    repository = relationship("Repository", back_populates="issues")
    tasks = relationship("Task", back_populates="issue")


class Task(Base):
    """A task – optionally linked to a scanned issue, or created standalone."""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    issue_id = Column(Integer, ForeignKey("issues.id"), nullable=True)
    local_path = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default="prep")  # prep, evaluating, complete

    # HFI session info
    hfi_session_id = Column(String(255), nullable=True)
    trajectory_a_id = Column(String(255), nullable=True)
    trajectory_b_id = Column(String(255), nullable=True)

    # Step 1 checklist (JSON blob)
    prep_checklist = Column(JSON, default=dict)

    issue = relationship("Issue", back_populates="tasks")
    iterations = relationship("Iteration", back_populates="task")


class Iteration(Base):
    """An evaluation iteration for a task"""
    __tablename__ = "iterations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    iteration_num = Column(Integer, nullable=False)

    # Input: what was pasted
    issue_context = Column(Text, nullable=True)
    model_a_response = Column(Text, nullable=True)
    model_b_response = Column(Text, nullable=True)

    # Output: AI evaluation (raw text from external AI)
    ai_evaluation = Column(Text, nullable=True)
    next_instruction = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    task = relationship("Task", back_populates="iterations")


class LabelingSubmission(Base):
    """Structured evaluation submission for a model comparison iteration."""
    __tablename__ = "labeling_submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    iteration_id = Column(Integer, ForeignKey("iterations.id"), nullable=False)
    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    user_prompt = Column(Text, nullable=True)

    model_a_pros = Column(Text, nullable=True)
    model_a_cons = Column(Text, nullable=True)
    model_b_pros = Column(Text, nullable=True)
    model_b_cons = Column(Text, nullable=True)

    overall_preference = Column(String(1), nullable=True)  # "A" or "B"
    overall_justification = Column(Text, nullable=True)

    axis_evaluations = Column(JSON, nullable=True)

    next_prompt = Column(Text, nullable=True)

    status = Column(String(20), default="pending")  # pending, approved, rejected
    is_final = Column(Integer, default=0)  # 1 = final iteration (no next prompt needed)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaskKeyRequest(Base):
    """Request for an HFI auth key to start a new task."""
    __tablename__ = "task_key_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    project_name = Column(String(255), nullable=False)
    auth_key = Column(Text, nullable=False)
    response_key = Column(Text, nullable=True)
    status = Column(String(20), default="pending")  # pending, approved, rejected
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class TaskSubmission(Base):
    """User submits a completed task with tar file, issue link, and description.
    Approver responds with a tar file, commit SHA, issue link, and repo link."""
    __tablename__ = "task_submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    issue_url = Column(Text, nullable=False)
    issue_description = Column(Text, nullable=False)
    tar_file_path = Column(Text, nullable=False)
    status = Column(String(20), default="pending")  # pending, approved, rejected
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    response_tar_file_path = Column(Text, nullable=True)
    response_commit_sha = Column(Text, nullable=True)
    response_issue_link = Column(Text, nullable=True)
    response_repo_link = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class FinalSubmission(Base):
    """Final task submission: tar file, Anthropic ID, app version, base SHA, repo/issue links, Dockerfile."""
    __tablename__ = "final_submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    tar_file_path = Column(Text, nullable=False)
    anthropic_id = Column(String(255), nullable=False)
    app_version = Column(String(100), nullable=False)
    base_sha = Column(Text, nullable=False)
    repo_link = Column(Text, nullable=False)
    issue_link = Column(Text, nullable=False)
    dockerfile = Column(Text, nullable=True)
    status = Column(String(20), default="pending")
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# =========================
# Database Initialization
# =========================

def _pg_type(sql_type: str) -> str:
    """Map SQLite-style types to Postgres equivalents when on Postgres."""
    if "sqlite" in DATABASE_URL:
        return sql_type
    mapping = {"DATETIME": "TIMESTAMP", "INTEGER": "INTEGER"}
    upper = sql_type.upper()
    for src, dst in mapping.items():
        if upper.startswith(src) and src != dst:
            return dst + upper[len(src):]
    return sql_type


def _add_columns_if_missing(inspector, table: str, columns: list[tuple[str, str]]):
    """Add columns to *table* if they don't exist yet, adapting types for Postgres."""
    if table not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns(table)}
    with engine.connect() as conn:
        for col_name, col_type in columns:
            if col_name not in existing:
                conn.execute(
                    __import__("sqlalchemy").text(
                        f"ALTER TABLE {table} ADD COLUMN {col_name} {_pg_type(col_type)}"
                    )
                )
                conn.commit()


def _migrate_db():
    """Add missing columns to existing tables (simple migration)."""
    from sqlalchemy import inspect

    inspector = inspect(engine)

    _add_columns_if_missing(inspector, "repositories", [
        ("saved_dockerfile", "TEXT"),
        ("saved_dependencies", "TEXT"),
        ("saved_readme_section", "TEXT"),
        ("setup_notes", "TEXT"),
        ("topics", "TEXT"),
        ("has_discussions", "INTEGER DEFAULT 0"),
        ("primary_language", "VARCHAR(100)"),
        ("stars_count", "INTEGER DEFAULT 0"),
        ("forks_count", "INTEGER DEFAULT 0"),
    ])

    _add_columns_if_missing(inspector, "issues", [
        ("pr_python_files", "INTEGER DEFAULT 0"),
        ("pr_python_additions", "INTEGER DEFAULT 0"),
        ("pr_python_deletions", "INTEGER DEFAULT 0"),
        ("pr_test_files", "INTEGER DEFAULT 0"),
        ("pr_test_additions", "INTEGER DEFAULT 0"),
        ("pr_test_deletions", "INTEGER DEFAULT 0"),
        ("pr_doc_files", "INTEGER DEFAULT 0"),
        ("pr_doc_additions", "INTEGER DEFAULT 0"),
        ("pr_doc_deletions", "INTEGER DEFAULT 0"),
        ("pr_other_files", "INTEGER DEFAULT 0"),
        ("pr_lock_files_ignored", "INTEGER DEFAULT 0"),
        ("dependencies_json", "TEXT"),
        ("usage_analysis_json", "TEXT"),
        ("dependency_workflow_json", "TEXT"),
    ])

    _add_columns_if_missing(inspector, "users", [
        ("username", "VARCHAR(100)"),
        ("password_hash", "VARCHAR(256) DEFAULT 'supabase_auth'"),
        ("email", "VARCHAR(255)"),
        ("supabase_uid", "VARCHAR(255)"),
        ("github_token", "VARCHAR(255)"),
        ("created_at", "DATETIME"),
        ("last_login", "DATETIME"),
        ("last_active_at", "DATETIME"),
        ("last_seen_ip", "VARCHAR(64)"),
        ("last_seen_device", "VARCHAR(128)"),
        ("last_seen_country", "VARCHAR(100)"),
        ("last_seen_location", "VARCHAR(255)"),
        ("is_admin", "INTEGER DEFAULT 0"),
        ("is_verified", "INTEGER DEFAULT 0"),
        ("role", "VARCHAR(50) DEFAULT 'user'"),
        ("issues_submitted", "INTEGER DEFAULT 0"),
        ("issues_reserved", "INTEGER DEFAULT 0"),
        ("issues_completed", "INTEGER DEFAULT 0"),
        ("max_ip_addresses", "INTEGER"),
        ("max_device_fingerprints", "INTEGER"),
        ("allowed_countries", "TEXT"),
        ("allowed_locations", "TEXT"),
    ])

    _add_columns_if_missing(inspector, "good_issues", [
        ("is_public", "INTEGER DEFAULT 1"),
    ])

    _add_columns_if_missing(inspector, "task_key_requests", [
        ("response_key", "TEXT"),
    ])

    _add_columns_if_missing(inspector, "task_submissions", [
        ("response_tar_file_path", "TEXT"),
        ("response_commit_sha", "TEXT"),
        ("response_issue_link", "TEXT"),
        ("response_repo_link", "TEXT"),
    ])

    _add_columns_if_missing(inspector, "labeling_submissions", [
        ("is_final", "INTEGER DEFAULT 0"),
    ])


def _create_admin_user():
    """Create the admin user if it doesn't exist."""
    session = SessionLocal()
    try:
        admin = session.query(User).filter_by(username="rebumex").first()
        if not admin:
            admin = User(
                username="rebumex",
                password_hash=hashlib.sha256("Bonsa@4213".encode()).hexdigest(),
                email="rebumatadele4@gmail.com",
                is_admin=1,
                is_verified=1,
                role="admin",
            )
            session.add(admin)
            session.commit()
        elif not admin.role or admin.role == "user":
            admin.role = "admin"
            session.commit()
    finally:
        session.close()


def init_db(force: bool = False):
    """
    Initialize database schema and run migrations.

    This runs once per process by default so app startup executes migrations
    deterministically while repeated page-level calls stay lightweight.
    """
    global _DB_INITIALIZED

    if _DB_INITIALIZED and not force:
        return

    with _DB_INIT_LOCK:
        if _DB_INITIALIZED and not force:
            return
        # First create any new tables
        Base.metadata.create_all(engine)
        # Then migrate existing tables
        _migrate_db()
        # Create admin user
        _create_admin_user()
        _DB_INITIALIZED = True


def get_session():
    """Get a new database session."""
    return SessionLocal()


# =========================
# User Access / Activity Helpers
# =========================

def _normalize_access_context(access_context: Optional[dict]) -> dict[str, Optional[str]]:
    """Normalize request context values into a stable shape."""
    raw = access_context or {}

    def _clean(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    country = _clean(raw.get("country"))
    location = _clean(raw.get("location"))
    city = _clean(raw.get("city"))
    region = _clean(raw.get("region"))
    if not location:
        parts = [part for part in [city, region, country] if part]
        location = ", ".join(parts) if parts else None

    return {
        "ip_address": _clean(raw.get("ip_address") or raw.get("ip")),
        "device_fingerprint": _clean(raw.get("device_fingerprint") or raw.get("device")),
        "mac_address": _clean(raw.get("mac_address") or raw.get("mac")),
        "country": country,
        "location": location,
        "user_agent": _clean(raw.get("user_agent")),
    }


def _load_json_list(value: Optional[str]) -> list[str]:
    if not value:
        return []
    try:
        payload = json.loads(value)
        if isinstance(payload, list):
            return [str(item).strip() for item in payload if str(item).strip()]
    except Exception:
        pass
    return []


def _dump_json_list(values: Optional[list[str]]) -> Optional[str]:
    if values is None:
        return None
    clean = [str(v).strip() for v in values if str(v).strip()]
    return json.dumps(clean) if clean else None


def _extract_issue_number(issue_url: Optional[str]) -> Optional[int]:
    if not issue_url:
        return None
    import re

    match = re.search(r"/issues/(\d+)", issue_url)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _record_user_activity_in_session(
    session,
    user_id: Optional[int],
    action: str,
    feature: str = None,
    repo_full_name: str = None,
    issue_url: str = None,
    issue_number: Optional[int] = None,
    task_id: Optional[int] = None,
    metadata: Optional[dict] = None,
    access_context: Optional[dict] = None,
    created_at: Optional[datetime] = None,
) -> UserActivity:
    """Create an activity row in an already-open session."""
    context = _normalize_access_context(access_context)
    username = None
    if user_id:
        user = session.query(User).filter_by(id=user_id).first()
        if user:
            username = user.username

    activity = UserActivity(
        user_id=user_id,
        username_snapshot=username,
        action=action,
        feature=feature,
        repo_full_name=repo_full_name,
        issue_url=issue_url,
        issue_number=issue_number if issue_number is not None else _extract_issue_number(issue_url),
        task_id=task_id,
        ip_address=context.get("ip_address"),
        device_fingerprint=context.get("device_fingerprint"),
        mac_address=context.get("mac_address"),
        country=context.get("country"),
        location=context.get("location"),
        metadata_json=json.dumps(metadata) if metadata else None,
        created_at=created_at or datetime.utcnow(),
    )
    session.add(activity)
    return activity


def record_user_activity(
    user_id: Optional[int],
    action: str,
    feature: str = None,
    repo_full_name: str = None,
    issue_url: str = None,
    issue_number: Optional[int] = None,
    task_id: Optional[int] = None,
    metadata: Optional[dict] = None,
    access_context: Optional[dict] = None,
    created_at: Optional[datetime] = None,
) -> Optional[UserActivity]:
    """Persist a user activity event."""
    session = get_session()
    try:
        activity = _record_user_activity_in_session(
            session=session,
            user_id=user_id,
            action=action,
            feature=feature,
            repo_full_name=repo_full_name,
            issue_url=issue_url,
            issue_number=issue_number,
            task_id=task_id,
            metadata=metadata,
            access_context=access_context,
            created_at=created_at,
        )
        session.commit()
        session.refresh(activity)
        return activity
    finally:
        session.close()


def touch_user_session(
    user_id: int,
    session_key: str,
    access_context: Optional[dict] = None,
    signed_in: bool = False,
) -> bool:
    """Upsert session heartbeat and refresh last-seen markers."""
    if not session_key:
        return False

    session = get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return False

        context = _normalize_access_context(access_context)
        now = datetime.utcnow()

        entry = session.query(UserSession).filter_by(user_id=user_id, session_key=session_key).first()
        if not entry:
            entry = UserSession(
                user_id=user_id,
                session_key=session_key,
                signed_in_at=now,
                last_active_at=now,
                is_active=1,
            )
            session.add(entry)
        elif signed_in:
            entry.signed_in_at = now

        entry.last_active_at = now
        entry.signed_out_at = None
        entry.is_active = 1
        entry.ip_address = context.get("ip_address")
        entry.device_fingerprint = context.get("device_fingerprint")
        entry.mac_address = context.get("mac_address")
        entry.country = context.get("country")
        entry.location = context.get("location")
        entry.user_agent = context.get("user_agent")

        user.last_active_at = now
        user.last_seen_ip = context.get("ip_address")
        user.last_seen_device = context.get("device_fingerprint")
        user.last_seen_country = context.get("country")
        user.last_seen_location = context.get("location")

        session.commit()
        return True
    finally:
        session.close()


def close_user_session(
    user_id: int,
    session_key: str,
    access_context: Optional[dict] = None,
) -> bool:
    """Mark a session as signed out."""
    if not session_key:
        return False

    session = get_session()
    try:
        entry = session.query(UserSession).filter_by(user_id=user_id, session_key=session_key).first()
        if not entry:
            return False

        now = datetime.utcnow()
        context = _normalize_access_context(access_context)

        entry.is_active = 0
        entry.signed_out_at = now
        entry.last_active_at = now

        if context.get("ip_address"):
            entry.ip_address = context.get("ip_address")
        if context.get("device_fingerprint"):
            entry.device_fingerprint = context.get("device_fingerprint")
        if context.get("mac_address"):
            entry.mac_address = context.get("mac_address")
        if context.get("country"):
            entry.country = context.get("country")
        if context.get("location"):
            entry.location = context.get("location")
        if context.get("user_agent"):
            entry.user_agent = context.get("user_agent")

        session.commit()
        return True
    finally:
        session.close()


def set_user_access_policy(
    user_id: int,
    max_ip_addresses: Optional[int] = None,
    max_device_fingerprints: Optional[int] = None,
    allowed_countries: Optional[list[str]] = None,
    allowed_locations: Optional[list[str]] = None,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> bool:
    """Set per-user access limits and allow-lists."""
    session = get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return False

        user.max_ip_addresses = max_ip_addresses if max_ip_addresses and max_ip_addresses > 0 else None
        user.max_device_fingerprints = (
            max_device_fingerprints if max_device_fingerprints and max_device_fingerprints > 0 else None
        )
        user.allowed_countries = _dump_json_list(allowed_countries)
        user.allowed_locations = _dump_json_list(allowed_locations)

        if actor_user_id:
            _record_user_activity_in_session(
                session=session,
                user_id=actor_user_id,
                action="user_access_policy_updated",
                feature="Admin",
                metadata={
                    "target_user_id": user_id,
                    "max_ip_addresses": user.max_ip_addresses,
                    "max_device_fingerprints": user.max_device_fingerprints,
                    "allowed_countries": _load_json_list(user.allowed_countries),
                    "allowed_locations": _load_json_list(user.allowed_locations),
                },
                access_context=access_context,
            )

        session.commit()
        return True
    finally:
        session.close()


def validate_user_access(
    user_id: int,
    access_context: Optional[dict] = None,
    session_key: Optional[str] = None,
) -> tuple[bool, str]:
    """Validate if a user can sign in from the current IP/device/location."""
    session = get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return False, "User not found."

        context = _normalize_access_context(access_context)
        country = (context.get("country") or "").strip().lower()
        location = (context.get("location") or "").strip().lower()
        current_ip = context.get("ip_address")
        current_device = context.get("device_fingerprint")

        allowed_countries = [c.lower() for c in _load_json_list(user.allowed_countries)]
        if allowed_countries:
            if not country:
                return False, "Sign-in blocked: country could not be determined."
            if not any(
                country == allowed or country.startswith(allowed) or allowed.startswith(country)
                for allowed in allowed_countries
            ):
                return False, "Sign-in blocked: country is not allowed."

        allowed_locations = [loc.lower() for loc in _load_json_list(user.allowed_locations)]
        if allowed_locations:
            if not location:
                return False, "Sign-in blocked: location could not be determined."
            if not any(allowed in location for allowed in allowed_locations):
                return False, "Sign-in blocked: location is not allowed."

        sessions_q = session.query(UserSession).filter_by(user_id=user_id)
        known_ips = {row[0] for row in sessions_q.with_entities(UserSession.ip_address).all() if row[0]}
        known_devices = {
            row[0] for row in sessions_q.with_entities(UserSession.device_fingerprint).all() if row[0]
        }

        if current_ip:
            known_ips.add(current_ip)
        if current_device:
            known_devices.add(current_device)

        if user.max_ip_addresses and len(known_ips) > user.max_ip_addresses:
            return (
                False,
                f"Sign-in blocked: max distinct IPs exceeded ({len(known_ips)}/{user.max_ip_addresses}).",
            )

        if user.max_device_fingerprints and len(known_devices) > user.max_device_fingerprints:
            return (
                False,
                (
                    "Sign-in blocked: max distinct devices exceeded "
                    f"({len(known_devices)}/{user.max_device_fingerprints})."
                ),
            )

        return True, ""
    finally:
        session.close()


def get_known_access_countries() -> list[str]:
    """Get all known countries seen in session/activity data."""
    session = get_session()
    try:
        session_countries = {
            row[0].strip()
            for row in session.query(UserSession.country).all()
            if row[0] and row[0].strip()
        }
        activity_countries = {
            row[0].strip()
            for row in session.query(UserActivity.country).all()
            if row[0] and row[0].strip()
        }
        return sorted(session_countries | activity_countries)
    finally:
        session.close()


def get_user_access_overview(
    user_id: Optional[int] = None,
    country: Optional[str] = None,
    location_query: Optional[str] = None,
    active_within_minutes: int = 15,
) -> list[dict]:
    """Return per-user access visibility including distinct IP/device counts."""
    session = get_session()
    try:
        users_q = session.query(User)
        if user_id:
            users_q = users_q.filter_by(id=user_id)
        users = users_q.order_by(User.username.asc()).all()

        country_filter = (country or "").strip().lower()
        location_filter = (location_query or "").strip().lower()
        active_cutoff = datetime.utcnow() - timedelta(minutes=max(1, active_within_minutes))
        rows = []

        for user in users:
            sessions_q = session.query(UserSession).filter_by(user_id=user.id)
            session_rows = sessions_q.order_by(UserSession.last_active_at.desc()).all()

            if country_filter:
                session_rows = [s for s in session_rows if (s.country or "").strip().lower() == country_filter]
            if location_filter:
                session_rows = [s for s in session_rows if location_filter in (s.location or "").strip().lower()]

            unique_ips = sorted({s.ip_address for s in session_rows if s.ip_address})
            unique_devices = sorted({s.device_fingerprint for s in session_rows if s.device_fingerprint})
            unique_macs = sorted({s.mac_address for s in session_rows if s.mac_address})

            active_sessions = sum(
                1
                for s in session_rows
                if s.is_active and s.last_active_at and s.last_active_at >= active_cutoff
            )

            rows.append(
                {
                    "user_id": user.id,
                    "username": user.username,
                    "last_login": user.last_login,
                    "last_active_at": user.last_active_at,
                    "last_seen_ip": user.last_seen_ip,
                    "last_seen_device": user.last_seen_device,
                    "last_seen_country": user.last_seen_country,
                    "last_seen_location": user.last_seen_location,
                    "unique_ip_count": len(unique_ips),
                    "unique_device_count": len(unique_devices),
                    "unique_mac_count": len(unique_macs),
                    "unique_ips": unique_ips,
                    "unique_devices": unique_devices,
                    "unique_macs": unique_macs,
                    "max_ip_addresses": user.max_ip_addresses,
                    "max_device_fingerprints": user.max_device_fingerprints,
                    "allowed_countries": _load_json_list(user.allowed_countries),
                    "allowed_locations": _load_json_list(user.allowed_locations),
                    "active_sessions": active_sessions,
                }
            )

        rows.sort(
            key=lambda row: (
                row["last_active_at"] or datetime.min,
                row["last_login"] or datetime.min,
            ),
            reverse=True,
        )
        return rows
    finally:
        session.close()


def get_user_address_history(
    user_id: Optional[int] = None,
    country: Optional[str] = None,
    location_query: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[dict], int]:
    """Paginated user session/address history."""
    session = get_session()
    try:
        query = session.query(UserSession, User.username).join(User, UserSession.user_id == User.id)

        if user_id:
            query = query.filter(UserSession.user_id == user_id)
        if country:
            query = query.filter(UserSession.country.ilike(country.strip()))
        if location_query:
            query = query.filter(UserSession.location.ilike(f"%{location_query.strip()}%"))

        total = query.count()
        page = max(1, page)
        page_size = max(1, page_size)
        rows = (
            query.order_by(UserSession.last_active_at.desc(), UserSession.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        items = []
        for row, username in rows:
            items.append(
                {
                    "session_id": row.id,
                    "user_id": row.user_id,
                    "username": username,
                    "session_key": row.session_key,
                    "ip_address": row.ip_address,
                    "device_fingerprint": row.device_fingerprint,
                    "mac_address": row.mac_address,
                    "country": row.country,
                    "location": row.location,
                    "signed_in_at": row.signed_in_at,
                    "last_active_at": row.last_active_at,
                    "signed_out_at": row.signed_out_at,
                    "is_active": bool(row.is_active),
                }
            )
        return items, total
    finally:
        session.close()


def get_user_activity_history(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    feature: Optional[str] = None,
    country: Optional[str] = None,
    location_query: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    """Paginated activity audit log."""
    session = get_session()
    try:
        query = session.query(UserActivity)

        if user_id:
            query = query.filter(UserActivity.user_id == user_id)
        if action:
            query = query.filter(UserActivity.action.ilike(f"%{action.strip()}%"))
        if feature:
            query = query.filter(UserActivity.feature.ilike(f"%{feature.strip()}%"))
        if country:
            query = query.filter(UserActivity.country.ilike(f"%{country.strip()}%"))
        if location_query:
            query = query.filter(UserActivity.location.ilike(f"%{location_query.strip()}%"))

        total = query.count()
        page = max(1, page)
        page_size = max(1, page_size)
        rows = (
            query.order_by(UserActivity.created_at.desc(), UserActivity.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        items = []
        for row in rows:
            metadata = None
            if row.metadata_json:
                try:
                    metadata = json.loads(row.metadata_json)
                except Exception:
                    metadata = row.metadata_json
            items.append(
                {
                    "id": row.id,
                    "user_id": row.user_id,
                    "username": row.username_snapshot or "",
                    "action": row.action,
                    "feature": row.feature,
                    "repo_full_name": row.repo_full_name,
                    "issue_url": row.issue_url,
                    "issue_number": row.issue_number,
                    "task_id": row.task_id,
                    "ip_address": row.ip_address,
                    "device_fingerprint": row.device_fingerprint,
                    "mac_address": row.mac_address,
                    "country": row.country,
                    "location": row.location,
                    "metadata": metadata,
                    "created_at": row.created_at,
                }
            )
        return items, total
    finally:
        session.close()


def get_active_users(active_within_minutes: int = 15) -> list[dict]:
    """Users currently active within the provided heartbeat window."""
    session = get_session()
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=max(1, active_within_minutes))
        users = (
            session.query(User)
            .filter(User.last_active_at.is_not(None))
            .order_by(User.last_active_at.desc())
            .all()
        )

        rows = []
        for user in users:
            active_sessions = (
                session.query(UserSession)
                .filter(UserSession.user_id == user.id)
                .filter(UserSession.is_active == 1)
                .filter(UserSession.last_active_at >= cutoff)
                .count()
            )
            if not active_sessions and (not user.last_active_at or user.last_active_at < cutoff):
                continue

            rows.append(
                {
                    "user_id": user.id,
                    "username": user.username,
                    "last_active_at": user.last_active_at,
                    "last_login": user.last_login,
                    "last_seen_ip": user.last_seen_ip,
                    "last_seen_country": user.last_seen_country,
                    "last_seen_location": user.last_seen_location,
                    "active_sessions": active_sessions,
                }
            )
        return rows
    finally:
        session.close()


def get_feature_usage_stats(
    user_id: Optional[int] = None,
    limit_per_user: int = 5,
) -> list[dict]:
    """Most-used features by user based on activity log."""
    from sqlalchemy import func

    session = get_session()
    try:
        query = (
            session.query(
                UserActivity.user_id,
                UserActivity.username_snapshot,
                UserActivity.feature,
                func.count(UserActivity.id).label("usage_count"),
                func.max(UserActivity.created_at).label("last_used_at"),
            )
            .filter(UserActivity.feature.is_not(None))
            .group_by(UserActivity.user_id, UserActivity.username_snapshot, UserActivity.feature)
        )
        if user_id:
            query = query.filter(UserActivity.user_id == user_id)

        grouped: dict[tuple[int, str], list[dict]] = {}
        for uid, username, feature_name, usage_count, last_used_at in query.all():
            key = (uid or 0, username or "")
            grouped.setdefault(key, []).append(
                {
                    "user_id": uid,
                    "username": username or "",
                    "feature": feature_name or "",
                    "usage_count": int(usage_count or 0),
                    "last_used_at": last_used_at,
                }
            )

        rows = []
        for _, entries in grouped.items():
            entries.sort(key=lambda item: (item["usage_count"], item["last_used_at"] or datetime.min), reverse=True)
            rows.extend(entries[: max(1, limit_per_user)])

        rows.sort(key=lambda item: (item["username"], -item["usage_count"]))
        return rows
    finally:
        session.close()


def get_user_work_history(
    user_id: Optional[int] = None,
    repo_query: Optional[str] = None,
    issue_query: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    """Paginated repo/issue activity history by user."""
    session = get_session()
    try:
        query = session.query(UserActivity).filter(
            (UserActivity.repo_full_name.is_not(None)) | (UserActivity.issue_url.is_not(None))
        )

        if user_id:
            query = query.filter(UserActivity.user_id == user_id)
        if repo_query:
            query = query.filter(UserActivity.repo_full_name.ilike(f"%{repo_query.strip()}%"))
        if issue_query:
            needle = issue_query.strip()
            if needle.isdigit():
                query = query.filter(
                    (UserActivity.issue_url.ilike(f"%{needle}%"))
                    | (UserActivity.issue_number == int(needle))
                )
            else:
                query = query.filter(UserActivity.issue_url.ilike(f"%{needle}%"))

        total = query.count()
        page = max(1, page)
        page_size = max(1, page_size)
        rows = (
            query.order_by(UserActivity.created_at.desc(), UserActivity.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return [
            {
                "id": row.id,
                "user_id": row.user_id,
                "username": row.username_snapshot or "",
                "action": row.action,
                "feature": row.feature,
                "repo_full_name": row.repo_full_name,
                "issue_url": row.issue_url,
                "issue_number": row.issue_number,
                "task_id": row.task_id,
                "ip_address": row.ip_address,
                "country": row.country,
                "location": row.location,
                "created_at": row.created_at,
            }
            for row in rows
        ], total
    finally:
        session.close()


# =========================
# Repository CRUD
# =========================

def get_or_create_repository(owner: str, name: str, metadata: dict) -> Repository:
    """Get existing repository or create new one with metadata."""
    session = get_session()
    try:
        full_name = f"{owner}/{name}"
        repo = session.query(Repository).filter_by(full_name=full_name).first()
        if repo:
            # Update metadata
            repo.description = metadata.get("description")
            repo.stars = metadata.get("stars", 0)
            repo.forks = metadata.get("forks", 0)
            repo.language = metadata.get("language")
            repo.default_branch = metadata.get("default_branch", "main")
            repo.url = metadata.get("url")
            repo.updated_at = datetime.utcnow()
        else:
            repo = Repository(
                owner=owner,
                name=name,
                full_name=full_name,
                description=metadata.get("description"),
                stars=metadata.get("stars", 0),
                forks=metadata.get("forks", 0),
                language=metadata.get("language"),
                default_branch=metadata.get("default_branch", "main"),
                url=metadata.get("url"),
            )
            session.add(repo)
        session.commit()
        session.refresh(repo)
        return repo
    finally:
        session.close()


def get_repository_by_full_name(full_name: str) -> Optional[Repository]:
    """Get repository by full name (owner/repo)."""
    session = get_session()
    try:
        return session.query(Repository).filter_by(full_name=full_name).first()
    finally:
        session.close()


# =========================
# Issue CRUD
# =========================

def create_issue(repo_id: int, issue_data: dict) -> Issue:
    """Create a new issue record."""
    session = get_session()
    try:
        # Check if issue already exists
        existing = session.query(Issue).filter_by(issue_url=issue_data.get("issue_url", "")).first()
        if existing:
            return existing

        issue = Issue(
            repo_id=repo_id,
            issue_url=issue_data.get("issue_url", ""),
            issue_number=issue_data.get("issue_number", 0),
            issue_title=issue_data.get("issue_title", ""),
            issue_body=issue_data.get("issue_body"),
            issue_state=issue_data.get("issue_state", "CLOSED"),
            issue_created_at=issue_data.get("issue_created_at"),
            base_sha=issue_data.get("base_sha"),
            pr_number=issue_data.get("pr_number"),
            pr_title=issue_data.get("pr_title"),
            pr_url=issue_data.get("pr_url"),
            pr_files_changed=issue_data.get("pr_files_changed", 0),
            pr_additions=issue_data.get("pr_additions", 0),
            pr_deletions=issue_data.get("pr_deletions", 0),
            pr_merged_at=issue_data.get("pr_merged_at"),
            # File breakdown
            pr_python_files=issue_data.get("pr_python_files", 0),
            pr_python_additions=issue_data.get("pr_python_additions", 0),
            pr_python_deletions=issue_data.get("pr_python_deletions", 0),
            pr_test_files=issue_data.get("pr_test_files", 0),
            pr_test_additions=issue_data.get("pr_test_additions", 0),
            pr_test_deletions=issue_data.get("pr_test_deletions", 0),
            pr_doc_files=issue_data.get("pr_doc_files", 0),
            pr_doc_additions=issue_data.get("pr_doc_additions", 0),
            pr_doc_deletions=issue_data.get("pr_doc_deletions", 0),
            pr_other_files=issue_data.get("pr_other_files", 0),
            pr_lock_files_ignored=issue_data.get("pr_lock_files_ignored", 0),
        )
        session.add(issue)
        session.commit()
        session.refresh(issue)
        return issue
    finally:
        session.close()


def get_issues_by_repo(repo_id: int) -> list[Issue]:
    """Get all issues for a repository."""
    session = get_session()
    try:
        return session.query(Issue).filter_by(repo_id=repo_id).order_by(Issue.scanned_at.desc()).all()
    finally:
        session.close()


def get_issue_by_id(issue_id: int) -> Optional[Issue]:
    """Get issue by ID."""
    session = get_session()
    try:
        return session.query(Issue).filter_by(id=issue_id).first()
    finally:
        session.close()


def get_all_issues() -> list[Issue]:
    """Get all issues."""
    session = get_session()
    try:
        return session.query(Issue).order_by(Issue.scanned_at.desc()).all()
    finally:
        session.close()


def _issue_quality_score_from_row(
    pr_files_changed: int,
    pr_python_files: int,
    pr_python_additions: int,
    pr_python_deletions: int,
    pr_test_files: int,
) -> float:
    """Lightweight score used to rank cached issue history."""
    py_lines = (pr_python_additions or 0) + (pr_python_deletions or 0)
    score = 0.0
    score += min(60.0, float((pr_python_files or 0) * 12))
    score += min(45.0, float((pr_test_files or 0) * 9))
    score += min(40.0, py_lines / 8.0)
    score += min(25.0, float((pr_files_changed or 0) * 2))
    return round(score, 2)


def get_issue_suggestions_by_urls(issue_urls: list[str]) -> dict[str, dict]:
    """
    Return cached issue history for the given URLs in suggestion-compatible shape.
    Keys are issue URLs.
    """
    if not issue_urls:
        return {}

    session = get_session()
    try:
        result: dict[str, dict] = {}
        chunk_size = 900  # SQLite parameter safety margin.

        for idx in range(0, len(issue_urls), chunk_size):
            chunk = issue_urls[idx : idx + chunk_size]
            rows = (
                session.query(Issue, Repository)
                .join(Repository, Issue.repo_id == Repository.id)
                .filter(Issue.issue_url.in_(chunk))
                .all()
            )

            for issue, repo in rows:
                issue_url = issue.issue_url
                if not issue_url:
                    continue

                quality_score = _issue_quality_score_from_row(
                    pr_files_changed=issue.pr_files_changed or 0,
                    pr_python_files=issue.pr_python_files or 0,
                    pr_python_additions=issue.pr_python_additions or 0,
                    pr_python_deletions=issue.pr_python_deletions or 0,
                    pr_test_files=issue.pr_test_files or 0,
                )

                result[issue_url] = {
                    "owner": repo.owner,
                    "repo": repo.name,
                    "full_name": repo.full_name,
                    "issue_url": issue.issue_url,
                    "issue_number": issue.issue_number,
                    "issue_title": issue.issue_title,
                    "issue_body": issue.issue_body,
                    "issue_state": issue.issue_state,
                    "issue_created_at": issue.issue_created_at,
                    "base_sha": issue.base_sha,
                    "base_sha_source": "cached_history",
                    "pr_number": issue.pr_number,
                    "pr_title": issue.pr_title,
                    "pr_url": issue.pr_url,
                    "pr_files_changed": issue.pr_files_changed or 0,
                    "pr_additions": issue.pr_additions or 0,
                    "pr_deletions": issue.pr_deletions or 0,
                    "pr_merged_at": issue.pr_merged_at,
                    "pr_python_files": issue.pr_python_files or 0,
                    "pr_python_additions": issue.pr_python_additions or 0,
                    "pr_python_deletions": issue.pr_python_deletions or 0,
                    "pr_test_files": issue.pr_test_files or 0,
                    "pr_test_additions": issue.pr_test_additions or 0,
                    "pr_test_deletions": issue.pr_test_deletions or 0,
                    "pr_doc_files": issue.pr_doc_files or 0,
                    "pr_doc_additions": issue.pr_doc_additions or 0,
                    "pr_doc_deletions": issue.pr_doc_deletions or 0,
                    "pr_other_files": issue.pr_other_files or 0,
                    "pr_lock_files_ignored": issue.pr_lock_files_ignored or 0,
                    "linked_merged_pr_count": 1,
                    "repo_has_tests": None,
                    "repo_test_indicators": [],
                    "quality_score": quality_score,
                    "from_history": True,
                    "history_cached_at": issue.scanned_at,
                }
        return result
    finally:
        session.close()


# =========================
# Task CRUD
# =========================

def create_task(
    name: str,
    issue_id: Optional[int] = None,
    local_path: str = None,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> Task:
    """Create a task, optionally linked to a scanned issue."""
    session = get_session()
    try:
        task = Task(
            name=name,
            issue_id=issue_id,
            local_path=local_path,
            prep_checklist={},
        )
        session.add(task)
        session.flush()

        if actor_user_id:
            issue = session.query(Issue).filter_by(id=issue_id).first() if issue_id else None
            repo = session.query(Repository).filter_by(id=issue.repo_id).first() if issue else None
            _record_user_activity_in_session(
                session=session,
                user_id=actor_user_id,
                action="task_created",
                feature="Repo Preparation",
                repo_full_name=repo.full_name if repo else None,
                issue_url=issue.issue_url if issue else None,
                issue_number=issue.issue_number if issue else None,
                task_id=task.id,
                metadata={"task_name": name},
                access_context=access_context,
            )

        session.commit()
        session.refresh(task)
        return task
    finally:
        session.close()


def get_task_by_id(task_id: int) -> Optional[Task]:
    """Get task by ID."""
    session = get_session()
    try:
        return session.query(Task).filter_by(id=task_id).first()
    finally:
        session.close()


def get_all_tasks() -> list[Task]:
    """Get all tasks (eager-load issue so issue_url is available after session close)."""
    session = get_session()
    try:
        return (
            session.query(Task)
            .options(joinedload(Task.issue))
            .order_by(Task.created_at.desc())
            .all()
        )
    finally:
        session.close()


def update_task(
    task_id: int,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
    **kwargs,
) -> Optional[Task]:
    """Update task fields."""
    session = get_session()
    try:
        task = session.query(Task).filter_by(id=task_id).first()
        if task:
            changed = {}
            for key, value in kwargs.items():
                if hasattr(task, key):
                    changed[key] = value
                    setattr(task, key, value)

            if actor_user_id and changed:
                issue = session.query(Issue).filter_by(id=task.issue_id).first()
                repo = session.query(Repository).filter_by(id=issue.repo_id).first() if issue else None
                _record_user_activity_in_session(
                    session=session,
                    user_id=actor_user_id,
                    action="task_updated",
                    feature="Repo Preparation",
                    repo_full_name=repo.full_name if repo else None,
                    issue_url=issue.issue_url if issue else None,
                    issue_number=issue.issue_number if issue else None,
                    task_id=task.id,
                    metadata={"changes": changed},
                    access_context=access_context,
                )

            session.commit()
            session.refresh(task)
        return task
    finally:
        session.close()


def update_task_checklist(
    task_id: int,
    key: str,
    value: bool,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> Optional[Task]:
    """Update a specific checklist item for a task."""
    session = get_session()
    try:
        task = session.query(Task).filter_by(id=task_id).first()
        if task:
            # Copy to force SQLAlchemy JSON change tracking for repeated updates.
            checklist = dict(task.prep_checklist or {})
            checklist[key] = value
            task.prep_checklist = checklist

            if actor_user_id:
                issue = session.query(Issue).filter_by(id=task.issue_id).first()
                repo = session.query(Repository).filter_by(id=issue.repo_id).first() if issue else None
                _record_user_activity_in_session(
                    session=session,
                    user_id=actor_user_id,
                    action="task_checklist_updated",
                    feature="Repo Preparation",
                    repo_full_name=repo.full_name if repo else None,
                    issue_url=issue.issue_url if issue else None,
                    issue_number=issue.issue_number if issue else None,
                    task_id=task.id,
                    metadata={"item": key, "value": bool(value)},
                    access_context=access_context,
                )

            session.commit()
            session.refresh(task)
        return task
    finally:
        session.close()


def get_next_task_number() -> int:
    """Get the next task number for naming."""
    session = get_session()
    try:
        count = session.query(Task).count()
        return count + 1
    finally:
        session.close()


# =========================
# Iteration CRUD
# =========================

def create_iteration(
    task_id: int,
    iteration_num: int,
    issue_context: str = None,
    model_a_response: str = None,
    model_b_response: str = None,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> Iteration:
    """Create a new iteration for a task."""
    session = get_session()
    try:
        iteration = Iteration(
            task_id=task_id,
            iteration_num=iteration_num,
            issue_context=issue_context,
            model_a_response=model_a_response,
            model_b_response=model_b_response,
        )
        session.add(iteration)
        session.flush()

        if actor_user_id:
            task = session.query(Task).filter_by(id=task_id).first()
            issue = session.query(Issue).filter_by(id=task.issue_id).first() if task else None
            repo = session.query(Repository).filter_by(id=issue.repo_id).first() if issue else None
            _record_user_activity_in_session(
                session=session,
                user_id=actor_user_id,
                action="iteration_created",
                feature="Model Evaluation",
                repo_full_name=repo.full_name if repo else None,
                issue_url=issue.issue_url if issue else None,
                issue_number=issue.issue_number if issue else None,
                task_id=task.id if task else None,
                metadata={"iteration_num": iteration_num},
                access_context=access_context,
            )

        session.commit()
        session.refresh(iteration)
        return iteration
    finally:
        session.close()


def update_repo_setup(repo_id: int, dockerfile: str = None, deps: str = None, readme: str = None) -> bool:
    """Update repository setup metadata (Dockerfile, frozen deps, README)."""
    session = get_session()
    try:
        repo = session.query(Repository).filter_by(id=repo_id).first()
        if repo:
            if dockerfile is not None:
                repo.saved_dockerfile = dockerfile
            if deps is not None:
                repo.saved_dependencies = deps
            if readme is not None:
                repo.saved_readme_section = readme
            session.commit()
            return True
        return False
    finally:
        session.close()


def get_iterations_by_task(task_id: int) -> list[Iteration]:
    """Get all iterations for a task."""
    session = get_session()
    try:
        return session.query(Iteration).filter_by(task_id=task_id).order_by(Iteration.iteration_num).all()
    finally:
        session.close()


def get_iteration_by_id(iteration_id: int) -> Optional[Iteration]:
    """Get iteration by ID."""
    session = get_session()
    try:
        return session.query(Iteration).filter_by(id=iteration_id).first()
    finally:
        session.close()


def update_iteration(
    iteration_id: int,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
    **kwargs,
) -> Optional[Iteration]:
    """Update iteration fields."""
    session = get_session()
    try:
        iteration = session.query(Iteration).filter_by(id=iteration_id).first()
        if iteration:
            changed = {}
            for key, value in kwargs.items():
                if hasattr(iteration, key):
                    changed[key] = value
                    setattr(iteration, key, value)

            if actor_user_id and changed:
                task = session.query(Task).filter_by(id=iteration.task_id).first()
                issue = session.query(Issue).filter_by(id=task.issue_id).first() if task else None
                repo = session.query(Repository).filter_by(id=issue.repo_id).first() if issue else None
                _record_user_activity_in_session(
                    session=session,
                    user_id=actor_user_id,
                    action="iteration_updated",
                    feature="Model Evaluation",
                    repo_full_name=repo.full_name if repo else None,
                    issue_url=issue.issue_url if issue else None,
                    issue_number=issue.issue_number if issue else None,
                    task_id=task.id if task else None,
                    metadata={"changes": list(changed.keys())},
                    access_context=access_context,
                )

            session.commit()
            session.refresh(iteration)
        return iteration
    finally:
        session.close()


def get_next_iteration_num(task_id: int) -> int:
    """Get the next iteration number for a task."""
    session = get_session()
    try:
        count = session.query(Iteration).filter_by(task_id=task_id).count()
        return count + 1
    finally:
        session.close()


# =========================
# Repo History CRUD
# =========================

def save_repo_history(
    repo_id: int,
    task_id: int = None,
    dockerfile_content: str = None,
    dependencies_content: str = None,
    readme_section: str = None,
    python_version: str = None,
    notes: str = None,
) -> RepoHistory:
    """Save repo preparation history for reuse."""
    session = get_session()
    try:
        history = RepoHistory(
            repo_id=repo_id,
            task_id=task_id,
            dockerfile_content=dockerfile_content,
            dependencies_content=dependencies_content,
            readme_section=readme_section,
            python_version=python_version,
            notes=notes,
        )
        session.add(history)
        session.commit()
        session.refresh(history)
        return history
    finally:
        session.close()


def get_repo_history(repo_id: int) -> list[RepoHistory]:
    """Get all history entries for a repository."""
    session = get_session()
    try:
        return session.query(RepoHistory).filter_by(repo_id=repo_id).order_by(RepoHistory.created_at.desc()).all()
    finally:
        session.close()


def get_latest_repo_history(repo_id: int) -> Optional[RepoHistory]:
    """Get the most recent history entry for a repository."""
    session = get_session()
    try:
        return session.query(RepoHistory).filter_by(repo_id=repo_id).order_by(RepoHistory.created_at.desc()).first()
    finally:
        session.close()


def update_repo_saved_setup(
    repo_id: int,
    dockerfile: str = None,
    dependencies: str = None,
    readme_section: str = None,
    notes: str = None,
) -> Optional[Repository]:
    """Update the saved setup on a repository for quick reuse."""
    session = get_session()
    try:
        repo = session.query(Repository).filter_by(id=repo_id).first()
        if repo:
            if dockerfile is not None:
                repo.saved_dockerfile = dockerfile
            if dependencies is not None:
                repo.saved_dependencies = dependencies
            if readme_section is not None:
                repo.saved_readme_section = readme_section
            if notes is not None:
                repo.setup_notes = notes
            repo.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(repo)
        return repo
    finally:
        session.close()


# =========================
# Blacklist CRUD
# =========================

def add_to_blacklist(
    issue_url: str,
    reason: str = None,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> Optional[Blacklist]:
    """Add an issue URL to the blacklist."""
    import re
    session = get_session()
    try:
        # Check if already exists
        existing = session.query(Blacklist).filter_by(issue_url=issue_url).first()
        if existing:
            return existing
        
        # Parse owner/repo/issue from URL
        match = re.search(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)", issue_url)
        owner, repo, issue_num = None, None, None
        if match:
            owner, repo, issue_num = match.group(1), match.group(2), int(match.group(3))
        
        entry = Blacklist(
            issue_url=issue_url.strip(),
            owner=owner,
            repo=repo,
            issue_number=issue_num,
            reason=reason,
        )
        session.add(entry)
        session.flush()

        if actor_user_id:
            _record_user_activity_in_session(
                session=session,
                user_id=actor_user_id,
                action="blacklist_issue_added",
                feature="Blacklist",
                issue_url=entry.issue_url,
                issue_number=entry.issue_number,
                metadata={"reason": reason or ""},
                access_context=access_context,
            )

        session.commit()
        session.refresh(entry)
        return entry
    finally:
        session.close()


def add_bulk_to_blacklist(
    urls_text: str,
    reason: str = None,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> int:
    """Add multiple issue URLs (newline separated) to blacklist. Returns count added."""
    urls = [u.strip() for u in urls_text.strip().split("\n") if u.strip()]
    count = 0
    for url in urls:
        if "github.com" in url and "/issues/" in url:
            result = add_to_blacklist(
                url,
                reason,
                actor_user_id=actor_user_id,
                access_context=access_context,
            )
            if result:
                count += 1
    return count


def get_all_blacklist() -> list[Blacklist]:
    """Get all blacklisted issues."""
    session = get_session()
    try:
        return session.query(Blacklist).order_by(Blacklist.added_at.desc()).all()
    finally:
        session.close()


def get_blacklist_urls() -> set[str]:
    """Get set of all blacklisted issue URLs for quick lookup."""
    session = get_session()
    try:
        entries = session.query(Blacklist.issue_url).all()
        return {e[0] for e in entries}
    finally:
        session.close()


def is_blacklisted(issue_url: str) -> bool:
    """Check if an issue URL is blacklisted."""
    session = get_session()
    try:
        return session.query(Blacklist).filter_by(issue_url=issue_url).first() is not None
    finally:
        session.close()


def remove_from_blacklist(
    issue_url: str,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> bool:
    """Remove an issue from blacklist. Returns True if removed."""
    session = get_session()
    try:
        entry = session.query(Blacklist).filter_by(issue_url=issue_url).first()
        if entry:
            removed_issue_number = entry.issue_number
            session.delete(entry)

            if actor_user_id:
                _record_user_activity_in_session(
                    session=session,
                    user_id=actor_user_id,
                    action="blacklist_issue_removed",
                    feature="Blacklist",
                    issue_url=issue_url,
                    issue_number=removed_issue_number,
                    access_context=access_context,
                )

            session.commit()
            return True
        return False
    finally:
        session.close()


# =========================
# GitHub Token Pool CRUD
# =========================

def add_github_token(
    token: str,
    description: str = None,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> Optional[GitHubToken]:
    """Add a new GitHub token to the pool."""
    session = get_session()
    try:
        existing = session.query(GitHubToken).filter_by(token=token).first()
        if existing:
            return existing
        
        entry = GitHubToken(
            token=token.strip(),
            description=description,
        )
        session.add(entry)
        session.flush()

        if actor_user_id:
            _record_user_activity_in_session(
                session=session,
                user_id=actor_user_id,
                action="github_token_added",
                feature="Admin",
                metadata={"description": description or ""},
                access_context=access_context,
            )

        session.commit()
        session.refresh(entry)
        return entry
    finally:
        session.close()


def get_all_github_tokens(only_active: bool = True) -> list[GitHubToken]:
    """Get all GitHub tokens from the pool."""
    session = get_session()
    try:
        query = session.query(GitHubToken)
        if only_active:
            query = query.filter_by(is_active=1)
        return query.order_by(GitHubToken.added_at.desc()).all()
    finally:
        session.close()


def update_token_rate_limit(token_id: int, remaining: int, reset: datetime) -> bool:
    """Update rate limit info for a token."""
    session = get_session()
    try:
        token = session.query(GitHubToken).filter_by(id=token_id).first()
        if token:
            token.rate_limit_remaining = remaining
            token.rate_limit_reset = reset
            session.commit()
            return True
        return False
    finally:
        session.close()


def delete_github_token(
    token_id: int,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> bool:
    """Remove a token from the pool."""
    session = get_session()
    try:
        token = session.query(GitHubToken).filter_by(id=token_id).first()
        if token:
            session.delete(token)

            if actor_user_id:
                _record_user_activity_in_session(
                    session=session,
                    user_id=actor_user_id,
                    action="github_token_deleted",
                    feature="Admin",
                    metadata={"token_id": token_id, "description": token.description or ""},
                    access_context=access_context,
                )

            session.commit()
            return True
        return False
    finally:
        session.close()


def set_token_active_status(
    token_id: int,
    is_active: bool,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> bool:
    """Enable or disable a token."""
    session = get_session()
    try:
        token = session.query(GitHubToken).filter_by(id=token_id).first()
        if token:
            token.is_active = 1 if is_active else 0

            if actor_user_id:
                _record_user_activity_in_session(
                    session=session,
                    user_id=actor_user_id,
                    action="github_token_status_changed",
                    feature="Admin",
                    metadata={"token_id": token_id, "is_active": bool(is_active)},
                    access_context=access_context,
                )

            session.commit()
            return True
        return False
    finally:
        session.close()


def clear_blacklist() -> int:
    """Clear all blacklist entries. Returns count deleted."""
    session = get_session()
    try:
        count = session.query(Blacklist).count()
        session.query(Blacklist).delete()
        session.commit()
        return count
    finally:
        session.close()


# =========================
# Repo Blacklist CRUD
# =========================

def add_repo_to_blacklist(
    full_name: str,
    reason: str = None,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> Optional[BlacklistRepo]:
    """Add a repository to blacklist (all its issues will be skipped)."""
    session = get_session()
    try:
        existing = session.query(BlacklistRepo).filter_by(full_name=full_name).first()
        if existing:
            return existing
        
        parts = full_name.split("/")
        owner = parts[0] if len(parts) >= 1 else None
        repo = parts[1] if len(parts) >= 2 else None
        
        entry = BlacklistRepo(
            full_name=full_name.strip(),
            owner=owner,
            repo=repo,
            reason=reason,
        )
        session.add(entry)
        session.flush()

        if actor_user_id:
            _record_user_activity_in_session(
                session=session,
                user_id=actor_user_id,
                action="blacklist_repo_added",
                feature="Blacklist",
                repo_full_name=entry.full_name,
                metadata={"reason": reason or ""},
                access_context=access_context,
            )

        session.commit()
        session.refresh(entry)
        return entry
    finally:
        session.close()


def get_all_blacklisted_repos() -> list[BlacklistRepo]:
    """Get all blacklisted repositories."""
    session = get_session()
    try:
        return session.query(BlacklistRepo).order_by(BlacklistRepo.added_at.desc()).all()
    finally:
        session.close()


def get_blacklisted_repo_names() -> set[str]:
    """Get set of all blacklisted repo full names for quick lookup."""
    session = get_session()
    try:
        entries = session.query(BlacklistRepo.full_name).all()
        return {e[0] for e in entries}
    finally:
        session.close()


def is_repo_blacklisted(full_name: str) -> bool:
    """Check if a repository is blacklisted."""
    session = get_session()
    try:
        return session.query(BlacklistRepo).filter_by(full_name=full_name).first() is not None
    finally:
        session.close()


def remove_repo_from_blacklist(
    full_name: str,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> bool:
    """Remove a repo from blacklist. Returns True if removed."""
    session = get_session()
    try:
        entry = session.query(BlacklistRepo).filter_by(full_name=full_name).first()
        if entry:
            session.delete(entry)

            if actor_user_id:
                _record_user_activity_in_session(
                    session=session,
                    user_id=actor_user_id,
                    action="blacklist_repo_removed",
                    feature="Blacklist",
                    repo_full_name=full_name,
                    access_context=access_context,
                )

            session.commit()
            return True
        return False
    finally:
        session.close()


# =========================
# Repo Whitelist CRUD
# =========================

def add_repo_to_whitelist(
    full_name: str,
    reason: str = None,
    source: str = None,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> Optional[RepoWhitelist]:
    """Add a repository to whitelist (known good)."""
    session = get_session()
    try:
        normalized = (full_name or "").strip()
        if not normalized:
            return None

        existing = session.query(RepoWhitelist).filter_by(full_name=normalized).first()
        if existing:
            if reason is not None:
                existing.reason = reason
            if source is not None:
                existing.source = source
            session.commit()
            session.refresh(existing)
            return existing

        parts = normalized.split("/")
        owner = parts[0] if len(parts) >= 1 else None
        repo = parts[1] if len(parts) >= 2 else None

        entry = RepoWhitelist(
            full_name=normalized,
            owner=owner,
            repo=repo,
            reason=reason,
            source=source,
        )
        session.add(entry)
        session.flush()

        if actor_user_id:
            _record_user_activity_in_session(
                session=session,
                user_id=actor_user_id,
                action="whitelist_repo_added",
                feature="Repo Search",
                repo_full_name=entry.full_name,
                metadata={"reason": reason or "", "source": source or ""},
                access_context=access_context,
            )

        session.commit()
        session.refresh(entry)
        return entry
    finally:
        session.close()


def get_all_whitelisted_repos() -> list[RepoWhitelist]:
    """Get all whitelisted repositories."""
    session = get_session()
    try:
        return session.query(RepoWhitelist).order_by(RepoWhitelist.added_at.desc()).all()
    finally:
        session.close()


def get_whitelisted_repo_names() -> set[str]:
    """Get set of all whitelisted repo full names for quick lookup."""
    session = get_session()
    try:
        entries = session.query(RepoWhitelist.full_name).all()
        return {e[0] for e in entries}
    finally:
        session.close()


def is_repo_whitelisted(full_name: str) -> bool:
    """Check if a repository is whitelisted."""
    session = get_session()
    try:
        return session.query(RepoWhitelist).filter_by(full_name=full_name).first() is not None
    finally:
        session.close()


def remove_repo_from_whitelist(
    full_name: str,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> bool:
    """Remove a repo from whitelist. Returns True if removed."""
    session = get_session()
    try:
        normalized = (full_name or "").strip()
        entry = session.query(RepoWhitelist).filter_by(full_name=normalized).first()
        if entry:
            session.delete(entry)

            if actor_user_id:
                _record_user_activity_in_session(
                    session=session,
                    user_id=actor_user_id,
                    action="whitelist_repo_removed",
                    feature="Repo Search",
                    repo_full_name=normalized,
                    access_context=access_context,
                )

            session.commit()
            return True
        return False
    finally:
        session.close()


# =========================
# Data Management (CRUD for all tables)
# =========================

def delete_issue_by_id(issue_id: int) -> bool:
    """Delete an issue by ID."""
    session = get_session()
    try:
        issue = session.query(Issue).filter_by(id=issue_id).first()
        if issue:
            session.delete(issue)
            session.commit()
            return True
        return False
    finally:
        session.close()


def delete_task_by_id(task_id: int) -> bool:
    """Delete a task and its iterations by ID."""
    session = get_session()
    try:
        # Delete iterations first
        session.query(Iteration).filter_by(task_id=task_id).delete()
        task = session.query(Task).filter_by(id=task_id).first()
        if task:
            session.delete(task)
            session.commit()
            return True
        return False
    finally:
        session.close()


def delete_repository_by_id(repo_id: int) -> bool:
    """Delete a repository and all its issues by ID."""
    session = get_session()
    try:
        # Delete issues first
        session.query(Issue).filter_by(repo_id=repo_id).delete()
        repo = session.query(Repository).filter_by(id=repo_id).first()
        if repo:
            session.delete(repo)
            session.commit()
            return True
        return False
    finally:
        session.close()


def get_all_repositories() -> list[Repository]:
    """Get all repositories."""
    session = get_session()
    try:
        return session.query(Repository).order_by(Repository.updated_at.desc()).all()
    finally:
        session.close()


def get_scanned_repos_with_issue_counts(limit: int = 100):
    """Repos that have been scanned (have at least one issue), with issue count and last scanned_at.
    Returns list of (Repository, issue_count, last_scanned_at)."""
    from sqlalchemy import func
    session = get_session()
    try:
        subq = (
            session.query(
                Issue.repo_id,
                func.count(Issue.id).label("issue_count"),
                func.max(Issue.scanned_at).label("last_scanned_at"),
            )
            .group_by(Issue.repo_id)
        ).subquery()
        rows = (
            session.query(Repository, subq.c.issue_count, subq.c.last_scanned_at)
            .join(subq, Repository.id == subq.c.repo_id)
            .order_by(subq.c.last_scanned_at.desc())
            .limit(limit)
            .all()
        )
        return [(r, int(c), t) for r, c, t in rows]
    finally:
        session.close()


def save_repo_search_run(
    min_stars: int,
    max_stars: Optional[int],
    language: Optional[str],
    min_closed_issues: int,
    max_results: int,
    sort_by: str,
    results: list[dict],
) -> "RepoSearchRun":
    """Save a repo search run for history."""
    import json
    session = get_session()
    try:
        run = RepoSearchRun(
            min_stars=min_stars,
            max_stars=max_stars,
            language=language or None,
            min_closed_issues=min_closed_issues,
            max_results=max_results,
            sort_by=sort_by,
            results_count=len(results),
            results_json=json.dumps(results) if results else None,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return run
    finally:
        session.close()


def get_repo_search_run_history(limit: int = 50) -> list["RepoSearchRun"]:
    """Get past repo search runs, newest first."""
    session = get_session()
    try:
        return session.query(RepoSearchRun).order_by(RepoSearchRun.created_at.desc()).limit(limit).all()
    finally:
        session.close()


def get_all_issues() -> list[Issue]:
    """Get all issues."""
    session = get_session()
    try:
        return session.query(Issue).order_by(Issue.scanned_at.desc()).all()
    finally:
        session.close()


def clear_all_issues() -> int:
    """Clear all issues. Returns count deleted."""
    session = get_session()
    try:
        count = session.query(Issue).count()
        session.query(Issue).delete()
        session.commit()
        return count
    finally:
        session.close()


def clear_all_tasks() -> int:
    """Clear all tasks and iterations. Returns count deleted."""
    session = get_session()
    try:
        session.query(Iteration).delete()
        count = session.query(Task).count()
        session.query(Task).delete()
        session.commit()
        return count
    finally:
        session.close()


def clear_all_repositories() -> int:
    """Clear all repositories and their issues. Returns count deleted."""
    session = get_session()
    try:
        session.query(Issue).delete()
        count = session.query(Repository).count()
        session.query(Repository).delete()
        session.commit()
        return count
    finally:
        session.close()


# =========================
# User Auth CRUD
# =========================

def _hash_password(password: str) -> str:
    """Hash password with SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()


def _serialize_user_auth(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_admin": user.is_admin,
        "is_verified": user.is_verified,
        "last_login": user.last_login,
        "last_active_at": user.last_active_at,
    }


def create_user(
    username: str,
    password: str,
    email: str = None,
    is_admin: bool = False,
    is_verified: bool = False,
    access_context: Optional[dict] = None,
) -> Optional[dict]:
    """Create a new user. Returns dict with user info, None if username exists."""
    session = get_session()
    try:
        existing = session.query(User).filter_by(username=username).first()
        if existing:
            return None  # Username taken
        
        user = User(
            username=username,
            password_hash=_hash_password(password),
            email=email,
            is_admin=1 if is_admin else 0,
            is_verified=1 if is_verified else 0,
        )
        session.add(user)
        session.flush()

        if not is_admin:
            _record_user_activity_in_session(
                session=session,
                user_id=user.id,
                action="user_signup",
                feature="Auth",
                metadata={"email": email or ""},
                access_context=access_context,
            )

        session.commit()
        session.refresh(user)
        # Return dict to avoid DetachedInstanceError
        return _serialize_user_auth(user)
    finally:
        session.close()


def verify_user(
    user_id: int,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> bool:
    """Admin: Verify a user account."""
    session = get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if user:
            user.is_verified = 1

            if actor_user_id:
                _record_user_activity_in_session(
                    session=session,
                    user_id=actor_user_id,
                    action="user_verified",
                    feature="Admin",
                    metadata={"target_user_id": user_id, "target_username": user.username},
                    access_context=access_context,
                )

            session.commit()
            return True
        return False
    finally:
        session.close()


def unverify_user(
    user_id: int,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> bool:
    """Admin: Unverify a user account."""
    session = get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if user:
            user.is_verified = 0

            if actor_user_id:
                _record_user_activity_in_session(
                    session=session,
                    user_id=actor_user_id,
                    action="user_unverified",
                    feature="Admin",
                    metadata={"target_user_id": user_id, "target_username": user.username},
                    access_context=access_context,
                )

            session.commit()
            return True
        return False
    finally:
        session.close()


def get_pending_users() -> list[User]:
    """Get all users pending verification."""
    session = get_session()
    try:
        return session.query(User).filter_by(is_verified=0).order_by(User.created_at.desc()).all()
    finally:
        session.close()


def get_verified_users() -> list[User]:
    """Get all verified users."""
    session = get_session()
    try:
        return session.query(User).filter_by(is_verified=1).order_by(User.created_at.desc()).all()
    finally:
        session.close()


def delete_user(
    user_id: int,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> bool:
    """Delete a user account."""
    session = get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if user:
            deleted_name = user.username

            # Remove dependent telemetry rows first (no need to keep orphaned references).
            session.query(UserSession).filter_by(user_id=user_id).delete()
            session.query(UserActivity).filter_by(user_id=user_id).delete()

            session.delete(user)

            if actor_user_id:
                log_actor_id = actor_user_id if actor_user_id != user_id else None
                _record_user_activity_in_session(
                    session=session,
                    user_id=log_actor_id,
                    action="user_deleted",
                    feature="Admin",
                    metadata={"target_user_id": user_id, "target_username": deleted_name},
                    access_context=access_context,
                )

            session.commit()
            return True
        return False
    finally:
        session.close()


def authenticate_user(
    username: str,
    password: str,
    access_context: Optional[dict] = None,
    session_key: Optional[str] = None,
    detailed: bool = False,
) -> Optional[dict] | tuple[Optional[dict], Optional[str]]:
    """Authenticate user with optional access-control checks."""
    session = get_session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user or user.password_hash != _hash_password(password):
            if detailed:
                return None, "Invalid username or password."
            return None

        is_allowed, denial_reason = validate_user_access(
            user_id=user.id,
            access_context=access_context,
            session_key=session_key,
        )
        if not is_allowed:
            try:
                _record_user_activity_in_session(
                    session=session,
                    user_id=user.id,
                    action="sign_in_blocked",
                    feature="Auth",
                    metadata={"reason": denial_reason},
                    access_context=access_context,
                )
                session.commit()
            except Exception:
                session.rollback()
            if detailed:
                return None, denial_reason
            return None

        now = datetime.utcnow()
        context = _normalize_access_context(access_context)
        user.last_login = now
        user.last_active_at = now
        user.last_seen_ip = context.get("ip_address")
        user.last_seen_device = context.get("device_fingerprint")
        user.last_seen_country = context.get("country")
        user.last_seen_location = context.get("location")

        try:
            _record_user_activity_in_session(
                session=session,
                user_id=user.id,
                action="sign_in_success",
                feature="Auth",
                access_context=access_context,
            )
            session.commit()
        except Exception:
            session.rollback()
            # Login still succeeds; persistence may fail on read-only environments.

        if session_key:
            try:
                touch_user_session(
                    user_id=user.id,
                    session_key=session_key,
                    access_context=access_context,
                    signed_in=True,
                )
            except Exception:
                pass

        user_data = _serialize_user_auth(user)
        if detailed:
            return user_data, None
        return user_data
    finally:
        session.close()


def get_user_by_id(user_id: int) -> Optional[User]:
    """Get user by ID. Retries once on transient connection errors (e.g. server closed)."""
    for attempt in range(2):
        session = get_session()
        try:
            return session.query(User).filter_by(id=user_id).first()
        except OperationalError:
            if attempt == 0:
                continue
            raise
        finally:
            session.close()
    return None


def get_user_by_username(username: str) -> Optional[User]:
    """Get user by username."""
    session = get_session()
    try:
        return session.query(User).filter_by(username=username).first()
    finally:
        session.close()


def update_user_token(
    user_id: int,
    github_token: str,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> bool:
    """Update user's GitHub token."""
    session = get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if user:
            user.github_token = github_token

            actor = actor_user_id or user_id
            if actor:
                _record_user_activity_in_session(
                    session=session,
                    user_id=actor,
                    action="user_token_updated",
                    feature="Settings",
                    metadata={"target_user_id": user_id, "has_token": bool(github_token)},
                    access_context=access_context,
                )

            session.commit()
            return True
        return False
    finally:
        session.close()


def update_user_stats(user_id: int, submitted: int = 0, reserved: int = 0, completed: int = 0):
    """Increment user stats."""
    session = get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if user:
            user.issues_submitted += submitted
            user.issues_reserved += reserved
            user.issues_completed += completed
            session.commit()
    finally:
        session.close()


def get_all_users() -> list[User]:
    """Get all users."""
    session = get_session()
    try:
        return session.query(User).order_by(User.created_at.desc()).all()
    finally:
        session.close()


# =========================
# Good Issues CRUD
# =========================

def submit_good_issue(
    issue_url: str,
    submitted_by: int,
    issue_title: str = None,
    pr_url: str = None,
    base_sha: str = None,
    python_files: int = 0,
    test_files: int = 0,
    total_lines: int = 0,
    notes: str = None,
    is_public: bool = True,
    access_context: Optional[dict] = None,
) -> Optional[GoodIssue]:
    """Submit a good quality issue."""
    session = get_session()
    try:
        # Check if already exists
        existing = session.query(GoodIssue).filter_by(issue_url=issue_url).first()
        if existing:
            changed = False
            requested_visibility = 1 if is_public else 0
            if existing.submitted_by == submitted_by and int(existing.is_public or 0) != requested_visibility:
                existing.is_public = requested_visibility
                changed = True
            if notes and not existing.notes:
                existing.notes = notes
                changed = True
            if changed:
                session.commit()
                session.refresh(existing)
            return existing
        
        # Parse URL
        import re
        match = re.match(r"https://github\.com/([^/]+)/([^/]+)/issues/(\d+)", issue_url)
        owner, repo, issue_number = None, None, None
        if match:
            owner, repo, issue_number = match.group(1), match.group(2), int(match.group(3))
        
        # Parse PR URL
        pr_number = None
        if pr_url:
            pr_match = re.match(r"https://github\.com/[^/]+/[^/]+/pull/(\d+)", pr_url)
            if pr_match:
                pr_number = int(pr_match.group(1))
        
        issue = GoodIssue(
            issue_url=issue_url,
            owner=owner,
            repo=repo,
            issue_number=issue_number,
            issue_title=issue_title,
            pr_url=pr_url,
            pr_number=pr_number,
            base_sha=base_sha,
            python_files=python_files,
            test_files=test_files,
            total_lines=total_lines,
            submitted_by=submitted_by,
            notes=notes,
            is_public=1 if is_public else 0,
            status="available",
        )
        session.add(issue)
        session.flush()

        _record_user_activity_in_session(
            session=session,
            user_id=submitted_by,
            action="good_issue_submitted",
            feature="Good Issues",
            repo_full_name=f"{owner}/{repo}" if owner and repo else None,
            issue_url=issue_url,
            issue_number=issue_number,
            metadata={
                "python_files": python_files,
                "test_files": test_files,
                "total_lines": total_lines,
                "is_public": bool(is_public),
            },
            access_context=access_context,
        )

        session.commit()
        
        # Update user stats
        update_user_stats(submitted_by, submitted=1)
        
        session.refresh(issue)
        return issue
    finally:
        session.close()


def get_all_good_issues(
    public_only: bool = False,
    submitted_by: Optional[int] = None,
) -> list[GoodIssue]:
    """Get good issues with optional visibility and submitter filters."""
    session = get_session()
    try:
        query = session.query(GoodIssue)
        if public_only:
            query = query.filter(GoodIssue.is_public == 1)
        if submitted_by is not None:
            query = query.filter(GoodIssue.submitted_by == submitted_by)
        return query.order_by(GoodIssue.submitted_at.desc()).all()
    finally:
        session.close()


def get_public_good_issues() -> list[GoodIssue]:
    """Get all public community good issues."""
    return get_all_good_issues(public_only=True)


def get_available_good_issues(public_only: bool = True) -> list[GoodIssue]:
    """Get all available (not reserved) good issues."""
    session = get_session()
    try:
        query = session.query(GoodIssue).filter_by(status="available")
        if public_only:
            query = query.filter(GoodIssue.is_public == 1)
        return query.order_by(GoodIssue.submitted_at.desc()).all()
    finally:
        session.close()


def set_good_issue_visibility(
    issue_id: int,
    is_public: bool,
    actor_user_id: int,
    access_context: Optional[dict] = None,
) -> bool:
    """Set issue visibility. Owner or admin can toggle personal/private vs community/public."""
    session = get_session()
    try:
        issue = session.query(GoodIssue).filter_by(id=issue_id).first()
        if not issue:
            return False

        actor = session.query(User).filter_by(id=actor_user_id).first()
        if not actor:
            return False
        if not actor.is_admin and issue.submitted_by != actor_user_id:
            return False

        new_value = 1 if is_public else 0
        if int(issue.is_public or 0) == new_value:
            return True

        issue.is_public = new_value
        _record_user_activity_in_session(
            session=session,
            user_id=actor_user_id,
            action="good_issue_visibility_updated",
            feature="Good Issues",
            repo_full_name=f"{issue.owner}/{issue.repo}" if issue.owner and issue.repo else None,
            issue_url=issue.issue_url,
            issue_number=issue.issue_number,
            metadata={"is_public": bool(new_value)},
            access_context=access_context,
        )
        session.commit()
        return True
    finally:
        session.close()


def reserve_good_issue(
    issue_id: int,
    user_id: int,
    access_context: Optional[dict] = None,
) -> bool:
    """Reserve an issue for a user."""
    session = get_session()
    try:
        issue = session.query(GoodIssue).filter_by(id=issue_id).first()
        if issue and issue.status == "available":
            if not issue.is_public and issue.submitted_by != user_id:
                return False
            issue.reserved_by = user_id
            issue.reserved_at = datetime.utcnow()
            issue.status = "reserved"

            _record_user_activity_in_session(
                session=session,
                user_id=user_id,
                action="good_issue_reserved",
                feature="Good Issues",
                repo_full_name=f"{issue.owner}/{issue.repo}" if issue.owner and issue.repo else None,
                issue_url=issue.issue_url,
                issue_number=issue.issue_number,
                task_id=None,
                access_context=access_context,
            )

            session.commit()
            
            # Update user stats
            update_user_stats(user_id, reserved=1)
            return True
        return False
    finally:
        session.close()


def release_good_issue(
    issue_id: int,
    user_id: int,
    access_context: Optional[dict] = None,
) -> bool:
    """Release a reserved issue (only by the user who reserved it)."""
    session = get_session()
    try:
        issue = session.query(GoodIssue).filter_by(id=issue_id).first()
        if issue and issue.reserved_by == user_id:
            issue.reserved_by = None
            issue.reserved_at = None
            issue.status = "available"

            _record_user_activity_in_session(
                session=session,
                user_id=user_id,
                action="good_issue_released",
                feature="Good Issues",
                repo_full_name=f"{issue.owner}/{issue.repo}" if issue.owner and issue.repo else None,
                issue_url=issue.issue_url,
                issue_number=issue.issue_number,
                access_context=access_context,
            )

            session.commit()
            return True
        return False
    finally:
        session.close()


def complete_good_issue(
    issue_id: int,
    user_id: int,
    access_context: Optional[dict] = None,
) -> bool:
    """Mark an issue as completed."""
    session = get_session()
    try:
        issue = session.query(GoodIssue).filter_by(id=issue_id).first()
        if issue and issue.reserved_by == user_id:
            issue.status = "completed"

            _record_user_activity_in_session(
                session=session,
                user_id=user_id,
                action="good_issue_completed",
                feature="Good Issues",
                repo_full_name=f"{issue.owner}/{issue.repo}" if issue.owner and issue.repo else None,
                issue_url=issue.issue_url,
                issue_number=issue.issue_number,
                access_context=access_context,
            )

            session.commit()
            
            # Update user stats
            update_user_stats(user_id, completed=1)
            return True
        return False
    finally:
        session.close()


def delete_good_issue(
    issue_id: int,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> bool:
    """Delete a good issue."""
    session = get_session()
    try:
        issue = session.query(GoodIssue).filter_by(id=issue_id).first()
        if issue:
            repo_full_name = f"{issue.owner}/{issue.repo}" if issue.owner and issue.repo else None
            issue_url = issue.issue_url
            issue_number = issue.issue_number
            session.delete(issue)

            if actor_user_id:
                _record_user_activity_in_session(
                    session=session,
                    user_id=actor_user_id,
                    action="good_issue_deleted",
                    feature="Good Issues",
                    repo_full_name=repo_full_name,
                    issue_url=issue_url,
                    issue_number=issue_number,
                    access_context=access_context,
                )

            session.commit()
            return True
        return False
    finally:
        session.close()


def get_user_reserved_issues(user_id: int) -> list[GoodIssue]:
    """Get issues reserved by a user."""
    session = get_session()
    try:
        return session.query(GoodIssue).filter_by(reserved_by=user_id).all()
    finally:
        session.close()


# =========================
# Role Management CRUD
# =========================

def set_user_role(user_id: int, role: str) -> Optional[User]:
    """Set a user's role (user, admin, role_manager). role_manager = manager (can approve keys/submissions)."""
    session = get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if user:
            user.role = role
            if role == "admin":
                user.is_admin = 1
            else:
                user.is_admin = 0
            session.commit()
            session.refresh(user)
        return user
    finally:
        session.close()


def get_role_managers() -> list[User]:
    """Get all users with role_manager role."""
    session = get_session()
    try:
        return session.query(User).filter(
            (User.role == "role_manager") | (User.role == "admin")
        ).all()
    finally:
        session.close()


def can_approve(user: User) -> bool:
    """Check if a user can approve task key requests, step 1 task submissions, and final submissions."""
    if not user:
        return False
    return user.username == "rebumex" or user.role in ("admin", "role_manager")


def get_user_by_supabase_uid(uid: str) -> Optional[User]:
    """Get a local user by their Supabase auth UID."""
    session = get_session()
    try:
        return session.query(User).filter_by(supabase_uid=uid).first()
    finally:
        session.close()


def create_user_from_supabase(
    username: str,
    email: str,
    supabase_uid: str,
    access_context: Optional[dict] = None,
) -> Optional[dict]:
    """Create a local user linked to a Supabase auth user."""
    session = get_session()
    try:
        existing = session.query(User).filter(
            (User.username == username) | (User.supabase_uid == supabase_uid)
        ).first()
        if existing:
            if existing.supabase_uid != supabase_uid:
                existing.supabase_uid = supabase_uid
                session.commit()
            return {"id": existing.id, "username": existing.username}

        user = User(
            username=username,
            password_hash="supabase_auth",
            email=email,
            supabase_uid=supabase_uid,
            is_verified=0,
            role="user",
        )
        session.add(user)
        session.commit()
        return {"id": user.id, "username": user.username}
    except Exception:
        session.rollback()
        return None
    finally:
        session.close()


# =========================
# Labeling Submission CRUD
# =========================

def create_labeling_submission(
    iteration_id: int,
    submitted_by: int,
    user_prompt: str = None,
    model_a_pros: str = None,
    model_a_cons: str = None,
    model_b_pros: str = None,
    model_b_cons: str = None,
    overall_preference: str = None,
    overall_justification: str = None,
    axis_evaluations: dict = None,
    next_prompt: str = None,
    is_final: bool = False,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
) -> LabelingSubmission:
    """Create a new labeling submission for an iteration."""
    session = get_session()
    try:
        submission = LabelingSubmission(
            iteration_id=iteration_id,
            submitted_by=submitted_by,
            user_prompt=user_prompt,
            model_a_pros=model_a_pros,
            model_a_cons=model_a_cons,
            model_b_pros=model_b_pros,
            model_b_cons=model_b_cons,
            overall_preference=overall_preference,
            overall_justification=overall_justification,
            axis_evaluations=axis_evaluations,
            next_prompt=next_prompt,
            is_final=1 if is_final else 0,
            status="pending",
        )
        session.add(submission)
        session.flush()

        if actor_user_id:
            _record_user_activity_in_session(
                session=session,
                user_id=actor_user_id,
                action="labeling_submitted",
                feature="Labeling",
                metadata={"iteration_id": iteration_id, "preference": overall_preference},
                access_context=access_context,
            )

        session.commit()
        session.refresh(submission)
        return submission
    finally:
        session.close()


def update_labeling_submission(
    submission_id: int,
    actor_user_id: Optional[int] = None,
    access_context: Optional[dict] = None,
    **kwargs,
) -> Optional[LabelingSubmission]:
    """Update a labeling submission."""
    session = get_session()
    try:
        sub = session.query(LabelingSubmission).filter_by(id=submission_id).first()
        if sub:
            for key, value in kwargs.items():
                if hasattr(sub, key):
                    setattr(sub, key, value)
            sub.updated_at = datetime.utcnow()

            if actor_user_id:
                _record_user_activity_in_session(
                    session=session,
                    user_id=actor_user_id,
                    action="labeling_updated",
                    feature="Labeling",
                    metadata={"submission_id": submission_id},
                    access_context=access_context,
                )

            session.commit()
            session.refresh(sub)
        return sub
    finally:
        session.close()


def get_labeling_submission(submission_id: int) -> Optional[LabelingSubmission]:
    session = get_session()
    try:
        return session.query(LabelingSubmission).filter_by(id=submission_id).first()
    finally:
        session.close()


def get_labeling_submissions_by_iteration(iteration_id: int) -> list[LabelingSubmission]:
    session = get_session()
    try:
        return session.query(LabelingSubmission).filter_by(iteration_id=iteration_id).order_by(LabelingSubmission.created_at.desc()).all()
    finally:
        session.close()


def get_pending_labeling_submissions() -> list[LabelingSubmission]:
    session = get_session()
    try:
        return session.query(LabelingSubmission).filter_by(status="pending").order_by(LabelingSubmission.created_at.asc()).all()
    finally:
        session.close()


def approve_labeling_submission(
    submission_id: int,
    approver_user_id: int,
    is_final: bool = None,
    access_context: Optional[dict] = None,
) -> Optional[LabelingSubmission]:
    """Approve a labeling submission. If not final, auto-creates the next iteration
    using next_prompt as context. If final, marks the task complete."""
    session = get_session()
    try:
        sub = session.query(LabelingSubmission).filter_by(id=submission_id).first()
        if sub:
            # Use the submission's own is_final flag when not explicitly overridden
            if is_final is None:
                is_final = bool(sub.is_final)

            sub.status = "approved"
            sub.approved_by = approver_user_id
            sub.approved_at = datetime.utcnow()
            sub.updated_at = datetime.utcnow()

            iteration = session.query(Iteration).filter_by(id=sub.iteration_id).first()
            task = session.query(Task).filter_by(id=iteration.task_id).first() if iteration else None

            # Also save the structured evaluation into the iteration's ai_evaluation
            if iteration and not iteration.ai_evaluation:
                iteration.ai_evaluation = _build_eval_text(sub, iteration.iteration_num)

            if is_final and task:
                task.status = "complete"
            elif sub.next_prompt and iteration and task:
                next_num = session.query(Iteration).filter_by(task_id=task.id).count() + 1
                new_iter = Iteration(
                    task_id=task.id,
                    iteration_num=next_num,
                    issue_context=sub.next_prompt,
                )
                session.add(new_iter)

            _record_user_activity_in_session(
                session=session,
                user_id=approver_user_id,
                action="labeling_approved",
                feature="Labeling",
                metadata={"submission_id": submission_id, "is_final": is_final},
                access_context=access_context,
            )

            session.commit()
            session.refresh(sub)
        return sub
    finally:
        session.close()


def reject_labeling_submission(
    submission_id: int,
    approver_user_id: int,
    reason: str = None,
    access_context: Optional[dict] = None,
) -> Optional[LabelingSubmission]:
    session = get_session()
    try:
        sub = session.query(LabelingSubmission).filter_by(id=submission_id).first()
        if sub:
            sub.status = "rejected"
            sub.approved_by = approver_user_id
            sub.approved_at = datetime.utcnow()
            sub.rejection_reason = reason
            sub.updated_at = datetime.utcnow()

            _record_user_activity_in_session(
                session=session,
                user_id=approver_user_id,
                action="labeling_rejected",
                feature="Labeling",
                metadata={"submission_id": submission_id, "reason": reason},
                access_context=access_context,
            )

            session.commit()
            session.refresh(sub)
        return sub
    finally:
        session.close()


def _build_eval_text(sub: LabelingSubmission, iteration_num: int) -> str:
    """Build evaluation text from a labeling submission in the GUIDELINE.md format."""
    sep = "=" * 100
    axes_text = ""
    if sub.axis_evaluations:
        import json as _json
        evals = sub.axis_evaluations
        if isinstance(evals, str):
            try:
                evals = _json.loads(evals)
            except (ValueError, TypeError):
                evals = {}
        axis_labels = {
            "logic_correctness": "Logic and correctness",
            "logic": "Logic and correctness",
            "naming_clarity": "Naming and clarity",
            "naming": "Naming and clarity",
            "organization_modularity": "Organization and modularity",
            "organization": "Organization and modularity",
            "interface_design": "Interface design",
            "interface": "Interface design",
            "error_handling": "Error handling and robustness",
            "comments_documentation": "Comments and documentation",
            "comments": "Comments and documentation",
            "review_merge_readiness": "Review/merge readiness",
            "review_readiness": "Review/merge readiness",
        }
        seen_labels = set()
        for key, label in axis_labels.items():
            if label in seen_labels:
                continue
            val = evals.get(key, None)
            if val is not None:
                seen_labels.add(label)
                axes_text += f"\n{label}: {val}\n"

    return (
        f"{sep}\nITERATION {iteration_num} EVALUATION\n{sep}\n\n"
        f"{sep}\nMODEL A PROS:\n{sep}\n\n{sub.model_a_pros or ''}\n\n"
        f"{sep}\nMODEL A CONS:\n{sep}\n\n{sub.model_a_cons or ''}\n\n"
        f"{sep}\nMODEL B PROS:\n{sep}\n\n{sub.model_b_pros or ''}\n\n"
        f"{sep}\nMODEL B CONS:\n{sep}\n\n{sub.model_b_cons or ''}\n\n\n"
        f"{sep}\nAXIS SELECTIONS:\n{sep}\n{axes_text}\n\n"
        f"{sep}\nOVERALL PREFERENCE JUSTIFICATION:\n{sep}\n\n{sub.overall_justification or ''}\n\n\n"
        f"Axis Selection\nOverall preference: {sub.overall_preference or ''}\n\n\n"
        f"{sep}\nNEXT INSTRUCTION\n{sep}\n\n{sub.next_prompt or ''}\n"
    )


def get_approved_key_for_task(task_id: int) -> Optional[TaskKeyRequest]:
    """Get the approved task key request linked to a task."""
    session = get_session()
    try:
        return session.query(TaskKeyRequest).filter_by(
            task_id=task_id, status="approved"
        ).first()
    finally:
        session.close()


def get_key_request_for_task(task_id: int) -> Optional[TaskKeyRequest]:
    """Get any task key request linked to a task (any status)."""
    session = get_session()
    try:
        return session.query(TaskKeyRequest).filter_by(
            task_id=task_id
        ).order_by(TaskKeyRequest.created_at.desc()).first()
    finally:
        session.close()


# =========================
# Task Key Request CRUD
# =========================

def create_task_key_request(
    user_id: int,
    project_name: str,
    auth_key: str,
    task_id: int = None,
    access_context: Optional[dict] = None,
) -> TaskKeyRequest:
    session = get_session()
    try:
        req = TaskKeyRequest(
            user_id=user_id,
            project_name=project_name,
            auth_key=auth_key,
            task_id=task_id,
            status="pending",
        )
        session.add(req)
        session.flush()

        _record_user_activity_in_session(
            session=session,
            user_id=user_id,
            action="task_key_requested",
            feature="Task Key",
            metadata={"project_name": project_name, "task_id": task_id},
            access_context=access_context,
        )

        session.commit()
        session.refresh(req)
        return req
    finally:
        session.close()


def get_pending_task_key_requests() -> list[TaskKeyRequest]:
    session = get_session()
    try:
        return session.query(TaskKeyRequest).filter_by(status="pending").order_by(TaskKeyRequest.created_at.asc()).all()
    finally:
        session.close()


def get_task_key_requests_by_user(user_id: int) -> list[TaskKeyRequest]:
    session = get_session()
    try:
        return session.query(TaskKeyRequest).filter_by(user_id=user_id).order_by(TaskKeyRequest.created_at.desc()).all()
    finally:
        session.close()


def approve_task_key_request(
    request_id: int,
    approver_user_id: int,
    response_key: str = None,
    task_id: int = None,
    access_context: Optional[dict] = None,
) -> Optional[TaskKeyRequest]:
    session = get_session()
    try:
        req = session.query(TaskKeyRequest).filter_by(id=request_id).first()
        if req:
            req.status = "approved"
            req.approved_by = approver_user_id
            req.approved_at = datetime.utcnow()
            req.response_key = response_key
            if task_id:
                req.task_id = task_id

            linked_task_id = task_id or req.task_id
            if linked_task_id:
                task = session.query(Task).filter_by(id=linked_task_id).first()
                if task:
                    task.hfi_session_id = req.auth_key

            _record_user_activity_in_session(
                session=session,
                user_id=approver_user_id,
                action="task_key_approved",
                feature="Task Key",
                metadata={"request_id": request_id, "project_name": req.project_name, "task_id": linked_task_id},
                access_context=access_context,
            )

            session.commit()
            session.refresh(req)
        return req
    finally:
        session.close()


def reject_task_key_request(
    request_id: int,
    approver_user_id: int,
    reason: str = None,
    access_context: Optional[dict] = None,
) -> Optional[TaskKeyRequest]:
    session = get_session()
    try:
        req = session.query(TaskKeyRequest).filter_by(id=request_id).first()
        if req:
            req.status = "rejected"
            req.approved_by = approver_user_id
            req.approved_at = datetime.utcnow()
            req.rejection_reason = reason

            _record_user_activity_in_session(
                session=session,
                user_id=approver_user_id,
                action="task_key_rejected",
                feature="Task Key",
                metadata={"request_id": request_id, "reason": reason},
                access_context=access_context,
            )

            session.commit()
            session.refresh(req)
        return req
    finally:
        session.close()


def get_all_task_key_requests() -> list[TaskKeyRequest]:
    session = get_session()
    try:
        return session.query(TaskKeyRequest).order_by(TaskKeyRequest.created_at.desc()).all()
    finally:
        session.close()


# =========================
# Task Submission CRUD
# =========================

def create_task_submission(
    user_id: int,
    issue_url: str,
    issue_description: str,
    tar_file_path: str,
    task_id: int = None,
    access_context: Optional[dict] = None,
) -> TaskSubmission:
    session = get_session()
    try:
        sub = TaskSubmission(
            user_id=user_id,
            task_id=task_id,
            issue_url=issue_url,
            issue_description=issue_description,
            tar_file_path=tar_file_path,
            status="pending",
        )
        session.add(sub)
        session.flush()

        _record_user_activity_in_session(
            session=session,
            user_id=user_id,
            action="task_submitted",
            feature="Task Submission",
            metadata={"issue_url": issue_url, "task_id": task_id},
            access_context=access_context,
        )

        session.commit()
        session.refresh(sub)
        return sub
    finally:
        session.close()


def get_task_submissions_by_user(user_id: int) -> list[TaskSubmission]:
    session = get_session()
    try:
        return session.query(TaskSubmission).filter_by(user_id=user_id).order_by(TaskSubmission.created_at.desc()).all()
    finally:
        session.close()


def get_pending_task_submissions() -> list[TaskSubmission]:
    session = get_session()
    try:
        return session.query(TaskSubmission).filter_by(status="pending").order_by(TaskSubmission.created_at.asc()).all()
    finally:
        session.close()


def approve_task_submission(
    submission_id: int,
    approver_user_id: int,
    response_tar_file_path: str = None,
    response_commit_sha: str = None,
    response_issue_link: str = None,
    response_repo_link: str = None,
    access_context: Optional[dict] = None,
) -> Optional[TaskSubmission]:
    session = get_session()
    try:
        sub = session.query(TaskSubmission).filter_by(id=submission_id).first()
        if sub:
            sub.status = "approved"
            sub.approved_by = approver_user_id
            sub.approved_at = datetime.utcnow()
            sub.response_tar_file_path = response_tar_file_path
            sub.response_commit_sha = response_commit_sha
            sub.response_issue_link = response_issue_link
            sub.response_repo_link = response_repo_link

            _record_user_activity_in_session(
                session=session,
                user_id=approver_user_id,
                action="task_submission_approved",
                feature="Task Submission",
                metadata={"submission_id": submission_id, "commit_sha": response_commit_sha},
                access_context=access_context,
            )

            session.commit()
            session.refresh(sub)
        return sub
    finally:
        session.close()


def reject_task_submission(
    submission_id: int,
    approver_user_id: int,
    reason: str = None,
    access_context: Optional[dict] = None,
) -> Optional[TaskSubmission]:
    session = get_session()
    try:
        sub = session.query(TaskSubmission).filter_by(id=submission_id).first()
        if sub:
            sub.status = "rejected"
            sub.approved_by = approver_user_id
            sub.approved_at = datetime.utcnow()
            sub.rejection_reason = reason

            _record_user_activity_in_session(
                session=session,
                user_id=approver_user_id,
                action="task_submission_rejected",
                feature="Task Submission",
                metadata={"submission_id": submission_id, "reason": reason},
                access_context=access_context,
            )

            session.commit()
            session.refresh(sub)
        return sub
    finally:
        session.close()


# =========================
# Final Submission CRUD
# =========================

def create_final_submission(
    user_id: int,
    tar_file_path: str,
    anthropic_id: str,
    app_version: str,
    base_sha: str,
    repo_link: str,
    issue_link: str,
    dockerfile: str = None,
    task_id: int = None,
    access_context: Optional[dict] = None,
) -> FinalSubmission:
    session = get_session()
    try:
        sub = FinalSubmission(
            user_id=user_id,
            task_id=task_id,
            tar_file_path=tar_file_path,
            anthropic_id=anthropic_id,
            app_version=app_version,
            base_sha=base_sha,
            repo_link=repo_link,
            issue_link=issue_link,
            dockerfile=dockerfile,
            status="pending",
        )
        session.add(sub)
        session.flush()
        _record_user_activity_in_session(
            session=session,
            user_id=user_id,
            action="final_submitted",
            feature="Final Submission",
            metadata={"issue_link": issue_link, "task_id": task_id},
            access_context=access_context,
        )
        session.commit()
        session.refresh(sub)
        return sub
    finally:
        session.close()


def get_final_submissions_by_user(user_id: int) -> list[FinalSubmission]:
    session = get_session()
    try:
        return session.query(FinalSubmission).filter_by(user_id=user_id).order_by(FinalSubmission.created_at.desc()).all()
    finally:
        session.close()


def get_pending_final_submissions() -> list[FinalSubmission]:
    session = get_session()
    try:
        return session.query(FinalSubmission).filter_by(status="pending").order_by(FinalSubmission.created_at.asc()).all()
    finally:
        session.close()


def approve_final_submission(
    submission_id: int,
    approver_user_id: int,
    access_context: Optional[dict] = None,
) -> Optional[FinalSubmission]:
    session = get_session()
    try:
        sub = session.query(FinalSubmission).filter_by(id=submission_id).first()
        if sub:
            sub.status = "approved"
            sub.approved_by = approver_user_id
            sub.approved_at = datetime.utcnow()
            _record_user_activity_in_session(
                session=session,
                user_id=approver_user_id,
                action="final_submission_approved",
                feature="Final Submission",
                metadata={"submission_id": submission_id},
                access_context=access_context,
            )
            session.commit()
            session.refresh(sub)
        return sub
    finally:
        session.close()


def reject_final_submission(
    submission_id: int,
    approver_user_id: int,
    reason: str = None,
    access_context: Optional[dict] = None,
) -> Optional[FinalSubmission]:
    session = get_session()
    try:
        sub = session.query(FinalSubmission).filter_by(id=submission_id).first()
        if sub:
            sub.status = "rejected"
            sub.approved_by = approver_user_id
            sub.approved_at = datetime.utcnow()
            sub.rejection_reason = reason
            _record_user_activity_in_session(
                session=session,
                user_id=approver_user_id,
                action="final_submission_rejected",
                feature="Final Submission",
                metadata={"submission_id": submission_id, "reason": reason},
                access_context=access_context,
            )
            session.commit()
            session.refresh(sub)
        return sub
    finally:
        session.close()
