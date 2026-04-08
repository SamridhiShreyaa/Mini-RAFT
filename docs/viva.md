# Viva + Concept Navigation

## Section 1: Viva Questions

**Q1: How do you handle a scenario where two nodes believe they are the leader?**
*Answer:* Split-brain happens during a network partition. RAFT resolves this by requiring a strict majority quorum (`N/2 + 1`) to commit any log entries. A leader cut off from the majority can never commit an `AppendEntries` operation. Once the partition heals, the system accepts the leader with the highest term block.

**Q2: What happens if a replica fails and is restarted?**
*Answer:* The restarted node comes up as a Follower with an empty volatile state. During the next `AppendEntries` heartbeat from the leader, its `prevLogIndex` validation fails. The leader then triggers the `SyncLogRequest` which dumps the missing committed log items directly to the lagging follower.

**Q3: How does the Gateway ensure clients don’t drop connections during leader failovers?**
*Answer:* The Gateway catches Axios HTTP errors when talking to the backend block. On failure, it caches the client's drawing stroke, pauses, polls `/state` for all replicas to find the new leader, and redirects the payload. The client's WebSocket connection remains untouched during backend volatility.

**Q4: How does RAFT guarantee ordering in the append-only log?**
*Answer:* Each node strictly asserts that `PrevLogIndex` and `PrevLogTerm` on incoming requests match correctly with their local memory. If a mismatch is detected, the entry is rejected, and the leader is forced to backtrack until the local logs match exactly. 

---

## Section 2: Concept → Code Mapping

| Concept | File + Line Number | Short Explanation |
| :--- | :--- | :--- |
| **Leader Election** | `replica/consensus/node.py` (Line 56) | Converts follower to candidate, increments term, requests votes. |
| **Heartbeats** | `replica/consensus/node.py` (Line 132) | Continual POST signals resetting the follower election timeout limits. |
| **Log Replication** | `replica/log/appendEntries.py` (Line 6) | RPC processing incoming append actions and verifying log consistency limits. |
| **State Machine Commits** | `replica/log/commitManager.py` (Line 5) | Analyzes array of follower ACKs to transition pending logs to committed history. |
| **Fault Recovery Catch-Up** | `replica/recovery/restart_recovery.py` (Line 16) | Resolves discrepancy in restarted clusters pulling logs back to sync. |
| **Split-Brain Quorum** | `tests/chaos/test_network_partition.py` (Line 1) | Ensures only the half of the cluster with 3/4 voting power maintains commit authority. |
| **Zero-Downtime Swap** | `gateway/index.js` (Line 143) | Re-polls node properties on failing leader network connection. |
| **Client Abstraction** | `frontend/websocket/ws.js` (Line 150) | The unified socket code that operates regardless of the cluster's leader death. |
