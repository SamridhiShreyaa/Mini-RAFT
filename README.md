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
