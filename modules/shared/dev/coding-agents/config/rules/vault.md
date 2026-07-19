---
paths: ["@vaultDir@/**"]
---

# Vault rules

How to work inside Jack's Obsidian vault at `@vaultDir@`.

## Reading

- Notes are plain Markdown. A `[[Wikilink]]` names another note by title:
  resolve `[[Name]]` to `pages/Name.md`, falling back to the vault root or
  another folder — find it by filename if it isn't in `pages/`.
- `[[Name#^blockid]]` references the single line in `Name.md` tagged with a
  trailing `^blockid`.
- Apply progressive disclosure: start from a map of content (listed in
  `~/.agents/AGENTS.md`), follow only the links the task needs, and never
  bulk-read the vault.

## Writing (only when asked)

- One idea per note. General pages go in `pages/` with no top-level title
  header; daily journals go in `journals/YYYY_MM_DD.md`.
- Match Jack's style: bullets, tab-indented subbullets, `[[wikilinks]]`.
- Link liberally — a `[[link]]` to a note that doesn't exist yet is fine.
- Only reference a block via `[[Name#^uniqueid]]` after confirming the
  `^uniqueid` tag exists on a line in the target file.
- For a project- or company-specific wiki, follow the structure in
  `pages/Open Knowledge Format.md`.
