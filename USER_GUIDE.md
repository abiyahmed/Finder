# Rebirth User Guide

## Quick Start

```bash
pip install -r requirements.txt
python -m streamlit run run.py
```

## Structure

```
Rebirth/
├── run.py              # Entry point (Streamlit dashboard)
├── pages/              # Streamlit pages (UI)
├── src/
│   ├── domain/         # Data models
│   ├── application/    # Services (business logic)
│   └── infrastructure/ # Database, GitHub API, Supabase
└── tests/
```

## Workflow

**Path A (Issue Finder):** Find Issue → Scan repo → Select issue → Create task → Request key → Prepare repo → Evaluate → Label

**Path B (Standalone):** Task Key Request (create task + key) → Prepare repo → Evaluate → Label

## Commands

| Action | Command |
|--------|---------|
| Run app | `python -m streamlit run run.py` |
| Run tests | `python -m pytest tests/` |

## Admin / rebumex login

The default admin user **rebumex** is created on first run. Default password: **`Bonsa@4213`** (use **Email or username** = `rebumex` and this password for legacy login).

To use a different password (e.g. `Rebu@4213`), set in env or Streamlit secrets:

- **`ADMIN_DEFAULT_PASSWORD=Rebu@4213`**

On next app start, the rebumex password is updated to that value. You can then log in with username `rebumex` and the password you set.

If you use **Supabase** login with the rebumex email, the app links that Supabase account to the existing rebumex user and skips verification.

## Streamlit Cloud: Keep data across redeploys

To avoid losing users and data when the app is redeployed:

1. In the Streamlit Cloud app dashboard, open your app → **Settings** → **General**.
2. Enable **Persistent storage** (if available on your plan). Storage is mounted at `/home/app-user/data`.
3. The app automatically uses that path for the SQLite database when it exists, so no env vars are required.

Alternatively, set `DATABASE_URL` in app secrets to a writable path (e.g. `sqlite:////home/app-user/data/tasks.db`) or to an external database (e.g. PostgreSQL).

## Time Tracking Playbook (5:30 Countdown)

Use a single countdown timer that starts at `5:30:00` and always pauses while the model is running.

### Visual Timeline

```text
Start 5:30:00
|------------------- Setup + launch HFI -------------------| 4:00:00 remaining
|------ Evaluate first response + write second prompt ------| 2:30:00 remaining
|------ Evaluate second response + write third prompt ------| 1:30:00 remaining
|---------------------- Final polish -----------------------| < 1:00:00 remaining
Finish before 0:00:00
```

### Phase Targets

| Remaining Time | Required Outcome | Timer State |
|---|---|---|
| `5:30:00` -> `4:00:00` | Finish initial setup and start `claude-hfi --vscode` by `4:00:00` remaining | Running |
| During model run #1 | Wait for model output | Paused |
| Resume after run #1 -> `2:30:00` | Finish evaluating first response and provide second prompt by `2:30:00` remaining | Running |
| During model run #2 | Wait for model output | Paused |
| Resume after run #2 -> `1:30:00` | Finish evaluating second response and provide third prompt by `1:30:00` remaining | Running |
| During model run #3 | Wait for model output | Paused |
| Resume after run #3 -> final | Finish evaluation and submission with under `1:00:00` remaining | Running |

### Operating Rules

1. Start timer at exactly `5:30:00`.
2. Pause timer every time the model is actively running.
3. Resume timer immediately after model output is complete.
4. Do not spend countdown time waiting on model runtime.
5. Keep a small safety buffer and aim to finish with more than `00:10:00` remaining.
