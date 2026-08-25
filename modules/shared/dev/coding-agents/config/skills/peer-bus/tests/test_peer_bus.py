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
