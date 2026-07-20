#!/usr/bin/env python3
"""Referenced from ~/.claude/settings.json by the `coding-agents` module of
Jack's nix config. PostToolUse hook implementing the agent-rules contract for
Claude Code, mirroring the pi extension (pi-extensions/agent-rules.ts): rules
in ~/.claude/rules/ with YAML frontmatter `paths` globs are injected as
additionalContext the first time a tool call in the session touches a matching
file. Claude Code handles rules without `paths` natively (always-on, loaded at
session start) but never fires path-scoped rules whose globs point outside the
project — this hook fills that gap.

Python stdlib only; must stay runnable by the macOS system python3 (3.9)."""

import json
import os
import re
import sys
import time

RULES_DIR = os.path.expanduser("~/.claude/rules")
STATE_DIR = os.path.expanduser("~/.cache/claude-code/global-rule-files")
STATE_MAX_AGE_SECONDS = 7 * 24 * 3600


def parse_paths_list(frontmatter):
    """Supports the two YAML list spellings used in rules frontmatter:
    paths: ["a/**", "b/**"]     and     paths:\n  - a/**\n  - b/**"""
    inline = re.search(r"^paths:\s*\[([^\]]*)\]", frontmatter, re.MULTILINE)
    if inline:
        entries = [e.strip().strip("\"'") for e in inline.group(1).split(",")]
        return [e for e in entries if e]
    block = re.search(r"^paths:\s*\r?\n((?:\s+-\s+.*\r?\n?)+)", frontmatter, re.MULTILINE)
    if not block:
        return []
    entries = [
        re.sub(r"^\s+-\s+", "", line).strip().strip("\"'")
        for line in block.group(1).splitlines()
    ]
    return [e for e in entries if e]


def parse_rule(name, raw):
    match = re.match(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?", raw)
    if not match:
        return {"name": name, "paths": [], "body": raw.strip()}
    return {
        "name": name,
        "paths": parse_paths_list(match.group(1)),
        "body": raw[match.end():].strip(),
    }


def glob_to_regexp(glob):
    expanded = os.path.join(os.path.expanduser("~"), glob[2:]) if glob.startswith("~/") else glob
    source = re.sub(r"[.+^${}()|\[\]\\]", lambda m: "\\" + m.group(0), expanded)
    source = source.replace("**", "\x00")
    source = source.replace("*", "[^/]*")
    source = source.replace("?", "[^/]")
    source = source.replace("\x00", ".*")
    return re.compile("^" + source + "$")


def load_path_scoped_rules():
    try:
        names = sorted(os.listdir(RULES_DIR))
    except OSError:
        return []
    rules = []
    for name in names:
        if not name.endswith(".md"):
            continue
        try:
            with open(os.path.join(RULES_DIR, name), encoding="utf-8") as f:
                rule = parse_rule(name, f.read())
        except OSError:
            continue
        if rule["paths"]:
            rules.append(rule)
    return rules


def tool_path(tool_input):
    for key in ("file_path", "path", "filePath", "notebook_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def matches(rule, absolute_path):
    return any(glob_to_regexp(g).match(absolute_path) for g in rule["paths"])


def rule_reminder(rule):
    return '<agent-rule source="~/.claude/rules/{name}">\n{body}\n</agent-rule>'.format(
        name=rule["name"], body=rule["body"]
    )


def state_path(session_id):
    return os.path.join(STATE_DIR, re.sub(r"[^A-Za-z0-9._-]", "_", session_id))


def read_injected(session_id):
    try:
        with open(state_path(session_id), encoding="utf-8") as f:
            return set(f.read().split())
    except OSError:
        return set()


def record_injected(session_id, names):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(state_path(session_id), "a", encoding="utf-8") as f:
        f.write("".join(name + "\n" for name in names))
    prune_stale_state()


def prune_stale_state():
    cutoff = time.time() - STATE_MAX_AGE_SECONDS
    try:
        for name in os.listdir(STATE_DIR):
            path = os.path.join(STATE_DIR, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.unlink(path)
            except OSError:
                pass
    except OSError:
        pass


def main():
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input") or {}
    raw_path = tool_path(tool_input)
    if not raw_path:
        return
    if os.path.isabs(raw_path):
        absolute_path = os.path.normpath(raw_path)
    else:
        absolute_path = os.path.normpath(os.path.join(data.get("cwd") or os.getcwd(), raw_path))

    rules = load_path_scoped_rules()
    if not rules:
        return
    session_id = data.get("session_id") or "unknown"
    injected = read_injected(session_id)
    due = [r for r in rules if r["name"] not in injected and matches(r, absolute_path)]
    if not due:
        return

    record_injected(session_id, [r["name"] for r in due])
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "\n\n".join(rule_reminder(r) for r in due),
        }
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
