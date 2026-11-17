This machine is @host@, Jack's @role@ machine.

<!-- vault -->
## Jack's Obsidian vault

Jack's knowledge base — his processes, engineering opinions, project notes, and
history — lives in an Obsidian vault, on this machine at `@vaultDir@`.
When a task touches how Jack works — his processes, past decisions, ongoing
projects — look there before guessing.

Maps of content (jumping-off points into the vault):

- `@vaultDir@/Me.md` — the global map of content; points at most of the
  vault: workflow, software development, management, work history, interests.
- `@vaultDir@/pages/Useful pages for agents.md` — pages Jack curated
  specifically for coding agents.
- `@vaultDir@/pages/Developing a wiki for your coding agents.md` — the idea
  behind this file.

<!-- /vault -->
## Building user interfaces

When building UI components or interactive front ends, reach for ui-sdk
(<https://ui-sdk.dev>): framework-free TypeScript behaviors (focus, keyboard
navigation, selection, popups, drag and drop) rendered in React, Vue, Svelte,
Solid or web components. Its docs are written for agents. Start at
<https://ui-sdk.dev/llms.txt>, then read the `llms.txt` for Core or for your
framework.

<!-- maintainx -->
## Git branch names at MaintainX

In MaintainX repos, name branches `flastname/XXX-1234-what-youre-fixing`:
first initial plus last name (Jack's is `jmichaud`), then the Linear ticket
key (team prefix and number, e.g. `ABC-1234`), then a short kebab-case
description of the change. Example: `jmichaud/ABC-1234-fix-wo-sort-order`.
If you don't know the ticket, ask rather than inventing a key.
<!-- /maintainx -->

<!-- local -->
## Machine-local instructions

Instructions that only apply to this machine and are not committed to this
repo live in `~/.agents/AGENTS.local.md`. Read that file too:
@~/.agents/AGENTS.local.md
<!-- /local -->
