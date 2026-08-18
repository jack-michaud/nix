// ship-check: verify a PR's attestations before the orchestrator's model reads
// about it. Seam, guarantees and non-guarantees: ../../skills/ship-check/SKILL.md

import * as fs from "node:fs/promises";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILLS = path.resolve(HERE, "..", "..", "skills");
const CHECKER = path.join(SKILLS, "ship-check", "src");
const ATTEST = path.join(SKILLS, "attest", "src");

const AGENT_MESSAGE_MARKER = "Agent-to-agent message received.";
const PR_URL = /https?:\/\/(?:www\.)?github\.com\/[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+\/pull\/\d+/;
const ALREADY_ANNOTATED = "SHIP-CHECK:";

function textParts(message) {
  const content = message?.content;
  if (typeof content === "string") return [{ get: () => content, set: undefined }];
  if (!Array.isArray(content)) return [];
  return content
    .filter((part) => part && part.type === "text" && typeof part.text === "string")
    .map((part) => ({ get: () => part.text, set: (value) => { part.text = value; } }));
}

function candidates(messages) {
  const found = [];
  for (const message of messages ?? []) {
    for (const part of textParts(message)) {
      const text = part.get();
      if (!text.includes(AGENT_MESSAGE_MARKER)) continue;
      if (!PR_URL.test(text)) continue;
      if (text.includes(ALREADY_ANNOTATED)) continue;
      found.push({ message, part, text });
    }
  }
  return found;
}

export default function shipCheck(pi) {
  pi.on("context", async (event) => {
    // Guarded whole: `emitContext` swallows a throwing handler, so an escaping
    // exception would disable the gate silently. Failures become visible instead.
    try {
      return await run(pi, event);
    } catch (error) {
      annotateAll(event.messages,
        `SHIP-CHECK: the check itself failed (${error?.message ?? String(error)}). ` +
        "Treat every PR URL above as UNVERIFIED.");
      return { messages: event.messages };
    }
  });
}

function annotateAll(messages, notice) {
  for (const message of messages ?? []) {
    for (const part of textParts(message)) {
      const text = part.get();
      if (!text.includes(AGENT_MESSAGE_MARKER) || !PR_URL.test(text)) continue;
      if (text.includes(ALREADY_ANNOTATED) || !part.set) continue;
      part.set(`${text}\n\n---\n${notice}\n`);
    }
  }
}

async function run(pi, event) {
  {
    const pending = candidates(event.messages);
    if (pending.length === 0) return undefined;
    for (const item of pending) {
      let notice;
      let scratch;
      try {
        scratch = await fs.mkdtemp(path.join(os.tmpdir(), "ship-check-"));
        const messageFile = path.join(scratch, "message.txt");
        await fs.writeFile(messageFile, item.text, "utf8");
        const result = await pi.exec("python3", ["-m", "ship_check", "--message-file", messageFile], {
          timeout: 180_000,
          env: { PYTHONPATH: [CHECKER, ATTEST].join(path.delimiter) },
        });
        if (result.code !== 0) {
          notice = `SHIP-CHECK: could not run (exit ${result.code}): ` +
            `${(result.stderr || result.stdout || "").trim().slice(0, 400)}`;
        } else {
          const parsed = JSON.parse(result.stdout || "{}");
          notice = parsed.notice || undefined;
        }
      } catch (error) {
        notice = `SHIP-CHECK: could not run (${error?.message ?? String(error)})`;
      } finally {
        if (scratch) await fs.rm(scratch, { recursive: true, force: true }).catch(() => {});
      }
      if (notice && item.part.set) {
        item.part.set(`${item.text}\n\n---\n${notice}\n`);
      }
    }
    return { messages: event.messages };
  }
}
