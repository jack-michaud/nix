"""peer_bus — consensual, scoped connections between agent sessions over a filesystem bus.

Disk holds only discovery (registry) and in-flight frames (spool, claimed atomically by
rename). Connections, offers, and history live in each agent's kernel. Wake-up is an
agent_message from a session that has family reach to the target -- often a courier, but ANOTHER
root can only be woken by a root directly, while any agent (root included) can be woken by a
courier it spawns for its own spool; see watcher_prompt(). Protocol v1:
OFFER / ACCEPT (may narrow scopes) / REJECT / MSG / REVOKE. Connections are permanent
until revoked. Kernel-state loss degrades to a fresh OFFER, so consent is re-confirmed,
never resurrected. Set PEER_BUS_TRACE=1 to log frames to trace.jsonl (off by default);
PEER_BUS_DIR overrides the bus root.
"""
import json, os, re, time, uuid, pathlib

_STATE = {"me": None, "conns": {}, "offers": {}, "history": []}
BUS_DIR = None  # optional override; else PEER_BUS_DIR env, else ~/.prime/agent/peer-bus

def _bus():
    return pathlib.Path(BUS_DIR or os.environ.get("PEER_BUS_DIR", os.path.expanduser("~/.prime/agent/peer-bus")))

def _reg(): return _bus() / "registry"
def _spool(alias): return _bus() / "spool" / alias
def _now(): return time.strftime("%H:%M:%S", time.localtime()) + f".{int(time.time()*1000)%1000:03d}"

def _trace(event, frame):
    if os.environ.get("PEER_BUS_TRACE") != "1": return
    p = _bus() / "trace.jsonl"; p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f: f.write(json.dumps({"t": _now(), "event": event, "frame": frame}) + "\n")

def init(alias: str) -> str:
    """Adopt a stable bus identity and create my spool. Call once per kernel."""
    _STATE["me"] = alias
    _spool(alias).mkdir(parents=True, exist_ok=True)
    return alias

def _me():
    if not _STATE["me"]: raise RuntimeError("peer_bus.init(alias) first")
    return _STATE["me"]

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

def identity() -> dict:
    """Best-effort daemon identity of THIS session: {"session_id", "depth"}, keys omitted if unknown.

    An alias is a bus name, not a routing address: agent_message resolves receivers inside the
    family roster by session id/name, so a peer that publishes no session id cannot be woken
    except by guesswork. The daemon exports no session-id variable today, so we fall back to the
    only path that always contains our OWN id: RLM_HARNESS_STATE_DIR is
    <artifact-dir-of-this-session>/harness. RLM_SESSION_DIR is deliberately NOT used -- for a
    subagent it is the PARENT's artifact dir plus a sub-<hash> segment, so reading a uuid out of
    it would publish someone else's identity. Unknown beats wrong: we omit, never guess.
    """
    out = {}
    sid = os.environ.get("PRIME_AGENT_SESSION_ID") or os.environ.get("RLM_SESSION_ID")
    if not sid:
        found = _UUID.findall(os.environ.get("RLM_HARNESS_STATE_DIR", ""))
        sid = found[-1] if found else None
    if sid: out["session_id"] = sid
    try: out["depth"] = int(os.environ["RLM_DEPTH"])
    except (KeyError, ValueError): pass
    return out

def publish(purpose: str, accepting: bool = True, session_id: str = None, depth: int = None) -> dict:
    """Opt in to discovery. Unlisted agents cannot be offered to.

    Also records who to send an agent_message to (session_id) and whether this session is a root
    (depth 0), because another root is wakeable only by a root sending directly, or by a courier
    that root spawns for its own spool. Pass them explicitly from the
    authoritative source when you have it -- me = (await agent_message.list_agents())["current"]
    -- otherwise they are sniffed from the environment and simply omitted if unavailable, which
    keeps old readers and identity-less publishers working (both fields are optional).
    """
    _reg().mkdir(parents=True, exist_ok=True)
    who = identity()
    if session_id is not None: who["session_id"] = session_id
    if depth is not None: who["depth"] = depth
    _STATE["identity"] = who
    card = {"alias": _me(), "purpose": purpose, "accepting": accepting, "published": _now(), **who}
    (_reg() / f"{_me()}.json").write_text(json.dumps(card, indent=1))
    return card

def unpublish():
    (_reg() / f"{_me()}.json").unlink(missing_ok=True)

def registry() -> list:
    return [json.loads(p.read_text()) for p in sorted(_reg().glob("*.json"))]

def _emit(to_alias, frame):
    frame.update({"v": 1, "id": uuid.uuid4().hex[:8], "ts": _now(),
                  "from": _me(), "to": to_alias})
    d = _spool(to_alias); d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".tmp-{frame['id']}"
    tmp.write_text(json.dumps(frame))
    os.rename(tmp, d / f"{int(time.time()*1000)}-{frame['id']}.json")
    frame["dir"] = "sent"
    _trace("emit", frame); _STATE["history"].append(frame)
    return frame

def pump() -> list:
    """Claim every frame addressed to me into kernel state. Call on every peer-bus wake."""
    d = _spool(_me()); new = []
    for p in sorted(d.glob("*.json")):
        claimed = d / f".claimed-{p.name}"
        try: os.rename(p, claimed)
        except OSError: continue
        frame = json.loads(claimed.read_text()); claimed.unlink()
        if any(h.get("id") == frame["id"] for h in _STATE["history"]): continue
        frame["dir"] = "recv"
        _trace("claim", frame); _STATE["history"].append(frame); new.append(frame)
        k = frame["frame"]
        if k == "OFFER":
            _STATE["offers"][frame["id"]] = {**frame, "status": "received"}
        elif k == "ACCEPT":
            _STATE["conns"][frame["connId"]] = {"peer": frame["from"], "scopes": frame["scopes"], "state": "ACTIVE"}
        elif k == "REVOKE":
            if frame["conn"] in _STATE["conns"]: _STATE["conns"][frame["conn"]]["state"] = "REVOKED"
    return new

def offer(to_alias: str, scopes: list, purpose: str = "") -> dict:
    cards = {c["alias"]: c for c in registry()}
    if to_alias not in cards or not cards[to_alias].get("accepting"):
        raise LookupError(f"'{to_alias}' has no accepting presence card")
    f = _emit(to_alias, {"frame": "OFFER", "purpose": purpose, "scopes": scopes})
    _STATE["offers"][f["id"]] = {**f, "status": "sent"}
    return f

def accept(offer_id: str, scopes: list = None):
    """Accept an offer, optionally narrowing to a subset of its scopes. Permanent until revoked."""
    off = _STATE["offers"][offer_id]
    scopes = off["scopes"] if scopes is None else scopes
    if not set(scopes) <= set(off["scopes"]): raise ValueError("ACCEPT may only narrow scopes")
    conn_id = "c-" + uuid.uuid4().hex[:6]
    _STATE["conns"][conn_id] = {"peer": off["from"], "scopes": scopes, "state": "ACTIVE"}
    _emit(off["from"], {"frame": "ACCEPT", "offerId": offer_id, "connId": conn_id, "scopes": scopes})
    off["status"] = "accepted"
    return Conn(conn_id)

def reject(offer_id: str, reason: str):
    off = _STATE["offers"][offer_id]
    off["status"] = "rejected"
    return _emit(off["from"], {"frame": "REJECT", "offerId": offer_id, "reason": reason})

class Conn:
    """Handle for one connection. Reads are kernel-state reads; send/revoke emit frames."""
    def __init__(self, conn_id): self.id = conn_id

    @property
    def _c(self): return _STATE["conns"][self.id]
    @property
    def peer(self): return self._c["peer"]
    @property
    def scopes(self): return self._c["scopes"]
    @property
    def state(self): return self._c["state"]

    def send(self, text: str, data=None) -> dict:
        if self.state != "ACTIVE": raise RuntimeError(f"conn {self.id} is {self.state}")
        return _emit(self.peer, {"frame": "MSG", "conn": self.id, "text": text, "data": data})

    def inbox(self) -> list:
        """Unread MSG frames on this conn; marks them read."""
        out = [h for h in _STATE["history"]
               if h.get("dir") == "recv" and h.get("conn") == self.id
               and h.get("frame") == "MSG" and not h.get("_read")]
        for h in out: h["_read"] = True
        return out

    def history(self, limit: int = 50) -> list:
        return [h for h in _STATE["history"] if h.get("conn") == self.id][-limit:]

    def request(self, text: str, timeout_s: int = 600, poll_s: int = 2) -> dict:
        """Send, then poll pump() until the peer's next MSG on this conn."""
        self.send(text)
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            for f in pump():
                if f.get("frame") == "MSG" and f.get("conn") == self.id:
                    f["_read"] = True
                    return f
            time.sleep(poll_s)
        raise TimeoutError(f"no reply on {self.id} within {timeout_s}s")

    def revoke(self, reason: str):
        self._c["state"] = "REVOKED"
        return _emit(self.peer, {"frame": "REVOKE", "conn": self.id, "reason": reason})

    def __repr__(self):
        return f"<Conn {self.id} peer={self.peer} scopes={self.scopes} state={self.state}>"

def connection(peer_alias: str) -> Conn:
    """The ACTIVE connection with a peer, by alias."""
    for cid, c in _STATE["conns"].items():
        if c["peer"] == peer_alias and c["state"] == "ACTIVE": return Conn(cid)
    raise LookupError(f"no ACTIVE connection with '{peer_alias}'")

def connections() -> dict:
    return _STATE["conns"]

def _poll_clause(d, wakes, minutes) -> str:
    return (f"Poll the directory {d} every 2 seconds. Each time one or more *.json files appear "
            f"(ignore dotfiles): send ONE agent_message reading 'peer-bus wake: N frame(s) in your "
            f"spool' with N the count, then wait until the directory has no *.json files before "
            f"watching for the next batch. Exit after {wakes} notifications or {minutes} minutes. "
            f"Never notify when no frames exist; never touch any file.")

def watcher_prompt(target_alias: str, wakes: int = 10, minutes: int = 60) -> str:
    """Generate the courier prompt for waking a peer -- or refuse, when no courier of yours reaches it.

    agent_message reach is family-only (parent, siblings, own children) and every courier you can
    spawn is your CHILD, so a courier is never a root. Roots are siblings of each other, therefore
    ANOTHER root is reachable only by a root messaging it directly from its own kernel. That case
    is provable from the registry, and failing here beats spawning a courier that will die on
    'No sibling matches ...' -- which is exactly what happened on 2026-08-25.

    Watching your OWN spool is the exception and is always allowed, root or not: the courier is
    your child, so it wakes you as its PARENT. The generic branch already emits that correctly --
    the courier reads its roster, finds you listed with relationship 'parent', and omits
    receiver_name -- so self-watch only needs the root refusal to step aside.
    """
    d = _spool(target_alias)
    card = {c["alias"]: c for c in registry()}.get(target_alias, {})
    sid, target_depth = card.get("session_id"), card.get("depth")
    mine = _STATE.get("identity") or identity()

    # Am I the target? Alias first: it is the one signal that survives a silent runtime, where
    # identity() legitimately returns {} and no session id can be compared. The id is belt-and-
    # braces for the case where I published under a different alias in an earlier kernel.
    is_self = bool(target_alias == _STATE.get("me") or (sid and sid == mine.get("session_id")))

    if sid and target_depth == 0 and not is_self:
        fix = (f"You are a root too, so send it directly from your own kernel:\n"
               f"  await agent_message.send('peer-bus wake: frames in your spool', "
               f"receiver_role='sibling', receiver_name='{sid}')"
               if mine.get("depth") == 0 else
               f"You are not a root, so you cannot reach it either: ask a root session (your "
               f"top-level ancestor) to send directly to receiver_role='sibling', "
               f"receiver_name='{sid}'.")
        raise ValueError(
            f"'{target_alias}' is ANOTHER ROOT session (id {sid}); roots are reachable only as "
            f"siblings, and every courier you spawn is your child, so no courier YOU spawn can "
            f"wake it. A courier IT spawns can -- that child wakes its own parent -- so the other "
            f"option is to ask '{target_alias}' to self-watch. {fix}\n"
            f"Not urgent either way: {target_alias} claims its spool the next time it runs pump().")

    if sid:
        return (f"You are a peer-bus courier for the session with id {sid} (bus alias "
                f"'{target_alias}'). First establish reach: roster = await "
                f"agent_message.list_agents(); find the entry whose 'id' is '{sid}'. Send with that "
                f"entry's 'relationship' as receiver_role and its 'name' as receiver_name (omit "
                f"receiver_name when the target is your parent). If no entry matches you have NO "
                f"reach -- say so to your parent and exit immediately; never guess a receiver name "
                f"from the bus alias. {_poll_clause(d, wakes, minutes)}")

    return (f"You are a peer-bus courier for the bus alias '{target_alias}'. REACH WARNING: that "
            f"peer published no session id, so its alias is only a guess at a receiver name -- "
            f"agent_message resolves receiver_name against session names in your family roster "
            f"(parent, siblings, children), not against bus aliases, and roots are reachable only "
            f"by other roots. Check await agent_message.list_agents() first and use the matching "
            f"entry's relationship and name; if nothing matches, report no reach to your parent "
            f"and exit rather than retrying. A missed wake only delays delivery -- the peer drains "
            f"its own spool with pump() on its next turn. {_poll_clause(d, wakes, minutes)}")

def dump_state() -> str:
    return json.dumps(_STATE, indent=1)

async def run(action: str = "status"):
    """CLI entrypoint: peer_bus --action status|registry."""
    return json.dumps(registry(), indent=1) if action == "registry" else dump_state()
