"""peer_bus — consensual, scoped connections between agent sessions over a filesystem bus.

Disk holds only discovery (registry) and in-flight frames (spool, claimed atomically by
rename). Connections, offers, and history live in each agent's kernel. Wake-up is a courier
session sending family-legal agent_messages; see watcher_prompt(). Protocol v1:
OFFER / ACCEPT (may narrow scopes) / REJECT / MSG / REVOKE. Connections are permanent
until revoked. Kernel-state loss degrades to a fresh OFFER, so consent is re-confirmed,
never resurrected. Set PEER_BUS_TRACE=1 to log frames to trace.jsonl (off by default);
PEER_BUS_DIR overrides the bus root.
"""
import json, os, time, uuid, pathlib

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

def publish(purpose: str, accepting: bool = True) -> dict:
    """Opt in to discovery. Unlisted agents cannot be offered to."""
    _reg().mkdir(parents=True, exist_ok=True)
    card = {"alias": _me(), "purpose": purpose, "accepting": accepting, "published": _now()}
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

def watcher_prompt(target_alias: str, wakes: int = 10, minutes: int = 60) -> str:
    """Generate the courier prompt; spawn it in any session with family reach to the target."""
    d = _spool(target_alias)
    return (f"Poll the directory {d} every 2 seconds. Each time one or more *.json files appear "
            f"(ignore dotfiles): send await agent_message.send('peer-bus wake: N frame(s) in your spool', "
            f"receiver_role='sibling', receiver_name='{target_alias}') with N the count, then wait until "
            f"the directory has no *.json files before watching for the next batch. Exit after {wakes} "
            f"notifications or {minutes} minutes. Never notify when no frames exist; never touch any file.")

def dump_state() -> str:
    return json.dumps(_STATE, indent=1)

async def run(action: str = "status"):
    """CLI entrypoint: peer_bus --action status|registry."""
    return json.dumps(registry(), indent=1) if action == "registry" else dump_state()
