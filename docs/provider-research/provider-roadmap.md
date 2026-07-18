# Provider Research Roadmap

## 1. N4C outcome

Phase 5-N4C establishes architecture and Approval-draft inputs for three
directions without activating a Provider:

- video metadata: Provider-neutral identities, DTOs, `search`, `detail`,
  optional `asset_list`, provenance, conflict, and merge rules;
- subscription and future playback: catalog/revision/candidate/diff validation,
  candidate-only Approval, explicit refresh, playback DTOs, and state machines;
- comics: fixed Python adapters, Provider-scoped comic/chapter/page identities,
  search/category/detail/chapter/page/asset operations, and local reading-state
  separation.

The Production Provider Registry remains `EndpointRegistry(())`. All three
Approval documents are `draft / not approved` and contain placeholders only.

## 2. Evidence ledger

| Direction | Public reference | Reviewed commit | License conclusion | Adopted only as architecture |
|---|---|---|---|---|
| Video metadata/state | `lmixture/JavdBviewed` | `e26dfdf97c1a68a8f27035ecf8e982208bdc79e0` | `AGPL-3.0-only` | layer separation, local/source state split, parser/refresh boundaries, preview lifecycle |
| Video metadata aggregation | `Yuukiy/JavSP` | `c4cfe61188234dd24c75b53b42b054327fef3e58` | `GPL-3.0-only`; README adds Anti-996/additional claims | source-scoped results, metadata vocabulary, deterministic merge/required-field/fixtures |
| Subscription catalog | `EWEDLCM/FnDepot` | `e565623a1797aaf40b6b376720046d9451bc6a0d` | no root license established | catalog identity, revision/override/diff concepts |
| Comic capability model | `venera-app/venera` | `a0eba914f4c2a84ac1bc925adec2baabe920b9be` | `GPL-3.0`; project states unmaintained | capability/DTO/lifecycle/reading-flow concepts |

No code is copied. Site-specific networking, crawling, DOM/userscript behavior,
filesystem mutation, dynamic import, auto-sync/update/retry/download, and remote
JavaScript execution are rejected.

## 3. Missing inputs and blockers

| Input | N4C evidence | Consequence |
|---|---|---|
| User-provided subscription JSON | unavailable outside the protected local-data boundary | only the authorized field names `id`, `name`, `baseUrl`, `group`, `enabled`, `priority` are modeled; envelope/version/types remain blocked |
| User-provided standalone userscript | unavailable outside the protected local-data boundary | SPA/HLS/progress/cancellation/conversion specifics remain blocked; public repository script is not a substitute |
| Real video Provider Approval | placeholder only | N4D cannot begin implementation |
| Catalog source Approval | placeholder only | N4E cannot fetch any subscription |
| Runtime streaming Provider Approval | placeholder only | N4F cannot resolve or play media |
| Real comic Provider Approval | placeholder only | N4G cannot begin implementation |

If missing inputs are supplied later, they may be statically read only under a
new explicit GOAL. Subscription candidate addresses must remain uncontacted,
and scripts must remain unexecuted.

## 4. Fixed implementation sequence

### N4C - static research and Approval drafts

Deliverables are these seven documents. Exit gate:

- exact public commit/license/reference ledger recorded;
- all DTO, operation, network, write, permission, auth, error, and uncertainty
  boundaries documented;
- Approval drafts contain placeholders only and are not approved;
- no runtime/configuration/Schema/dependency/Registry change.

### N4D - first video metadata Provider

Scope:

```text
search + detail + optional asset_list
```

Entry gate: one complete video Approval with exact Provider identity, lawful and
terms basis, fixed hosts/operations, response types/limits, mappings, and static
fixtures; typed production Approval must pass the local Validator.

Exit gate: fixed reviewed adapter, shared client only, no user URL/host input,
no operation chaining, immutable DTOs with provenance, deterministic fixtures,
Production Registry containing only the explicitly approved surface. Auth,
playback, download, background sync, and a second Provider remain denied.

### N4E - subscription catalog management

Scope:

```text
refresh + parse + validate + revision + diff + approve candidate + disable
```

Entry gate: actual subscription format is statically reviewed and the one fixed
catalog source has a complete Approval. Implementation must never access a
candidate `baseUrl` during refresh or review.

Exit gate: authenticated explicit POST refresh only; GET zero-network; strict
bounded all-or-nothing parsing; immutable revision/diff; candidate approval is
separate from runtime Provider activation; ordinary/`premium` groups confer no
auth/playback permission; no background refresh.

### N4F - online playback Provider

Scope:

```text
search + detail + playback_list + playback_resolve + playback UI
```

Entry gate: one candidate has a separate complete runtime Streaming Provider
Approval, including exact metadata/asset/playback/auth/redirect hosts, manifest
types, relative-reference rules, auth lifecycle, limits, and fixtures. Catalog
approval alone is insufficient.

Exit gate: explicit player lifecycle and cancellation, opaque source/manifest/
variant identities, short-lived internal locators, exact host and DNS/TLS/peer
checks, no silent refresh/retry, no download or access-control bypass, and
unknown never displayed as ready/success.

### N4G - comic Provider

Initial scope:

```text
search + detail + chapter_list + page_list
```

`category_list`, `category_items`, and `asset_list` are included only if the
same explicit Approval authorizes them. Entry gate: complete comic Approval,
fixed reviewed Python adapter design, exact hosts/operations, and static
fixtures. JavaScript engines and remote Source packages remain prohibited.

Exit gate: Provider-scoped comic/chapter/page identities, page/asset/locator
separation, local reading progress separate from remote state, no full-chapter
automatic fetch, and no auth/favorite/comment/rating/download unless separately
authorized.

### N5 - unified source search, preview, and manual import UI

Consumes approved Provider DTOs only. Search and detail remain network reads;
apply is a separate signed local write with manual-field conflict review.
Subscription review and playback are not implicit search side effects.

### N6 - controlled asset save and download tasks

Requires separate per-Provider download Approval and explicit user
confirmation. Reuses temporary isolation, streamed actual-byte bounds,
MIME/magic/hash checks, no-overwrite publication, exact reference writes,
independent commit-error review, cancellation, and one media-index coordination
per request. No hidden worker, unlimited batch, or inferred download right.

### N7 - multi-source update, controlled sync, and recommendation

Still requires a new GOAL. Any background work is visible, default-off,
bounded, cancellable, and separately approved. Local recommendations do not
create network/download authority. Optional AI remains outside the current
roadmap unless separately authorized.

## 5. Cross-phase gates

Every real phase must prove:

1. Provider Approval is complete, production-scoped, explicitly approved by the
   user, and exactly matches code-owned capabilities/endpoints.
2. Fixed hosts and operations cannot be expanded by browser input, catalog
   data, Provider responses, locators, redirects, scripts, or environment.
3. GET rendering has no hidden Provider network, secret test, refresh, or local
   write. Unsafe actions are explicit authenticated signed POSTs.
4. Search, detail, asset list/resolve, playback, apply, remote mutation, and
   download are separate operations and permissions.
5. DTO identity and provenance are deterministic; missing does not mean delete;
   user fields and local state remain authoritative.
6. Stable failures cover `invalid_request`, `not_approved`, `not_supported`,
   `unauthorized`, `forbidden`, `not_found`, `rate_limited`,
   `provider_unavailable`, `invalid_payload`, `response_too_large`, `expired`,
   `cancelled`, and `unknown` without leaking raw values.
7. Tests use reviewed static fixtures, fake resolver/transport/clock, and
   isolated temporary storage; no real media, Provider, candidate address, or
   protected local data is accessed.
8. Unknown or mixed outcomes preserve evidence, never guess deletion or
   success, and invalidate derived state where a later local mutation requires
   it.

## 6. Invariants preserved by N4C

- Application version: `1.1.0`.
- Schema: `4`.
- Backup: `nsfwtrack.backup.v2` with v1 restore compatibility.
- Production Provider Registry: `EndpointRegistry(())`.
- No real Provider, host, endpoint, credential, authentication, playback,
  download, background task, dependency, migration, Schema, Backup, Docker,
  Compose, or CI change.
- No userscript or remote JavaScript execution.
- No Hermes call, tag, Release, or N100 deployment.
- Existing local `data/` remains outside all research and test activity.
