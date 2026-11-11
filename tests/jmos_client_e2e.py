"""End to end: the jmos client config this flake builds for a host, in a real
jmos window against a real, throwaway `jmos jmosd`.

Run on the machine the config names as its server (DAMOCLES for AUTODESK),
because the config is used byte for byte: the window connects to the host
and port written in it. The server here is a temporary one with its own data
folder, socket and token; the real jmosd, its database and the vault are
never touched. The port must be free (the real jmosd does not listen on TCP
until it is set up for this).

    nix build --no-link --print-out-paths \
      '.#darwinConfigurations.AUTODESK.config.home-manager.users.michauj.home.file.".config/jmos/1.0/config.toml".source'
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=~/Code/github.com/jack-michaud/os/tests \
      python3 tests/jmos_client_e2e.py --config /nix/store/...-jmos-config.toml

A jmos before jmos#166 fails this test at "[CONNECTED]": its edge sent the
config's `${KEY}` text itself as the token instead of the secret.
`--raw-reference-token` shows that bug: it gives the temporary server the
reference text as its token. Never set a real server up that way: that text
is in this repo, not a secret.

Run it through `av inject +KEY -- python3 …` (KEY as the config names it) to
use the vault's secret for both the temporary server and the window.

Needs pyte (the jmos repo's tests/requirements.txt) and that repo's PTY
window harness (tests/harness/two_ui.py) on PYTHONPATH; it is only read.
"""

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import tomllib
from pathlib import Path

from harness.two_ui import WaitTimeout, Window

TOKEN = "e2e-token-not-a-real-secret"


def env_for(home):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("JMOS_", "JMOSD_"))}
    env["HOME"] = str(home)
    return env


class Writer:
    """A scripted edge on the same TCP listener: another machine's writes."""

    def __init__(self, address, space, token):
        host, port = address.rsplit(":", 1)
        self.sock = socket.create_connection((host, int(port)), timeout=5)
        self.buf = b""
        self.n = 0
        hello = {"v": 1, "t": "hello", "session": "01E2EWRITER00000000000001",
                 "machine": "x", "space": space, "cursor": 0}
        if token is not None:
            hello["token"] = token
        self.send(hello)

    def send(self, message):
        self.sock.sendall((json.dumps(message) + "\n").encode())

    def first(self):
        try:
            while b"\n" not in self.buf:
                chunk = self.sock.recv(65536)
                if not chunk:
                    return None
                self.buf += chunk
        except (socket.timeout, ConnectionError):
            return None
        return json.loads(self.buf.split(b"\n", 1)[0])

    def create(self, title):
        self.n += 1
        self.send({"v": 1, "t": "intent", "op_id": "01E2EOP%019d" % self.n,
                   "name": "todo.create", "args": {"todo": {"title": title}}, "base_seq": 0})
        deadline = time.time() + 5
        while b'"applied"' not in self.buf and time.time() < deadline:
            self.buf += self.sock.recv(65536)
        assert b'"applied"' in self.buf, self.buf[-400:]
        self.buf = b""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path, help="the built jmos-config.toml")
    parser.add_argument("--binary", type=Path, default=Path(shutil.which("jmos") or "jmos"))
    parser.add_argument("--raw-reference-token", action="store_true",
                        help="the server accepts the unresolved ${KEY} text (jmos 2.0.0's edge sends that)")
    args = parser.parse_args()

    text = args.config.read_text()
    config = tomllib.loads(text)
    (name, server), = config["servers"].items()
    key = re.fullmatch(r"\$\{([A-Z0-9_]+)\}", server["token"])
    assert key, f"token must be a ${{KEY}} reference, got {server['token']!r}"
    key = key.group(1)
    assert server["url"].startswith("tcp://")
    address = server["url"][len("tcp://"):]
    host, port = address.rsplit(":", 1)
    listen = f"{socket.gethostbyname(host)}:{port}"
    # The secret the config names, when the caller supplies it (`av inject
    # +KEY -- python3 …`); else a made-up one. Never printed.
    secret = server["token"] if args.raw_reference_token else os.environ.get(key) or TOKEN
    print(f"config: [servers.{name}] {server['url']} space={server['space']} token=${{{key}}}")

    root = Path(tempfile.mkdtemp(prefix="jn-", dir="/tmp"))
    windows, proc = [], None
    try:
        # --- the throwaway server, as DAMOCLES's jmosd.toml would be set ---
        srv = root / "s"
        srv.mkdir()
        (srv / "jmosd.toml").write_text(
            f'[server]\nlisten = ["tcp:{listen}"]\n'
            f'[auth]\ntokens = {{ autodesk = "${{{key}}}" }}\n')
        proc = subprocess.Popen(
            [str(args.binary), "jmosd", "--socket", str(srv / "sock"), "--data-dir", str(srv / "data"),
             "--settings", str(srv / "jmosd.toml"), "--space", server["space"]],
            stderr=subprocess.PIPE, env={**env_for(srv), key: secret})
        deadline = time.time() + 10
        while True:
            try:
                socket.create_connection(tuple(listen.split(":")), timeout=0.5).close()
                break
            except OSError:
                assert time.time() < deadline and proc.poll() is None, "jmosd did not listen"
                time.sleep(0.05)
        print(f"server: temporary jmosd listening on tcp:{listen}")

        assert Writer(address, server["space"], "wrong").first() is None, "wrong token was let in"
        assert Writer(address, server["space"], None).first() is None, "no token was let in"
        writer = Writer(address, server["space"], secret)
        assert writer.first()["t"] == "welcome"
        writer.create("Milk from the server")
        print("server: wrong and missing tokens are closed; the right one is welcomed")

        def window(label, token, *flags):
            # The file where home-manager puts it: a symlink into the store.
            home = root / label
            path = home / ".config/jmos/1.0/config.toml"
            path.parent.mkdir(parents=True)
            path.symlink_to(args.config.resolve())
            env = {**env_for(home), "JMOS_CONFIG": str(path), "TERM": "xterm-256color"}
            if token is not None:
                env[key] = token
            win = Window(label, [str(args.binary), *flags], env, str(home))
            windows.append(win)
            return win

        # --- a window with the right token -------------------------------
        win = window("ok", secret)
        win.peek_for("MAIN MENU")
        try:  # an upgrade shows "What's new" once; close it
            win.peek_for("What's new in jmos", timeout=3)
            for _ in range(10):
                win.send(b"\x1b", settle=0.4)
                if "What's new in jmos" not in win.text():
                    break
        except WaitTimeout:
            pass
        menu = win.text()
        print("---- main menu ----\n" + menu + "\n-------------------")
        # A menu row: an optional cursor, the key, the entry's name in capitals.
        names = re.findall(r"^ >? +\S {2,}([A-Z][A-Z' ]*[A-Z]) {2,}", menu, re.M)
        assert names == ["TODO LIST", "QUIT"], f"main menu entries: {names}"
        print("window: the main menu is the todo list and quit, nothing else")
        win.peek_for("[CONNECTED]")
        win.send("t", settle=1.0)
        win.peek_for("Milk from the server")
        print("window: the server's todo shows in To Do's")
        # From here the window is only watched: the next todo must arrive live.
        writer.create("Bread, added while the window is open")
        win.wait_for_text("Bread, added while the window is open")
        assert "offline" not in win.text().lower()
        print("window: a todo written on the server appears with no key pressed")
        print("---- to do's ----\n" + win.text() + "\n-----------------")

        # --- wrong token, then none (vault off, so the real `av` is not asked).
        # Skipped with --raw-reference-token: that jmos ignores the variable.
        cases = (("bad", "not-the-token", ()), ("none", None, ("--no-vault",)))
        for label, token, flags in () if args.raw_reference_token else cases:
            bad = window(label, token, *flags)
            bad.peek_for("MAIN MENU")
            time.sleep(4)
            bad.send(b"\x1b", settle=0.4)
            bad.send("t", settle=2.0)
            screen = bad.text()
            print(f"---- token: {label} ----\n" + screen + "\n---------------------")
            assert "Milk from the server" not in screen, f"token {label}: the server's todos were read"
            assert "[CONNECTED]" not in screen, f"token {label}: the window says connected"
        print("PASS (the server took the unresolved reference text as the token)"
              if args.raw_reference_token else "PASS")
    finally:
        for w in windows:
            w.close()
        if proc:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
            err = proc.stderr.read().decode(errors="replace")
            if err.strip():
                print("---- jmosd stderr ----\n" + err[-3000:])
        shutil.rmtree(root, True)


if __name__ == "__main__":
    main()
