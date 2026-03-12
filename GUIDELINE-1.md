# Task Understanding & Step-by-Step Guide

## Overview

This project involves two major steps:
1. **Preparing a REPO** - Setting up the codebase with Docker, frozen dependencies, and updated documentation
2. **Evaluating Model Solutions** - Testing and comparing model responses to select the best solution

## STEP 1: Preparing a REPO

### Objective
Prepare a codebase at a specific commit state with a working Dockerfile, frozen dependencies, and clear build instructions.

### Prerequisites
- [ ] Repository cloned locally
- [ ] Base commit SHA identified (commit before the issue was solved)
- [ ] Git environment configured for the folder

### Checklist

#### 1.1 Repository Setup
- [ ] Clone the repository
- [ ] Reset repository to clean state and disable file mode tracking:
  ```bash
  # Disable file mode changes (prevents permission-only diffs)
  git config core.fileMode false
  
  # Reset to clean state
  git reset --hard HEAD
  git clean -fd
  ```

#### 1.2 Delete Lock Files
- [ ] Delete any existing lock files (e.g., `poetry.lock`, `Pipfile.lock`, `package-lock.json`, `yarn.lock`, `uv.lock`, etc.)
  ```bash
  # Find and remove lock files
  find . -name "*.lock" -type f -delete
  find . -name "poetry.lock" -type f -delete
  find . -name "Pipfile.lock" -type f -delete
  ```

#### 1.3 Verify Test Suite is Self-Contained (CRITICAL - DO THIS FIRST)
- [ ] **BEFORE creating any Dockerfile**, verify the test suite can run without external dependencies
- [ ] Check test files for:
  - [ ] External API requirements (Digi-Key, Mouser, AWS, Stripe, etc.)
  - [ ] Required environment variables or config files with credentials
  - [ ] Database connections that require running servers
  - [ ] Network calls to external services
- [ ] Read the test runner script (e.g., `run_tests.py`, `pytest.ini`, `conftest.py`)
- [ ] Look for signs the tests are NOT self-contained:
  - [ ] API key checks at startup
  - [ ] Config file loading that fails without credentials
  - [ ] `requests` or `httpx` calls to external URLs
  - [ ] Database connection setup
- [ ] **If tests require external APIs/credentials that aren't mocked**:
  - [ ] **STOP** - This repo is NOT suitable for Dockerized testing
  - [ ] **ABANDON** the repo and find another one
  - [ ] Do NOT waste time building a Dockerfile that won't produce runnable tests
- [ ] Verify by running tests locally first (if possible) to see what fails
  ```bash
  # Try running tests to see what's required
  python -m pytest --collect-only  # Just collect, don't run
  python run_tests.py  # Or whatever test command
  ```

#### 1.4 Dockerfile Creation/Update
- [ ] Check if Dockerfile exists in the root folder
- [ ] If Dockerfile exists, review and update it; if not, create a new one
- [ ] Dockerfile requirements:
  - [ ] Use slim versions of Python (e.g., `python:3.9-slim`)
  - [ ] Copy project files with `COPY . .` (do NOT clone the repo inside Dockerfile)
  - [ ] Install dependencies strictly from project managers, NO HARDCODING:
    - `requirements.txt` (for pip)
    - `pyproject.toml` (for poetry, pip, or uv)
    - `Pipfile` (for pipenv)
    - `setup.py` (for setuptools)
  - [ ] Do NOT use lock files for installation
  - [ ] Ensure Dockerfile is in the root folder of the project
  - [ ] Always add a CMD for Testing, (pytest for example)
- [ ] Build the Docker image to verify it works:
  ```bash
  docker build -t <project-name> .
  ```

#### 1.5 Test Docker Build
- [ ] Run the Docker container
- [ ] Verify the application runs (if it's an app)
- [ ] Run tests inside the container:
  ```bash
  docker run <project-name> <test-command>
  docker run -it --rm <image name>
  docker run --rm <image name> pytest -n auto tests/unit
  ```
- [ ] Ensure all tests pass
- [ ] Verify no dependency version conflicts or issues
- [ ] Even if there are failing tests make sure they are not due to dependecy.

#### 1.6 Find Compatible Versions (Optional - Before Docker)
- [ ] Use `uv` to resolve compatible versions before building Docker:
  ```bash
  pip install uv
  python -m uv pip compile pyproject.toml --all-extras
  ```
- [ ] Review the output for resolved package versions
- [ ] Use these versions to update dependency files before Docker build

#### 1.7 Freeze Dependencies
- [ ] After Docker build and tests pass successfully, freeze dependencies:
    ```bash
  docker run --rm <image-name> pip freeze
  ```
- [ ] Review the output to see all installed package versions (both regular and dev dependencies)
- [ ] Manually update the dependency file (requirements.txt, pyproject.toml, etc.) with the pinned versions
- [ ] If dev packages are not installed in Docker, update the Dockerfile to install them first, But never hardcode.
- [ ] Verify the dependency file is updated with pinned versions
- [ ] Re-run tests to ensure frozen dependencies work correctly

#### 1.8 Update README.md
- [ ] Open README.md
- [ ] Add/update "Installation and how to run tests" section
- [ ] Requirements for README update:
  - [ ] Specify Python version required
  - [ ] List which dependencies must be installed
  - [ ] Provide exact command to run tests
  - [ ] Provide exact command to run the app (if applicable)
  - [ ] Do NOT include instructions for cloning from GitHub
  - [ ] Focus on how to build/setup the already existing codebase
  - [ ] Match the setup process that the Dockerfile follows
- [ ] Example format:
  ```markdown
  ## Installation and how to run tests
  
  To install <project-name>:
  
  pip install -e .
  
  Or install from requirements:
  
  pip install -r requirements.txt
  
  To run tests:
  
  pytest tests/
  ```

#### 1.9 Commit Changes
- [ ] Stage all changes (Dockerfile, updated dependency files, README.md)
- [ ] Commit with anonymized author info:
  ```bash
  git config user.name "PR writer" &&
  git config user.email "pr-writer@example.com" &&
  git add . &&
  git commit --author="PR Writer <prwriter@rebirthexperts.com>" -m "Set up initial instructions"
  ```
- [ ] Verify commit was created successfully:
  ```bash
  git log --oneline -1
  ```

#### 1.10 Final Verification
- [ ] Verify Dockerfile builds successfully
- [ ] Verify tests run and pass in Docker container
- [ ] Verify README.md has clear build instructions
- [ ] Verify all lock files are deleted
- [ ] Verify dependencies are frozen in dependency manager files
- [ ] Verify all changes are committed
- [ ] Verify repository is in a clean state (no uncommitted changes)

---
