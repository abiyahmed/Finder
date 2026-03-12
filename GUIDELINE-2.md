# Task Understanding & Step-by-Step Guide

## Overview

This project involves two major steps:
1. **Preparing a REPO** - Setting up the codebase with Docker, frozen dependencies, and updated documentation
2. **Evaluating Model Solutions** - Testing and comparing model responses to select the best solution


--- 
## STEP 2: Evaluating Model Solutions

### Objective
Provide the prepared repository with an issue to two models (Model A and Model B), evaluate their solutions, and select the best performing solution for each iteration.

### Prerequisites
- [x] Step 1 completed (repo prepared with Dockerfile, frozen dependencies, updated README)
- [x] Issue title and description ready
- [x] HFI tool installed and configured
- [x] VS Code installed and configured
- [x] tmux installed and configured

### Checklist

#### 2.1 Issue Preparation
- [x] Review issue title and description
- [x] Ensure issue is complex enough (should not be solvable in 2 interactions)
- [x] Verify issue is well-scoped (not too broad, not too trivial)
- [x] Issue should include:
  - [x] Clear title
  - [x] Detailed description
  - [x] No links-only descriptions

##### 2.1.1 Rewriting the Issue Description
Rewrite the issue description in your own words before using it as a prompt. The goal is a natural, freeform prompt that a developer might actually write — not a copy-paste of the original issue.

**Rules:**
- State the problem and the expected solution **clearly and explicitly**
- Remove any links or images from the original issue description
- Do **not** add information that is not already present in the issue (e.g., do not mention writing tests unless the issue specifically asks for them)
- Keep the same scope and intent as the original — just rephrase it naturally

#### 2.2 Start HFI Session
- [x] Navigate to repository folder
    - Windows paths are mounted under `/mnt/`
    - `C:\` becomes `/mnt/c/`
    - `C:\Users\rebum\OneDrive\Desktop\rebirth\task_27\dbx` becomes `/mnt/c/Users/rebum/OneDrive/Desktop/rebirth/task_27/dbx`
    - Navigate with:
      ```bash
      cd /mnt/c/Users/rebum/OneDrive/Desktop/rebirth/task_27/dbx
      ```
    - **Note:** Use forward slashes `/` in WSL, not backslashes `\`
    - **OneDrive paths:** OneDrive folders are accessible in WSL at `/mnt/c/Users/<username>/OneDrive/...`

#### 2.2.1 Tmux Session Management
**Creating and Managing Tmux Sessions:**

- [x] **Create a named tmux session:**
  ```bash
  tmux new -s task
  ```
  This creates a persistent session named "task" that survives terminal disconnections.

- [x] **List all tmux sessions:**
  ```bash
  tmux ls
  ```
  Shows all active tmux sessions with their names and status.

- [x] **Attach to an existing session:**
  ```bash
  tmux attach -t task
  # or shorter:
  tmux a -t task
  ```
  Reconnects to a session if you disconnected or closed your terminal.

- [x] **Detach from tmux session (without killing it):**
  - Press `Ctrl+B`, then press `D`
  - Or type: `tmux detach`
  - Session continues running in background

- [x] **Kill a tmux session:**
  ```bash
  tmux kill-session -t <session-name>
  # Example:
  tmux kill-session -t task
  tmux kill-session -t 68a8b9b2-4513-411f-adb8-9cc06ab52a03
  tmux kill-session -t 68a8b9b2-4513-411f-adb8-9cc06ab52a03-B
  ```
  Only use this when you're sure you don't need the session anymore.
  
- [x] **Kill all tmux sessions:**
  ```bash
  tmux kill-server
  ```
  **Warning:** This kills ALL tmux sessions. Use with caution!
  
- [x] **Kill multiple specific sessions:**
  ```bash
  # Kill session A
  tmux kill-session -t 68a8b9b2-4513-411f-adb8-9cc06ab52a03
  
  # Kill session B
  tmux kill-session -t 68a8b9b2-4513-411f-adb8-9cc06ab52a03-B
  ```

- [x] **Rename a tmux session:**
  ```bash
  tmux rename-session -t old-name new-name
  ```

**Recovery and Best Practices:**

- [x] **Save HFI trajectory session IDs immediately:**
  - When HFI starts, it provides trajectory session IDs like: `68a8b9b2-4513-411f-adb8-9cc06ab52a03-A`
  - Save these to a text file for easy reference
  - Example: Create `hfi-sessions.txt` with both trajectory IDs

- [x] **Attach to HFI trajectory sessions:**
  ```bash
  # Trajectory A
  tmux attach -t 68a8b9b2-4513-411f-adb8-9cc06ab52a03-A
  
  # Trajectory B (in another terminal)
  tmux attach -t 68a8b9b2-4513-411f-adb8-9cc06ab52a03-B
  ```

- [x] **If you lose connection or something goes wrong:**
  1. List all sessions: `tmux ls`
  2. Find your HFI trajectory sessions (they'll have the UUID in the name)
  3. Attach to them: `tmux attach -t <session-id>`
  4. Your work will still be there - tmux sessions persist until explicitly killed

- [x] **Create a recovery script:**
  Save this to `attach-trajectories.sh`:
  ```bash
  #!/bin/bash
  # Replace with your actual session IDs
  TRAJECTORY_A="68a8b9b2-4513-411f-adb8-9cc06ab52a03-A"
  TRAJECTORY_B="68a8b9b2-4513-411f-adb8-9cc06ab52a03-B"
  
  echo "Attaching to Trajectory A..."
  tmux attach -t $TRAJECTORY_A &
  
  echo "Attaching to Trajectory B..."
  tmux attach -t $TRAJECTORY_B &
  ```

- [x] **Multiple terminal windows:**
  - Open multiple terminal windows/tabs to monitor both trajectories simultaneously
  - Each terminal can attach to a different tmux session
  - Use `tmux split-window` within a session to see multiple panes

- [x] **Session persistence:**
  - Tmux sessions survive:
    - Terminal window closure
    - SSH disconnections
    - System reboots (if tmux server is configured to persist)
    - Network interruptions
  - Always check `tmux ls` before creating new sessions to avoid duplicates

#### 2.2.2 Start HFI Tool
After navigating to the repository folder (and optionally creating a tmux session), start the HFI tool:

Before that:
git config --global core.fileMode false

# Then unstage any permission changes that were auto-staged
git reset HEAD
git checkout -- .


- [x] **Start HFI in VS Code mode:**
  ```bash
  claude-hfi --vscode
  ```
  - This will start the HFI interface and create trajectory sessions automatically
  - HFI will create its own tmux sessions for trajectories A and B (you don't need to create these manually)
  - The command will output trajectory session IDs that you should save

- [x] **Authenticate via browser:**
  - HFI will open a browser window for Auth0 login
  - Use your Rebirth expert email to log in
  - Complete the authentication process

- [x] **Enter HFI code:**
  - When prompted, enter: `cc_agentic_coding`
  - This code identifies the project type

- [x] **Save session information:**
  - Save the Anthropic UUID (session ID) to a text file immediately
  - Save the trajectory session IDs (A and B) that HFI displays
  - Example output:
    ```
    Trajectory A:
      Worktree: /path/to/worktree/A
      Terminal: tmux attach -t <session-id-A>
    
    Trajectory B:
      Worktree: /path/to/worktree/B
      Terminal: tmux attach -t <session-id-B>
    ```
  - Create a file like `hfi-sessions.txt` with this information for easy recovery

#### 2.3 First Prompt
- [x] Enter the issue title and description as the first prompt
- [x] Do NOT add extra context or instructions
- [x] Prompt should only contain:
  - [x] Issue title
  - [x] Issue description
- [x] Submit the prompt
- [x] Wait for Model A and Model B responses (3-15 minutes)

#### 2.4 Monitor Trajectories
- [x] Open integrated terminals in VS Code:
  - [x] Trajectory A: `tmux attach -t <session-id-a>`
  - [x] Trajectory B: `tmux attach -t <session-id-b>`
- [x] Watch for permission prompts and user input requests
- [x] Monitor both terminals for completion
- [x] Pause task on Rebirth platform while models are running

#### 2.5 Evaluate Model Responses
For each interaction, evaluate both Model A and Model B responses:

- [x] **Check Changes:**
  - [x] Review code changes made by Model A
  - [x] Review code changes made by Model B
  - [x] Compare implementation approaches

- [x] **Run Tests:**
  - [x] Run tests for Model A's solution
  - [x] Run tests for Model B's solution
  - [x] Verify both solutions work correctly

- [x] **Check Best Practices:**
  - [x] Verify appropriate documentation is added
  - [x] Verify commits are made regularly with meaningful messages
  - [x] Verify model reviewed its own work
  - [x] Verify model ran tests to validate fixes
  - [x] Verify model follows software engineering best practices

- [x] **Check Production Readiness:**
  - [x] Feature implemented thoroughly and completely
  - [x] Edge cases considered and handled
  - [x] Security implications considered (if applicable)
  - [x] No unnecessary comments (no chain-of-thought, no obvious explanations)
  - [x] Code matches existing codebase style
  - [x] Well-factored code with reasonable abstractions
  - [x] Comprehensive tests in codebase style (if applicable)


#### 2.6 Submit Preferences

**Evaluation Document Format:**
Create and save a text file named `iteration{N}_evaluation.txt` in the task folder (e.g., `iteration1_evaluation.txt`, `iteration2_evaluation.txt`). This file serves as a permanent record of your evaluation for each iteration. Use the following structure:
```
====================================================================================================
ITERATION {N} EVALUATION
====================================================================================================

====================================================================================================
MODEL A PROS:
====================================================================================================

[Concise paragraph without bullet points]

====================================================================================================
MODEL A CONS:
====================================================================================================

[Concise paragraph without bullet points]

====================================================================================================
MODEL B PROS:
====================================================================================================

[Concise paragraph without bullet points]

====================================================================================================
MODEL B CONS:
====================================================================================================

[Concise paragraph without bullet points]


====================================================================================================
AXIS SELECTIONS:
====================================================================================================

Logic and correctness: [selection]

Naming and clarity: [selection]

Organization and modularity: [selection]

Interface design: [selection]

Error handling and robustness: [selection]

Comments and documentation: [selection]

Review/merge readiness: [selection]


====================================================================================================
OVERALL PREFERENCE JUSTIFICATION:
====================================================================================================

[Concise paragraph synthesizing key differences and reasoning]


Axis Selection
Overall preference: A or B


====================================================================================================
NEXT INSTRUCTION
====================================================================================================

[Single instructional paragraph without praise, directly stating what needs to be done]
```

**Closeness Indicators:**
Select the position on each axis using these indicators:
- **A** = Strongly prefer A
- **AA** = Prefer A
- **AAA** = Slightly prefer A
- **AAAA** = Very slightly prefer A (closest to center, leaning A)
- **BBBB** = Very slightly prefer B (closest to center, leaning B)
- **BBB** = Slightly prefer B
- **BB** = Prefer B
- **B** = Strongly prefer B
- **N/A** = Not applicable to this iteration (use sparingly - typically one model is better)

**Axes to evaluate:**
- [ ] **Overall preference**
  - Choose the better answer overall
  - Select: A or B
  - **Important:** Do not let response streaming speed affect your choice
  
- [ ] **Logic and correctness**
  - Which code has better logic and correctness?
  - Considers: correct implementation of requirements, absence of bugs, proper algorithm/data structure choices
  - Prioritize: actual test results over theoretical correctness, validation in target environments (Docker, CI/CD)
  - Select: A / AA / AAA / AAAA / BBBB / BBB / BB / B / N/A

- [ ] **Naming and clarity**
  - Which code has better naming and clarity?
  - Considers: variable/function names, code readability, self-documenting code
  - Select: A / AA / AAA / AAAA / BBBB / BBB / BB / B / N/A

- [ ] **Organization and modularity**
  - Which code has better organization and modularity?
  - Considers: file structure, function decomposition, separation of concerns, dependency management
  - Select: A / AA / AAA / AAAA / BBBB / BBB / BB / B / N/A

- [ ] **Interface design**
  - Which code has better interface design?
  - Considers: API design, function signatures, abstraction levels
  - Select: A / AA / AAA / AAAA / BBBB / BBB / BB / B / N/A

- [ ] **Error handling and robustness**
  - Which code has better error handling and robustness?
  - Considers: validation, edge cases, graceful failure, meaningful error messages
  - Prioritize: actual crash handling, validation of user inputs, safe handling of missing dependencies
  - Select: A / AA / AAA / AAAA / BBBB / BBB / BB / B / N/A

- [ ] **Comments and documentation**
  - Which code has better comments and documentation?
  - Considers: code comments, docstrings, commit messages, README updates
  - Select: A / AA / AAA / AAAA / BBBB / BBB / BB / B / N/A

- [ ] **Review/merge readiness**
  - Which code is more ready for review/merge?
  - Considers: passes tests, follows conventions, complete implementation, production-ready
  - Prioritize: working in target environments, portable solutions, no risky workarounds
  - Select: A / AA / AAA / AAAA / BBBB / BBB / BB / B / N/A
  - This axis is always applicable

**Critical Evaluation Principles:**

**What to Look For:**
- **Actual results over theoretical benefits**: If tests pass in Docker, that proves correctness better than theoretical claims
- **Working solutions in target environments**: Does it work in Docker/CI/CD where it will actually be used?
- **Alignment between axis selections and pros/cons**: Your axis preferences should match the strengths/weaknesses you document
- **Practical engineering decisions**: Pragmatic solutions that work are often better than complex ideal solutions
- **Production-ready patterns**: Proper validation, dependency injection, error handling, portable code
- **Scope adherence**: Changes should address the specific issue requirements, not add unrelated improvements
- **Incremental improvements**: Each iteration should make meaningful progress on identified cons

**What to Avoid:**
- **N/A overuse**: Rarely use N/A - one model is almost always better on each axis. Only use when truly not applicable (e.g., interface design when no interfaces were created)
- **Bias toward complexity**: Don't automatically favor more complex solutions; simpler working solutions often win
- **Ignoring real failures**: If tests fail in Docker but pass locally, that's a critical issue
- **Misalignment**: Don't select A for "logic and correctness" if Model A's tests completely failed
- **Praise in instructions**: Next instructions should be direct, not "Good work, now do X"
- **Risky workarounds**: Solutions using --break-system-packages, hard-coded paths, or bypassing safety mechanisms should be penalized
- **Scope creep**: Don't expect or reward changes beyond the issue requirements
- **Mocking bias**: Mocking dependencies is an acceptable production-ready pattern - don't penalize it for "not testing real implementation" if it provides adequate coverage

**Alignment Check:**
Before finalizing, verify:
- [ ] If Model A wins overall, do most axes favor Model A?
- [ ] Do axis selections match the severity of pros/cons?
- [ ] Does "Logic and correctness" align with actual test results?
- [ ] Does "Review/merge readiness" reflect whether code works in production environments?
- [ ] Are cons proportional (critical bugs vs minor style issues)?

#### 2.7 Document Pros and Cons

For each iteration, document the following in **concise, cohesive paragraphs** (not bullet points). Write as continuous prose with specific examples integrated naturally into sentences.

**Model A Pros:**
- [ ] What did Model A do well? 
- [ ] Include specific examples: function names, file changes, test counts, commit messages, Docker results
- [ ] Focus on actual achievements: "tests passed in Docker (26 passed in 0.25s)", "refactored 7 components to use dependency injection", "added explicit validation with meaningful error messages"
- [ ] Mention engineering decisions that proved correct
- [ ] Reference concrete numbers: lines of code, test coverage, file counts

**Example Good Pros:**
> Model A refactored 7 components (ConsoleWidget, DevicesListWidget, BrokerDialog, BSSIdDialog, PatternsDialog, PrefsDialog, TasmotaDevicesModel) to accept settings as required constructor parameters, enforcing true dependency injection by removing all QSettings imports from child components. Model A's tests successfully passed in Docker (26 passed in 0.25s) without requiring additional system dependencies, proving the portable mocking approach works in containerized environments. Model A added explicit directory validation using validate_directory() function that checks for file vs directory conflicts and parent directory existence before allowing operations.

**Model A Cons:**
- [ ] What could Model A improve?
- [ ] Be proportional: distinguish critical bugs from minor issues
- [ ] Include specific examples of the issue
- [ ] Avoid vague criticism: instead of "could be better", explain what's missing or wrong
- [ ] Focus on production-readiness concerns within task scope

**Example Good Cons:**
> Model A's exec() approach duplicates validate_directory and resolve_paths functions in the test file requiring manual updates if implementation changes. Model A's menu button tests mock QDesktopServices.openUrl() calls without testing actual integration with the system file browser, though this is acceptable for unit testing core logic.

**Avoid:**
- Generic statements: "could have better error handling" (be specific about which errors)
- Out-of-scope criticism: "missing documentation" when docs aren't required
- Overly harsh criticism of valid approaches: "mocking is bad" (mocking can be production-ready)
- Contradicting your axis selections: don't say "poor logic" in cons if you selected A for logic

**Model B Pros:**
- [ ] Follow same guidelines as Model A Pros
- [ ] Include specific achievements even if overall solution has issues
- [ ] Acknowledge good engineering decisions even when other aspects failed

**Model B Cons:**
- [ ] Follow same guidelines as Model A Cons
- [ ] **Highlight critical failures prominently**: Use bold for test failures, import errors, or broken functionality
- [ ] Distinguish between "didn't work" (critical) vs "could be improved" (minor)
- [ ] Connect cons to axis selections (critical cons should reflect in axis preferences)

**Example Critical Con:**
> **Model B's tests completely failed in Docker with ImportError: libgssapi_krb5.so.2 cannot open shared object file - 0 tests collected, 1 error during collection.** PyQt5 requires additional system dependencies not installed in the Dockerfile. Model B used --break-system-packages flag which bypasses system package manager protection and is strongly discouraged in Python ecosystem.

**Overall Preference Justification:**
- [ ] Synthesize key differences between models
- [ ] Explain why the winning model wins (not just repeat pros)
- [ ] Address the most critical factors: actual results, production readiness, scope adherence
- [ ] Acknowledge trade-offs: "While Model B has X benefit, Model A's Y is more important because..."
- [ ] Use **bold** for critical points: **actual Docker test results prove Model A works while Model B fails**
- [ ] Connect to production-ready definition: working in target environments, proper validation, no risky workarounds

**Example Good Justification:**
> I prefer Model A because **actual Docker test results prove Model A works while Model B fails**. Model A's tests passed successfully in Docker (26 passed in 0.25s) while Model B's tests failed with ImportError collecting 0 tests due to missing system libraries. Model A's pragmatic approach of mocking dependencies is an acceptable and production-ready testing strategy that creates portable tests working in any environment without complex dependency installation. While mocking means some integration aspects aren't tested, the core logic validation Model A provides is sufficient for production readiness and the tests successfully pass in the containerized environment specified by the prompt.

**Important Writing Guidelines:**
- [ ] Every response should have both pros and cons (there's always room for improvement)
- [ ] Write in paragraph form, not bullet points
- [ ] Be concise but include specific examples with numbers, file names, function names
- [ ] Short and terse is better than long and verbose
- [ ] Integrate multiple points into flowing sentences rather than listing separately
- [ ] Use natural transitions: "Additionally", "Furthermore", "However", "While"

**Proportionality in Evaluation:**
- [ ] Critical issues (tests fail, crashes, wrong implementation): Major impact on axes and overall preference
- [ ] Moderate issues (missing validation, no error messages, suboptimal patterns): Moderate impact
- [ ] Minor issues (naming, comments, verbosity): Minor impact, rarely changes overall preference
- [ ] If one model's tests pass and the other fails completely, this should dominate the evaluation

**Evaluation Focus by Iteration:**
- [ ] **Iteration 1**: Focus on correctness of initial implementation, whether all acceptance criteria are met
- [ ] **Iteration 2+**: Focus on how well the model addressed previous iteration's identified cons
- [ ] **Final iterations**: Focus on production readiness, test coverage, whether solution is complete

**Note:** 
- If model only commits code in this turn, focus on "Review/merge readiness" and "Overall preference"
- If model writes new code, evaluate all applicable axes
- Your preference for a specific axis does not need to match overall preference
- Use closeness indicators (A, AA, AAA, AAAA, BBBB, BBB, BB, B) to show how close the comparison is on each axis

**Submitting Preferences in HFI:**
- [ ] For each iteration, submit your preferences directly in the HFI interface
- [ ] Fill out all applicable evaluation axes in the HFI web interface or terminal interface
- [ ] Select your preferences using the closeness indicators (A, AA, AAA, etc.) for each axis
- [ ] Choose overall preference (A or B)
- [ ] Click "Submit" or use the submit option in the HFI interface to save your evaluation for that iteration
- [ ] Repeat this process for each iteration until the solution is production-ready

#### 2.8 Iterate with Follow-up Prompts

If solution is not production-ready, write the next instruction and add it to the evaluation document.

**Prompt Writing Principles:**

**DO:**
- [ ] Write as a direct, instructional paragraph (not bulleted or numbered lists)
- [ ] Be specific about what needs to change: file names, function names, specific issues
- [ ] Focus on addressing the documented cons from the current iteration
- [ ] Think of it as actionable code review feedback
- [ ] Ensure the prompt will result in meaningful changes (aim for 4+ file edits if substantial work needed)
- [ ] Focus on Python code changes, architecture improvements, and test coverage
- [ ] Keep within the scope of the original task/issue

**IMPORTANT - Models are NOT expected to run Docker:**
- [ ] Models should focus on writing/modifying Python code, tests, and documentation
- [ ] Do NOT ask models to run Docker commands - YOU (the evaluator) will run Docker to verify
- [ ] Prompts should request code changes, not execution verification
- [ ] The evaluator runs `docker build` and `docker run` to test the model's code changes

**DO NOT:**
- [ ] Use praise or pleasantries: "Good work", "Great job", "Well done", "Thanks for"
- [ ] Be vague: "improve the code", "make it better", "fix issues"
- [ ] Increase scope beyond the original task requirements
- [ ] Use bullet points or numbered lists in the prompt
- [ ] Give away the answer - instruct on patterns/principles, not specific code
- [ ] Use AI tools to write follow-up prompts (write them yourself based on evaluation)

**Good Next Instruction Examples:**

**Example 1 - Addressing Missing Validation:**
> Your implementation correctly handles the basic path resolution but lacks validation for edge cases. Add explicit validation in resolve_paths to check if provided directories are files rather than directories, and verify parent directories exist before attempting to create subdirectories. Update the crash handler to safely access logging handlers using try-except blocks instead of assuming handlers[0] exists. Replace QDir.tempPath() with tempfile.gettempdir() as the former requires QApplication to be instantiated. Run the tests to verify all edge cases are properly handled.

**Example 2 - Addressing Architecture/Modularity:**
> The filtering logic is currently embedded directly in the parse function, making it difficult to test in isolation and reuse across different contexts. Extract the filtering logic into a dedicated filter module with a standalone function that takes a table and selection criteria as inputs and returns a boolean. This separation allows unit testing the filter logic independently from the parsing logic and makes it reusable for other algorithms that may need the same selection behavior.

**Example 3 - Addressing Architecture Issues:**
> Your implementation uses global QSettings.setPath() but child components still create their own QSettings instances, leading to configuration inconsistency. Refactor the architecture to use dependency injection - modify ConsoleWidget, DevicesListWidget, BrokerDialog, BSSIdDialog, PatternsDialog, PrefsDialog, and TasmotaDevicesModel to accept settings objects as required constructor parameters. Remove QSettings imports from these child components and pass self.settings from MainWindow when instantiating them. This ensures all components use the same configuration source determined by command-line arguments.

**Example 4 - Addressing Test Requirements:**
> Your implementation is complete but lacks test coverage. Write comprehensive unit tests for the new filter module covering each rule type independently: name-based prefix matching, schema-based matching, and wildcard pattern matching. Add parametrized tests that verify AND logic works correctly when rules contain comma-separated conditions, and verify OR logic works when multiple -s flags are provided. Include edge case tests for empty rules, invalid rule formats, and case sensitivity behavior.

**Example 5 - Final Polish:**
> The implementation is functionally complete. Update the CLI documentation to reflect the new selection syntax including examples for each rule type. Add docstrings to all new public functions explaining their parameters, return values, and usage. Ensure the help text for --select and --exclude flags accurately describes the supported rule formats and the AND/OR logic behavior.

**Bad Next Instruction Examples:**

**Bad Example 1 - Using Praise:**
> Good work on the implementation! Now please add validation for edge cases and improve error handling. Also, the tests look great but could use more coverage.

**Why it's bad:** Starts with praise, vague about what to add/improve

**Bad Example 2 - Bullet Points:**
> Please make the following changes:
> - Add validation to resolve_paths
> - Fix the crash handler
> - Replace QDir.tempPath()
> - Run tests

**Why it's bad:** Uses bullet points instead of paragraph, less context on why changes are needed

**Bad Example 3 - Scope Creep:**
> Add validation, write comprehensive documentation including API docs and user guide, implement logging throughout the application, add configuration file schema validation, create integration tests, and set up CI/CD pipeline.

**Why it's bad:** Adds requirements (comprehensive docs, CI/CD) beyond the original task scope

**Bad Example 4 - Too Vague:**
> Your code has some issues. Please review and fix them. Make sure everything works properly and follows best practices.

**Why it's bad:** Doesn't specify what issues, what to fix, or what "works properly" means

**Prompt Iteration Strategy:**
- [ ] **Iteration 1→2**: Focus on critical bugs, missing acceptance criteria, fundamental architecture issues
- [ ] **Iteration 2→3**: Focus on code organization, modularity, and test coverage
- [ ] **Iteration 3→4**: Focus on documentation, edge cases, and final polish
- [ ] **Each iteration**: Ensure prompt addresses specific cons identified in the evaluation
- [ ] **Final iteration**: Request documentation updates and ensure all tests are comprehensive

**Verification:**
Before finalizing next instruction:
- [ ] Is it a paragraph (not bullets/numbers)?
- [ ] Does it avoid praise and pleasantries?
- [ ] Is it specific about what to change?
- [ ] Will it result in meaningful file edits (4+ for substantial work)?
- [ ] Does it stay within the task scope?
- [ ] Does it address the documented cons?
- [ ] Does it focus on code changes (NOT asking model to run Docker)?
- [ ] Does it guide toward better architecture without giving away the exact solution?

**After Writing Prompt:**
- [ ] Add instruction to the evaluation document under "NEXT INSTRUCTION" section
- [ ] Submit follow-up prompt to both models
- [ ] Wait for Model A and Model B responses
- [ ] Repeat evaluation process (sections 2.5-2.7)
- [ ] Continue iterating until solution is production-ready

**Evaluation Quality Checklist:**

Before finalizing any iteration evaluation, verify:

**Format:**
- [ ] **Saved evaluation to file**: Write evaluation to `iteration{N}_evaluation.txt` in the task folder
- [ ] Used correct file name: `iteration{N}_evaluation.txt`
- [ ] Followed exact format with section separators (====...====)
- [ ] All sections present: Axis Selections, Model A Pros, Model A Cons, Model B Pros, Model B Cons, Overall Preference Justification, Next Instruction

**Axis Selections:**
- [ ] Overall preference is A or B (not both)
- [ ] Each axis uses correct indicators: A/AA/AAA/AAAA/BBBB/BBB/BB/B/N/A
- [ ] N/A used sparingly (only when truly not applicable)
- [ ] Axis selections align with pros/cons severity
- [ ] Logic and correctness reflects actual test results
- [ ] Review/merge readiness reflects production-ready status

**Pros and Cons:**
- [ ] Written as paragraphs, not bullet points
- [ ] Include specific examples: file names, function names, numbers, test results
- [ ] Short and concise (avoid verbosity)
- [ ] Both models have pros and cons listed
- [ ] Critical issues highlighted with **bold**
- [ ] Proportional severity (don't treat minor issues as critical)
- [ ] Connected to axis selections

**Overall Justification:**
- [ ] Synthesizes key differences (doesn't just repeat pros)
- [ ] Explains why the winner wins with specific reasoning
- [ ] Critical points in **bold**
- [ ] Addresses trade-offs between models
- [ ] Connects to production-ready criteria

**Next Instruction:**
- [ ] Written as single instructional paragraph
- [ ] No praise, pleasantries, or bullet points
- [ ] Specific about what to change
- [ ] Addresses documented cons
- [ ] Includes verification steps
- [ ] Stays within task scope
- [ ] Will result in meaningful changes (4+ file edits if substantial)

**Content Quality:**
- [ ] Evaluation based on actual changes made in this specific iteration
- [ ] Prioritizes actual results (test passing/failing) over theory
- [ ] Considers production environment (Docker, CI/CD)
- [ ] No bias toward complexity (simple working solutions can win)
- [ ] No unfair penalization of valid patterns (mocking, pragmatic approaches)
- [ ] Proper context of what "production-ready" means for this task

#### 2.9 Final Submission
When solution reaches production-ready state:

**Step 1: Verify and Complete HFI Evaluations**
- [ ] Ensure you have submitted preferences for all iterations in the HFI interface
- [ ] Verify all evaluation axes have been filled out for each iteration
- [ ] Double-check that your overall preferences are recorded for each iteration

**Step 2: Finish HFI Interaction**
- [ ] Verify model has committed all final changes
- [ ] Press `Ctrl+C` in the control terminal (where you ran `claude-hfi --vscode`) to finish the interaction
- [ ] This will close the HFI session and finalize the trajectory data

**Step 3: Verify Commits and Generate Deliverables**
- [ ] Verify all commits are present in original repo folder:
  ```bash
  git log
  ```
- [ ] Generate TAR file from source repository folder:
  ```bash
  tar -cf task_1.tar csaps
  ```
- [ ] Include Anthropic task UUID (session ID saved earlier) in your submission

**Step 4: Submit on Platforms**
- [ ] Submit TAR file on Rebirth platform
- [ ] Submit task on Claude HFI platform:
  - Navigate to the HFI web interface or platform
  - Locate your task using the Anthropic UUID (session ID)
  - Complete any final submission steps required by the HFI platform
  - Ensure all evaluations and feedback are properly saved
- [ ] Mark task as finished successfully (if applicable)

---

## Production-Ready Definition

A solution is production-ready when you can answer "yes" to:
> "If the model was my co-worker and presented me with this code in a PR, would I happily approve the PR?"

### Production-Ready Code Must:
- ✅ Implement the feature requested thoroughly and completely
- ✅ Consider legitimate edge cases and handle them
- ✅ Consider security implications (where appropriate)
- ✅ Not contain comments that add no value
- ✅ Match the style of the existing codebase
- ✅ Be well-factored with reasonable abstractions
- ✅ Include comprehensive tests in codebase style (if applicable)

---

## Quick Reference Commands

### Step 1 Commands
```bash
# Checkout base commit
git checkout <base_sha>

# Configure git
git config user.name "PR writer"
git config user.email "pr-writer@example.com"

# Delete lock files
find . -name "*.lock" -type f -delete

# Build Docker
docker build -t <project-name> .

# Run tests in Docker
docker run <project-name> <test-command>

# Freeze dependencies
docker run --rm <image-name> pip freeze

# Commit changes
git add .
git commit --author="PR writer <pr-writer@example.com>" -m "Setup: Add Dockerfile, freeze dependencies, and update README"
```

### Step 2 Commands
```bash
# Navigate to repository
# WSL example:
cd /mnt/c/Users/rebum/OneDrive/Desktop/rebirth/task_27/dbx
# Native Linux/Mac example:
# cd /path/to/repository

# Verify you're in the right place
pwd
ls -la

# Start tmux
tmux new -s task

# Start HFI
claude-hfi --vscode

# List all tmux sessions
tmux ls

# Attach to trajectory
tmux attach -t <session-id>
# or shorter:
tmux a -t <session-id>

# Detach from tmux (without killing)
# Press Ctrl+B, then D
# Or:
tmux detach

# Attach to main task session
tmux attach -t task

# Kill a session (use carefully)
tmux kill-session -t <session-name>

# Rename a session
tmux rename-session -t old-name new-name

# Generate TAR
tar -czf <project-name>-final.tar.gz .
```

### Tmux Session Recovery
If something goes wrong or you need to reconnect:

```bash
# 1. List all active sessions
tmux ls

# 2. Find your HFI trajectory sessions (they contain UUIDs)
# Example output:
# 68a8b9b2-4513-411f-adb8-9cc06ab52a03-A: 1 windows (created ...)
# 68a8b9b2-4513-411f-adb8-9cc06ab52a03-B: 1 windows (created ...)
# task: 1 windows (created ...)

# 3. Attach to the sessions you need
tmux attach -t 68a8b9b2-4513-411f-adb8-9cc06ab52a03-A
tmux attach -t 68a8b9b2-4513-411f-adb8-9cc06ab52a03-B

# 4. If sessions don't appear, check if tmux server is running
tmux list-sessions

# 5. If you need to find session IDs from HFI output, check:
# - The terminal where you ran claude-hfi --vscode
# - Your saved session ID file (hfi-sessions.txt)
# - The HFI tool output which shows trajectory session IDs
```

---

## Notes

- Always work from the original repository folder, never worktrees
- **WSL Path Navigation:**
  - Windows `C:\` drive is accessible at `/mnt/c/` in WSL
  - Always use forward slashes `/` in WSL, never backslashes `\`
  - Example: `C:\Users\rebum\Desktop\project` → `/mnt/c/Users/rebum/Desktop/project`
  - OneDrive paths: `/mnt/c/Users/<username>/OneDrive/...`
  - You can verify your current path with `pwd` command
  - Your specific path: `/mnt/c/Users/rebum/OneDrive/Desktop/rebirth/task_27/dbx`
- Save Anthropic UUID (session ID) immediately after starting HFI
- **Save HFI trajectory session IDs immediately** - write them to a file for easy recovery
- Tmux sessions persist across disconnections - use `tmux ls` and `tmux attach` to recover
- If you lose connection, your work is still in the tmux sessions - just reattach
- Verify all commits are present before generating TAR
- Each model response should have both pros and cons
- Continue iterating until solution is production-ready
- Pause Rebirth task when models are running (3-15 minutes per response)
- **Always check `tmux ls` before creating new sessions** to avoid duplicates