---
name: peer-bus
description: Negotiate a consensual, scoped connection between two agent sessions over an external filesystem bus (registry for discovery, transient claim-by-rename spool as the wire, kernel state as the record), then exchange messages across family-reach boundaries with watcher-driven agent_message wakes. Use when two sessions that cannot message each other directly (different roots, different trees) need to communicate, when the user asks to connect/bridge two agents, or when building orchestrator-of-orchestrators topologies without daemon changes.
compatibility: Same-machine, same-user (v0). No network, no daemon changes. Wake-up needs a watcher session with agent_message family reach to the target.
---

# peer-bus

Consent-based peer connections between agent sessions. Protocol v1:
OFFER / ACCEPT (may narrow scopes — subset only) / REJECT / MSG / REVOKE; accepts are permanent until revoked.
Disk holds only the opt-in registry and in-flight frames (claim-by-rename spool);
connections, offers, and history live in each agent's own kernel. State loss
degrades to a fresh OFFER — consent is re-confirmed, never resurrected.

## Acceptor bootstrap (minimal)

```python
peer_bus.init("oss-contrib")
peer_bus.publish("domain orchestrator: owns OSS contributions")
# end turn; on each "peer-bus wake" agent_message:
for f in peer_bus.pump():
    ...  # OFFER → peer_bus.accept(f["id"], scopes=[...]) per policy (narrow freely)
         # MSG   → work, then peer_bus.connection(f["from"]).send(answer)
         # REVOKE → verified via peer_bus.connections()
```

## Initiator bootstrap (minimal)

```python
peer_bus.init("front-door")            # wait until registry() shows the peer accepting
peer_bus.offer("oss-contrib", scopes=["delegate-task"])
# poll pump() until the ACCEPT arrives, then:
conn = peer_bus.connection("oss-contrib")
reply = conn.request("delegate-task: ...", timeout_s=900)   # sync sugar
conn.revoke("mission complete")
```

## Waking a passive/idle peer

The spool is inert disk; delivery of an `agent_message` is what starts a turn.
Spawn a courier with the generated one-liner:

```python
await rlm(peer_bus.watcher_prompt("oss-contrib"), name="bus-watcher")
```

(Any session with family reach to the target works — its child, its sibling, or
its parent. RLM depth limits often force the sibling shape.)

## Notes

- `pump()` is the single drain primitive; call it on every wake.
- `conn.inbox()` / `conn.history()` are kernel reads, no I/O.
- `PEER_BUS_TRACE=1` appends frame evidence to `trace.jsonl` (off by default — privacy).
- `PEER_BUS_DIR` overrides the bus root (default `~/.prime/agent/peer-bus`).
