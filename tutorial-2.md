# Tutorial Part 2 — Evaluating Model Solutions (Using Rebirth)

By this point, repo preparation (Step 1) is already done. This tutorial covers the evaluation workflow — from starting HFI to finalizing your task — using the **Rebirth** tool to coordinate with your manager.

---

## The User Flow at a Glance

```
Login → Start HFI → HFI gives you an auth URL →
Paste URL into Rebirth (Task Key Request) → Manager approves & sends back the key →
Use key to authenticate HFI locally → Rewrite issue → Submit prompt →
Evaluate models → Submit labeling in Rebirth → Manager approves →
Iterate → Final labeling → Task Complete
```

---

## 1. Log In to Rebirth

1. Open Rebirth in your browser (default: `http://localhost:8501`).
2. Log in with your email and password.
3. If you don't have an account, use the **Sign Up** tab. Your account will be pending until an admin verifies you.

---

## 2. Start HFI (in your terminal)

Navigate to your prepared repo in WSL and start HFI:

```bash
cd /mnt/c/Users/you/Desktop/rebirth/task_14/repo
claude-hfi --vscode
```

HFI will prompt you to authenticate and display an **auth URL**. **Do not close this terminal.** You need to get this URL approved before you can continue.

---

## 3. Send the Auth URL to Your Manager via Rebirth

This is where the Rebirth tool comes in. You take the URL that HFI gave you and submit it for manager approval.

1. Go to **Task Key Request** in the Rebirth sidebar (under Workflow).
2. Toggle **"Create a new task"** on (or select an existing task if you have one).
3. Fill in:
   - **Task Name** — e.g., `task_14`
   - **Local Repo Path** — where you cloned the repo
   - **Project Name** — what you're working on
   - **HFI Auth Key / Link** — **paste the auth URL that HFI just gave you**
4. Click **Create Task & Submit Request**.

Your request is now **pending**. The manager sees it in their Rebirth dashboard.

### What happens on the manager's side

The manager (a `role_manager` or `rebumex`) opens Rebirth, sees your pending request under **Pending Approvals**, reviews it, and clicks **Approve**. Once approved, the auth key is linked to your task.

### Check your request status

Stay on the **Task Key Request** page and look at the **My Requests** section:
- **Pending** — waiting for the manager
- **Approved** — you have the key, proceed
- **Rejected** — read the reason, fix, and resubmit

---

## 4. Authenticate HFI Locally

Once the manager approves your request, go back to your HFI terminal. Use the approved key to complete the authentication:

- Enter the code when prompted: `cc_agentic_coding`
- **Save the trajectory session IDs** (A and B) immediately to a text file

HFI creates two trajectory sessions — one for Model A, one for Model B.

---

## 5. Rewrite the Issue Description

Before submitting the issue as your first prompt, rewrite it in your own words.

**Rules:**
- State the problem and solution **clearly and explicitly**
- **Remove** any links or images from the original
- Do **not** add info that isn't in the original (don't invent test requirements, etc.)
- Keep the same scope — just rephrase naturally

**Example:**

Original:
> `TypeError` when calling `process_data()` with empty list. See screenshot: ![error](img.png). Related: #42

Rewritten:
> The `process_data()` function raises a `TypeError` when called with an empty list. Fix it so that an empty list is handled gracefully and returns an empty result.

---

## 6. Submit Your First Prompt

In the HFI interface, enter **only** your rewritten issue title and description. Do not add extra context or instructions.

Then monitor both trajectories in separate terminals:

```bash
tmux attach -t <session-id-A>
```

```bash
tmux attach -t <session-id-B>
```

Watch for permission prompts. Pause your timer while models are running (3–15 minutes per response).

---

## 7. Record the Iteration in Rebirth

Once both models have responded, go to **Model Evaluation** in the Rebirth sidebar.

1. Select your task.
2. In the **Iteration 1** tab, paste:
   - The issue context (your rewritten prompt)
   - Model A's response summary
   - Model B's response summary
3. Save the iteration.
4. Click the link to go to the **Labeling** page.

---

## 8. Submit a Labeling Evaluation

Navigate to **Labeling** in the sidebar. Select your task and iteration, then fill in the structured evaluation form:

| Field | What to write |
|-------|---------------|
| **Prompt given to models** | Your rewritten issue description |
| **Model A Pros** | Concise paragraph — what A did well (specific examples, test results, file names) |
| **Model A Cons** | Concise paragraph — what could improve (specific, not vague) |
| **Model B Pros** | Same format |
| **Model B Cons** | Same format |
| **Axis evaluations** | 7 dropdowns — use the closeness scale below |
| **Overall preference** | A or B |
| **Overall justification** | Why the winner wins — key differences |
| **Next instruction** | Direct paragraph for the next iteration (no praise, no bullet points) |

If this is **not** the final iteration, leave "Final iteration" unchecked. Click **Submit Evaluation**.

### Closeness scale

| Code | Meaning |
|------|---------|
| A | Strongly prefer A |
| AA | Prefer A |
| AAA | Slightly prefer A |
| AAAA | Very slightly prefer A |
| BBBB | Very slightly prefer B |
| BBB | Slightly prefer B |
| BB | Prefer B |
| B | Strongly prefer B |
| N/A | Not applicable (use sparingly) |

### What happens after you submit

Your submission goes to the manager for approval. Once approved:
- Your evaluation is saved to the iteration record
- A **new iteration** is automatically created using your "Next instruction" as the starting context
- You can move to the next round

---

## 9. Iterate

Repeat steps 6–8 for each iteration:

1. In HFI, submit the next prompt (the "Next instruction" the manager just approved).
2. Wait for model responses. Monitor both trajectories.
3. Record the iteration in **Model Evaluation**.
4. Submit a new **Labeling** evaluation.
5. Wait for manager approval.

Each approval auto-creates the next iteration. Keep going until the solution is production-ready.

### Writing good next instructions

**Do:**
- Be direct and specific — file names, function names, what to change
- Focus on the cons you just documented
- Think of it as actionable code review feedback

**Don't:**
- Use praise ("Good work, now...")
- Be vague ("improve the code")
- Expand scope beyond the original issue
- Use bullet points or numbered lists

**Example:**
> Your implementation correctly handles basic path resolution but lacks validation for edge cases. Add explicit validation in `resolve_paths` to check if provided directories are files rather than directories, and verify parent directories exist before creating subdirectories. Replace `QDir.tempPath()` with `tempfile.gettempdir()` as the former requires `QApplication` to be instantiated.

---

## 10. Final Submission

When the solution is production-ready:

1. In **Labeling**, fill in your final evaluation as usual.
2. Check the **"Final iteration"** checkbox. The "Next instruction" field disappears.
3. Submit. Wait for manager approval.
4. On approval, your task is automatically marked **complete**.

### After completion

- The Labeling page shows a task completion summary.
- You can download the combined evaluation of all iterations.
- Generate your TAR file:

```bash
tar -cf task_14.tar repo_folder
```

---

## Quick Reference

| Step | Where | What you do |
|------|-------|-------------|
| Log in | Rebirth → Login | Email + password |
| Start HFI | Terminal (WSL) | `claude-hfi --vscode` |
| Send auth URL to manager | Rebirth → Task Key Request | Paste the URL HFI gave you |
| Wait for key approval | Rebirth → Task Key Request | Check "My Requests" |
| Authenticate HFI | Terminal | Use approved key |
| Rewrite issue | Your notes | Rephrase in own words |
| Submit prompt | HFI terminal | Paste rewritten issue |
| Monitor models | Terminal (tmux) | Watch both trajectories |
| Record iteration | Rebirth → Model Evaluation | Paste responses |
| Structured evaluation | Rebirth → Labeling | Pros/cons, axes, preference |
| Wait for eval approval | Rebirth → Labeling | Manager reviews |
| Iterate | Repeat HFI → Labeling | Until production-ready |
| Finalize | Rebirth → Labeling | Check "Final iteration" |
| Submit deliverable | Terminal | `tar -cf task.tar repo` |

---

## Tips

- **Pause your timer** while models are running — you're not doing active work during that time.
- **Save HFI session IDs immediately** — if you lose connection, `tmux ls` + `tmux attach` gets you back.
- **Be specific in evaluations** — mention file names, function names, test counts, Docker results.
- **Every response has pros AND cons** — there's always room for improvement on both sides.
- **Axis selections should match your prose** — if you say Model A has better logic, the logic axis should favor A.
- **Don't use N/A unless truly not applicable** — one model is almost always better on each axis.
