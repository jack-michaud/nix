# Using code mode

## Storing values

### Reference
store(key, value) keeps a JSON value under a string key for later codemode calls; storing undefined deletes the key. load(key) returns the value, or undefined. Writes are kept only when the script succeeds: each successful script that stores values appends a codemode-store custom entry to the session, so resumed sessions keep the values and each branch sees only the values written on its path.

The store is for small state such as IDs, cursors, or summaries. One value may have at most 262144 characters of JSON and all values together at most 1048576. Do not store image data; show images with image(), which also saves them to a temp file.

### Using stored values
- Save bash script helpers
- Compose task descriptions instead of rewriting them from scratch

# Herdr Projects

## When to ask for human input

- RLY-33’s [denied D1 renewal check](https://damocles.bison-draconis.ts.net:8750/qr-relay/33/report/report.md) left both renewals unknown: ask Jack for scoped access help and keep the task awaiting him despite report approval—the final quote wrongly omits that ask.
  - > Cloudflare rejected the query request: **API error 7403 — “The given account is not valid or is not authorized to access this service.”** Wrangler exited 1 and returned no subscription rows.
  - > **Exact missing capability:** successful authenticated, scoped remote D1 SELECT access to this production database under the existing operator access.
  - > **No new generic permission or setup change is requested from Jack.**
