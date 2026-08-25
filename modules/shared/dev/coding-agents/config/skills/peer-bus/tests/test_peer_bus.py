"""Protocol test: two personas share one module by swapping kernel state."""
import json
import pathlib

import peer_bus
import pytest


@pytest.fixture()
def bus(tmp_path):
    peer_bus.BUS_DIR = str(tmp_path)
    states = {k: {"me": None, "conns": {}, "offers": {}, "history": []}
             for k in ("a", "b")}
    def use(k):
        peer_bus._STATE = states[k]
    yield use
    peer_bus.BUS_DIR = None
    peer_bus._STATE = {"me": None, "conns": {}, "offers": {}, "history": []}


def test_full_protocol(bus, tmp_path):
    use = bus
    use("a"); peer_bus.init("alice"); peer_bus.publish("initiator")
    use("b"); peer_bus.init("bob"); peer_bus.publish("acceptor")

    use("a")
    off = peer_bus.offer("bob", ["ask", "report"], purpose="test")
    assert off["frame"] == "OFFER"

    use("b")
    got = peer_bus.pump()
    assert [f["frame"] for f in got] == ["OFFER"]
    conn_b = peer_bus.accept(got[0]["id"], scopes=["ask"])          # narrowed
    assert conn_b.scopes == ["ask"]

    use("a")
    peer_bus.pump()
    conn_a = peer_bus.connection("bob")
    assert conn_a.scopes == ["ask"]
    conn_a.send("question?")

    use("b")
    peer_bus.pump()
    inbox = peer_bus.connection("alice").inbox()
    assert [m["text"] for m in inbox] == ["question?"]
    assert peer_bus.connection("alice").inbox() == []               # read-once
    peer_bus.connection("alice").send("answer!")

    use("a")
    peer_bus.pump()
    assert conn_a.inbox()[0]["text"] == "answer!"
    conn_a.revoke("done")

    use("b")
    peer_bus.pump()
    assert peer_bus.connections()[conn_b.id]["state"] == "REVOKED"
    assert conn_a.state == "REVOKED"
    assert list((tmp_path / "spool").rglob("*.json")) == []         # wire, not store


def test_accept_cannot_widen(bus):
    use = bus
    use("a"); peer_bus.init("alice"); peer_bus.publish("x")
    use("b"); peer_bus.init("bob"); peer_bus.publish("y")
    use("a"); peer_bus.offer("bob", ["ask"])
    use("b")
    oid = peer_bus.pump()[0]["id"]
    with pytest.raises(ValueError):
        peer_bus.accept(oid, scopes=["ask", "extra"])


def test_offer_requires_accepting_card(bus):
    use = bus
    use("a"); peer_bus.init("alice")
    with pytest.raises(LookupError):
        peer_bus.offer("nobody", ["ask"])


def test_pump_dedupes_and_drains(bus, tmp_path):
    use = bus
    use("a"); peer_bus.init("alice"); peer_bus.publish("x")
    use("b"); peer_bus.init("bob"); peer_bus.publish("y")
    use("a"); off = peer_bus.offer("bob", ["ask"])
    # duplicate frame on the wire (redelivery)
    spool = tmp_path / "spool" / "bob"
    dup = json.loads((sorted(spool.glob("*.json"))[0]).read_text())
    (spool / "999-dup.json").write_text(json.dumps(dup))
    use("b")
    assert len(peer_bus.pump()) == 1
    assert peer_bus.pump() == []


def test_send_requires_active(bus):
    use = bus
    use("a"); peer_bus.init("alice"); peer_bus.publish("x")
    use("b"); peer_bus.init("bob"); peer_bus.publish("y")
    use("a"); peer_bus.offer("bob", ["ask"])
    use("b"); conn = peer_bus.accept(peer_bus.pump()[0]["id"])
    conn.revoke("bye")
    with pytest.raises(RuntimeError):
        conn.send("too late")


# --- reach / identity (the 2026-08-25 root-to-root failure) --------------------------------

IDENTITY_ENV = ("PRIME_AGENT_SESSION_ID", "RLM_SESSION_ID", "RLM_HARNESS_STATE_DIR", "RLM_DEPTH")
ROOT_A = "01a03a51-5401-7519-8c0f-248c76852908"
ROOT_B = "01a02491-e010-7705-bfc0-6a833755997c"
CHILD = "01a0258a-5158-71a6-9779-8d5d5ff38708"


@pytest.fixture()
def env(monkeypatch):
    """The kernel running pytest is itself a session, so scrub its identity before every test."""
    for k in IDENTITY_ENV:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def test_publish_records_session_identity(bus, env):
    env.setenv("PRIME_AGENT_SESSION_ID", ROOT_A)
    env.setenv("RLM_DEPTH", "0")
    bus("a"); peer_bus.init("alice")
    card = peer_bus.publish("initiator")
    assert (card["session_id"], card["depth"]) == (ROOT_A, 0)
    assert peer_bus.registry()[0]["session_id"] == ROOT_A          # written, not just returned


def test_publish_derives_id_from_the_harness_dir(bus, env):
    # A subagent's own id only appears in RLM_HARNESS_STATE_DIR; RLM_SESSION_DIR holds its parent's.
    env.setenv("RLM_HARNESS_STATE_DIR",
               f"/a/session-artifacts/{ROOT_B}/session-artifacts/{CHILD}/harness")
    env.setenv("RLM_DEPTH", "1")
    bus("a"); peer_bus.init("alice")
    card = peer_bus.publish("child")
    assert (card["session_id"], card["depth"]) == (CHILD, 1)


def test_publish_omits_identity_when_the_runtime_is_silent(bus, env):
    bus("a"); peer_bus.init("alice")
    card = peer_bus.publish("initiator")
    assert "session_id" not in card and "depth" not in card        # omitted, never guessed
    assert set(card) == {"alias", "purpose", "accepting", "published"}   # v0 schema unchanged


def test_publish_prefers_explicit_identity(bus, env):
    env.setenv("PRIME_AGENT_SESSION_ID", "sniffed-and-wrong")
    bus("a"); peer_bus.init("alice")
    card = peer_bus.publish("initiator", session_id=ROOT_A, depth=0)
    assert card["session_id"] == ROOT_A


def test_watcher_prompt_names_the_receiver_session(bus, env):
    env.setenv("PRIME_AGENT_SESSION_ID", ROOT_A); env.setenv("RLM_DEPTH", "0")
    bus("b"); peer_bus.init("bob"); peer_bus.publish("acceptor", session_id=CHILD, depth=1)
    bus("a"); peer_bus.init("alice"); peer_bus.publish("initiator")
    prompt = peer_bus.watcher_prompt("bob")
    assert CHILD in prompt                                          # the receiver, by session id
    assert "agent_message.list_agents()" in prompt                  # resolve the role from the roster
    assert str(peer_bus._spool("bob")) in prompt


def test_watcher_prompt_refuses_root_to_root(bus, env):
    env.setenv("PRIME_AGENT_SESSION_ID", ROOT_A); env.setenv("RLM_DEPTH", "0")
    bus("b"); peer_bus.init("bob"); peer_bus.publish("acceptor", session_id=ROOT_B, depth=0)
    bus("a"); peer_bus.init("alice"); peer_bus.publish("initiator")
    with pytest.raises(ValueError) as e:
        peer_bus.watcher_prompt("bob")
    msg = str(e.value)
    assert "directly" in msg and ROOT_B in msg and "receiver_role='sibling'" in msg


def test_watcher_prompt_tells_a_non_root_to_ask_a_root(bus, env):
    env.setenv("RLM_DEPTH", "1")
    bus("b"); peer_bus.init("bob"); peer_bus.publish("acceptor", session_id=ROOT_B, depth=0)
    bus("a"); peer_bus.init("alice")                                # never published: identity from env
    with pytest.raises(ValueError) as e:
        peer_bus.watcher_prompt("bob")
    assert "ask a root session" in str(e.value)


def test_watcher_prompt_warns_when_identity_is_unknown(bus, env):
    bus("b"); peer_bus.init("bob"); peer_bus.publish("acceptor")    # v0 card, no identity
    bus("a"); peer_bus.init("alice")
    prompt = peer_bus.watcher_prompt("bob")
    assert "REACH WARNING" in prompt and "bob" in prompt
    assert "pump()" in prompt                                       # wakes optimise, never guarantee
    assert str(peer_bus._spool("bob")) in prompt
