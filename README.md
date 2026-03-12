# Finder

Streamlit app for GitHub issue discovery, dependency analysis, and repo preparation workflows.

## DeepSeek Integration (Dependency Workflow)

DeepSeek is integrated as a **fallback-only** path in dependency auto-fix:

- Local candidate search runs first for failed exact import checks.
- DeepSeek is called only for unresolved packages.
- Every DeepSeek suggestion is validated locally in an isolated virtual environment before acceptance.
- Suggested versions are applied only to dependency-resolution outputs (no source/test code rewriting).

### Required Environment Variables

- `GITHUB_TOKEN`: GitHub API access for repository/issue analysis
- `DEEPSEEK_API_KEY`: enables DeepSeek fallback for unresolved dependency/import failures

## Exact Pinned Dependencies

This repository uses exact versions in `requirements.txt`:

- `requests==2.32.5`
- `python-dotenv==1.2.1`
- `streamlit==1.53.1`
- `sqlalchemy==2.0.46`
- `pandas==2.3.3`
- `pytest==9.0.1`
- `uv==0.9.26`

## Local Run

```bash
pip install -r requirements.txt
streamlit run run.py
```

## Tests

Default test run:

```bash
python -m pytest -q
```

Live GitHub dependency integration test is intentionally opt-in and requires external API access:

- `RUN_LIVE_GITHUB_TESTS=1`
- `GITHUB_TOKEN` configured

## Docker

Build and run:

```bash
docker build -t finder-app .
docker run --rm finder-app
```

### Ignored Test Categories in Docker CMD

The Docker test command excludes categories likely to require external APIs/infrastructure:

- `live`: live endpoint/credential dependent tests
- `external`: third-party API/network dependent tests
- `network`: tests requiring host connectivity assumptions
- `redis`: tests requiring Redis service
- `pgadmin`: tests requiring external admin/database infrastructure

These exclusions keep container test execution deterministic for dependency-validation workflows.
