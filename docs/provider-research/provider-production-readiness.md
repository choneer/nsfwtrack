# Provider Production Readiness v1

## Decision

No repository-derived candidate is production-ready. None may be registered as
the first NSFWTrack Production Provider. The profile is `reference only`, the
video metadata Approval draft remains `draft / not approved / no production
activation`, and the Production Registry remains `EndpointRegistry(())`.

## Readiness matrix

| Candidate | Useful evidence | Blocking facts | Decision |
|---|---|---|---|
| JavdBviewed | local state, manual-field protection, soft delete and sync contract | browser extension/site-specific behavior, AGPL implementation, no user-approved fixed Provider facts | not activatable |
| JavSP | broad metadata vocabulary and deterministic multi-source merge | multi-site scraper, GPL plus README additional terms, no single approved Provider or fixed response contract | not activatable |
| FnDepot | versioned manifest, stable keys, explicit overrides and compatibility concepts | application source rather than content Provider; no root license; executable/download-shaped fields excluded | not activatable |
| Venera | source identity/version and operation/pagination taxonomy | archived and explicitly unmaintained; GPL-3.0; JavaScript/remote-source model excluded | not activatable |

## Production Readiness Blockers

Before any production Provider work, a new explicit approval must provide all of:

- Provider identity, NSFW-core purpose, lawful access and terms basis;
- exact HTTPS host and endpoint facts for each individually approved operation;
- method, typed parameters, response kind/schema, limits, pagination and errors;
- authentication/cookie policy or an explicit no-auth statement without secrets;
- field mappings, provenance, conflict and retention obligations;
- redacted static success/error fixtures and exact digest catalog;
- an immutable code-owned adapter binding and the production Artifact v1;
- review of license, attribution and maintenance risk.

The package must then pass existing N4D-C and N4D-D-A gates. A repository README,
manifest, source response, user input or locator cannot substitute for approval.

## Preserved safety boundaries

- Search, detail and optional asset listing remain separate, explicit,
  zero-write operations; no operation chains to another operation.
- No arbitrary URL, crawler, selector, browser automation, login, Cookie,
  playback, download, remote JavaScript or dynamic import is admitted.
- Unknown, incomplete or contradictory evidence is retained as a blocker; it is
  never guessed into a Provider, success, deletion or permission.
- Provider content does not authorize filesystem, database, credential or media
  writes. Local user fields and manual edits remain authoritative.
- No Schema, Backup, dependency, Registry, Outbound, Docker, CI, version,
  background task, tag, Release or N100 deployment is part of B0.
