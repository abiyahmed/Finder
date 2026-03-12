"""
Prompt Library - copy-ready prompts aligned with project rules.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from src.infrastructure.database import init_db
from src.ui.sidebar import quick_hide, render_sidebar, require_auth

init_db()

st.set_page_config(page_title="Prompt Library", page_icon=":material/menu_book:", layout="wide")
quick_hide()
render_sidebar()
require_auth("Prompt Library")

st.title("Prompt Library")
st.caption("Use these prompts when automation needs manual AI help.")

st.markdown("### Global Rules")
st.markdown("- Delete lock files at task start and do not use lock files for install or analysis.")
st.markdown("- Dockerfile must install from dependency manager files only and must include `COPY . .` and a test `CMD`.")
st.markdown("- README install section must not include Docker commands.")
st.markdown("- Prompts should require direct file edits with concrete file names and exact commands.")

PROMPTS = {
    "Dockerfile Generator": """Write a Dockerfile for this repository using the constraints below.

Constraints:
- Base image: `python:<PYTHON_VERSION>-slim`
- Use `WORKDIR /app`
- Use `COPY . .`
- Install dependencies strictly from project dependency files (`requirements*.txt`, `pyproject.toml`, `setup.py`, `setup.cfg`, `Pipfile`)
- Do not hardcode package names
- Do not install from any lock file
- Add a testing CMD using: `<TEST_COMMAND>`
- Include only minimal apt packages if needed.""",
    "Dependency Pinning (In-Repo Edits)": """Use the provided pinned dependency list and pin dependencies directly in repository files.

Inputs:
- Pinned dependency map: `<PINNED_DEPENDENCIES>`

Rules:
- Ignore all lock files (`*.lock`, `poetry.lock`, `Pipfile.lock`, `uv.lock`, etc.)
- Use only dependency manager files (`requirements*.txt`, `pyproject.toml`, `setup.py`, `setup.cfg`, `Pipfile`, `tox.ini`)
- Treat `<PINNED_DEPENDENCIES>` as source of truth
- Replace non-exact specifiers (`>=`, `<=`, `~=`, `^`, ranges) with exact pins (`==`) everywhere applicable
- Preserve extras and environment markers while pinning base versions
- Ensure package versions are consistent across all dependency files
- If a dependency is used in code but missing in dependency files, add it as an exact pin in the appropriate file
- Do not generate lock files""",
    "Dependency Usage Audit": """Analyze the current issue context and repository.

Tasks:
- Find dependency files (excluding lock files)
- Extract dependencies and infer import module names
- Scan Python files to list import and usage occurrences per dependency
- Return dependency, resolved version (if provided), imports, and usage snippets

Output format:
- Dependency summary table
- Imports/usage evidence grouped by dependency
- Missing imports/usages called out explicitly""",
    "README Install Section": """Write a README section titled exactly: `Installation and how to run tests`.

Requirements:
- Include required Python version
- Include install command(s) from project dependency files
- Include exact test command
- Include exact app run command when applicable
- Do not include clone instructions
- Do not include any Docker commands
- Keep it concise and copy-ready

Return markdown only.""",
    "Repo Prep Plan": """Create a step-by-step repo preparation plan for this issue.

Must include:
- Lock file deletion step
- Test self-containment verification before Docker work
- Dockerfile creation/update constraints (no hardcoded deps, no lock files)
- Dependency freeze/update step in dependency manager files
- README install/test/run update (no Docker commands)
- Final verification checklist

Return a practical ordered checklist with exact commands where needed.""",
    "Model Evaluation Instruction": """Evaluate two candidate code changes for this issue and produce a strict evaluation document.

Inputs:
- Issue scope and acceptance criteria: `<ISSUE_SCOPE>`
- Candidate A change summary: `<MODEL_A_CHANGES>`
- Candidate B change summary: `<MODEL_B_CHANGES>`
- Test evidence, commands, and outputs: `<TEST_EVIDENCE>`
- Output file path: `<TASK_DIR>/evaluation_report.txt`

Evaluation priorities:
1) Logic and correctness based on actual evidence
2) Review and merge readiness in target runtime
3) Error handling and robustness
4) Scope adherence to the issue
5) Clarity and maintainability

Required axes and allowed selections:
- Logic and correctness: A / AA / AAA / AAAA / BBBB / BBB / BB / B / N/A
- Naming and clarity: A / AA / AAA / AAAA / BBBB / BBB / BB / B / N/A
- Organization and modularity: A / AA / AAA / AAAA / BBBB / BBB / BB / B / N/A
- Interface design: A / AA / AAA / AAAA / BBBB / BBB / BB / B / N/A
- Error handling and robustness: A / AA / AAA / AAAA / BBBB / BBB / BB / B / N/A
- Comments and documentation: A / AA / AAA / AAAA / BBBB / BBB / BB / B / N/A
- Review and merge readiness: A / AA / AAA / AAAA / BBBB / BBB / BB / B / N/A
- Overall preference: A or B

Critical rules:
- Use paragraph style only for pros, cons, justification, and next instruction
- Do not use bullets or numbered lists inside those paragraphs
- Do not refer to PR, golden solution, ground truth, response, or iteration in those paragraphs
- Do not use hyphen, colon, or semicolon characters inside those paragraphs
- Keep claims grounded in concrete evidence with file names, function names, and test outcomes
- Ensure axis selections align with stated pros and cons
- Penalize failed tests, broken behavior, risky workarounds, and scope creep
- Do not reward out of scope changes
- Keep proportionality between issue severity and scoring

Next instruction rules:
- Write one direct paragraph only
- No praise and no pleasantries
- Stay strictly within issue scope
- Address only the highest impact gaps from the preferred candidate
- Request concrete code edits with file and function targets
- Do not ask for Docker execution in that paragraph

Write result to file:
- Save the full output exactly to `<TASK_DIR>/evaluation_report.txt`

Output format to write:
====================================================================================================
EVALUATION
====================================================================================================

====================================================================================================
MODEL A PROS
====================================================================================================
[Single paragraph]

====================================================================================================
MODEL A CONS
====================================================================================================
[Single paragraph]

====================================================================================================
MODEL B PROS
====================================================================================================
[Single paragraph]

====================================================================================================
MODEL B CONS
====================================================================================================
[Single paragraph]

====================================================================================================
AXIS SELECTIONS
====================================================================================================
Logic and correctness: [selection]
Naming and clarity: [selection]
Organization and modularity: [selection]
Interface design: [selection]
Error handling and robustness: [selection]
Comments and documentation: [selection]
Review and merge readiness: [selection]

====================================================================================================
OVERALL PREFERENCE JUSTIFICATION
====================================================================================================
[Single paragraph]

Overall preference: [A or B]

====================================================================================================
NEXT INSTRUCTION
====================================================================================================
[Single paragraph]""",
}

template_name = st.selectbox("Template", list(PROMPTS.keys()))
base_prompt = PROMPTS[template_name]

extra_context = st.text_area(
    "Optional extra context",
    placeholder="Paste repo path, issue text, test output, or file names to include in the prompt.",
    height=120,
)

final_prompt = base_prompt
if extra_context.strip():
    final_prompt = f"{base_prompt}\n\nContext:\n{extra_context.strip()}"

st.markdown("### Prompt")
st.code(final_prompt, language="text")
st.download_button(
    "Download prompt",
    data=final_prompt,
    file_name=f"{template_name.lower().replace(' ', '_')}.txt",
    mime="text/plain",
)
