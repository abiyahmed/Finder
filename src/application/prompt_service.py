"""
Prompt generation service.
Application layer - generates AI prompts for evaluation workflow.
"""


class PromptService:
    """Service for generating AI prompts."""

    @staticmethod
    def generate_evaluation_prompt(
        iteration_num: int,
        issue_context: str,
        model_a_response: str,
        model_b_response: str,
    ) -> str:
        """
        Generate a comprehensive evaluation prompt for external AI.

        Args:
            iteration_num: The iteration number (1, 2, 3, etc.)
            issue_context: The issue title and description
            model_a_response: Full response/output from Model A
            model_b_response: Full response/output from Model B

        Returns:
            A prompt string to paste into Claude/ChatGPT
        """
        return f"""You are evaluating two AI model responses for a coding task.

## Issue Context
{issue_context}

## Model A Response
{model_a_response}

## Model B Response
{model_b_response}

## Evaluation Instructions

Evaluate both responses using these criteria and output in the EXACT format below.

**Axes to evaluate** (use indicators: A/AA/AAA/AAAA/BBBB/BBB/BB/B/N/A):
- Logic and correctness: correct implementation, absence of bugs, proper algorithms
- Naming and clarity: variable/function names, code readability
- Organization and modularity: file structure, separation of concerns
- Interface design: API design, function signatures, abstraction levels
- Error handling and robustness: validation, edge cases, graceful failure
- Comments and documentation: code comments, docstrings, README updates
- Review/merge readiness: passes tests, follows conventions, production-ready

**Closeness indicators**:
- A = Strongly prefer A
- AA = Prefer A
- AAA = Slightly prefer A
- AAAA = Very slightly prefer A (closest to center, leaning A)
- BBBB = Very slightly prefer B (closest to center, leaning B)
- BBB = Slightly prefer B
- BB = Prefer B
- B = Strongly prefer B
- N/A = Not applicable (use sparingly - one model is almost always better)

**What to prioritize**:
- Actual test results over theoretical correctness
- Working solutions in target environments (Docker, CI/CD)
- Scope adherence (changes should address the specific issue, not add unrelated improvements)
- Practical engineering decisions over complex ideal solutions

**What to avoid**:
- N/A overuse (rarely use N/A - one model is almost always better on each axis)
- Bias toward complexity (simpler working solutions often win)
- Ignoring real failures (if tests fail in Docker but pass locally, that's critical)
- Praise in next instructions (be direct, no "Good work")
- Mocking bias (mocking dependencies is an acceptable production-ready pattern)

**Writing style**:
- Write in concise paragraphs, NOT bullet points
- Include specific examples: file names, function names, test results, numbers
- Use **bold** for critical issues like test failures
- Short and terse is better than long and verbose

## Required Output Format

====================================================================================================
ITERATION {iteration_num} EVALUATION
====================================================================================================

====================================================================================================
MODEL A PROS:
====================================================================================================

[Concise paragraph with specific examples: file names, function names, test results, numbers]

====================================================================================================
MODEL A CONS:
====================================================================================================

[Concise paragraph - use **bold** for critical issues like test failures]

====================================================================================================
MODEL B PROS:
====================================================================================================

[Concise paragraph with specific examples]

====================================================================================================
MODEL B CONS:
====================================================================================================

[Concise paragraph - use **bold** for critical issues]

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

[Paragraph explaining why winner wins, with **bold** for critical points]

Overall preference: [A or B]

====================================================================================================
NEXT INSTRUCTION
====================================================================================================

[Single instructional paragraph - NO praise, NO bullet points, specific about what to change. If solution is production-ready, write "Solution is production-ready. No further iterations needed."]
"""

    @staticmethod
    def generate_next_instruction_prompt(
        issue_context: str,
        current_cons: str,
        winning_model: str,
    ) -> str:
        """
        Generate a prompt to help write the next instruction based on evaluation cons.

        Args:
            issue_context: The original issue title and description
            current_cons: The cons identified for the winning model
            winning_model: "A" or "B"

        Returns:
            A prompt string to paste into Claude/ChatGPT
        """
        return f"""Based on the evaluation below, write the next instruction for the AI model.

## Original Issue Context
{issue_context}

## Current Cons (from winning model {winning_model})
{current_cons}

## Instructions for Writing Next Prompt

Write a single instructional paragraph that:
- Addresses the specific cons identified above
- Is direct and actionable (no praise like "Good work", "Great job")
- Uses NO bullet points or numbered lists
- Specifies file names, function names, specific issues where applicable
- Stays within the original task scope (don't add new requirements)
- Will result in meaningful changes (aim for 4+ file edits if substantial work needed)
- Focuses on code changes (NOT asking to run Docker - the evaluator does that)
- Guides toward better architecture without giving away the exact solution

**Bad examples to avoid**:
- "Good work on the implementation! Now please add validation..."
- Starting with praise or pleasantries
- Vague requests like "improve the code" or "make it better"
- Bullet point lists

**Good example**:
"Your implementation correctly handles the basic path resolution but lacks validation for edge cases. Add explicit validation in resolve_paths to check if provided directories are files rather than directories, and verify parent directories exist before attempting to create subdirectories. Update the crash handler to safely access logging handlers using try-except blocks instead of assuming handlers[0] exists."

Output ONLY the next instruction paragraph, nothing else.
"""

    @staticmethod
    def generate_initial_prompt_template(issue_title: str, issue_body: str) -> str:
        """
        Generate the initial prompt to give to HFI (just the issue).

        Args:
            issue_title: The issue title
            issue_body: The full issue description/body

        Returns:
            The prompt to submit as the first interaction
        """
        return f"""{issue_title}

{issue_body}
"""

    @staticmethod
    def generate_final_submission_checklist() -> str:
        """Generate a checklist for final submission verification."""
        return """## Final Submission Checklist

Before submitting, verify:

1. [ ] All iterations evaluated and preferences submitted in HFI interface
2. [ ] Model has committed all final changes
3. [ ] Tests pass in Docker container
4. [ ] Solution is production-ready (would approve this PR)
5. [ ] All evaluation documents saved (iteration{N}_evaluation.txt)

## Final Steps

1. Press Ctrl+C in the control terminal to finish HFI interaction
2. Verify commits in original repo folder: `git log`
3. Generate TAR file: `tar -cf task_N.tar <repo_folder>`
4. Submit TAR file on Rebirth platform
5. Submit task on Claude HFI platform using session ID
"""
