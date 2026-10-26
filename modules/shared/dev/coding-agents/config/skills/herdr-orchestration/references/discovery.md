# Version-checked discovery and relay

## Establish capabilities without mutation

Use the actual installed launchers. On Jack's current macOS setup `board` below
means `/Users/Jack/.herdr-projects/data/bin/herdr-projects`; on another host resolve
its installed launcher there. Do not copy that macOS path to Linux. Do not dump the
whole environment, settings files, process argv or transcript: they may contain secrets.

These read-only examples were checked on **2026-10-26** against Herdr **0.9.5**
(client/server protocol 22), Projects **1.2.26**, and Pi **1.4.0**. Check again before
use, especially on remote hosts. The installed Projects checkout's docs lag some
binary help: `docs/autopilot.md` was referenced by help but absent. Its older
`roles-and-commands.md` says task agents can run all commands; that is not proof
that the executing binary permits coordinator-setting writes from a task pane.
Jack's observed guard refusal must be honored; never probe permissions by mutating.

```bash
board=/Users/Jack/.herdr-projects/data/bin/herdr-projects
"$board" version
"$board" --help
herdr --version
herdr --help
herdr status
pi --version
```

Read installed Projects `docs/coordinator.md`,
`docs/machine-and-project-coordinators.md`, `docs/roles-and-commands.md`,
`docs/other-machines.md`, `docs/several-boards.md`, `docs/settings.md` and relevant
linked docs. `version` names the executing binary; locate its installed checkout
rather than assuming a development checkout matches it. Consult `herdr --skill`
and nested `--help`. Never use bare `herdr` or a mutating command with missing
arguments to discover syntax.

## Discover caller and coordinators

Only inspect/control Herdr when the caller is Herdr-managed. Do not strip its
identity to get a different answer. The following prints only identity fields:

```bash
test "${HERDR_ENV:-}" = 1 || exit 1
printf 'pane=%s task=%s socket=%s\n' \
  "${HERDR_PANE_ID:-unknown}" "${HERDR_PROJECTS_ID:-unknown}" \
  "${HERDR_SOCKET_PATH:-unknown}"
herdr pane current --help
herdr pane current --current
"$board" coordinator --json
"$board" coordinator --machine --json
"$board" autopilot --json
herdr machine list --json
herdr agent list
herdr pane list
```

`autopilot` with no action is coordinator **inventory**, not an instruction to turn
it on. Run project status only with a repo actually returned by that inventory or
board data. The following is a safe dated example using the existing dotfiles
project; a `state: none` response is absence, not permission to start it:

```bash
"$board" coordinator --project dotfiles --json
"$board" show --repo dotfiles --json
```

Match board `.pane` to Herdr `.result.agents[]`/`.result.panes[]` IDs, live cwd,
agent kind, `agent_session`, `agent_status` and `interactive_ready` where returned.
Check the response envelope instead of assuming a JSON shape from another version.
For the returned main pane only, after reviewing help:

```bash
herdr agent get --help
# Set main_pane to the .pane returned above, never an old note or display title.
herdr agent get "$main_pane"
herdr pane process-info --help
# Process-info may contain secret-bearing argv: filter to identity, never print raw.
herdr pane process-info --pane "$main_pane" | python3 -c '
import json, sys
p = json.load(sys.stdin)["result"]["process_info"]
print(json.dumps({"pane_id": p["pane_id"], "processes": [
    {k: v.get(k) for k in ("pid", "name", "cwd")}
    for v in p.get("foreground_processes", [])]}))'
```

`main_pane` is deliberately unset in this document: resolve it from the current
response, check non-empty and host/session match before using it. A general agent
name must be unique and live; a pane can outlive its former agent.

A Pi `agent_session` with `kind: path` names a transcript **filename**, not necessarily
the session ID. If necessary read only that returned file's first JSONL session
header with a structured reader (type/id/cwd/timestamp fields only); compare its
header ID and cwd to live metadata. Do not scan unrelated transcripts or infer the
ID by stripping a timestamp from its filename. Saved board state can be stale and
can even associate the same session string with different coordinator directories:
it is a hint, not authority. Even header IDs can coincide across different cwd/path
namespaces: bind host/socket, pane, cwd, header and transcript path together rather
than routing on session ID alone. Do not open/resume the file as a second writer.

Keep these distinct: canonical task ID, human task alias, Herdr pane ID, terminal
ID, Pi session header ID, transcript path and Herdr persistent-session name.
A lifecycle state such as idle/done does not prove an external receiver is active;
a retained agent may not be foreground. An active process is not necessarily ready
to receive. Use the receiver owner's supported readiness evidence if relevant;
otherwise report receiver readiness unknown. HOME-26 owns that interface.

## Machine boundaries

`herdr machine list --json` is saved registrations, **not** a reachable fleet or
cross-machine pane inventory. Network status is read-only, but may take time:

```bash
herdr machine status --help
herdr machine status --json
"$board" machines --json
```

Do not wake unreachable hosts. On a saved enabled/reachable profile whose local
and remote versions support API forwarding, use its returned ID or unique,
case-sensitive label consistently. Example after setting `machine_id` from that
inventory (not an arbitrary SSH hostname):

```bash
herdr --machine "$machine_id" agent list
herdr --machine "$machine_id" pane list
```

Herdr's `--machine` targets that profile's Herdr API, not arbitrary Projects shell
commands; `herdr-projects coordinator --machine` means the **local machine
coordinator**, not a remote selector. Do not invent `--on` support for commands
whose installed help does not offer it. Board remote task views and Herdr remote
pane forwarding are different interfaces. Discover the remote Projects version,
help and host-local coordinator inventory through an already authorized supported
remote interface, or mark remote discovery incomplete. Do not invent a federated
coordinator command or a credential-changing SSH workaround. No local fallback
on remote failure. Client, server and Projects versions may differ by host.

## Relay without role bypass

Only after verifying the actual main process/cwd/session and supported help,
relay the authorized request. Do not send merely to test the interface; `tell`
can start an absent coordinator. No `--delegate` in a relay/status request.
`$relay` must be a shell variable holding reviewed literal text, not executable
shell content. Example message:

> Jack requested [exact words]. Original caller: [host/socket/pane, task ID,
> project/root]; actual target: [fresh main identity evidence]. Authorized scope:
> [exact requested board/coordinator change]. Already answered/approved: [context].
> Excluded: [new work, credential/trust changes, restarts, unrelated settings].
> Preserve existing custom instructions and task/operator/history ownership. You
> are actual main: execute only within Jack's scope, do not relay back to yourself.
> Return acceptance, applied changes and exact scoped readback, or a genuine owner
> blocker. No duplicate task/worker/coordinator. Request key: [unique correlation].

```bash
# Side effect: sends this explicitly authorized relay to the verified main.
"$board" coordinator tell "$relay"
# Read-only follow-up; do not assume the immediate response proves application.
"$board" coordinator --json
```

Read back only the requested values with supported status/`show` for that scope;
avoid dumping instructions that may contain private context. A latest `said`
response can belong to an earlier request. Match the correlation and request
context. `coordinator where` is main's supported way to reconcile message context;
a forwarded shell's cwd does not necessarily identify Jack's intended repo.
If readback isn't exposed in that version, get a scoped receipt from the actual
owner and label verification limits instead of claiming independent verification.

Failure outcomes: auth denied → genuine owner auth blocker; no live main → target
availability limitation; wrong cwd/session → identity failure; missing coordinator
inventory/remote help → incomplete discovery. Preserve work and report the four-part
progress context in every case. Never unset task context, change guards, start a
second coordinator, blindly retry uncertain delivery, or write into transcripts.

## Dated observations, not configuration

**2026-10-26 only:** Sesame caller `w8X:p1` was associated with FKB-1; local main
was independently verified at `w95:pC`, and machine reported `w95:pB`. This task's
fresh discovery corroborated main's live Pi cwd/session metadata. None of these
IDs is a constant or proof of future identity. The main routing receipt in
`/Users/Jack/.herdr-projects/data/coordinator/default/chat/AGENTS.md` is historical
context, not the sole reusable result or a receiver implementation.

Reporting-policy settings were previously saved/readback-verified across six
DAMOCLES coordinators (main, machine, Jack, chenplan, home-digital-twin, qr-relay)
and Spark main/error-trace-dreamer, preserving custom instructions and future
defaults on both. This is a dated receipt, not fresh live acceptance by all eight.
Spark reported Projects 1.2.17 while local reported 1.2.26. Darkforest was registered
but unreachable: not updated/activated. Rediscover before future action.
