# Phase 5-N3 Provider Contract

## 1. Status and scope

This document is the code-facing planning contract for Provider work targeted at
`v1.2.0`. It defines boundaries and handoff requirements; it does not authorize
or implement a real Provider, network endpoint, credential store, download, UI,
Schema change, dependency, or background task.

The production Provider Registry remains empty. A normal page URL, source URL,
remote response, or user-supplied value never grants outbound access. Every
Provider, host, operation, authentication mode, response type, and asset rule
must be immutable, code-owned, and separately approved before implementation.

The terms MUST, MUST NOT, SHOULD, and MAY in this document describe requirements
for future N4-N7 implementation. Statements under "Current implementation" are
the only descriptions of behavior already present in the repository.

Permanent boundaries remain unchanged:

- NSFW-first, local-first, privacy-first, single-user, and self-hosted;
- no arbitrary URL fetch, unrestricted crawler, recursive site traversal, or
  access-control bypass;
- no credential theft, browser-secret extraction, cross-Provider secret use,
  hidden network activity, or unconfirmed bulk write/download;
- no Provider response may expand its own capabilities or network allowlist;
- local records, media, preferences, and secrets are not uploaded by default;
- unknown results are never guessed, deleted speculatively, or reported as
  ordinary success.

## 2. Current implementation audit

### 2.1 Adapter and DTOs

The current `SourceAdapter` protocol in `app/source_adapters/contracts.py` has
only:

```python
async def search(query: str, *, page: int, page_size: int) -> SourceSearchPage
async def fetch_detail(external_id: str) -> SourceDetail
```

Current frozen DTOs are `SourceCreator`, `SourceTag`, `SourceSearchResult`,
`SourceDetail`, and `SourceSearchPage`. There is no capability manifest,
authentication adapter, discovery operation, asset DTO, asset-list/resolve
operation, download adapter, credential broker, or secret store.

### 2.2 Endpoint Registry

The immutable registry in `app/source_adapters/registry.py` currently binds a
Provider key to a lowercase ASCII HTTPS hostname on port 443, fixed printable
ASCII path templates, typed business parameters, required parameters, JSON
top-level shape, response limits, and page-size limits.

It does not yet express HTTP method, request body, authentication, cookies,
fixed authentication headers, discovery, asset hosts, file response types,
download limits, or a Provider-specific redirect policy. The production value
is exactly an empty `EndpointRegistry`.

### 2.3 Outbound HTTP

`OutboundRequest` in `app/services/outbound_http.py` currently accepts only a
Provider key, operation, query, external ID, page, and page size. The client is
fixed to GET and JSON, uses `trust_env=False`, and disables auth, cookies,
environment proxy use, redirects, retries, and HTTP/2. It retains whole-set DNS
validation, numeric-IP connection pinning, TLS hostname/SNI/Host preservation,
TCP and TLS peer revalidation, bounded deadlines, bounded streamed response
size, bounded concurrency, immutable JSON, and redacted logging.

It accepts no arbitrary URL, host, path, method, body, header, cookie, token,
password, or asset locator. Future work MUST preserve that public-input
boundary.

### 2.4 Source tracking and backup

Schema 4 `ItemSource` stores nullable `provider_key`, `external_id`,
`last_checked_at`, and `metadata_hash`, with a partial unique identity index
when Provider key and external ID are both present. There is no Provider,
credential, secret, asset, or download table.

`nsfwtrack.backup.v2` explicitly exports business data and source-tracking
facts. It does not export a Secret Vault or derived media-index rows. Restore
uses `BEGIN IMMEDIATE`, transaction-internal conflict reclassification, and an
independent Session digest after commit errors to distinguish committed after
error, confirmed rollback, and unknown outcomes. Future secret state MUST stay
outside ordinary backup and configuration export.

### 2.5 Reusable local-media safety patterns

The current repository provides patterns, not a finished download service:

- `media_operation_lock()` supplies bounded cross-process exclusion and stable
  lock-object revalidation;
- `coordinate_media_mutation()` and
  `synchronize_media_index_after_mutation()` separate filesystem outcome from
  index synchronization and invalidate the index on unknown outcomes;
- local-media validation uses directory FDs, `O_NOFOLLOW`, stable
  mode/device/inode identities, mapping checks, no-overwrite publication, and
  parent-directory synchronization;
- directory and file mutation services use exact reference checks,
  `BEGIN IMMEDIATE`, independent Sessions after commit exceptions, and explicit
  committed/rolled-back/unknown classifications;
- upload code provides bounded type/magic/hash checks, isolated temporary files,
  content-addressed names, and no-overwrite hard-link publication.

N6 MUST reuse the security properties of these patterns. It MUST NOT assume the
current upload helper is itself a complete streamed remote-download pipeline.

## 3. Immutable Provider capability manifest

Every implemented Provider MUST have one frozen, code-owned manifest. Remote
responses, database rows, browser forms, and environment values cannot add or
alter capabilities.

The manifest has five capability layers:

| Layer | Purpose | Examples of independently declared operations |
|---|---|---|
| Metadata | Provider-neutral candidate metadata | `search`, `detail` |
| Auth | User-authorized Provider session lifecycle | `auth_test`, `auth_login`, `auth_refresh`, `auth_revoke` |
| Discovery | Bounded candidate discovery | `discover` |
| Asset | Resource metadata and short-lived locator resolution | `asset_list`, `asset_resolve` |
| Download | Controlled byte transfer policy | `download` |

A planned shape is:

```python
@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    provider_key: str
    display_name: str
    content_scope: str
    auth_modes: tuple[AuthMode, ...]
    operations: tuple[ProviderOperation, ...]
    metadata: MetadataCapabilities
    auth: AuthCapabilities
    discovery: DiscoveryCapabilities
    assets: AssetCapabilities
    downloads: DownloadCapabilities
    attribution_required: bool
```

The exact Python form is an N4 decision, but these invariants are mandatory:

- absence means denial; there is no capability inference;
- each operation is independently defined and approved;
- search, detail, discovery, asset list, asset resolve, and download remain
  separate operations rather than one universal fetch method;
- capability declarations cannot be loaded from a Provider response;
- display metadata is not authority to contact a host or download an asset;
- an approved metadata host is not automatically an auth or asset host;
- an approved operation cannot reuse another operation's body, content-type,
  redirect, authentication, response-size, or rate limits unless the manifest
  explicitly gives both the same code-owned policy;
- capabilities remain bounded even when the Provider claims broader support.

## 4. Adapter responsibility layers

### 4.1 `SourceMetadataAdapter`

Maps approved search and detail payloads into immutable Provider-neutral DTOs.
It MUST NOT write the database, touch local files, read a secret file, create a
private HTTP client, follow response URLs, auto-fetch detail from search, or
persist raw responses.

### 4.2 `ProviderAuthAdapter`

Maps an approved Provider-specific authentication flow onto the shared
credential broker and outbound service. Its possible responsibilities are
start, submit, test, refresh, revoke, and logout. Only operations and credential
fields present in the approved manifest may exist.

It MUST NOT persist plaintext secrets, access another Provider's vault record,
write secrets to ordinary backup/configuration, or bypass shared network policy.

### 4.3 `ProviderDiscoveryAdapter`

Maps one bounded, code-owned discovery operation into finite candidate DTOs.
Discovery is optional and remains disabled for `v1.2.0` unless a later explicit
GOAL and Provider approval authorize it. It MUST NOT crawl, recurse through
links, upload local preferences, auto-import candidates, or auto-download.

### 4.4 `ProviderAssetAdapter`

Provides `asset_list` and, only when required, `asset_resolve`. Listing returns
resource facts and opaque asset IDs; resolving validates a short-lived locator
for one already listed asset. It MUST NOT treat a URL as an asset ID or expose a
locator as general fetch authority.

### 4.5 `ProviderDownloadAdapter`

Declares Provider-specific download policy: whether an asset kind is eligible,
required authentication scope, exact asset hosts, allowed content types,
Provider and operation size limits, checksum rules, Range support, and redirect
rules. The shared controlled-download service, not the adapter, owns the byte
stream, temporary file, validation, publication, database relationship, and
media-index coordination.

## 5. Authentication contract

Only these code-owned authentication modes are planned:

```text
none
api_token
oauth
username_password
session_cookie
```

Each real Provider implements only modes explicitly approved for it. Public and
protected operations are declared separately. Missing or uncertain auth state
fails closed for protected operations.

### 5.1 Common requirements

- credentials originate from the user's own lawful authorization;
- authentication does not bypass age, paywall, subscription, region, account,
  or other access controls;
- secrets are isolated by Provider key and auth mode;
- secrets never enter URLs, query logs, request IDs, exceptions, raw-response
  logs, ordinary database fields, ordinary backup, or configuration export;
- UI accepts secrets only on an explicit POST and never displays a complete
  stored value;
- GET pages do not contact a Provider, test credentials, refresh sessions, or
  write auth state;
- 401/403 does not delete credentials or prove revocation;
- an auth failure never clears local items, sources, or media;
- automatic refresh and repeated login are denied unless later authorized with
  strict retry and abuse bounds.

### 5.2 `none`

Only operations declared public may run. No credential record or implicit
cookie jar is created. A Provider that supports public metadata and protected
downloads MUST declare those operation requirements separately.

### 5.3 `api_token`

The user explicitly supplies the token. Code fixes the credential field and
injection point. A form or adapter cannot choose a header name or add a new
header. URL/query placement is denied unless the Provider approval explicitly
documents that unavoidable requirement and its redaction controls.

### 5.4 `oauth`

The approval fixes authorization host, token host, client configuration,
callback, scopes, and every operation. The flow MUST use `state`; PKCE is
required whenever supported. Access and refresh tokens are distinct vault
fields. Refresh is bounded and never loops. Revoke/logout removes the local
record only after its outcome is classified; remote revocation failure is not
reported as success.

There is no arbitrary OAuth-client configuration UI.

### 5.5 `username_password`

Credentials may be sent only to the approved fixed login operation. The default
is to exchange them for a narrower session/token and discard the password.
Encrypted long-term password retention requires an explicit Provider-specific
approval proving it is necessary. Provider response text is never echoed on
login failure.

### 5.6 `session_cookie`

Cookies are explicitly imported by the user or created by an approved login
operation. Browser stores are never scanned or extracted. Only approved cookie
names are retained, with validated Domain, Path, Secure, SameSite, and expiry
facts. Records bind to one Provider and approved host scope; there is no global
cookie jar. Revoke/logout removes the isolated local record according to a
classified outcome.

### 5.7 Auth state matrix

| State | Proven fact | Allowed action | Denied implication |
|---|---|---|---|
| `not_configured` | No usable local record | Public operations; explicit configure | Protected request |
| `configured` | Record saved, not verified | Explicit user-triggered test | Treat as valid |
| `valid` | Last explicit test succeeded and has not expired | Approved protected operations | Broader scopes/hosts |
| `expired` | Expiry is known | Explicit refresh or login | Silent reuse |
| `invalid` | Explicit test proved invalid | Replace/test credential | Protected request |
| `revoked` | Revocation and local removal are proven | Configure again | Reuse old secret |
| `unknown` | Final remote or local state is unprovable | User-visible retry/review | Assume valid or revoked |

Auth state is operational secret metadata. It is not part of ordinary backup
and is not verified merely by rendering a page.

## 6. Provider Secret Vault plan

The recommended `v1.2.0` architecture is a local, versioned Provider Secret
Vault beneath the application data directory, encrypted by a separate
deployment secret named `PROVIDER_SECRET_KEY`.

`PROVIDER_SECRET_KEY` MUST NOT reuse `APP_PASSWORD` or the application's
`SECRET_KEY`. It is never stored in the repository, database, vault envelope,
logs, diagnostics, ordinary backup, or configuration export. The existing
`SECRET_KEY` remains for HMAC authentication of operation snapshots; it is not
Provider-secret encryption material.

The planned vault properties are:

- versioned AEAD envelopes, with confidentiality and integrity;
- authenticated associated data binding format version, purpose, Provider key,
  auth mode, and record identity;
- a fresh nonce generated by the selected AEAD construction for every write;
- minimal plaintext fields for the approved mode only;
- Provider-scoped access through a credential broker, never raw vault access by
  routers or metadata adapters;
- storage under the persistent application-data area, not the media tree and
  not temporary runtime storage;
- owner-only permissions and safe parent-directory validation;
- rejection of symlinks, hardlinks, special files, unsafe ownership/mode, and
  replaced mappings;
- directory-FD-relative open/write, `O_NOFOLLOW`, fsync, no-overwrite creation
  of a new envelope, and a validated atomic replace/swap step that preserves
  the last valid envelope on failure;
- explicit outcome classification if a write, replacement, or cleanup result
  cannot be proven;
- key loss affects Provider authentication only and never makes business data
  or local media unreadable;
- no secret, nonce-bearing envelope, auth state, or credential metadata in
  `nsfwtrack.backup.v2` or ordinary configuration exports.

N3 selects no cryptographic package. N4 MUST review the first approved
Provider's real requirements and separately justify any new dependency. A
system keyring MAY be a later deployment backend, but container deployments
cannot assume a desktop keyring exists.

## 7. Typed outbound HTTP extension plan

All future outbound capabilities remain code-owned. The registry may be
extended with frozen operation definitions such as:

```text
method
request_encoding
auth_requirement
fixed_headers
cookie_policy
response_kind
allowed_content_types
response_limit
rate_policy
redirect_policy
allowed_asset_hosts
```

### 7.1 Method and body

Only an operation's fixed GET or POST is planned. Users and routers cannot
submit a method. Bodies are generated by a Provider-specific typed strategy and
are limited to a fixed `application/json` or
`application/x-www-form-urlencoded` schema. There is no arbitrary dictionary,
raw body, multipart body, or body-derived host/path input.

Credential values enter only through the internal auth strategy after the
operation and Provider binding are validated.

### 7.2 Headers and cookies

Fixed non-secret headers belong to the operation definition. Auth headers are
injected by the credential broker. Cookies come from the one Provider-isolated
session record. Routers, adapters, DTOs, and users cannot supply a header map,
header name, Cookie header, or cookie jar.

`Set-Cookie` may be captured only by an approved auth operation and only for
approved cookie names/scopes. Metadata operations cannot silently establish a
shared session. `trust_env=False`, `.netrc` denial, and environment-proxy denial
remain mandatory.

### 7.3 Response kinds

JSON remains the default. Provider-specific HTML may be separately approved as
a fixed response kind with strict type/size rules, no script execution, no
third-party subresource loading, no link traversal, and fixture-only parser
tests. File streams are accepted only by the download service, never by the
metadata JSON parser.

### 7.4 Redirects

Redirects remain denied by default. An approved exception fixes the starting
host, exact target hosts, path rules, maximum hop count, method behavior, and
whether auth is stripped. A redirect never adds a host, carries credentials to
an asset host by default, or bypasses DNS/IP/TLS/peer validation.

### 7.5 N1 invariants retained

Every request continues to require exact HTTPS host and port policy, validation
of the complete DNS answer set, numeric-IP connection pinning, correct TLS
hostname/SNI/Host, TCP and TLS peer verification, bounded connect/total time,
bounded streamed bytes, bounded concurrency, cancellation propagation, stable
sanitized errors, and logs without query values, external IDs, locators,
headers, cookies, DNS addresses, response bodies, or raw exceptions.

## 8. Asset and dynamic locator contract

### 8.1 `SourceAsset`

A future immutable Provider-neutral DTO is planned:

```python
@dataclass(frozen=True, slots=True)
class SourceAsset:
    provider_key: str
    external_id: str
    asset_id: str
    kind: AssetKind
    display_name: str | None
    mime_type: str | None
    size_bytes: int | None
    checksum_algorithm: str | None
    checksum_value: str | None
    requires_auth: bool
    downloadable: bool
```

`AssetKind` is code-owned and bounded, initially considering `cover`,
`preview`, `media`, and `attachment`. A Provider approval selects only the kinds
it needs.

`asset_id` is an opaque Provider-scoped identifier, never an arbitrary URL.
`downloadable=True` records Provider/manifest eligibility, not user consent.
Search results carry no download authority. Detail may carry bounded summaries;
the complete list comes only from `asset_list`.

### 8.2 List and resolve separation

`asset_list(provider_key, external_id)` returns asset facts and IDs. It performs
no download and exposes no universal locator. `asset_resolve(provider_key,
external_id, asset_id)` is allowed only for a selected listed asset and returns
an internal short-lived locator object. Resolution does not publish a URL to a
router, form, database, log, or ordinary backup.

### 8.3 Locator validation

Every dynamic locator is untrusted and MUST pass all of these checks:

- HTTPS only, port 443 only;
- no credentials, fragment, backslash, literal whitespace, or ambiguous host;
- hostname is an exact member of that Provider's user-approved Asset Host
  allowlist; wildcards, suffix matching, and user-supplied hosts are denied;
- Provider-specific path and query grammar is code-owned and bounded;
- expiry and binding to Provider key, external ID, asset ID, operation, and auth
  scope are valid;
- whole-set DNS/IP validation, numeric-IP pinning, TLS hostname/SNI/Host, and
  TCP/TLS peer checks are applied again at transfer time;
- redirects cannot expand hosts or preserve credentials unless the exact rule
  was approved;
- an expired locator is discarded and explicitly re-resolved, never guessed.

Locators remain in a short-lived process object or purpose-specific signed
snapshot. A snapshot should bind a locator digest or opaque resolution identity,
not store or display the complete locator. A locator is never persisted as a
normal `ItemSource` URL.

## 9. Metadata and content operations

| Operation | Trigger | Output | Writes | Automatic follow-up |
|---|---|---|---|---|
| `search` | Explicit user POST | Bounded search page DTO | None | None |
| `detail` | Explicit selection POST | Detail DTO | None | None |
| `discover` | Future explicit authorization | Finite candidate DTOs | None | None |
| `asset_list` | Explicit asset-preview POST | Bounded `SourceAsset` tuple | None | None |
| `asset_resolve` | Explicit selected asset | Internal short-lived locator | None | No download |
| `download` | Separate signed confirmation POST | Classified local result | Controlled file/DB writes | One index coordination |

Search does not call detail. Detail does not import. Import apply is a separate
signed, zero-network operation. Asset preview does not write files or database
rows. Download confirmation is separate from search, detail, and import.

Provider-specific HTML, if later approved, is an operation response format and
not a generic crawler or browser.

## 10. Signed operation snapshots

Operation snapshots use the existing application `SECRET_KEY` only for
HMAC-SHA256 authentication and constant-time signature comparison. They do not
encrypt Provider credentials. Every purpose has a distinct versioned identifier:

```text
source_search_result.v1
source_import_preview.v1
provider_asset_preview.v1
provider_download_confirm.v1
source_update_preview.v1
```

A snapshot binds format, purpose, version, expiry, Provider key, external ID,
asset ID where relevant, display facts, approved limits, intended local target,
reference/conflict facts, and any safe digest needed to revalidate a short-lived
resolution. It contains no password, token, cookie, raw response, complete
dynamic locator, or encryption key.

Purpose mismatch, expiry, signature failure, capability change, local-state
change, asset mismatch, or limit mismatch fails closed. A signature never
replaces login, same-origin protection, current capability/host approval,
fresh local filesystem and reference checks, or final content validation.

## 11. `v1.2.0` controlled-download MVP

### 11.1 Included scope

- one user-triggered selected asset;
- an explicitly selected, code-bounded small batch;
- request-bound execution with cancellation propagation;
- no network or write on the initial GET;
- a separate preview POST and signed confirmation POST;
- streamed transfer into an isolated temporary area;
- streamed size enforcement and SHA-256 calculation;
- content-type, magic/signature, size, and approved Provider hash validation;
- safe no-overwrite publication into the local media root;
- exact local relationship write;
- at most one media-index coordination step for the confirmation request;
- explicit per-asset and overall outcome reporting.

### 11.2 Excluded scope

There is no hidden worker, page-close continuation, persistent queue, pause or
resume, scheduled download, automatic retry, startup recovery, recommendation
auto-download, unbounded batch, or silent background transfer. These require a
later explicit GOAL.

### 11.3 Request sequence

1. GET renders local state only: no Provider call, lock creation, file write, or
   database write.
2. Asset-preview POST may execute one approved bounded `asset_list` or
   `asset_resolve`; it writes neither local file nor business row.
3. Confirmation POST verifies login, same-origin protections, purpose-specific
   HMAC snapshot, expiry, selected asset set, capability, current auth state,
   exact approved limits, and current local target/reference facts.
4. The download service resolves a locator when needed and streams bytes into a
   private temporary file outside the published media namespace. Content-Length
   is only a hint; actual bytes enforce every limit.
5. The service fsyncs and reopens/revalidates the temporary object by stable
   identity, then validates content type, magic/signature, local SHA-256, and any
   approved Provider checksum.
6. Only after validation does the service acquire the existing M4 media lock.
   Under that lock it revalidates the media root, destination parent, target
   absence, signed local facts, and cancellation state.
7. It publishes with a directory-FD-relative no-overwrite operation, records
   stable published identity, acquires `BEGIN IMMEDIATE`, writes only the exact
   approved relationship, verifies the final relationship set, and commits.
8. A commit exception triggers an independent Session review of both exact
   database relationships and exact file identity. Cleanup occurs only when
   ownership and absence of references are proven.
9. Before releasing the media lock, the request performs one index coordination:
   known changes receive one incremental refresh; unknown filesystem state
   invalidates the index. Index status is reported separately from business
   outcome.
10. The temporary object is removed by exact identity. Failure to prove cleanup
    is a visible failure/unknown state, never ordinary success.

For a small batch, the selected IDs and aggregate byte/file limits are signed.
Each asset has an explicit result. The implementation MUST define transaction
and compensation boundaries before N6 coding; it cannot imply all-or-nothing
success when only some final states are proven.

### 11.4 File safety

- all storage paths and final basenames are generated by application code;
- remote filenames and `Content-Disposition` are display metadata only;
- absolute paths, traversal, user paths, and locator-derived paths are denied;
- temporary and final parents are validated by directory FD and stable
  mode/device/inode plus mapping checks;
- `O_NOFOLLOW` is used where available; symlinks, hardlinked temporary objects,
  special files, unsafe ownership/mode, and replaced parents fail closed;
- publication is no-overwrite and cross-device copy is not an implicit fallback;
- final file identity and parent identity are rechecked around publication;
- actual streamed bytes must satisfy the minimum of global, Provider,
  operation, signed-request, and remaining batch limits;
- declared length, extension, and content type are never sufficient alone;
- files are not executed, rendered as templates, automatically opened,
  extracted, or transformed;
- a failed validation cannot create a completed local relationship.

Exact byte, file-count, MIME, magic, hash, and Range policies are supplied by
the approved Provider contract and N6 implementation. N3 does not invent them.

## 12. Download states and outcomes

### 12.1 File lifecycle state

| State | Meaning | Durable success allowed? |
|---|---|---|
| `not_started` | No network/file operation began | No |
| `temporary` | Isolated incomplete bytes exist | No |
| `validated` | Complete temporary object passed checks | No |
| `published` | Exact final file exists, relationship not yet proven | No |
| `linked` | Exact relationship commit and file identity are proven | Yes |
| `failed` | Failure with final facts proven | No |
| `cancelled` | Cancellation honored before an irreversible boundary | No |
| `unknown` | File or database final facts cannot be proven | No |

State names describe evidence, not optimistic progress. After publication,
cancellation is handled as a mutation outcome and cannot simply be relabeled
`cancelled` if final cleanup is unproven.

### 12.2 Outcome matrix

| Event/facts | Required classification | Compensation and reporting |
|---|---|---|
| Failure before transfer | `not_committed` | No local change |
| Temporary write/validation failure, exact temp removed | `not_committed_rolled_back` | Stable failure; no relationship |
| Cancellation before publication, exact temp removed | `cancelled` | No local relationship |
| Final file published, DB unchanged, exact file safely removed | `not_committed_rolled_back` | Stable failure |
| File and exact relationship proven after normal commit | `committed` | Ordinary success; report index status separately |
| Commit raised but independent review proves file and relationship | `committed_after_error` | Success with explicit warning; no duplicate retry |
| Cleanup cannot remove an owned unreferenced object | `cleanup_failed` | Preserve evidence, invalidate index as required, recovery entry |
| Mixed/unexpected references or file identity mismatch | `download_outcome_unknown` | Preserve scene; invalidate index; no success |
| Independent DB or filesystem review unavailable | `download_outcome_unknown` | Preserve scene; invalidate index; no success |

Network, database, fsync, cleanup, cancellation, and response exceptions do not
prove rollback. A retry is never automatic. A user-visible retry must first
reinspect current file, relationship, and source facts to avoid duplication.

## 13. Stable errors and redacted logs

The planned stable error set includes:

```text
auth_not_configured
auth_invalid
auth_expired
auth_revoked
auth_failed
provider_unavailable
rate_limited
invalid_provider_payload
asset_not_found
asset_not_downloadable
asset_locator_invalid
asset_host_not_allowed
download_too_large
download_type_rejected
download_integrity_failed
download_cancelled
download_publish_failed
download_link_failed
download_cleanup_failed
download_outcome_unknown
```

Public errors and log events are separate. Neither contains query text,
external ID, username, complete URL/locator, header, cookie, token, password,
raw response, complete filesystem path, SQL, traceback, or raw exception.
Logs are limited to Provider key, operation, stable outcome/error code, bounded
status class, latency bucket, and request ID. Provider key is safe only because
it is code-owned and bounded.

## 14. Deterministic test contract

N4-N7 tests MUST use static fixtures and deterministic fakes only. No test may
resolve or contact a real Provider, host, endpoint, DNS service, or remote file.

Required coverage is selected per approved capability and includes:

- manifest absence/denial and immutable operation boundaries;
- typed request encoding and rejection of arbitrary URL/header/cookie/body;
- auth success/failure/expiry/revocation/unknown and Provider isolation;
- vault envelope version/binding/tamper/key-loss/write-failure behavior;
- search/detail/discovery/asset mapping with malformed and oversized payloads;
- unsafe/mixed DNS, disallowed asset host, locator grammar/expiry, peer mismatch,
  redirect, timeout, 401/403/404/429/5xx, and cancellation;
- streamed global/Provider/operation/request/batch size limits;
- MIME, magic, checksum, Range, truncated stream, and overlong stream failures;
- temporary cleanup, no-overwrite publication, parent/object replacement,
  database relationship failure, commit-after-error, cleanup failure, and
  outcome unknown;
- one request-bound index coordination and unknown invalidation;
- log and public-error redaction.

Docker acceptance uses an isolated data volume and network-disabled or fully
fake transport. It never uses the existing repository `data/`.

## 15. Phase ownership and handoff

### N4: first approved Provider foundation

Requires a completely approved `PROVIDER_APPROVAL_TEMPLATE.md`. N4 may implement
only the approved manifest, minimum required auth/vault support, search/detail
adapter, and approved asset metadata mapping with deterministic fixtures. It
does not add the search UI, database import, or file download.

Any missing Provider identity, host, endpoint, method, encoding, response type,
auth lifecycle, legal/attribution basis, fixture, dependency implication, or
Schema implication is a blocker. Codex does not infer or search for it.

### N5: search, detail, and manual import

Implements explicit search/detail preview, field selection, purpose-specific
signed import snapshots, zero-network apply, and Schema 4 `ItemSource`
association. It does not download.

### N6: controlled download

Implements asset preview, signed confirmation, streamed isolated transfer,
validation, safe publication, exact relationship write, one index coordination,
cancellation, and the complete download outcome matrix. It adds no hidden
worker or unapproved Schema/dependency.

### N7: manual update and hardening

Implements user-triggered source check, signed diff, manual update, approved
auth/download hardening, rate/abuse controls, i18n, accessibility, performance,
and complete related regression coverage. Background synchronization remains
default denied unless a later GOAL explicitly authorizes it.

No N4 work begins until the user completes and explicitly approves the Provider
Approval Template. This N3 contract itself names or approves no real Provider,
host, endpoint, authentication secret, or download source.
