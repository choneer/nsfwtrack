# Phase 5-N4C Subscription Catalog and Future Playback Research

## 1. Status, inputs, and hard boundary

This is a static design document. N4C does not fetch a subscription, register a
candidate, resolve playback, stream media, or download anything. The Production
Provider Registry remains `EndpointRegistry(())`.

The user-provided subscription JSON and standalone userscript were not present
in the supplied workspace outside the protected local-data boundary. Their
contents are therefore **unavailable and blocked**, not inferred. This study
uses only the six subscription field names authorized in `GOAL.md`:
`id`, `name`, `baseUrl`, `group`, `enabled`, and `priority`. No candidate
`baseUrl` was contacted.

`JavdBviewed/Tampermonkey/javdb.js` is a public-repository historical script,
not the missing user-provided script. It was read as text only and was never
executed. It does not provide evidence for the unavailable script's playback,
membership, HLS-download, or container-conversion behavior.

## 2. Reviewed public repository facts

| Repository | Default branch | Reviewed commit | License at reviewed commit |
|---|---|---|---|
| `EWEDLCM/FnDepot` | `main` | `e565623a1797aaf40b6b376720046d9451bc6a0d` | No root `LICENSE`, `COPYING`, or SPDX declaration was found. `fntermx/README.md` claims MIT for that subproject but links to an absent license file; this does not license the root catalog. |
| `lmixture/JavdBviewed` | `main` | `e26dfdf97c1a68a8f27035ecf8e982208bdc79e0` | `AGPL-3.0-only`; used only for public architecture observations |

### 2.1 FnDepot references and conclusions

Reviewed files:

- root `README.md`;
- root `fnpack.json`;
- tracked root/subproject layout and subproject README metadata.

Observed architecture:

- a root catalog maps stable package IDs to display metadata and version facts;
- one catalog entry may have common values plus architecture-specific
  overrides, with a documented deterministic precedence rule;
- omitted download location can fall back to a repository-relative convention;
- the documented client behavior synchronizes catalog changes and filters by
  platform/version.

Adopted as ideas:

- a catalog snapshot is separate from installed/activated runtime state;
- stable candidate identity, catalog revision, deterministic normalization,
  explicit override precedence, and a visible diff before activation;
- metadata and artifact authority are separate.

Not adopted:

- automatic synchronization, direct activation/install, remote source
  discovery, URL fallback construction, or response-defined download authority;
- package/archive handling or any source code, because root licensing is
  unestablished and the product domain differs from Provider playback.

### 2.2 JavdBviewed references and conclusions

Reviewed files:

- `apps/extension/src/apps/content/contentLifecycle.ts`;
- `apps/extension/src/features/previews/listPreviewLoader.ts`;
- `apps/extension/src/features/previews/nativeJavdbPreview.ts`;
- `apps/extension/src/features/previews/previewSourceRules.ts`;
- `apps/extension/src/features/previews/previewVideoPreload.ts`;
- `apps/extension/src/features/previews/previewVolumeControl.ts`;
- `apps/extension/src/features/previews/backgroundHandlers.ts`;
- public historical `Tampermonkey/javdb.js`.

Adopted as ideas:

- page/SPA lifecycle owns setup, cancellation, and cleanup;
- preview source identity, media type, verification time, and failure count are
  explicit state rather than loose URLs;
- player state must survive source switching deliberately, and detached media
  elements must be paused/restored/cleaned;
- bounded cancellation and task status belong in the operation model.

Not adopted:

- DOM mutation observers, browser extension messaging, localStorage, raw URL
  caching, hard-coded source fallbacks, automatic availability probes, or
  source-specific browser requests;
- swallowed exceptions, automatic retry loops, raw URL/error logging, magnet
  lookup, userscript injection, or browser-page access;
- membership impersonation, access-control bypass, unauthenticated protected
  resource extraction, or download logic under any circumstances;
- AGPL source code.

The reviewed public script does not establish a safe general design for HLS
query inheritance, segment concurrency, retry, TS-to-MP4 conversion, or
membership flows. Those topics remain unverified until the actual user-provided
script is supplied in a future static-research authorization.

Requested standalone-userscript review ledger:

| Research item | Available evidence | N4C decision |
|---|---|---|
| SPA route monitoring | Missing standalone script; public historical script uses DOM observers but is not equivalent | blocked; lifecycle concept only |
| Player initialization/source switching | Missing standalone script; public preview code shows attach/restore cleanup | blocked; require explicit lifecycle and cleanup |
| Page source of playback facts | Missing standalone script | blocked; never infer DOM/API fields |
| HLS manifest/segment address handling | Missing standalone script | blocked; no locator or host rule inferred |
| Relative address/query inheritance | Missing standalone script | blocked; future Approval must define exact same-host/path/query rule |
| Progress/concurrency/retry/cancel | Missing standalone script | blocked; cancellation/state concepts only, no automatic retry |
| TS-to-MP4 remux responsibility | Missing standalone script | blocked; conversion/download remains outside playback |
| UI injection/site-player synchronization | Missing standalone script; public code is browser-specific | rejected for NSFWTrack; future UI uses application-owned components |

## 3. Two-layer authority model

```text
Subscription Catalog
  -> untrusted candidate inventory and revision history
  -> never runtime network authority

Approved Streaming Provider
  -> separate, explicit production Approval
  -> immutable code-owned Capability + Endpoint Registry entry
  -> only then eligible for a user-triggered operation
```

A catalog candidate can generate an Approval draft. It cannot create or mutate
`ProviderCapabilities`, `ProviderEndpoint`, or the Production Registry. A
candidate `baseUrl` is inert data before approval: it is displayed in a
redacted/review-safe form, never resolved, probed, redirected to, embedded, or
used to derive metadata/asset/playback hosts.

`group = premium` is a catalog label only. It does not prove a subscription,
valid credentials, lawful access, an authentication mode, playable content, or
download rights. The same is true for an ordinary group.

## 4. Subscription DTO draft

### `ProviderSubscription`

```text
subscription_id
display_name
approved_subscription_host_id
approved_fixed_path_id
refresh_policy = explicit_post_only
current_revision_id
last_attempt_at
last_success_at
last_status
```

The actual subscription URL is code-owned only after a separate catalog-source
Approval. It is never accepted from a browser form or candidate payload.

### `SubscriptionRevision`

```text
subscription_id
revision_id
observed_at
content_digest
candidate_count
normalization_version
previous_revision_id
validation_status
```

`content_digest` is over validated canonical candidate data, not a signature or
proof of publisher authenticity. Raw response bodies are not retained by this
draft. A future implementation must define bounded snapshot retention and exact
failure semantics separately.

### `SubscriptionCandidate`

```text
candidate_id
display_name
base_url
group
enabled_by_source
priority
subscription_revision
first_seen_at
last_seen_at
change_type
approval_state
```

Mapping from the only known input schema:

| Input field | Candidate field | Validation concept |
|---|---|---|
| `id` | `candidate_id` | bounded opaque catalog identity; unique within revision |
| `name` | `display_name` | bounded nonempty display text |
| `baseUrl` | `base_url` | syntactically validated candidate fact; never contacted or treated as approval |
| `group` | `group` | bounded catalog label; ordinary/`premium` has no permission meaning |
| `enabled` | `enabled_by_source` | strict boolean recommendation fact only |
| `priority` | `priority` | bounded integer used for display ordering only |

Unknown keys, duplicate JSON keys, duplicate candidate IDs, invalid types,
non-finite numbers, malformed text, or conflicting normalized identities reject
the entire revision. There is no partial best-effort activation.

### `SubscriptionDiff`

```text
subscription_id
from_revision_id
to_revision_id
added_candidates
changed_candidates
removed_candidates
unchanged_count
diff_digest
```

Changed fields are explicit. A `base_url`, group, enabled, priority, or display
name change is never collapsed into "unchanged". Host changes invalidate any
prior candidate approval and require a fresh production Approval; removal does
not delete local data or an independently approved runtime Provider.

### `SubscriptionValidationResult`

```text
status
revision_id
accepted_count
error_code
error_location
response_size
content_type
```

It contains stable bounded errors only, not the raw body, candidate URL,
credentials, or exception text.

Candidate `approval_state` values:

```text
unreviewed
drafted
approved_candidate
rejected
disabled_locally
superseded
unknown
```

`approved_candidate` means only that a user accepted the catalog candidate for
the next Approval workflow. It is not runtime activation.

## 5. Explicit subscription refresh flow

```text
authenticated user POSTs refresh
  -> verify signed confirmation and fixed catalog-source Approval
  -> fetch exactly one fixed subscription endpoint
  -> enforce deadline, status, Content-Type, compressed/actual-byte bounds
  -> parse strict JSON with duplicate-key and finite-number rejection
  -> validate exactly the approved schema/version
  -> normalize all candidates deterministically
  -> build an immutable revision and complete diff
  -> present added/changed/removed candidates
  -> user reviews candidates individually
  -> generate placeholder Approval drafts
  -> separate future implementation and production activation gate
```

Requirements:

- GET pages perform zero network and do not refresh timestamps or state;
- there is no background, scheduled, startup, or page-load refresh;
- the subscription body is data, never code, configuration, import, include, or
  Registry content;
- refresh does not access candidate `baseUrl` values;
- `enabled` is only the publisher's recommendation and never enables runtime;
- local enable/disable and ordering are UI/catalog facts, not network authority;
- one revision is all-valid or rejected; a failed fetch does not replace the
  last valid revision;
- changed host/base URL returns the candidate to review;
- removed candidates do not remove local Items, sources, media, credentials, or
  separately approved Providers;
- no retry is automatic. An unknown fetch result is visible and does not create
  a revision claimed as successful.

## 6. Future streaming DTO draft

`StreamingSearchResult`

```text
provider_key
external_id
title
alternate_titles
summary
cover_asset_id
release_date
duration_seconds
availability_state
available_fields
provenance
```

`StreamingDetail`

```text
provider_key
external_id
title
alternate_titles
summary
cover_asset_id
release_date
duration_seconds
performers
director
studio
publisher
series
tags
content_rating
availability_state
source_updated_at
available_fields
provenance
```

Search output remains an incomplete preview; detail does not imply that a
playback source is available. `availability_state` is a Provider-reported fact,
not authentication, entitlement, or play authority.

`PlaybackGroup`

```text
provider_key
external_id
group_id
display_name
source_ids
selection_policy
```

`PlaybackSource`

```text
provider_key
playback_source_id
group_id
display_name
manifest_kind
requires_auth
expires_at
available_fields
```

`PlaybackVariant`

```text
variant_id
bandwidth
average_bandwidth
width
height
frame_rate
video_codec
audio_codec
audio_group_id
subtitle_group_id
```

`PlaybackManifest`

```text
provider_key
playback_source_id
manifest_id
manifest_kind
variants
duration_seconds
is_live
expires_at
resolved_at
```

`PlaybackSegment`

```text
segment_id
sequence
duration_seconds
byte_range
initialization_segment_id
discontinuity
```

`PlaybackError` contains stable `code`, `operation`, `retryable` (policy fact,
not automatic action), and optional bounded status class. It contains no URL,
manifest, segment locator, credential, response body, or raw exception.

Manifest and segment locators are intentionally absent from Provider-neutral
persisted DTOs. A future player may receive a short-lived internal locator only
after exact Provider/operation/host/path/query/expiry/auth and DNS/TLS/peer
validation. Relative references cannot expand the approved host set.

## 7. Future operation and state-machine draft

| Operation | Input | Output | Paging | Writes DB | Network chaining | N4C status |
|---|---|---|---|---:|---|---|
| `search` | bounded query/page | `StreamingSearchResult` page | explicit bounded | no | none | design only |
| `detail` | opaque external ID | `StreamingDetail` | none | no | none | design only |
| `playback_list` | Provider/external ID | bounded `PlaybackGroup`/`PlaybackSource` facts | none | no | no resolve | design only |
| `playback_resolve` | one selected opaque playback source ID | one bounded `PlaybackManifest` | none | no | manifest parsing only inside exact operation policy | design only |

Playback state machine:

```text
not_requested
  -> previewed
  -> resolving
  -> ready
  -> playing <-> paused
  -> ended

resolving/ready/playing/paused
  -> failed | expired | cancelled | unknown
```

Only an explicit user action leaves `previewed`. `failed` is a classified
failure; `unknown` means the final remote/player state is unproven. Expired
manifests cannot be silently reused or refreshed.

Future download planning remains separate from playback and is not authorized:

```text
not_requested -> confirmed -> resolving -> downloading -> validating
-> publishing -> committed | committed_after_error

any active state -> rolled_back | cleanup_failed | cancelled | unknown
```

Playback success does not authorize download. A download requires its own
Provider Approval, explicit confirmation, operation, limits, temporary-file
isolation, validation, no-overwrite publication, and independently reviewed
outcome.

## 8. Status matrices

### 8.1 Operation status matrix

| Status | Subscription refresh | Candidate review | Playback operations |
|---|---:|---:|---:|
| `success` | valid revision/diff | local decision recorded | exact operation completed |
| `invalid_request` | bad local confirmation/input | invalid transition | bad typed selection |
| `not_approved` | catalog source not approved | candidate cannot activate | Provider/operation denied |
| `not_supported` | schema/version unsupported | n/a | capability absent |
| `unauthorized` | approved catalog auth missing | n/a | playback auth missing |
| `forbidden` | remote denial | n/a | remote denial |
| `not_found` | fixed resource absent | candidate absent | content/source absent |
| `rate_limited` | possible | n/a | possible |
| `provider_unavailable` | possible | n/a | possible |
| `invalid_payload` | JSON/schema invalid | candidate facts invalid | metadata/manifest invalid |
| `response_too_large` | possible | n/a | possible |
| `expired` | catalog auth/session only | stale revision | manifest/auth expired |
| `cancelled` | possible | user exits review | possible |
| `unknown` | outcome unproven | mixed/stale facts | final state unproven |

### 8.2 Network side-effect matrix

| Action | Network count | May access candidate `baseUrl` | May fetch media |
|---|---:|---:|---:|
| GET catalog/review page | 0 | no | no |
| Explicit refresh POST | at most one fixed catalog operation | no | no |
| Normalize/diff/review/disable/order | 0 | no | no |
| Generate Approval draft | 0 | no | no |
| N4C playback design | 0 | no | no |
| Future playback operation | only exact separately approved operation | only after independent code-owned Approval, never from catalog directly | only within future playback Approval |

### 8.3 Database write matrix

| Action | Catalog revision | Candidate decision | Production Registry | Local media/user data |
|---|---:|---:|---:|---:|
| N4C | none | none | none | none |
| Future successful refresh POST | planned bounded revision/diff only | none | none | none |
| Candidate approve/reject/disable | planned explicit local state | explicit row only | none | none |
| Refresh failure/unknown | preserve last proven revision | unchanged | unchanged | unchanged |
| Playback | no catalog write | none | never response-driven | local progress only in a separately designed local write |

### 8.4 Permission matrix

| Authority source | Refresh fixed catalog | Approve candidate | Register Provider | Play/download |
|---|---:|---:|---:|---:|
| Authenticated user + signed POST | yes after catalog Approval | yes, as candidate only | no | no implicit authority |
| Catalog `enabled` | no | no | no | no |
| `premium` group | no | no | no | no |
| Candidate `baseUrl` | no | no | no | no |
| Provider response/manifest | no expansion | no | no | no operation/host expansion |
| Background task | no | no | no | no |

### 8.5 Authentication matrix

| Context | `none` | Configured/valid auth | Expired/invalid/revoked | Unknown |
|---|---:|---:|---:|---:|
| Catalog refresh | only if separately approved public | exact catalog scope only | denied | denied |
| Candidate review | local only | no secret required | local only | local only |
| Ordinary group | no implied auth | no implied auth | no implication | no implication |
| `premium` group | no implied auth | still requires separately approved lawful credential | denied | denied |
| Playback | public only if Approval says so | exact operation/host scope | denied | denied |

### 8.6 Error matrix

| Failure | Stable result | Required behavior |
|---|---|---|
| Local schema/confirmation rejected | `invalid_request` | zero network/write |
| Approval/capability missing | `not_approved` / `not_supported` | zero DNS/network |
| 401/403/404/429 | `unauthorized` / `forbidden` / `not_found` / `rate_limited` | no credential deletion or retry loop |
| DNS/TLS/timeout/5xx | `provider_unavailable` | keep last revision/state |
| Wrong type, duplicate key, bad candidate/manifest | `invalid_payload` | reject whole response; do not log raw data |
| Stream/media bound exceeded | `response_too_large` | stop reading; no partial success |
| User cancellation | `cancelled` | close resources and keep proven prior state |
| Unprovable response/player final state | `unknown` | no revision/activation/success claim |

### 8.7 Result uncertainty matrix

| Proven facts | Classification | Consequence |
|---|---|---|
| Entire catalog validated and diff built | `success` | revision may become latest proven snapshot |
| Fetch started, completion unknown | `unknown` | retain prior revision; explicit retry only |
| Candidate removed from catalog | `success` diff fact | do not delete Provider/local records/media |
| Candidate host changed | changed + `unreviewed` | invalidate candidate approval; no probe |
| Manifest partially parsed | `invalid_payload` or `unknown` | no playable state |
| Playback response lost after request | `unknown` | no auto-resolve, retry, or download |
| Cleanup/player detach uncertain | `unknown` | stop claiming playback success; expose recovery action |

## 9. Missing evidence and future handoff

The actual subscription JSON is required to determine its envelope, version,
top-level shape, duplicate behavior, encoding, and whether the six known fields
are optional or repeated. The actual standalone userscript is required to
review its SPA route lifecycle, player model, HLS parsing, query inheritance,
progress, cancellation, concurrency, retry, and container-conversion boundary.

Supplying either input does not authorize network access or script execution.
A future GOAL must authorize static reading, and candidate addresses must remain
uncontacted. N4E may implement catalog refresh/parse/diff/approve/disable only
after a fixed catalog-source Approval. N4F may implement playback only after a
separate approved streaming Provider; neither phase may infer authority from a
catalog group or URL.
