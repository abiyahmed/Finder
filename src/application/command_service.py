"""
Command generation service.
Application layer - generates shell commands for copy-paste.
"""
import re
import shlex
from typing import Optional, List, Dict


class CommandService:
    """Service for generating shell commands."""

    TEST_VERBOSITY_PATTERN = re.compile(r"(^|\s)(-q|-v+|--verbose|--quiet)(\s|$)")
    DEFAULT_EXTERNAL_TEST_EXCLUSIONS = [
        "integration",
        "e2e",
        "redis",
        "external",
        "live",
        "network",
        "postgres",
        "pgadmin",
    ]
    EXCLUSION_REASON_MAP = {
        "integration": "Integration tests often depend on external services or full system orchestration.",
        "e2e": "End-to-end tests can require deployed infrastructure not available in isolated builds.",
        "redis": "Redis-backed tests require a running Redis service.",
        "external": "External tests typically call third-party APIs or internet resources.",
        "live": "Live tests require real external endpoints and credentials.",
        "network": "Network tests may require reachable hosts unavailable in offline/restricted CI.",
        "postgres": "PostgreSQL tests require a running Postgres database service.",
        "pgadmin": "pgAdmin-related tests require external admin infrastructure.",
    }
    DEFAULT_DOCKER_PYTHON_TAG = "3.11"
    KNOWN_DOCKER_PYTHON_TAGS = ["3.13", "3.12", "3.11", "3.10", "3.9", "3.8", "3.7"]

    # =========================
    # Path Conversion
    # =========================

    @staticmethod
    def wsl_path(windows_path: str) -> str:
        """
        Convert Windows path to WSL path.
        C:\\Users\\... -> /mnt/c/Users/...
        """
        if not windows_path:
            return ""
        path = windows_path.replace("\\", "/")
        match = re.match(r"^([A-Za-z]):/(.*)$", path)
        if match:
            drive = match.group(1).lower()
            rest = match.group(2)
            return f"/mnt/{drive}/{rest}"
        return path

    @staticmethod
    def windows_path(wsl_path_str: str) -> str:
        """
        Convert WSL path to Windows path.
        /mnt/c/Users/... -> C:\\Users\\...
        """
        if not wsl_path_str:
            return ""
        match = re.match(r"^/mnt/([a-z])/(.*)$", wsl_path_str)
        if match:
            drive = match.group(1).upper()
            rest = match.group(2).replace("/", "\\")
            return f"{drive}:\\{rest}"
        return wsl_path_str

    # =========================
    # Git Commands
    # =========================

    @staticmethod
    def git_setup_commands(repo_path: str) -> list[str]:
        """Generate git setup commands for repo preparation."""
        return [
            f'cd "{repo_path}"',
            "git config core.fileMode false",
            "git reset --hard HEAD",
            "git clean -fd",
        ]

    @staticmethod
    def git_checkout_command(sha: str) -> str:
        """Generate git checkout command for a specific SHA."""
        return f"git checkout {sha}"

    @staticmethod
    def git_clone_command(repo_url: str, target_dir: str = None) -> str:
        """Generate git clone command."""
        if target_dir:
            return f'git clone {repo_url} "{target_dir}"'
        return f"git clone {repo_url}"

    @staticmethod
    def git_commit_command(message: str) -> str:
        """Generate git commit command with anonymized author."""
        escaped_msg = message.replace('"', '\\"')
        return f'''git config user.name "PR writer" ; \\
git config user.email "pr-writer@example.com" ; \\
git add . ; \\
git commit --author="PR Writer <prwriter@rebirth.dev>" -m "{escaped_msg}"'''

    @staticmethod
    def git_log_command(n: int = 10) -> str:
        """Generate git log command."""
        return f"git log --oneline -n {n}"

    @staticmethod
    def git_status_command() -> str:
        """Generate git status command."""
        return "git status"

    @staticmethod
    def delete_lock_files_command() -> str:
        """Generate command to delete lock files."""
        return '''find . -name "poetry.lock" -type f -delete ; \\
find . -name "Pipfile.lock" -type f -delete ; \\
find . -name "package-lock.json" -type f -delete ; \\
find . -name "yarn.lock" -type f -delete ; \\
find . -name "uv.lock" -type f -delete ; \\
find . -name "pdm.lock" -type f -delete ; \\
find . -name "pnpm-lock.yaml" -type f -delete'''

    # =========================
    # Docker Commands
    # =========================

    @staticmethod
    def docker_build_command(image_name: str, dockerfile_path: str = ".") -> str:
        """Generate docker build command."""
        return f'docker build -t {image_name} "{dockerfile_path}"'

    @staticmethod
    def docker_run_command(image_name: str, command: str = None) -> str:
        """Generate docker run command."""
        if command:
            return f"docker run --rm {image_name} {command}"
        return f"docker run -it --rm {image_name}"

    @staticmethod
    def docker_run_tests_command(image_name: str, test_command: str = "pytest") -> str:
        """Generate docker run command for tests."""
        normalized = CommandService.normalize_test_command_for_docker(test_command)
        return f"docker run --rm {image_name} {normalized}"

    @staticmethod
    def freeze_deps_command(image_name: str) -> str:
        """Generate command to freeze dependencies from docker container."""
        return f"docker run --rm {image_name} pip freeze"

    @staticmethod
    def uv_compile_command() -> str:
        """Generate uv pip compile command for resolving dependencies."""
        return "python -m uv pip compile pyproject.toml --all-extras"

    # =========================
    # Tar Commands
    # =========================

    @staticmethod
    def tar_create_command(archive_name: str, source_dir: str) -> str:
        """Generate tar create command."""
        return f'tar -cf {archive_name} "{source_dir}"'

    @staticmethod
    def tar_create_gz_command(archive_name: str, source_dir: str) -> str:
        """Generate tar create with gzip command."""
        return f'tar -czf {archive_name} "{source_dir}"'

    # =========================
    # HFI Commands
    # =========================

    @staticmethod
    def hfi_start_command() -> str:
        """Generate HFI start command."""
        return "claude-hfi --vscode"

    @staticmethod
    def tmux_new_session_command(session_name: str) -> str:
        """Generate tmux new session command."""
        return f"tmux new -s {session_name}"

    @staticmethod
    def tmux_attach_command(session_id: str) -> str:
        """Generate tmux attach command."""
        return f"tmux attach -t {session_id}"

    @staticmethod
    def tmux_list_command() -> str:
        """Generate tmux list sessions command."""
        return "tmux ls"

    @staticmethod
    def tmux_kill_session_command(session_id: str) -> str:
        """Generate tmux kill session command."""
        return f"tmux kill-session -t {session_id}"

    # =========================
    # Combined Command Sets
    # =========================

    @classmethod
    def repo_setup_commands(cls, repo_path: str, base_sha: str = None) -> list[str]:
        """Generate all commands for initial repo setup."""
        commands = cls.git_setup_commands(repo_path)
        if base_sha:
            commands.append(cls.git_checkout_command(base_sha))
        return commands

    @staticmethod
    def _normalize_file_name(path: str) -> str:
        return path.replace("\\", "/").split("/")[-1].lower()

    @classmethod
    def infer_install_commands(cls, dependency_files: Optional[List[str]] = None) -> List[str]:
        """Infer Docker install RUN commands based on available dependency files."""
        dependency_files = dependency_files or []
        dep_files_lower = [cls._normalize_file_name(f) for f in dependency_files]

        req_files = [
            f for f in dependency_files
            if cls._normalize_file_name(f).startswith("requirements")
            and cls._normalize_file_name(f).endswith((".txt", ".in"))
        ]
        if req_files:
            return [f"RUN pip install --no-cache-dir -r {fpath}" for fpath in req_files]

        if any(name in dep_files_lower for name in ("pyproject.toml", "setup.py", "setup.cfg")):
            return ["RUN pip install --no-cache-dir ."]

        if "pipfile" in dep_files_lower:
            return [
                "RUN pip install --no-cache-dir pipenv",
                "RUN pipenv install --system --skip-lock",
            ]

        return ["RUN pip install --no-cache-dir -e ."]

    @classmethod
    def infer_readme_install_commands(cls, dependency_files: Optional[List[str]] = None) -> List[str]:
        """Infer README install commands based on available dependency files."""
        dependency_files = dependency_files or []
        dep_files_lower = [cls._normalize_file_name(f) for f in dependency_files]

        req_files = [
            f for f in dependency_files
            if cls._normalize_file_name(f).startswith("requirements")
            and cls._normalize_file_name(f).endswith((".txt", ".in"))
        ]
        if req_files:
            return [f"pip install -r {fpath}" for fpath in req_files]

        if any(name in dep_files_lower for name in ("pyproject.toml", "setup.py", "setup.cfg")):
            return ["pip install ."]

        if "pipfile" in dep_files_lower:
            return ["pip install pipenv", "pipenv install --dev --skip-lock"]

        return ["pip install -e ."]

    @staticmethod
    def infer_system_packages(dependency_entries: Optional[List[Dict[str, str]]] = None) -> List[str]:
        """Infer apt packages from detected dependencies/specifiers."""
        dependency_entries = dependency_entries or []
        apt = {"ca-certificates"}

        # Common native build essentials for extension-heavy projects.
        native_trigger = False
        for entry in dependency_entries:
            name = str(entry.get("name", "")).strip().lower().replace("-", "_")
            spec = str(entry.get("specifier", "")).lower()

            if "git+" in spec or name == "gitpython":
                apt.add("git")

            if name in {"psycopg2", "psycopg", "psycopg2_binary"}:
                apt.add("libpq-dev")
                native_trigger = True
            if name in {"lxml"}:
                apt.update({"libxml2-dev", "libxslt1-dev"})
                native_trigger = True
            if name in {"pyodbc"}:
                apt.add("unixodbc-dev")
                native_trigger = True
            if name in {"cffi", "cryptography"}:
                apt.add("libffi-dev")
                native_trigger = True
            if name in {"pillow"}:
                apt.update({"libjpeg62-turbo-dev", "zlib1g-dev"})
                native_trigger = True
            if name in {"mysqlclient"}:
                apt.add("default-libmysqlclient-dev")
                native_trigger = True
            if name in {"pygraphviz"}:
                apt.update({"graphviz", "libgraphviz-dev"})
                native_trigger = True

        if native_trigger:
            apt.update({"build-essential", "pkg-config"})

        preferred_order = [
            "ca-certificates",
            "git",
            "build-essential",
            "gcc",
            "g++",
            "pkg-config",
            "libffi-dev",
            "libpq-dev",
            "libxml2-dev",
            "libxslt1-dev",
            "unixodbc-dev",
            "default-libmysqlclient-dev",
            "libjpeg62-turbo-dev",
            "zlib1g-dev",
        ]
        ordered = [pkg for pkg in preferred_order if pkg in apt]
        ordered.extend(sorted(pkg for pkg in apt if pkg not in ordered))
        return ordered

    @classmethod
    def normalize_test_command(cls, test_command: str) -> str:
        """Normalize test commands to Python-invoked commands with readable verbosity."""
        cmd = (test_command or "").strip()
        if not cmd:
            return "python -m pytest -v"

        lower = cmd.lower()
        if lower.startswith(("python ", "python3 ", "py ")):
            return cmd

        def add_verbose_if_missing(base: str) -> str:
            if cls.TEST_VERBOSITY_PATTERN.search(base):
                return base
            return f"{base} -v"

        if lower.startswith("pytest"):
            rest = cmd[len("pytest"):].strip()
            normalized = "python -m pytest"
            if rest:
                normalized = f"{normalized} {rest}"
            return add_verbose_if_missing(normalized)

        if lower.startswith("nosetests"):
            rest = cmd[len("nosetests"):].strip()
            normalized = "python -m nose"
            if rest:
                normalized = f"{normalized} {rest}"
            return add_verbose_if_missing(normalized)

        if lower.startswith("nose2"):
            rest = cmd[len("nose2"):].strip()
            normalized = "python -m nose2"
            if rest:
                normalized = f"{normalized} {rest}"
            return add_verbose_if_missing(normalized)

        if lower.startswith("unittest"):
            rest = cmd[len("unittest"):].strip()
            normalized = "python -m unittest"
            if rest:
                normalized = f"{normalized} {rest}"
            return add_verbose_if_missing(normalized)

        if lower.startswith("tox"):
            rest = cmd[len("tox"):].strip()
            normalized = "python -m tox"
            if rest:
                normalized = f"{normalized} {rest}"
            return normalized

        if lower.startswith("manage.py"):
            return f"python {cmd}"

        return cmd

    @classmethod
    def normalize_test_command_for_docker(cls, test_command: str) -> str:
        """Normalize test commands for Docker CMD (prefer tool executables where practical)."""
        normalized = (test_command or "").strip()
        if not normalized:
            return "pytest"
        lower = normalized.lower()

        def suffix(prefix: str) -> str:
            tail = normalized[len(prefix):].strip()
            return f" {tail}" if tail else ""

        if lower.startswith("python -m pytest"):
            tail = suffix("python -m pytest").strip()
            if tail in {"-v", "--verbose"}:
                return "pytest"
            return f"pytest {tail}".strip()
        if lower.startswith("python -m nose2"):
            return f"nose2{suffix('python -m nose2')}"
        if lower.startswith("python -m nose"):
            return f"nosetests{suffix('python -m nose')}"
        if lower.startswith("python -m tox"):
            return f"tox{suffix('python -m tox')}"
        if lower.startswith(("pytest", "nosetests", "nose2", "tox")):
            return normalized
        return cls.normalize_test_command(normalized)

    @classmethod
    def build_pytest_exclusion_expression(cls, exclusions: Optional[List[str]] = None) -> str:
        """Build a pytest -k expression from exclusion tags."""
        tags = [str(tag).strip() for tag in (exclusions or []) if str(tag).strip()]
        if not tags:
            return ""
        ordered = []
        seen = set()
        for tag in tags:
            key = tag.lower()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(key)
        return " and ".join([f"not {tag}" for tag in ordered])

    @classmethod
    def apply_pytest_exclusions(
        cls,
        test_command: str,
        exclusions: Optional[List[str]] = None,
    ) -> str:
        """Apply pytest -k exclusions to a test command when appropriate."""
        normalized = cls.normalize_test_command(test_command)
        if exclusions is None:
            return normalized
        lower = normalized.lower()
        if "pytest" not in lower:
            return normalized
        if " -k " in f" {normalized} ":
            return normalized
        expression = cls.build_pytest_exclusion_expression(exclusions)
        if not expression:
            return normalized
        if not cls.TEST_VERBOSITY_PATTERN.search(normalized):
            normalized = f"{normalized} -q"
        escaped = expression.replace('"', '\\"')
        return f'{normalized} -k "{escaped}"'

    @classmethod
    def test_exclusion_reason_lines(cls, exclusions: Optional[List[str]] = None) -> List[str]:
        """Return human-readable exclusion reasons for README text."""
        tags = [str(tag).strip().lower() for tag in (exclusions or []) if str(tag).strip()]
        lines = []
        seen = set()
        for tag in tags:
            if tag in seen:
                continue
            seen.add(tag)
            reason = cls.EXCLUSION_REASON_MAP.get(tag, "Excluded to avoid infrastructure-dependent failures in isolated runs.")
            lines.append(f"- `{tag}`: {reason}")
        return lines

    @staticmethod
    def normalize_run_command(run_command: str) -> str:
        """Normalize run command to Python-invoked forms when possible."""
        cmd = (run_command or "").strip()
        if not cmd:
            return "python -m <module>"

        lower = cmd.lower()
        if lower.startswith(("python ", "python3 ", "py ")):
            return cmd
        if lower.startswith("flask"):
            return f"python -m {cmd}"
        if lower.startswith("uvicorn"):
            return f"python -m {cmd}"
        if lower.startswith("manage.py"):
            return f"python {cmd}"
        return cmd

    @staticmethod
    def infer_specific_test_command(test_command: str, specific_target: str = "") -> str:
        """Provide a concrete example command for running a specific test."""
        cmd = (test_command or "").strip()
        lower = cmd.lower()
        target = (specific_target or "").strip()
        if "pytest" in lower:
            if target:
                return f"python -m pytest -v {target}"
            return "python -m pytest -v"
        if "unittest" in lower:
            return "python -m unittest -v tests.test_module.TestClass.test_method"
        if "nose2" in lower:
            return "python -m nose2 -v tests.module.TestClass.test_method"
        if "nose" in lower:
            return "python -m nose -v tests/module.py:TestClass.test_method"
        return cmd

    @staticmethod
    def docker_cmd_line(command: str) -> str:
        """Render Docker CMD; use exec form by default, shell fallback for complex commands."""
        normalized = (command or "").strip() or "python -m pytest -v"
        has_shell_operators = any(op in normalized for op in ["|", "&&", "||", ";", ">", "<", "$(", "`"])
        if has_shell_operators:
            escaped = normalized.replace("\\", "\\\\").replace('"', '\\"')
            return f'CMD ["sh", "-c", "{escaped}"]'
        try:
            parts = shlex.split(normalized, posix=True)
        except ValueError:
            escaped = normalized.replace("\\", "\\\\").replace('"', '\\"')
            return f'CMD ["sh", "-c", "{escaped}"]'
        if not parts:
            return 'CMD ["pytest"]'
        escaped_parts = [p.replace("\\", "\\\\").replace('"', '\\"') for p in parts]
        parts_literal = ", ".join([f'"{p}"' for p in escaped_parts])
        return f"CMD [{parts_literal}]"

    @classmethod
    def _parse_major_minor(cls, value: str) -> Optional[tuple[int, int]]:
        match = re.match(r"^\s*(\d+)(?:\.(\d+))?", str(value or "").strip())
        if not match:
            return None
        major = int(match.group(1))
        minor = int(match.group(2) or 0)
        return major, minor

    @classmethod
    def normalize_python_version_for_docker(cls, python_version: str) -> str:
        """
        Convert Python version specs into a valid Docker python tag.
        Examples:
        - "3.10" -> "3.10"
        - "==3.9" -> "3.9"
        - ">=3.8,<3.11" -> "3.10" (highest known tag within range)
        - ">=3.7" -> "3.13" (highest known tag satisfying lower bound)
        """
        raw = str(python_version or "").strip()
        if not raw:
            return cls.DEFAULT_DOCKER_PYTHON_TAG

        # Strip common prefixes.
        raw = re.sub(r"^\s*python\s*", "", raw, flags=re.IGNORECASE).strip()

        # Exact/bare versions.
        exact_match = re.match(r"^\s*(?:==\s*)?(\d+(?:\.\d+)?)\s*$", raw)
        if exact_match:
            parsed = cls._parse_major_minor(exact_match.group(1))
            if parsed:
                return f"{parsed[0]}.{parsed[1]}"

        approx_match = re.search(r"~=\s*(\d+(?:\.\d+)?)", raw)
        if approx_match:
            parsed = cls._parse_major_minor(approx_match.group(1))
            if parsed:
                return f"{parsed[0]}.{parsed[1]}"

        lower_bound: Optional[tuple[int, int]] = None
        lower_inclusive = True
        upper_bound: Optional[tuple[int, int]] = None
        upper_inclusive = True

        for token in [p.strip() for p in raw.split(",") if p.strip()]:
            m = re.match(r"^(<=|>=|<|>)\s*(\d+(?:\.\d+)?)$", token)
            if not m:
                continue
            op, version_text = m.group(1), m.group(2)
            parsed = cls._parse_major_minor(version_text)
            if not parsed:
                continue

            if op in {">", ">="}:
                if lower_bound is None or parsed > lower_bound:
                    lower_bound = parsed
                    lower_inclusive = (op == ">=")
                elif parsed == lower_bound and op == ">":
                    lower_inclusive = False
            else:
                if upper_bound is None or parsed < upper_bound:
                    upper_bound = parsed
                    upper_inclusive = (op == "<=")
                elif parsed == upper_bound and op == "<":
                    upper_inclusive = False

        for tag in cls.KNOWN_DOCKER_PYTHON_TAGS:
            candidate = cls._parse_major_minor(tag)
            if not candidate:
                continue
            if lower_bound is not None:
                if candidate < lower_bound:
                    continue
                if candidate == lower_bound and not lower_inclusive:
                    continue
            if upper_bound is not None:
                if candidate > upper_bound:
                    continue
                if candidate == upper_bound and not upper_inclusive:
                    continue
            return tag

        return cls.DEFAULT_DOCKER_PYTHON_TAG

    @classmethod
    def dockerfile_template(
        cls,
        python_version: str = "3.9",
        test_command: str = "pytest",
        dependency_files: Optional[List[str]] = None,
        dependency_entries: Optional[List[Dict[str, str]]] = None,
        test_exclusions: Optional[List[str]] = None,
    ) -> str:
        """Generate a Dockerfile template with inferred install/test commands."""
        install_lines = cls.infer_install_commands(dependency_files)
        apt_packages = cls.infer_system_packages(dependency_entries)
        normalized_with_exclusions = cls.apply_pytest_exclusions(test_command, exclusions=test_exclusions)
        normalized_test_command = cls.normalize_test_command_for_docker(normalized_with_exclusions)
        cmd_line = cls.docker_cmd_line(normalized_test_command)
        docker_python_tag = cls.normalize_python_version_for_docker(python_version)

        install_block = "\n".join(install_lines)
        apt_block = " \\\n    ".join(apt_packages)

        return f'''FROM python:{docker_python_tag}-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Install system dependencies (inferred from dependency set)
RUN apt-get update && apt-get install -y --no-install-recommends \\
    {apt_block} \\
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . .

# Install dependencies (no hardcoded packages)
{install_block}

# Inferred command for testing (override at docker run if needed)
{cmd_line}
'''

    @classmethod
    def readme_template(
        cls,
        project_name: str,
        python_version: str = "3.9",
        test_command: str = "pytest",
        run_command: str = "",
        dependency_files: Optional[List[str]] = None,
        test_exclusions: Optional[List[str]] = None,
        specific_test_target: str = "",
    ) -> str:
        """Generate a README template for installation/testing instructions."""
        install_commands = cls.infer_readme_install_commands(dependency_files)
        install_block = "\n".join(install_commands)
        normalized_test_command = cls.apply_pytest_exclusions(test_command, exclusions=test_exclusions)
        specific_test_command = cls.infer_specific_test_command(
            normalized_test_command,
            specific_target=specific_test_target,
        )
        normalized_run_command = cls.normalize_run_command(run_command) if (run_command or "").strip() else ""
        include_run_section = bool(normalized_run_command and "<module>" not in normalized_run_command)
        exclusion_lines = cls.test_exclusion_reason_lines(test_exclusions)
        exclusion_section = ""
        if exclusion_lines:
            exclusion_section = (
                "\nIgnored test categories and reasons:\n\n"
                + "\n".join(exclusion_lines)
                + "\n"
            )
        run_section = ""
        if include_run_section:
            run_section = f"""
To run the app:

```bash
{normalized_run_command}
```
"""
        return f'''## Installation and how to run tests

Python version: {python_version}

To install {project_name}:

```bash
{install_block}
```

To run tests:

```bash
{normalized_test_command}
```

To run all tests:

```bash
{normalized_test_command}
```

To run a specific test:

```bash
{specific_test_command}
```

{exclusion_section}

{run_section}
'''
