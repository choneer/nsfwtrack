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
| Video metadata/state | `lmixture/JavdBviewed` | `8c9245726906ece8d49f553542874980512d4504` | `AGPL-3.0-only` | local/source state split, manual edit protection, soft delete, sync facts |
| Video metadata aggregation | `Yuukiy/JavSP` | `c4cfe61188234dd24c75b53b42b054327fef3e58` | `GPL-3.0-only`; README adds Anti-996/additional claims | source-scoped results, metadata vocabulary, deterministic merge/required-field/fixtures |
| Manifest/versioning | `EWEDLCM/FnDepot` | `9a2449eaf012c352bca2ed4381e005a37f67d757` | no root license established | versioned JSON, stable key, required/optional, override/admission concepts |
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

### N4D-A - Approval policy closure

Completed: typed fixed-header, timeout, error-profile, raw-retention and exact
Approval/runtime policy checks. It approves no Provider.

### N4D-B - Video Metadata DTO / fixture / merge framework

Completed: immutable Video Metadata DTOs, async Protocol, tests-only static
fixture parser and deterministic zero-write merge planning.

### N4D-C - Provider Package binding and offline activation gate

Completed: Approval/Capabilities/Endpoint/Adapter/Evidence exact binding,
opaque SHA-256 fixture evidence, explicit operation authority, stable errors and
all-or-nothing Registry/binding construction. Production Registry remains empty.

### N4D-D-A - Provider Approval Artifact v1 and offline loader

Completed: strict bytes-only versioned JSON, canonical Unicode serialization,
SHA-256 payload attestation, exact typed reconstruction, opaque code-owned
Adapter factory lookup and final N4D-C Package validation. The only Artifact and
factory are tests-only; Production Registry remains empty.

### N4D-D-B0 - repository-derived Provider evidence profile

Completed: fixed-revision evidence ledger, field crosswalk, operation matrix,
metadata profile v1 and production-readiness blockers. The four repositories
remain reference-only; the Video Metadata Approval remains `draft / not
approved / no production activation`. The Production Profile retains only
`search`, `detail`, and optional `asset_list`, with no active Provider and an
empty Production Registry.

### N5A - Provider-neutral Search Orchestration Service

Completed: validated Video Metadata Packages are exposed through immutable,
stably ordered descriptors and strictly separate search/detail/asset-list
dispatch. Authority comes only from each Adapter Binding operation tuple;
missing capability is rejected before invocation, each request calls exactly
one Adapter operation, and exact result identity/type/page/asset bounds are
verified before success. Stable errors are redacted and cancellation propagates.

Production Search Packages and providers remain `()`. No synthetic or real
Provider, Host, Endpoint, network, Registry mutation, UI, database write,
download, dependency, Schema, Backup, Docker, Compose, or CI change is present.

### N4D-D-B - first explicitly approved video metadata Provider Artifact and Adapter

Scope:

```text
search + detail + optional asset_list
```

Entry gate: one complete video Approval with exact Provider identity, lawful and
terms basis, fixed hosts/operations, response types/limits, mappings, and redacted
static fixtures; its reviewed production Artifact must pass every N4D-D-A strict
parser/attestation/factory gate and the resulting Package every N4D-C gate.

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

### N5B - search/detail empty-state and approved-provider UI

Completed: consumes the N5A service only through a production dependency or
tests-only override. The empty production provider catalog is rendered as an
ordinary localized HTTP 200 state; any future Provider still requires the full
N4D-D-B Approval and activation gates. GET only lists descriptors. Search and
Detail require explicit authenticated POST, each invokes only its matching
approved operation once, and neither chains Asset List, import, playback, or
download.

Canonical URLs are not links, assets are not remote images or media sources,
and only non-locator asset facts may be displayed. Responses are not persisted.
Stable errors are localized and redacted, cancellation propagates, and the
Production Registry, Search Packages, and Search Providers remain empty.

### N5C-A - signed Provider apply-plan foundation

Completed: consumes exact approved Provider Detail envelopes and produces only a
read-only immutable apply plan. Four bounded SELECT categories snapshot Provider
identity/URL source state, the linked Item, and exact-title hints. Create never
binds by title; update never overwrites local title and can only fill blank
summary/release date plus refresh bounded source tracking facts.

Canonical plan bytes reject duplicate keys, schema/type/resource violations and
non-finite values. Purpose-bound HMAC-SHA256 tokens use exact byte secrets,
bounded TTL, context binding, and constant-time verification. They are decodable
integrity tokens, not encryption. N5C-A adds no route, UI, DB write, Provider
call, network, Schema, dependency, or production activation.

### N5C-B1 - transactional Provider apply service

Completed as a pure service layer. It verifies the existing purpose-bound Token
before any database or external action, rejects caller Session state, then uses
SQLite `BEGIN IMMEDIATE` before bounded identity source, normalized-URL source,
linked Item, and duplicate-title queries. Create reproves absence and writes one
Item/ItemSource without title linking. Update reproves exact source/Item state and
may write only approved summary, release-date, check-time, and metadata-hash
fields.

Flush is followed by an in-transaction exact post-check. A normal commit still
requires an independent Session to prove durable post-state. Exceptions are
classified only after independent post-state then pre-state proof as committed
after exception, write conflict, write failure, or unknown. Successful Token
replay is `stale_plan`. B1 adds no route, UI, Provider call, network, file access,
Schema, dependency, background task, Docker, Compose, or CI change.

### N5C-B2 - explicit Preview/Confirm UI

Not implemented. It requires a separate GOAL for authenticated Preview/Confirm
routes, session-bound secret/context derivation, template/i18n integration, and
user-visible results. It must consume B1 without re-calling the Provider and keep
GET zero-write, production catalogs empty, and download/playback/background work
outside this phase.

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

Phase 5-N4D-B is the completed video metadata foundation: immutable DTOs,
provenance/available-field rules, deterministic merge planning, and a tests-only
synthetic fixture adapter. It does not satisfy the real-Provider Approval gate;
N4D still requires explicit user approval before any network implementation.

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

## 6. Invariants preserved through N5C-B1

- Application version: `1.1.0`.
- Schema: `4`.
- Backup: `nsfwtrack.backup.v2` with v1 restore compatibility.
- Production Provider Registry: `EndpointRegistry(())`.
- Production Search Providers: `()`.
- No real Provider, host, endpoint, credential, authentication, playback,
  download, background task, dependency, migration, Schema, Backup, Docker,
  Compose, or CI change.
- No userscript or remote JavaScript execution.
- No Hermes call, tag, Release, or N100 deployment.
- Existing local `data/` remains outside all research and test activity.
