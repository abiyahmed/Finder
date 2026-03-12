"""
Integration tests for database and workflow.
"""
import os
import re
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test mode before importing database
os.environ["TEST_MODE"] = "1"

import pytest

from src.infrastructure.database import (
    Base,
    engine,
    SessionLocal,
    User,
    UserSession,
    UserActivity,
    Repository,
    RepoWhitelist,
    GoodIssue,
    Blacklist,
    BlacklistRepo,
    Issue,
    Task,
    Iteration,
    init_db,
    get_or_create_repository,
    create_issue,
    get_issues_by_repo,
    create_task,
    get_task_by_id,
    get_all_tasks,
    update_task,
    update_task_checklist,
    create_iteration,
    get_iterations_by_task,
    update_iteration,
    get_next_task_number,
    get_next_iteration_num,
    create_user,
    authenticate_user,
    set_user_access_policy,
    get_user_access_overview,
    get_user_activity_history,
    record_user_activity,
    touch_user_session,
    get_active_users,
    get_feature_usage_stats,
    get_user_work_history,
    add_repo_to_whitelist,
    remove_repo_from_whitelist,
    get_whitelisted_repo_names,
    get_issue_suggestions_by_urls,
    submit_good_issue,
    get_public_good_issues,
    set_good_issue_visibility,
)
from src.infrastructure.github_api import GitHubAPI
from src.application.prompt_service import PromptService


RUN_LIVE_GITHUB_TESTS = os.getenv("RUN_LIVE_GITHUB_TESTS", "").strip().lower() in {"1", "true", "yes"}
DEFAULT_LIVE_ISSUE_URL = "https://github.com/dlt-hub/dlt/issues/2515"


@pytest.fixture(autouse=True)
def setup_test_db():
    """Create fresh tables for each test."""
    Base.metadata.create_all(engine)
    yield
    # Clean up after test
    session = SessionLocal()
    try:
        session.query(UserActivity).delete()
        session.query(UserSession).delete()
        session.query(Iteration).delete()
        session.query(Task).delete()
        session.query(Issue).delete()
        session.query(Repository).delete()
        session.query(Blacklist).delete()
        session.query(BlacklistRepo).delete()
        session.query(GoodIssue).delete()
        session.query(RepoWhitelist).delete()
        session.query(User).delete()
        session.commit()
    finally:
        session.close()


def _parse_issue_url(issue_url: str) -> tuple[str, str, int]:
    match = re.search(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)", issue_url or "")
    if not match:
        raise ValueError(f"Invalid issue URL for live test: {issue_url}")
    return match.group(1), match.group(2), int(match.group(3))


def _resolve_base_sha_from_issue(api: GitHubAPI, owner: str, repo: str, issue_number: int) -> str:
    issue = api.fetch_issue_full_details(owner, repo, issue_number)
    if not issue:
        return ""

    timeline = issue.get("timelineItems", {}).get("nodes", []) or []
    linked_pr = None
    fallback_pr = None
    for event in timeline:
        source = event.get("source", {}) if event else {}
        if source.get("__typename") != "PullRequest":
            continue
        if source.get("merged"):
            linked_pr = source
            break
        if fallback_pr is None:
            fallback_pr = source
    if linked_pr is None:
        linked_pr = fallback_pr

    base_sha = linked_pr.get("baseRefOid") if linked_pr else None
    if base_sha:
        return base_sha

    repo_meta = api.fetch_repo_metadata(owner, repo)
    default_branch = repo_meta.get("default_branch", "main")
    created_at = issue.get("createdAt")
    if created_at:
        return api.get_base_sha_at_date(owner, repo, created_at, default_branch) or ""
    return ""


class TestRepositoryCRUD:
    def test_create_repository(self):
        metadata = {
            "description": "Test repo",
            "stars": 100,
            "forks": 50,
            "language": "Python",
            "default_branch": "main",
            "url": "https://github.com/test/repo",
        }
        repo = get_or_create_repository("test", "repo", metadata)

        assert repo.id is not None
        assert repo.owner == "test"
        assert repo.name == "repo"
        assert repo.full_name == "test/repo"
        assert repo.stars == 100

    def test_update_repository(self):
        metadata1 = {"stars": 100, "forks": 50}
        repo1 = get_or_create_repository("test", "repo", metadata1)

        metadata2 = {"stars": 200, "forks": 100}
        repo2 = get_or_create_repository("test", "repo", metadata2)

        assert repo1.id == repo2.id  # Same repo
        assert repo2.stars == 200  # Updated


class TestIssueCRUD:
    def test_create_issue(self):
        repo = get_or_create_repository("test", "repo", {})

        issue_data = {
            "issue_url": "https://github.com/test/repo/issues/1",
            "issue_number": 1,
            "issue_title": "Test Issue",
            "issue_body": "This is a test",
            "issue_state": "CLOSED",
            "base_sha": "abc123",
            "pr_number": 10,
            "pr_files_changed": 5,
            "pr_additions": 100,
            "pr_deletions": 50,
        }
        issue = create_issue(repo.id, issue_data)

        assert issue.id is not None
        assert issue.issue_number == 1
        assert issue.issue_title == "Test Issue"
        assert issue.base_sha == "abc123"

    def test_get_issues_by_repo(self):
        repo = get_or_create_repository("test", "repo", {})

        for i in range(3):
            create_issue(
                repo.id,
                {
                    "issue_url": f"https://github.com/test/repo/issues/{i}",
                    "issue_number": i,
                    "issue_title": f"Issue {i}",
                },
            )

        issues = get_issues_by_repo(repo.id)
        assert len(issues) == 3


class TestTaskCRUD:
    def test_create_task(self):
        repo = get_or_create_repository("test", "repo", {})
        issue = create_issue(
            repo.id,
            {
                "issue_url": "https://github.com/test/repo/issues/1",
                "issue_number": 1,
                "issue_title": "Test",
            },
        )

        task = create_task("task_1", issue.id, r"C:\path\to\repo")

        assert task.id is not None
        assert task.name == "task_1"
        assert task.status == "prep"

    def test_update_task_checklist(self):
        repo = get_or_create_repository("test", "repo", {})
        issue = create_issue(
            repo.id,
            {
                "issue_url": "https://github.com/test/repo/issues/1",
                "issue_number": 1,
                "issue_title": "Test",
            },
        )
        task = create_task("task_1", issue.id)

        update_task_checklist(task.id, "1.1", True)
        update_task_checklist(task.id, "1.2", True)

        updated_task = get_task_by_id(task.id)
        assert updated_task.prep_checklist.get("1.1") is True
        assert updated_task.prep_checklist.get("1.2") is True

    def test_get_next_task_number(self):
        repo = get_or_create_repository("test", "repo", {})
        issue = create_issue(
            repo.id,
            {
                "issue_url": "https://github.com/test/repo/issues/1",
                "issue_number": 1,
                "issue_title": "Test",
            },
        )

        num1 = get_next_task_number()
        create_task("task_1", issue.id)
        num2 = get_next_task_number()

        assert num2 == num1 + 1


class TestIterationCRUD:
    def test_create_iteration(self):
        repo = get_or_create_repository("test", "repo", {})
        issue = create_issue(
            repo.id,
            {
                "issue_url": "https://github.com/test/repo/issues/1",
                "issue_number": 1,
                "issue_title": "Test",
            },
        )
        task = create_task("task_1", issue.id)

        iteration = create_iteration(
            task.id,
            1,
            issue_context="Test context",
            model_a_response="Model A output",
            model_b_response="Model B output",
        )

        assert iteration.id is not None
        assert iteration.iteration_num == 1
        assert iteration.issue_context == "Test context"

    def test_update_iteration(self):
        repo = get_or_create_repository("test", "repo", {})
        issue = create_issue(
            repo.id,
            {
                "issue_url": "https://github.com/test/repo/issues/1",
                "issue_number": 1,
                "issue_title": "Test",
            },
        )
        task = create_task("task_1", issue.id)
        iteration = create_iteration(task.id, 1)

        update_iteration(iteration.id, ai_evaluation="Test evaluation")

        updated = get_iterations_by_task(task.id)[0]
        assert updated.ai_evaluation == "Test evaluation"

    def test_get_next_iteration_num(self):
        repo = get_or_create_repository("test", "repo", {})
        issue = create_issue(
            repo.id,
            {
                "issue_url": "https://github.com/test/repo/issues/1",
                "issue_number": 1,
                "issue_title": "Test",
            },
        )
        task = create_task("task_1", issue.id)

        assert get_next_iteration_num(task.id) == 1
        create_iteration(task.id, 1)
        assert get_next_iteration_num(task.id) == 2


class TestPromptService:
    def test_evaluation_prompt(self):
        prompt = PromptService.generate_evaluation_prompt(
            iteration_num=1,
            issue_context="Fix bug in auth",
            model_a_response="Model A fixed it by...",
            model_b_response="Model B fixed it by...",
        )

        assert "ITERATION 1 EVALUATION" in prompt
        assert "Fix bug in auth" in prompt
        assert "Model A fixed it by" in prompt
        assert "Model B fixed it by" in prompt
        assert "Logic and correctness" in prompt
        assert "MODEL A PROS:" in prompt
        assert "AXIS SELECTIONS:" in prompt

    def test_next_instruction_prompt(self):
        prompt = PromptService.generate_next_instruction_prompt(
            issue_context="Fix auth bug",
            current_cons="Missing validation",
            winning_model="A",
        )

        assert "Fix auth bug" in prompt
        assert "Missing validation" in prompt
        assert "model A" in prompt

    def test_initial_prompt(self):
        prompt = PromptService.generate_initial_prompt_template("Fix auth bug", "Users cannot log in when...")

        assert "Fix auth bug" in prompt
        assert "Users cannot log in" in prompt


class TestGoodIssueVisibility:
    def test_submit_good_issue_respects_public_filter(self):
        user = create_user("gooduser", "pass1234", "gooduser@example.com")
        assert user is not None

        private_issue = submit_good_issue(
            issue_url="https://github.com/org/repo/issues/101",
            submitted_by=user["id"],
            issue_title="Private issue",
            is_public=False,
        )
        public_issue = submit_good_issue(
            issue_url="https://github.com/org/repo/issues/102",
            submitted_by=user["id"],
            issue_title="Public issue",
            is_public=True,
        )

        assert private_issue is not None
        assert public_issue is not None

        public_urls = {row.issue_url for row in get_public_good_issues()}
        assert "https://github.com/org/repo/issues/102" in public_urls
        assert "https://github.com/org/repo/issues/101" not in public_urls

    def test_submit_same_issue_by_owner_can_promote_visibility(self):
        user = create_user("goodowner", "pass1234", "goodowner@example.com")
        assert user is not None

        first = submit_good_issue(
            issue_url="https://github.com/org/repo/issues/201",
            submitted_by=user["id"],
            issue_title="Initially private",
            is_public=False,
        )
        second = submit_good_issue(
            issue_url="https://github.com/org/repo/issues/201",
            submitted_by=user["id"],
            issue_title="Initially private",
            is_public=True,
        )

        assert first is not None
        assert second is not None
        assert first.id == second.id

        public_urls = {row.issue_url for row in get_public_good_issues()}
        assert "https://github.com/org/repo/issues/201" in public_urls

    def test_visibility_toggle_requires_owner_or_admin(self):
        owner = create_user("issueowner", "pass1234", "issueowner@example.com")
        other = create_user("issueother", "pass1234", "issueother@example.com")
        assert owner is not None
        assert other is not None

        issue = submit_good_issue(
            issue_url="https://github.com/org/repo/issues/301",
            submitted_by=owner["id"],
            issue_title="Owner private issue",
            is_public=False,
        )
        assert issue is not None

        denied = set_good_issue_visibility(issue.id, is_public=True, actor_user_id=other["id"])
        assert denied is False

        allowed = set_good_issue_visibility(issue.id, is_public=True, actor_user_id=owner["id"])
        assert allowed is True

        public_urls = {row.issue_url for row in get_public_good_issues()}
        assert "https://github.com/org/repo/issues/301" in public_urls


class TestUserAccessAndActivity:
    def test_authenticate_user_respects_ip_limit(self):
        user_data = create_user("alice", "pass1234", "alice@example.com")
        assert user_data is not None

        set_user_access_policy(user_data["id"], max_ip_addresses=1)

        first_login, first_error = authenticate_user(
            "alice",
            "pass1234",
            access_context={
                "ip_address": "1.1.1.1",
                "country": "US",
                "location": "New York, US",
                "device_fingerprint": "device-a",
            },
            session_key="session-a",
            detailed=True,
        )
        assert first_login is not None
        assert first_error is None

        second_login, second_error = authenticate_user(
            "alice",
            "pass1234",
            access_context={
                "ip_address": "2.2.2.2",
                "country": "US",
                "location": "Boston, US",
                "device_fingerprint": "device-a",
            },
            session_key="session-b",
            detailed=True,
        )
        assert second_login is None
        assert second_error is not None
        assert "max distinct IPs exceeded" in second_error

    def test_activity_feature_and_work_history_queries(self):
        user_data = create_user("bob", "pass1234", "bob@example.com")
        assert user_data is not None

        record_user_activity(
            user_id=user_data["id"],
            action="task_created",
            feature="Repo Preparation",
            repo_full_name="owner/repo",
            issue_url="https://github.com/owner/repo/issues/12",
            task_id=3,
            access_context={
                "ip_address": "3.3.3.3",
                "country": "US",
                "location": "San Francisco, US",
                "device_fingerprint": "device-b",
            },
        )
        record_user_activity(
            user_id=user_data["id"],
            action="feature_view",
            feature="Issue Finder",
            access_context={
                "ip_address": "3.3.3.3",
                "country": "US",
                "location": "San Francisco, US",
                "device_fingerprint": "device-b",
            },
        )

        activities, total_activities = get_user_activity_history(user_id=user_data["id"], page=1, page_size=20)
        assert total_activities >= 2
        assert any(a["action"] == "task_created" for a in activities)

        feature_rows = get_feature_usage_stats(user_id=user_data["id"], limit_per_user=10)
        assert any(row["feature"] == "Issue Finder" for row in feature_rows)

        work_rows, work_total = get_user_work_history(user_id=user_data["id"], page=1, page_size=20)
        assert work_total >= 1
        assert any(row["repo_full_name"] == "owner/repo" for row in work_rows)

    def test_touch_user_session_updates_active_and_access_overview(self):
        user_data = create_user("carol", "pass1234", "carol@example.com")
        assert user_data is not None

        touch_user_session(
            user_id=user_data["id"],
            session_key="session-carol",
            access_context={
                "ip_address": "4.4.4.4",
                "country": "US",
                "location": "Austin, US",
                "device_fingerprint": "device-c",
            },
            signed_in=True,
        )

        active_rows = get_active_users(active_within_minutes=15)
        assert any(row["user_id"] == user_data["id"] for row in active_rows)

        overview_rows = get_user_access_overview(user_id=user_data["id"])
        assert len(overview_rows) == 1
        assert overview_rows[0]["unique_ip_count"] == 1
        assert overview_rows[0]["unique_device_count"] == 1


class TestWhitelistAndIssueHistory:
    def test_repo_whitelist_add_remove_flow(self):
        add_repo_to_whitelist("pallets/flask", reason="good", source="test")
        names = get_whitelisted_repo_names()
        assert "pallets/flask" in names

        removed = remove_repo_from_whitelist("pallets/flask")
        assert removed is True
        names_after = get_whitelisted_repo_names()
        assert "pallets/flask" not in names_after

    def test_issue_history_lookup_by_urls(self):
        repo = get_or_create_repository("pallets", "flask", {"stars": 100, "default_branch": "main"})
        issue = create_issue(
            repo.id,
            {
                "issue_url": "https://github.com/pallets/flask/issues/77",
                "issue_number": 77,
                "issue_title": "History issue",
                "issue_state": "CLOSED",
                "base_sha": "abc123def456",
                "pr_number": 90,
                "pr_url": "https://github.com/pallets/flask/pull/90",
                "pr_files_changed": 6,
                "pr_additions": 120,
                "pr_deletions": 45,
                "pr_python_files": 3,
                "pr_python_additions": 80,
                "pr_python_deletions": 20,
                "pr_test_files": 2,
                "pr_test_additions": 30,
                "pr_test_deletions": 10,
            },
        )
        assert issue.id is not None

        cache = get_issue_suggestions_by_urls(
            [
                "https://github.com/pallets/flask/issues/77",
                "https://github.com/pallets/flask/issues/88",
            ]
        )
        assert "https://github.com/pallets/flask/issues/77" in cache
        row = cache["https://github.com/pallets/flask/issues/77"]
        assert row["full_name"] == "pallets/flask"
        assert row["from_history"] is True
        assert row["base_sha"] == "abc123def456"


class TestWorkflow:
    """Test the complete workflow from issue to evaluation."""

    def test_complete_workflow(self):
        # 1. Create repository
        repo = get_or_create_repository(
            "pallets",
            "flask",
            {
                "stars": 68000,
                "language": "Python",
            },
        )
        assert repo.id is not None

        # 2. Create issue from scan
        issue = create_issue(
            repo.id,
            {
                "issue_url": "https://github.com/pallets/flask/issues/5000",
                "issue_number": 5000,
                "issue_title": "Session handling bug",
                "issue_body": "When using secure cookies...",
                "issue_state": "CLOSED",
                "base_sha": "abc123def456",
                "pr_number": 5010,
                "pr_files_changed": 7,
                "pr_additions": 150,
                "pr_deletions": 30,
            },
        )
        assert issue.id is not None

        # 3. Create task from issue
        task = create_task("task_27", issue.id, r"C:\work\task_27\flask")
        assert task.status == "prep"

        # 4. Update checklist items
        for item in ["1.1", "1.2", "1.3", "1.4", "1.5"]:
            update_task_checklist(task.id, item, True)

        task = get_task_by_id(task.id)
        assert task.prep_checklist.get("1.1") is True

        # 5. Move to evaluation
        update_task(task.id, status="evaluating")
        task = get_task_by_id(task.id)
        assert task.status == "evaluating"

        # 6. Create iteration
        iteration = create_iteration(
            task.id,
            1,
            issue_context="Session handling bug\n\nWhen using secure cookies...",
            model_a_response="Model A: Fixed by adding validation...",
            model_b_response="Model B: Fixed by refactoring...",
        )

        # 7. Generate evaluation prompt
        prompt = PromptService.generate_evaluation_prompt(
            1,
            iteration.issue_context,
            iteration.model_a_response,
            iteration.model_b_response,
        )
        assert "ITERATION 1" in prompt

        # 8. Save evaluation
        update_iteration(iteration.id, ai_evaluation="Model A wins because...")

        # 9. Complete task
        update_task(task.id, status="complete")
        task = get_task_by_id(task.id)
        assert task.status == "complete"
