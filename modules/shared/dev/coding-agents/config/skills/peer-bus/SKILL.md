---
name: peer-bus
description: Negotiate a consensual, scoped connection between two agent sessions over an external filesystem bus (registry for discovery, transient claim-by-rename spool as the wire, kernel state as the record), then exchange messages across family-reach boundaries with watcher-driven agent_message wakes. Use when two sessions that cannot message each other directly (different roots, different trees) need to communicate, when the user asks to connect/bridge two agents, or when building orchestrator-of-orchestrators topologies without daemon changes.
compatibility: Same-machine, same-user (v0). No network, no daemon changes. Wake-up needs a sender with agent_message family reach to the target: another root can only be woken by a root directly, but any agent — root included — can be woken by a courier it spawns for its own spool.
---

# peer-bus

Consent-based peer connections between agent sessions. Protocol v1:
OFFER / ACCEPT (may narrow scopes — subset only) / REJECT / MSG / REVOKE; accepts are permanent until revoked.
Disk holds only the opt-in registry and in-flight frames (claim-by-rename spool);
connections, offers, and history live in each agent's own kernel. State loss
degrades to a fresh OFFER — consent is re-confirmed, never resurrected.

## Acceptor bootstrap (minimal)

```python
my_alias = peer_bus.init("oss-contrib")
me = (await agent_message.list_agents())["current"]          # authoritative id + depth
peer_bus.publish("domain orchestrator: owns OSS contributions",
                 session_id=me["id"], depth=me["depth"])     # so peers know HOW to wake me
await rlm(peer_bus.watcher_prompt(my_alias), name="self-watch")   # a child that wakes ME on new frames
# end turn; on each "peer-bus wake" agent_message:
for f in peer_bus.pump():
    ...  # OFFER → peer_bus.accept(f["id"], scopes=[...]) per policy (narrow freely)
         # MSG   → work, then peer_bus.connection(f["from"]).send(answer)
         # REVOKE → verified via peer_bus.connections()
```

## Initiator bootstrap (minimal)

```python
peer_bus.init("front-door")            # wait until registry() shows the peer accepting
me = (await agent_message.list_agents())["current"]
peer_bus.publish("initiator", session_id=me["id"], depth=me["depth"])
peer_bus.offer("oss-contrib", scopes=["delegate-task"])
# poll pump() until the ACCEPT arrives, then:
conn = peer_bus.connection("oss-contrib")
reply = conn.request("delegate-task: ...", timeout_s=900)   # sync sugar
conn.revoke("mission complete")
```

## Waking a passive/idle peer

The spool is inert disk; delivery of an `agent_message` is what starts a turn.
But `agent_message` reach is **family-only** — parent, siblings, own children —
and every courier you can spawn is your *child*, so a courier is never a root.
That constrains who may wake *someone else*; it never constrains waking **yourself**.
Reach matrix (target → who can send the wake):

| Target | Reachable by | Shape |
| --- | --- | --- |
| **Yourself** — *any* depth, **root included** | a courier **you** spawn (self-watch) | your child's roster lists you as its `parent`: `agent_message.send(..., receiver_role="parent")` with **no** `receiver_name`. This is the standard pattern for an idle root that wants its own spool watched |
| **Another root** (depth 0) | another **root**, directly — *or* a courier **that root** spawns for itself | roots are siblings of each other: `agent_message.send(..., receiver_role="sibling", receiver_name=<target session id>)` from your **own** kernel — **never** from a child *you* spawn. If you are not a root, ask the target to self-watch instead |
| **Another agent's child** (depth ≥ 1) | its parent, or a sibling courier | spawn the courier *in the target's family*: from the target itself (it wakes `receiver_role="parent"`) or from the target's parent (`receiver_role="sibling"`) |
| Anything else (cousin, grandchild, unknown) | nobody | no reach — say so, do not retry |

`watcher_prompt(alias)` reads the target's registry card and generates the right
prompt: it names the **session id** to send to and tells the courier to resolve the
role from `await agent_message.list_agents()` — which lands on `parent` for a
self-watch courier and on `sibling`/`child` for anyone else. It **raises `ValueError`**
only for the provably impossible **other**-root case, rather than spawning a doomed
courier (the real 2026-08-25 failure: `RuntimeError: No sibling matches "lomz-subdomains"`).
Passing your **own** alias is never refused, at any depth.

```python
await rlm(peer_bus.watcher_prompt("oss-contrib"), name="bus-watcher")   # courier-reachable target
await rlm(peer_bus.watcher_prompt(my_alias), name="self-watch")   # my OWN spool — allowed at any depth
# ValueError → the target is ANOTHER root: send it yourself, from your own kernel:
card = {c["alias"]: c for c in peer_bus.registry()}["oss-contrib"]
await agent_message.send("peer-bus wake: frames in your spool",
                         receiver_role="sibling", receiver_name=card["session_id"])
```

A wake is an **optimisation, not a delivery guarantee**: both sides also drain the
spool organically whenever they `pump()` on their own next turn, so a missed wake
delays a frame, it never loses one. A peer that published no `session_id` (old v0
card) can only be guessed at — the generated prompt says so out loud.

## Notes

- `pump()` is the single drain primitive; call it on every wake.
- `init()` returns your alias — keep it (`my_alias = peer_bus.init("front-door")`) for self-watch.
- `conn.inbox()` / `conn.history()` are kernel reads, no I/O.
- `PEER_BUS_TRACE=1` appends frame evidence to `trace.jsonl` (off by default — privacy).
- `PEER_BUS_DIR` overrides the bus root (default `~/.prime/agent/peer-bus`).
- Registry cards carry optional `session_id` / `depth`; `peer_bus.identity()` sniffs them from
  the environment when you do not pass them, and omits what it cannot prove (never guesses).
