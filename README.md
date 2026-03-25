# Mini-RAFT: Distributed Drawing Board

Base scaffold for the team project with RAFT replica components, gateway, UI modules, infrastructure, and tests.

## Repository Structure

```text
.
├── gateway/                  # T4
├── replica/
│   ├── consensus/            # T1
│   ├── log/                  # T2
│   ├── recovery/             # T3
│   ├── state/
│   └── rpc/
├── replica1/
├── replica2/
├── replica3/
├── replica4/                 # BONUS
├── infra/                    # T4
├── tests/                    # T3 lead
├── shared/
├── frontend/                 # T5 (ALL UI)
│   ├── canvas/
│   ├── websocket/
│   ├── dashboard/
│   └── controls/
├── docs/
├── docker-compose.yml
└── README.md
```

## CI/CD Pipeline

The repository uses **GitHub Actions** to automate testing and deployment.

### Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| **CI** (`.github/workflows/ci.yml`) | Push to `dev`, PR targeting `main` | Installs dependencies, runs `pytest tests/` |
| **CD** (`.github/workflows/cd.yml`) | Push to `dev` (after CI passes) | Auto-merges `dev` → `main` |

### Branch Strategy

| Branch | Rule |
|---|---|
| `main` | **No direct pushes allowed** — changes arrive only via the auto-merge from `dev` once CI passes |
| `dev` | Active development branch; CI runs on every push |

### Enabling Branch Protection for `main`

> **One-time setup** — a repository admin must do this once via GitHub.

1. Go to **Settings → Branches → Add branch protection rule**.
2. Set **Branch name pattern** to `main`.
3. Enable **Require status checks to pass before merging** and add `Run tests` as a required check.
4. Enable **Restrict pushes that create matching branches** and do **not** add any users/teams (this blocks direct pushes).
5. Enable **Do not allow bypassing the above settings**.
6. Click **Save changes**.

After this, all changes to `main` must flow through the CD workflow (which waits for CI to succeed on `dev`).
