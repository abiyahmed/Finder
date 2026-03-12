```markdown
# Task Understanding & Step-by-Step Guide

## Overview

This project involves two major steps:
1. **Preparing a REPO** - Setting up the codebase with Docker, frozen dependencies, and updated documentation
2. **Evaluating Model Solutions** - Testing and comparing model responses to select the best solution

## Git Basics – Quick Tutorial

Git is a version control system that tracks changes to files. In this workflow we mostly use it to clone, clean, commit, and inspect history.

### Most important commands used here

| Command                              | What it does                                      | Example / When to use                              |
|--------------------------------------|---------------------------------------------------|----------------------------------------------------|
| `git clone <url>`                    | Download (copy) a remote repository locally       | `git clone https://github.com/user/repo.git`       |
| `git reset --hard HEAD`              | Throw away all uncommitted changes, go to latest commit | Clean working directory before starting            |
| `git clean -fd`                      | Remove untracked files and directories            | Together with reset to get a pristine state        |
| `git config core.fileMode false`     | Ignore permission (chmod) changes on Windows/WSL  | Prevent useless diffs on cross-platform work       |
| `git status`                         | Show what is changed / staged / untracked         | Always run before add/commit                       |
| `git add .` or `git add <file>`      | Stage changes (prepare for commit)                | `git add Dockerfile README.md`                     |
| `git commit -m "message"`            | Save staged changes as a new snapshot             | `git commit -m "Add Dockerfile and frozen deps"`   |
| `git commit --author="Name <email>"` | Commit with custom author (for anonymization)     | Used in step 1.9                                   |
| `git log --oneline -n 5`             | Show last 5 commits in short form                 | Verify your commit landed correctly                |
| `git log -1`                         | Show details of the very last commit              | Final verification                                 |

Quick sequence example (used often in this guide):
```bash
git status
git add .
git commit -m "Update Dockerfile and README"
git log --oneline -3    # check last 3 commits
```

**Tip**: If something goes wrong, `git reset --hard HEAD` + `git clean -fd` is your "factory reset" button (but it permanently deletes uncommitted work!).

More: official Git tutorial → https://git-scm.com/docs/gittutorial  
Atlassian Git cheatsheet → https://www.atlassian.com/git/tutorials/atlassian-git-cheatsheet

## Docker Basics – Quick Tutorial

Docker lets you package applications with their dependencies into portable **containers**. We mainly build images and run tests inside them.

### Key concepts

- **Image**   – Blueprint (like a class or template)
- **Container** – Running instance of an image (like an object)
- **Dockerfile** – Recipe file that describes how to build the image

### Commands used in this workflow

| Command                                 | What it does                                          | Example / Common flags                             |
|-----------------------------------------|-------------------------------------------------------|----------------------------------------------------|
| `docker build -t name:tag .`            | Build image from Dockerfile in current directory      | `docker build -t myproj:test .`                    |
| `docker run --rm image`                 | Run a container (and remove it after exit)            | `docker run --rm myproj:test`                      |
| `docker run -it --rm image bash`        | Get an interactive shell inside the container         | Debugging / exploring                              |
| `docker run --rm image pytest`          | Run tests directly (override CMD if needed)           | `docker run --rm myproj:test pytest tests/`        |
| `docker run --rm image pip freeze`      | Execute command inside container and see output       | Capture frozen dependencies                        |

Quick typical sequence:
```bash
# 1. Build
docker build -t project:test .

# 2. Test run (non-interactive)
docker run --rm project:test pytest -v

# 3. Debug interactively if needed
docker run -it --rm project:test bash
    # inside →   pytest --lf   or   pip list   etc.
    exit
```

### Dockerfile – minimal best-practice structure for Python (2024–2025 style)

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy only dependency files first → better layer caching
COPY pyproject.toml requirements.txt* ./

# Install dependencies (use your project's tool)
RUN pip install --no-cache-dir -r requirements.txt \
    || pip install --no-cache-dir .[test,dev] \
    || uv pip install --system --no-cache .

# Now copy the actual code
COPY . .

# Optional: non-root user for better security
# RUN useradd -m appuser && chown -R appuser /app
# USER appuser

# Default command – usually overridden in docker run
CMD ["pytest", "tests/"]
```

**Tips**:
- Use `-slim` or `-alpine` base images → much smaller
- Copy dependency files first, install, then copy source → faster rebuilds
- `--no-cache-dir` → smaller image
- `--rm` on `docker run` → no leftover containers
- Multi-stage builds are great for production, but optional for testing repos

More: official Get Started → https://docs.docker.com/get-started/  
Dockerfile best practices → https://docs.docker.com/build/building/best-practices/

---

## Rewriting the Issue Description (Before Evaluation)

Before using an issue as a prompt for model evaluation, rewrite the description in your own words. The goal is a natural, freeform prompt — not a copy-paste of the original.

**Rules:**
- State the problem and the expected solution **clearly and explicitly**
- Remove any links or images from the original issue description
- Do **not** add information that is not already present in the issue (e.g., do not mention writing tests unless the issue specifically asks for them)
- Keep the same scope and intent as the original — just rephrase it naturally

**Example:**

Original issue:
> `TypeError` when calling `process_data()` with an empty list. See screenshot: ![error](img.png). Related: #42

Rewritten prompt:
> The `process_data()` function raises a `TypeError` when called with an empty list. Fix it so that an empty list is handled gracefully and returns an empty result.

---

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