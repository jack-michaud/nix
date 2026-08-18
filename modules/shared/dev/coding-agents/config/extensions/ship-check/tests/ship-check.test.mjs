/**
 * End-to-end test for the ship-check extension, run with `node test.mjs`.
 *
 * Fake, not mocked: the fake `pi` really spawns the real Python checker, which
 * really shells out to a `gh` executable written to disk. What is under test is
 * the seam - that the handler finds an inbound agent message carrying a PR URL,
 * and that the messages it RETURNS (the ones the model would be sent) carry the
 * verdict.
 */

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import * as fs from "node:fs/promises";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

import shipCheck from "../index.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));

function makePi() {
  const handlers = new Map();
  return {
    on: (event, handler) => handlers.set(event, handler),
    exec: (command, args, options = {}) =>
      new Promise((resolve, reject) => {
        const child = spawn(command, args, {
          env: { ...process.env, ...options.env },
        });
        let stdout = "";
        let stderr = "";
        child.stdout.on("data", (chunk) => { stdout += chunk; });
        child.stderr.on("data", (chunk) => { stderr += chunk; });
        child.on("error", reject);
        child.on("close", (code) => resolve({ stdout, stderr, code, killed: false }));
      }),
    fire: (event, payload) => handlers.get(event)(payload, {}),
    has: (event) => handlers.has(event),
  };
}

const message = (url) =>
  [
    "[from child:worker-7]",
    "Agent-to-agent message received.",
    "Source: agent_message",
    "From: active abc123def456, session 0199-aaa, client agent",
    "To: orchestrator, active ffffff000000",
    "Message id: agentmsg_1",
    "",
    `PR is up for review: ${url}`,
  ].join("\n");

const tmp = await fs.mkdtemp(path.join(os.tmpdir(), "ship-check-test-"));
const gh = path.join(tmp, "gh");
await fs.writeFile(
  gh,
  [
    "#!/usr/bin/env python3",
    "import json, sys",
    'print(json.dumps({"body": "A PR body with no trailer.", "base": {"ref": "main"},',
    '                  "head": {"ref": "feature", "sha": "0" * 40}, "state": "open",',
    '                  "draft": False, "html_url": "https://github.com/o/r/pull/9"}))',
  ].join("\n"),
  { mode: 0o755 },
);
process.env.SHIP_CHECK_HOME = tmp;
process.env.ATTEST_HOME = tmp;
process.env.GH_BIN = gh;

const pi = makePi();
shipCheck(pi);
assert.ok(pi.has("context"), "the extension must register a context handler");

const url = "https://github.com/o/r/pull/9";
const messages = [{ role: "user", content: [{ type: "text", text: message(url) }] }];
const result = await pi.fire("context", { type: "context", messages });
const seenByModel = result.messages[0].content[0].text;

assert.match(seenByModel, /SHIP-CHECK: attestations DO NOT validate/);
assert.match(seenByModel, /no `Shipped-With:` trailer/);
assert.match(seenByModel, /agent_message\.send/);
assert.match(seenByModel, /receiver_name="worker-7"/);
assert.ok(seenByModel.includes(url), "the original message text is preserved");

// Once per PR URL: a second delivery of the same URL adds nothing, and the
// handler leaves an already-annotated message alone.
const again = [{ role: "user", content: [{ type: "text", text: message(url) }] }];
const second = await pi.fire("context", { type: "context", messages: again });
assert.ok(!second.messages[0].content[0].text.includes("SHIP-CHECK"),
  "a PR URL already on record must not be checked or annotated again");

// A message with no PR URL is left untouched, and no check runs.
const plain = [{ role: "user", content: [{ type: "text", text: "no links here" }] }];
const third = await pi.fire("context", { type: "context", messages: plain });
assert.equal(third, undefined, "nothing to check must return no replacement");


// -- failure modes ---------------------------------------------------------
// An exception escaping this handler would be swallowed by `emitContext`, which
// disables the gate silently. Two properties are asserted: the handler does not
// throw (so the turn is never blocked - fail-open, documented), and the reason
// is visible in what the model reads rather than vanishing.

const broken = makePi();
broken.exec = () => { throw new Error("python3 is missing"); };
shipCheck(broken);
const brokenMessages = [
  { role: "user", content: [{ type: "text", text: message("https://github.com/o/r/pull/11") }] },
];
const brokenResult = await broken.fire("context", { type: "context", messages: brokenMessages });
assert.match(brokenResult.messages[0].content[0].text, /SHIP-CHECK: could not run/);
assert.match(brokenResult.messages[0].content[0].text, /python3 is missing/);

const hostile = makePi();
hostile.exec = () => ({ get stdout() { throw new Error("hostile result"); } });
shipCheck(hostile);
const hostileMessages = [
  { role: "user", content: [{ type: "text", text: message("https://github.com/o/r/pull/12") }] },
];
const hostileResult = await hostile.fire("context", { type: "context", messages: hostileMessages });
assert.match(hostileResult.messages[0].content[0].text, /SHIP-CHECK/);

// The orchestrator's own prose naming a PR URL is not an inbound agent message
// and must not be checked.
const ownProse = makePi();
let execs = 0;
ownProse.exec = () => { execs += 1; return { stdout: "{}", stderr: "", code: 0 }; };
shipCheck(ownProse);
await ownProse.fire("context", {
  type: "context",
  messages: [{ role: "user", content: [{ type: "text", text: "I opened https://github.com/o/r/pull/13" }] }],
});
assert.equal(execs, 0, "only a delivered agent message is checked");

await fs.rm(tmp, { recursive: true, force: true });
console.log("ok - ship-check extension");
