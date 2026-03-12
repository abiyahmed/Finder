# Executing the task

<aside>
🧠

Key things to remember for this project:

- You need to execute **at least 10 realistic interactions with the model unless told otherwise.**
- **The tasks must be realistic and difficult.**
- Your goal is **to have a high-quality architectural discussion with a model.**
- You must evaluate the behavior of the models.
- You must NOT write code
- You must NOT ask the model to write any code
</aside>

## 1. Set up and start your task
     Instead of just planning an application from scratch, you can also go in a different direction, selecting an existing repository/app and discussing with the model its architecture.
    
    ➡️ In this case, if this codebase is already a git repository, you don't need to follow the steps above from “**Initialize an empty git repository**”.
    
    </aside>
    
3. **Start a `tmux` session**
    - Navigate to the repository folder
    - Start a tmux session there with `tmux new -s task`.
        - This step will help you in case your terminal crashes. It will enable you to reattach to the tmux session called `task`
4. **Start HFI**
    - Run `claude-hfi --vscode` inside the tmux terminal from the repository folder.
    - Two VS Code windows open automatically:
        - One for trajectory A's worktree
        - One for trajectory B's worktree
    - Control remains in your current terminal
5. **Authentication**
    - Browser opens for Auth0 login in the control terminal
    - Once authenticated, you're back at the prompt
6. **Attach the tmux session** with VScode
    1. Copy the command from claude-hfi and paste in the respective vscode window:
    
7. **Enter HFI (Human Feedback Interface) code:**
    - Always use the interface code (experiment ID)  `cc_code_behavior`
    

The green terminal output in VS Code A and B are the confirmation that everything is now ready! ✅ ✅

## 2. Come up with a complex and challenging initial prompt

This project is about interacting with a model to **plan and architect** systems. **The goal for now is not to generate any sort of application or code**. This means we're expecting a high-quality discussion.

**Topic ideas that you can use to get inspired for your prompt:**

- Code architecture optimization for performance at scale
- Comprehensive testing strategies and test suite creation
- System design for new architectural components
- Cross-service integration planning and implementation

**Example task**

```yaml
We have a backend service where users upload files and the API validates, processes, and stores the results synchronously before responding. As file sizes and concurrent uploads increased, requests started timing out and CPU usage spikes during peak traffic. How would you redesign this flow so the system remains responsive and scales reliably under higher load?

```

**Follow ups**

Pay attention to the kinds of questions an expert software architect would do, ask the model to answer with drawbacks between selecting one implementation vs another, clarification if it's unclear, expand the constraints until you are able to achieve 10+ interactions.

```yaml
# 1 - Ask for clarification
How would you handle retries and failure recovery if processing is no longer tied to the request lifecycle?

# 2 — Come up with an alternative idea
What if we change the upload endpoint so it only validates and stores the file, then immediately returns a job ID while a background worker handles the heavy processing asynchronously?

# 3 — Ask follow up questions regarding the proposed implementation
What would be the best way to test this so my tests are efficient and don't depend on asynchronous processes?

# 4 - Ask for specific implementation details
In more practical ways, how would you structure the classes in Rust to deal with this? Which library could I use to make it easier to maintain?  

# 5 — Add constraints
What if we move file processing to an asynchronous worker and return a job ID immediately, but with the constraint that we can’t introduce new infrastructure like managed queues or external job systems—how would you design this using only the existing database and services, and what risks would that introduce at scale?

...
```

**Core Deliverables**

- ✅ A high-quality and realistic conversation with the model as a staff/principal engineer would have with at least 10 interactions.
- ✅ The repository you used for this interaction
- ❌ You do not need to write or ask the model to make any changes to the code. Focus on the planning.

 

## 3. Send your prompt to the model and evaluate the different answers

<aside>
❗

**Keep your prompts straight to the point**

- Remove irrelevant information
- Do **not** add any new framing or requirements (no “act as an engineer”)
</aside>

<aside>
➡️

If Claude HFI asks for a GitHub repository, inform the repository link you are using in your task or if you are not using any repos, just type **N/A**.

</aside>

**Sending the prompt and evaluating the preferred response**

You must send your prompt to the model and evaluate the different answers in each one of the instances of VS Code.

📝 **Axis evaluation**

After each interaction once both models finish to respond, you'll be prompted on Claude HFI to respond a few alternative questions such as the preferred model response and evaluate the answers. 

Do not attach on the 'code' perspective, since this project is about System Design, Architecture and Strategy, observe the model response and try to answer. **In Claude HFI there are tips on how to interpret these questions not only considering generated code** (which is not the focus in this project)**.** In other words, you can “replace” the term ***code*** with ***system design/architecture/strategy*.** 

Here are the aspects you must evaluate:

- **Logic and correctness**
    
    Evaluate the correctness and robustness of the design/architecture implementation:
    
    - Does the implementation match the intended behavior?
    • Are edge cases and error conditions properly handled?
    • Is the control flow clear and free of subtle bugs?
    • Are there any off-by-one errors, null pointer exceptions, or race
    conditions?
    • Is the algorithm/approach correct for the problem being solved?
    • Are boundary conditions (empty inputs, maximum values, etc.) handled
    correctly?
- **Naming and clarity**
    
    Assess the quality of naming and clarity:
    
    - Do block, variable, function, and class names clearly express their purpose?
    • Is domain terminology used consistently throughout?
    • Are boolean names and conditions expressed positively when possible?
    • Do names avoid ambiguous abbreviations or insider knowledge?
    • Are assumptions about inputs, outputs, or behavior clearly documented?
    • Would a new developer understand what each component does from its name
    alone?
    • Are units clear in variable names (e.g., delaySeconds vs delay)?
- **Organization and modularity**
    
    Evaluate design and architecture structure and organization:
    
    - Are functions/methods focused on a single responsibility?
    • Is there duplicate code that should be extracted into reusable functions?
    • Are source files reasonably sized (not thousands of lines)?
    • Are functions/methods concise and focused (not hundreds of lines)?
    • Is related functionality grouped together logically?
    • Are abstraction levels consistent (not mixing high and low-level operations)?
    • Is there proper separation of concerns (I/O separate from business logic)?
    • Does each class have high cohesion (all methods relate to its purpose)?
    • Is cyclomatic complexity reasonable (avoiding deeply nested code)?
    • Are there parallel implementations of the same functionality?
- **Interface design (is normally `N/A`)**
    
- **Error handling**
    
    Evaluate error handling:
    
    - Are specific exception types used with contextual error messages?
    • Is there a consistent error handling strategy (fail fast vs recovery)?
    
    • Is input validation performed early at system boundaries?
    
    • Are errors properly propagated rather than silently swallowed?
    
    • Is resource management handled properly (files closed, memory freed)?
    
    • Are there any bare except clauses that could hide bugs?
    
    • Do error messages provide enough context to debug issues?
    
    • Are partial failures handled gracefully?
    
    • Is defensive programming used appropriately (not excessively)?
    
- **Comments and documentation**
    
    Assess the quality of comments and documentation:
    
    - Do comments explain WHY something is done, not WHAT is being done?
    • Are complex algorithms or business logic clearly explained?
    
    • Have comments been updated to match code changes?
    
    • Are there any AI-generated chain-of-thought comments that should be removed?
    • Are there placeholder comments saying code was removed/replaced?
    
    • Is there appropriate documentation for public APIs?
    
    • Are edge cases and non-obvious behavior documented?
    
    • Are there too many obvious comments that add noise?
    
    • Do comments provide value to future maintainers?
    
- **Review/production readiness**
    
    Evaluate if the code is production-ready and follows best practices:
    
    - Is there any debug code, print statements, or console.log calls?
    
    • Has all commented-out code been removed?
    
    • Is the code properly formatted according to project standards?
    
    • Are all temporary files, build artifacts, or test outputs removed?
    
    • Does the code follow the established conventions for the codebase?
    
    • Are commit messages clear and follow project guidelines?
    
    • Is version control hygiene maintained (no large binary files, etc.)?
    
    • Are all tests passing and coverage adequate?
    
    • Has the code been linted and does it pass static analysis?
    
    • Are there any hardcoded values that should be configurable?
    
    • Is sensitive information (passwords, keys) properly handled?
    

**Alternative questions**

After each interaction once both models finish to respond, you'll be prompted on Claude HFI to respond a few alternative questions such as the preferred model response and evaluate the answers in terms of:

- **behavior of the model**
- **logic and correctness**
- **naming and clarity**
- **organization and modularity**
- **interface design**
- **error handling**
- **comments and documentation**
- **review/production readiness.**

<aside>
💡

You must not evaluate **interface design** - Always select N/A for this question

</aside>

**Other questions**

- **Overall preference justification:** Justification about why you preferred the selected response.
    - 1-3 Descriptive and concise sentences. Be direct and clear. Don’t be generic and verbose.
- **Model A and model B Pros:** Write in a free-text format the pros of each one of the answers.
    - 1-3 Descriptive and concise sentences. Be direct and clear. Don’t be generic and verbose.
- **Model A and model B Cons:** ⚠️ Comma-delimited list of behavioral codes observed, with the file and line number where each issue first appeared (when applicable). If an issue could be interpreted as multiple categories, choose the most appropriate one
    - ✅ Format: `CODE, CODE:FILENAME:LINE`
    - ✅ E.g.: `HALLUC, VERBOSE:README.md:3, FILE:tsconfig.yaml:25`
    - ⚠️ If there's no file related to the issue you found you can simply use the CODE, like: `SCOPE,HALLUC:index.js:12`
    - ⚠️ In very rare scenarios such as when you face errors in the model response, you can leave CONS empty, but don't abuse this. This should be used maximum 2 times across all interactions.
    - ⚠️ You should always provide CONS at least for the model responses that you didn't choose as the best answer. Example:
        - If you selected the Model's A response was better, you MUST provide at least 1 CONS for Model's B response, because it had something wrong that made you chose for the Model's A answer.
    - ⚠️ If a whole file has a behavioral issue, inform the file, its extension and the 1st line, like: `DESTRUCT:index.js:1`
    - ⚠️ If a whole folder has a behavioral issue, inform the folder name and the 1st line, like: `HALLUC:src:1`
    
    <aside>
    ⚠️
    
    **MAKE SURE TO WRITE THE CONS IN THE CORRECT FORMAT**
    
    - Writing the cons as a free text will cause the task to be **rejected.**
        - ❌ E.g.: `The answer fails to provide a good looking UI`
    - Writing the cons with repeated CODEs will cause the task to be **rejected**.
        - ❌ E.g.: **`HALLUC**:index.js:12, **HALLUC**:README.md:3, FILE:tsconfig.yaml:25`
    - Writing the cons passing a file and not provide the line number is incorrect**.**
        - ❌ E.g.: **`HALLUC**:index.js`
    - If there are no files associated with the issue and it was a behavioral issue noticed only on the response of the model rather than files, you can simply write the behavioral CODE like:
        - ✅ E.g.: `HALLUC, LAZY`
    </aside>
    

### **Behavioral codes**

If you don't find one that is 100% accurate, select the closest one from the list below.

| Behavioral Issue | Code | Description | Examples of What to Watch For |
| --- | --- | --- | --- |
| **Early Stopping** | STOP | Model implies it will call a tool but doesn't actually make the tool call. | "I'll use [tool]" statements with no subsequent tool execution |
| **Laziness** | LAZY | Model doesn't complete tasks fully, or gives up early. | Abandons a task prematurely; provides some but not all of the requested functionality without explanation; leaves TODOs/placeholders; incomplete refactors |
| **Instruction Following Failures** | INST | Disregards explicit instructions from user or CLAUDE.md files | Model ignores CLAUDE.md directives; continues with approach after user rejection; makes edits when told "don't make changes" |
| **Overscoping** | SCOPE | Makes changes beyond what was requested; adds unrequested features; over-engineers the solution | Implements unrequested APIs or CLI arguments; cleans up unrelated code; adds unrequested backwards compatibility; excessive error handling/validation; defensive coding beyond requirements |
| **Tool Use Errors** | TOOL | Fails to invoke tools that should be used, or invokes them incorrectly | Describes changes as opposed to using tools like str_replace or file edit tools; model invokes a tool; invokes a tool with wrong arguments; reads small file chunks repeatedly instead of whole file |
| **Verification Failures** | VERIFY | Fails to validate that changes work correctly | Fails to catch issues that would have been caught if model ran tests, type check, or linter; provides insufficient test coverage; proceeds without confirming current step works |
| **False Claims of Success** | FALSE | Incorrectly claims that something is true | Claims that a feature was implemented that wasn't; claims tests pass without running them; makes unsubstantiated performance claims |
| **Fails to Address Root Cause** | ROOT | Addresses symptoms rather than root causes | Patches call sites instead of fixing underlying abstraction; adds try-catch to mask an issue; over-mocks tests; disables tests instead of fixing code; hardcoding or special-casing solutions |
| **Unauthorized Destructive Operations** | DESTRUCT | Attempts harmful, system-modifying, or irreversible operations without explicit permission | Deletes files without asking; runs git operations that undo user work (checkout, reset, force push); commits/pushes without permission; modifies system configs |
| **File-Related Issues** | FILE | Creates unnecessary files, modifies wrong files, or mismanages file operations | Creates many unnecessary new files; modifies wrong file despite clarification; writes outputs to files instead of user messages; creates files in wrong location |
| **Insufficient Context Gathering** | CONTEXT | Fails to gather necessary information before proceeding | Proceeds without understanding requirements; doesn't review codebase before changes; uses wrong package manager/APIs for environment |
| **Code Hallucinations** | HALLUC | Invents or assumes existence of functions, APIs, libraries, or code structures that don't exist | Assumes libraries are installed when they're not; invents API functions; creates imports from non-existent modules; assumes scripts/functions exist that don't |
| **Documentation Issues** | DOCS | Creates unwanted documentation or adds bad/unnecessary comments | Adds documentation when not requested; excessive code comments; creates README files unnecessarily; documents obvious things; poor quality inline documentation |
| **Verbose Dialogue** | VERBOSE | Provides unnecessary validation, overly long responses, or uses excessive formatting like emojis/markdown | Unnecessary praise ("You're absolutely right!"); unnecessary emojis/markdown in technical responses; excessively long explanations |

**🤔 What should I do if the AI Model A and/or B didn't generate any answer?**

- Add the code `STOP or LAZY` in the CONS and explain it in the overall justification field AND in the Conversation Feedback — Kira will handle that part.
- In this very particular situation you can leave the PROs for the model that didn't answer empty or you can write a brief sentence like: *“Can't evaluate. Model B didn't generate a response.”*
- Even without having answer for a Model, you should be able to answer the Axis considering the Model that responded. If ultimately it's not possible to evaluate even the Axis, make it clear in the Justification field.

Example of **Acceptable** justification when PROs/CONs/Axis are empty ✅

> “The preferred response is MODEL A because it more clearly explains how yield-based interleaving can violate assumptions made during submission, especially around refcount updates and shared dictionary mutations. It connects the concurrency model to concrete failure scenarios such as negative refcounts, dead actor references, and fetch resolution inconsistencies. In  the other hand, MODEL B didn't provide any answer, preventing the PROs to be defined and the Axis to be answered. Even so, it was added in the MODEL B CONS the Behav code `STOP`."
> 

Example of **Incorrect** justification when PROs/CONs/Axis are empty ❌

> “The preferred response is MODEL A because MODEL B didn't answer anything.”
> 

---

## 4. Send follow-up questions and requests

Always push the model for a complete solution and a realistic conversation. Don't accept partial solutions. 

For each interaction you'll evaluate the model's responses using the same steps.

<aside>
⌛

**Keep track of how much time you're spending**

The interaction phase with the model is expected to take approximately **1 hour in total**

We understand that reaching a perfect solution may not always be possible. Please manage your time effectively to arrive at the best possible solution within the **5-hour** overall time-limit.

</aside>