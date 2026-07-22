# NSFWTrack

NSFWTrack is an NSFW-first, local-first, privacy-first, single-user,
self-hosted application for collecting content, aggregating sources, managing
local media, tracking state, and supporting personalized discovery.

Current application version: `1.5.0` (Schema `5`).

Latest stable release: `v1.3.0` (prior). Application development head: `1.5.0`.

Latest Release: [NSFWTrack v1.3.0](https://github.com/choneer/nsfwtrack/releases/tag/v1.3.0).

Current status: `Application 1.5.0 adds CookieCloud session import (+ /cookiecloud UI),
catalog readiness (/api/providers/readiness), HLS/playback-line inspect (no segment fetch),
and copymanga real-site comic PRODUCTION package, on top of nsfwpro factory Providers
(javdb/jiuse/zuidapi) and comic_local_fixture. Live-vs-fixture is reported honestly
per provider. Phase 6 runtime remains complete/frozen on Schema 5. No VIP/login bypass.
N100 is not deployed`.

Phase 6 = complete/frozen. Phase 6-R3 = frozen. Cloud RC diff review = PASS.
Hermes acceptance = PASS. Phase 6-R4 = released. Production catalogs = populated (1.5.0).
Published image = none. N100 = not deployed.
Real Provider packages = javdb_metadata + jiuse_vod + zuidapi_vod + copymanga (+ comic fixture).

Hermes acceptance: PASS. Phase 6-R4: released. N100: not deployed.

Phase 5-R4 formally released v1.2.0. Phase 5-R4: released. Its Tag, Release,
Actions, Schema 4, Backup v2, and Provider-neutral foundation remain preserved
as historical evidence. v1.3.0 kept production catalogs empty; v1.4.1 populated nsfwpro factory Providers;
v1.5.0 adds CookieCloud, HLS inspect, and copymanga real-site comic.

The long-term product baseline is recorded in [PRODUCT_VISION.md](PRODUCT_VISION.md).
Ordinary all-ages content may remain naturally compatible with the generic
model, but it is secondary and does not drive Provider selection, the data
model, or the roadmap. NSFWTrack is not being renamed to MediaTrack and is not
becoming a general film/television catalog.

The current Application version is `1.5.0` (Schema `5`). Latest published GitHub
Release remains `v1.3.0` until a `v1.5.0` tag is cut. Provider packages are
code-owned and fail-closed; live JavDB HTML scrape uses an operator-provided
session cookie only (env/file/CookieCloud import), never VIP bypass.

## Phase 6 — v1.3.0 formally released bundle

Schema 5 adds `operation_tasks`, bounded event/download/check/discovery facts,
and transactional local-asset links. The closed state matrix uses optimistic
versions, explicit leases, bounded redacted failures, pause/cancel/retry rules,
and conservative restart recovery: interrupted work becomes paused or blocked
and never performs automatic network access.

Controlled acquisition accepts only an approved code-owned acquisition package
and opaque Provider/source/asset identities. Preview is pure and creates no
file or network request. Confirm verifies a short-lived Session-bound signed
plan and creates one queued task without executing it. Explicit Start/Resume
uses a directory-descriptor downloader with `O_NOFOLLOW`, random mode-600 temp
files, streamed byte limits, MIME/magic/SHA checks, no-overwrite atomic link
publication, transactional Item/source/task linkage, and one coordinated media
index refresh or invalidation.

Manual source Check is an authenticated POST that calls exactly one approved
detail operation. Diff and per-field selection persist normalized facts only;
Confirm performs no Provider call and applies only summary, release date,
source title, checked time, and metadata hash after signed-plan and snapshot
revalidation. Item title, state, rating, review, tags, collections, creators,
cover, source identity, and source URL remain locally owned.

The bilingual Task Center provides paginated/filterable list/detail pages and
explicit Start, Pause, Resume, Cancel, safe Retry, and history deletion. GET
routes never run tasks or call Providers. Backup export remains v2, restore
continues to accept v1/v2, and all task/runtime/progress/lease/history tables
remain excluded from backup payloads.

Provider authentication, Provider-specific parsing, controlled downloads,
local recommendations, optional AI, and visible default-off background sync
are formal future capabilities, but remain denied until a separate GOAL
authorizes them. Arbitrary URL fetching, unrestricted crawling, access-control
bypass, credential theft or leakage, hidden network activity, and unconfirmed
bulk writes, overwrites, or downloads are permanently prohibited.

Phase 5-N2 extends only local source identity storage, migration, and backup
restore behavior. Application version remains `1.1.0`; Schema is now `4`, new
JSON exports use `nsfwtrack.backup.v2`, and restore continues to accept backup
v1. The production Provider Registry remains empty. N2 added no real Provider,
search UI, Provider credential storage, download, synchronization, tag,
Release, or N100 deployment.

The single Phase 5 Hermes acceptance passed against the frozen R3 candidate;
R4 did not call Hermes again.

Cloud diff review, Actions run `29586484449`, and Hermes independent acceptance
all passed on candidate commit
`b565ef1ca96b2b42315e1ef322c19f9e8ac227ea` without a corrective change before
the formal [v1.1.0 release](https://github.com/choneer/nsfwtrack/releases/tag/v1.1.0).

Phase 4 release evidence remains archived below and is unchanged by this
development phase.

## Phase 5-N4C Provider Direction Research

Phase 5-N4C adds seven documentation-only outputs under
[`docs/provider-research/`](docs/provider-research/): technical studies and
placeholder-only Approval drafts for video metadata, subscription/future
playback, and comics, plus a fixed Provider roadmap. The studies define
Provider-neutral DTOs, separate operations, provenance and merge rules,
subscription Candidate/Revision/Diff state, playback and download state
machines, comic reading flow, and operation/network/database/permission/auth/
error/unknown matrices.

The reviewed public snapshots are `lmixture/JavdBviewed` at
`e26dfdf97c1a68a8f27035ecf8e982208bdc79e0`, `Yuukiy/JavSP` at
`c4cfe61188234dd24c75b53b42b054327fef3e58`, `EWEDLCM/FnDepot` at
`e565623a1797aaf40b6b376720046d9451bc6a0d`, and `venera-app/venera` at
`a0eba914f4c2a84ac1bc925adec2baabe920b9be`. Only architecture ideas are
recorded; no licensed implementation code is copied.

The user-provided subscription JSON and standalone userscript were unavailable,
so their contents are not invented. Candidate addresses were not contacted,
and the public JavdBviewed userscript was not treated as a substitute or
executed. Future Comic Providers must be fixed reviewed Python adapters; remote
JavaScript execution is prohibited. Ordinary and `premium` subscription groups
remain catalog labels and grant no authentication, playback, or download
authority.

All three Approval drafts remain `draft / not approved` with placeholders only.
Application `1.1.0`, Schema `4`, Backup `nsfwtrack.backup.v2`, dependencies,
runtime code, tests, configuration, Docker/CI, and the empty Production
Provider Registry are unchanged. Local verification passed all `965` pytest
tests, `pip check`, and `git diff --check`.

## Phase 5-N4B Provider Approval Validation

Phase 5-N4B adds frozen `ProviderApproval`, Host, Operation, Auth, Asset,
Download, attribution, rate, scope, and stable-error models. The pure local
Validator checks exact Provider identity, capability and endpoint operation
sets, Host ID/hostname/purpose mappings, typed parameters, method/encoding,
auth/cookies, response/content type, redirects, Asset Hosts, exclusions, and
bounded limits against code-owned `ProviderCapabilities` and
`ProviderEndpoint` objects.

Approval is review data, not runtime registration. The module performs no
file, database, DNS, network, Vault, import, or Registry mutation and exposes no
Approval-to-Registry builder. A separate activation gate rejects `.invalid`
test fixtures and any current unimplemented Auth, Discovery, Asset Resolve,
Download, auth/cookie, non-JSON, or redirect behavior. The Production Provider
Registry remains exactly empty.

`SourceAsset.asset_id` now accepts only bounded ASCII letters, digits, `-`,
`_`, `.`, and `~`, with no leading/trailing dot or consecutive dots. URL/URI,
absolute/relative path, slash/backslash, dot segment, whitespace, control, and
non-ASCII forms fail closed. `external_id` compatibility is unchanged.

N4B verification passed 27 focused tests, 120 combined N4A/Adapter/Outbound
regressions, and all 965 pytest tests. `pip check` and `git diff --check`
passed. Application `1.1.0`, Schema `4`, Backup v2, dependencies, configuration,
Docker, CI, UI, authentication, Vault, import, download, recommendation, and
synchronization remain unchanged.

## Phase 5-N4A Provider Infrastructure and Fixture Reference

Phase 5-N4A implements immutable `ProviderCapabilities` across Metadata, Auth,
Discovery, Asset, and Download layers; typed layer Protocols; `SourceAsset`;
`ProviderAuthMode`, `ProviderAuthState`, and `ProviderAuthStatus`; and stable
redacted Provider errors. The compatibility `SourceAdapter` name now aliases
the capability-bearing `SourceMetadataAdapter` Protocol.

Every `ProviderEndpoint` must bind an exact same-key capability manifest, and
its typed endpoint set must exactly match declared operations. Endpoint policy
now fixes GET/POST, JSON/form body mappings, auth/cookie requirements, response
kind and content types, non-secret headers, redirect rules, limits, and exact
Asset Host allowlists. Wildcard hosts, sensitive fixed headers, cross-layer
operations, duplicated business parameters, and manifest/endpoint mismatches
fail during immutable construction.

The public `OutboundRequest` remains unchanged and accepts no URL, host, path,
method, body, header, cookie, token, password, or locator. The shared client can
only generate typed GET/POST JSON or form requests from code-owned business
parameter mappings. Authentication/cookie policies, non-JSON responses, and
non-denied redirects remain unimplemented and fail before DNS. Existing DNS/IP
pinning, TLS hostname/SNI/Host, TCP/TLS peer verification, deadlines, stream
limits, concurrency, cancellation, immutable JSON, and redacted logs remain.

The Reference Provider exists only in `tests/`, uses reserved synthetic
`.invalid` hosts, static JSON fixtures, a Fake Resolver, Fake Clock,
MockTransport, and Fake Network Backend, and implements only search, detail,
and asset list. Fixture responses deliberately suggest unapproved operations,
hosts, locators, and download flags; capability and Registry checks prevent
those values from expanding authority. The Production Provider Registry is
still exactly empty.

Initial N4A verification passed 17 focused tests, 116 combined N4A/N1 tests,
46 N2 and source regressions, and all 934 pytest tests. The final security audit
added four pre-DNS operation-policy regressions; its rerun passed 21 focused
tests and all 938 pytest tests. `pip check` found no broken requirements.
Application `1.1.0`, Schema `4`, Backup v2, dependencies,
configuration, UI, database import, authentication, Secret Vault, download,
recommendation, synchronization, Docker, and CI remain unchanged.

## Phase 5-N3 Core Provider Contract and Download Plan

Phase 5-N3 is a static audit and planning phase. Its normative output is
[PROVIDER_CONTRACT.md](PROVIDER_CONTRACT.md), and its mandatory user gate for
every real Provider is the blank
[PROVIDER_APPROVAL_TEMPLATE.md](PROVIDER_APPROVAL_TEMPLATE.md). No real
Provider, hostname, endpoint, credential, network request, Adapter extension,
download implementation, route, test, dependency, Schema change, migration,
backup change, Docker change, or CI change is part of N3.

At N3 completion, the contract recorded that `SourceAdapter`
has only search and detail; the Endpoint Registry expresses fixed HTTPS JSON
operations but no method/body/auth/cookie/asset/download policy; the outbound
client is fixed GET+JSON and accepts no URL/header/cookie/body/secret input;
Schema 4 has only `ItemSource` identity/check fields; and the production
Provider Registry is empty. N4A implements the provider-neutral planned types
and typed request-generation foundation while keeping that Registry empty.

Future capabilities are split into Metadata, Auth, Discovery, Asset, and
Download layers with immutable, code-owned manifests. Authentication is
limited to separately approved `none`, `api_token`, `oauth`,
`username_password`, and `session_cookie` modes. The recommended secret design
is a local versioned AEAD Vault under the persistent application-data area,
encrypted with a separate `PROVIDER_SECRET_KEY`; it does not reuse
`APP_PASSWORD` or `SECRET_KEY` and never enters ordinary backup or configuration
export. N3 selects no encryption dependency.

Outbound extensions remain typed and code-owned: fixed GET/POST, fixed JSON or
form body schemas, fixed non-secret headers, credential-broker auth injection,
Provider-isolated cookies, explicit response kinds, and exact Asset Host
allowlists. Arbitrary URL, header, cookie, body, wildcard host, user host, and
response-expanded host inputs remain prohibited. Dynamic asset locators are
short-lived and untrusted; they must pass exact host, path/query, expiry,
DNS/IP pinning, TLS/SNI/Host, peer, auth-scope, and redirect checks.

The planned `SourceAsset` DTO separates asset listing from locator resolution.
The `v1.2.0` download MVP is request-bound and supports one explicitly selected
asset or a bounded selected small batch. It requires signed confirmation,
streamed temporary isolation, actual-byte limits, MIME/magic/hash validation,
no-overwrite publication, exact relationship writes, cancellation propagation,
independent commit-error review, and one media-index coordination per request.
There is no hidden worker, pause/resume, queue, schedule, automatic retry,
startup recovery, recommendation download, or unlimited batch.

Auth and download state/outcome matrices fail closed on uncertainty. A commit
exception does not imply rollback; mixed file/reference facts, unavailable
independent review, or cleanup failure cannot produce ordinary success and must
preserve evidence and invalidate derived media state where required. All future
tests use deterministic fixtures, fake resolvers/transports/clocks, and isolated
storage only.

N4 may begin only after the user supplies and approves every Provider identity,
legal/attribution basis, host, endpoint, method, encoding, response type,
authentication lifecycle, metadata/asset mapping, dynamic locator rule,
download limit, fixture, fault case, dependency implication, and Schema
implication in the approval template. Missing facts are blockers and are never
inferred or searched.

## Phase 5-N2 Schema 4 Source Tracking and Backup v2

Phase 5-N2 adds nullable `provider_key`, `external_id`, `last_checked_at`, and
`metadata_hash` fields to `ItemSource`. A SQLite partial unique index enforces
`(provider_key, external_id)` only when both values are non-null. Provider keys
use a bounded lowercase code format; external IDs remain opaque and
case-sensitive. Legacy URL-only sources remain valid with all four fields null.

The production migration registry is now the continuous `1 -> 2 -> 3 -> 4`
chain. The `3 -> 4` step uses explicit SQLite DDL inside the existing
`BEGIN IMMEDIATE` transaction, preserves every historical source row, verifies
column type/nullability, the existing normalized-URL uniqueness and foreign
key, the exact partial-index predicate, null legacy metadata, and the Schema 4
version record. Fresh databases create the same Schema 4 structure directly.

New JSON exports use `nsfwtrack.backup.v2` and include the four tracking fields;
backup v1 remains accepted and restores those fields as null. Validation rejects
half identities, invalid provider keys/external IDs/timestamps/hashes, duplicate
normalized URLs or provider identities, and contradictory URL/identity/metadata
facts before database writes. Exact local matches are reused without overwriting
local title or metadata. URL, identity, Item, or legacy-enrichment conflicts
block the complete restore.

Restore apply reacquires `BEGIN IMMEDIATE`, repeats source classification inside
the transaction, and invalidates the derived media index only on a successful
restore. After any commit exception, a separate SQLAlchemy Session compares a
digest of every affected business table and media-index state, classifying the
result as committed, committed after an error, confirmed rollback, or unknown.
Migration, backup preview, and restore do not call the outbound client.

N2 acceptance passed 33 focused tests, a 164-test targeted matrix, and all
917 pytest tests; `pip check` reported no broken requirements. Stable `v1.1.0`
refused an isolated Schema 4 database with `application_outdated`, and the
database SHA-256 remained unchanged. Isolated, network-disabled Docker
lifecycles passed fresh Schema 4, v1/v2/conflict restore, persistence, real
stable-Schema-3 preview/apply, legacy-null verification, and recreation while
retaining UID/GID 10001, read-only root, dropped capabilities, and
no-new-privileges. All temporary resources were removed and the existing
`data/` was not used.

The implementation commit is
`df90473d827be86b83da4d7d8487fd852fcff35c`. GitHub Actions run
[`29637868492`](https://github.com/choneer/nsfwtrack/actions/runs/29637868492)
completed both `test` and `Docker production smoke` successfully.

## Phase 5-N1 Controlled Outbound Adapter Foundation

Phase 5-N1 provides an async `SourceAdapter` protocol, frozen provider-neutral
DTOs, an immutable code-owned endpoint registry, a stable outbound error model,
and one shared JSON client. The production registry is empty: the current app
has no real provider name, hostname, endpoint, search route, or reachable
external metadata request.

The client accepts only a provider key, operation, and typed query/detail/page
values. It never accepts a URL, scheme, host, port, base URL, arbitrary path,
header, proxy, cookie, or auth value. Registry definitions are restricted to
HTTPS, port 443, fixed paths, fixed query names, bounded response types, and
code-only construction. Fixed paths contain printable ASCII only. DTO canonical
URLs reject credentials, fragments, literal whitespace, and backslashes.

DNS results are handled as one set: empty, invalid, loopback, private,
link-local, multicast, reserved, unspecified, and mixed safe/unsafe results are
rejected. A fresh HTTP/1.1 pool connects exactly once to the selected approved
numeric IP while the request origin, TLS certificate hostname, SNI, and Host
header retain the allowlisted hostname. The TCP and post-TLS peer address must
both exactly match the selected IP and port 443.

Environment proxies and `.netrc` are disabled with `trust_env=False`; auth,
cookies, redirects, retries, HTTP/2, and compressed responses are disabled.
Limits are 3 seconds for connect, 10 seconds total, 1 MiB streamed body, query
length 200, page size 50, global concurrency 4, and per-provider concurrency 1.
Only JSON content types are accepted, and size validation completes before JSON
parsing. Duplicate object keys, non-finite numbers, and recursive parse failures
are rejected rather than entering adapter payloads.

The existing pinned `httpx2==2.5.0` dependency is now installed at runtime and
continues to pin `httpcore2==2.5.0`. The implementation uses only their exported
public transport, connection-pool, network-backend, and network-stream APIs.

Local verification passed 99 focused tests, 66 related security/configuration
tests, and `pip check`. Two isolated production-container lifecycles were healthy with `/login`
HTTP 200, runtime httpx2 2.5.0, application 1.1.0, Schema 3, UID/GID 10001,
read-only root, zero effective capabilities, and no-new-privileges. Tests used
fake resolvers, fake clocks, MockTransport, and fake network backends only; no
real DNS or provider was contacted.

## Phase 4-M5 Secure Media Directory Management

Phase 4-M5 adds authenticated directory lifecycle operations beneath the local
media root. Directory snapshots use HMAC-SHA256 with the existing application
secret and operation-token format,
bind source and parent mode/device/inode identities, mapping tokens, a complete
subtree manifest digest, and exact Item.cover_path / Creator.avatar_path
reference digests. POST operations revalidate all facts under the M4 lock and
`BEGIN IMMEDIATE`; directory rename uses no-overwrite `renameat2` semantics and
unknown commit outcomes keep the filesystem in place and invalidate the index.

The media root and default upload directory remain protected. Non-empty,
unclean, symlinked, special, damaged, unsupported, reserved, merged, or
cross-device directory trees are rejected. GET previews remain write-free and
do not create the operation lock; successful directory mutations refresh the
derived index once with source `post_directory`. Version `1.0.6`, Schema `3`,
dependencies, backup format, and local-only boundaries remain unchanged.

Final Phase 4-M5 acceptance passed targeted `60`, M5 `62`, related regression
`146`, core `152`, and full `777` pytest tests; `pip check` reported
`No broken requirements found`. GitHub Actions run
[`29563883918`](https://github.com/choneer/nsfwtrack/actions/runs/29563883918)
completed both `test` and `Docker production smoke` successfully.

Cloud-review corrective history is preserved in three implementation commits:
`d00d059701ae767094e5cb07babb58844c2be322` added bounded manifests,
streaming SHA-256, post-`BEGIN IMMEDIATE` final snapshots, exact-reference
independent review, and directory outcome/stale-reason handling;
`d651d1f649972c39ce7a3bd8af44b715b9c705cd` closed post-`mkdir` and
post-`rmdir` failures, quiet rollback, result-path lock verification, and
unknown-success messaging; `090eb61e10f0974bfed3f8379a7ba50a91f29207`
completed the outcome × index-status message matrix, accurate invalidation
failure warnings, directory-specific unknown reasons after lock upgrades, and
removed contradictory success/refresh/invalidation messages.

Hermes independently accepted the final code and Actions state. It confirmed
matching HEAD/origin, a clean tracked tree with only the existing untracked
`data/` marker, create/rename/move/empty-delete behavior, exact Item/Creator
reference migration, one `post_directory` incremental refresh per request,
directory-specific unknown handling without a normal success message, and
Docker persistence across the second lifecycle. The container remained UID
10001, non-root, read-only-root, capability-free (`CapEff=0`), protected by
`no-new-privileges`, and returned `/login` HTTP 200; isolated resources were
removed and the existing `data/` was untouched.

N100 deployment: `not started; waits for explicit user authorization`.

NSFWTrack remains local-first: records, media, credentials, and persistence stay
local. Future network, download, recommendation, and synchronization abilities
remain disabled until separately authorized and must preserve the permanent
boundaries in `PRODUCT_VISION.md` and `RULE.md`.

## Completion Audit

Phase 2-K1 found no genuine TODO / FIXME marker, stub route, 501 response, or
dead navigation entry. Phase 2-K2 closed the three pre-use findings and the
archived `v1.0.4` suite contains 358 passing tests.

The `v1.0.6` release is the previous stable tag. Code development and WSL
acceptance through Phase 3-B1 and B2 are complete. See
[COMPLETION_AUDIT.md](COMPLETION_AUDIT.md) for the archived K1 / K2 evidence.
The current B3-C5 integration, finding-state matrix, confirmed D1 fixes, and
584-test local acceptance evidence are recorded in
[PHASE3_COMPLETION_AUDIT.md](PHASE3_COMPLETION_AUDIT.md).

- Phase 2-K2 closed the local media-path, bulk / clear confirmation, deployment
  placeholder-secret, focused F4 test, and upgrade-runbook gaps.
- N100 / target-host deployment has not started and is not a current development
  task. It must wait for explicit user authorization.

The bounded Phase 3-A1 through A6 scope shipped in `v1.0.5`; the read-only
Phase 3-B1 and B2 duplicate-media views shipped in `v1.0.6`. Phase 3-B3 is
complete in Unreleased; Phase 3-B4 adds read-only recovery visibility and B5
adds explicit single-anchor restoration. B6 adds confirmed permanent deletion
only for legal zero-reference anchors. C1 adds explicit single cover/avatar
reference replacement or clearing without changing any media file. C2 adds
explicit deletion of one exact, unreferenced `.upload-*.tmp` residue without
reading its content or modifying database references. C3 adds a read-only,
per-path view of every safely skipped media-scan entry and its stable reason.
C4 adds explicit permanent deletion of one still-damaged, zero-reference
ordinary-media file after a write-free preview and locked safety rechecks.
C5 adds read-only media-root diagnostics and explicit missing-only safe
initialization without restoring media or changing broken references.

Phase 3-D1 audited the complete B3-C5 navigation and state closure. It adds the
missing exact-SHA duplicate-finding entry and closes confirmed parent-path
replacement races in Data Health scanning, shared B3-B6 validated-media
create/publish/delete operations, authenticated media serving, and C2 residue
deletion. Media responses and mutations now retain and recheck root/parent
directory fd identities before reading, linking, or unlinking; injected
external-symlink/hard-link races fail closed without returning or touching the
external entry.

The final create/publish checks also require every returned record to retain the
original root, logical parent path, and stable directory identity chain. Exact
post-create and post-link races replace the parent with an ordinary external
directory containing same-inode hard links; both reject success while preserving
the original directory, external entries, database references, and other media.
Hard-link ctime changes are intentionally not compared as an immutable snapshot.

Local D1 acceptance passes 365 integrated compatibility tests and all 584
tests. `pip check` is clean. The production image builds, isolated Compose is
healthy with the existing non-root/read-only/capability security boundaries,
and login plus the authenticated Data Health/media navigation pages return
HTTP 200. Repair commit `db0048d` is pushed, and GitHub Actions run
[`29386547600`](https://github.com/choneer/nsfwtrack/actions/runs/29386547600)
passed both `test` and `Docker production smoke`. No known D1 release blocker
remains, so the reviewed Unreleased development scope is frozen.

## Phase 4-M4 Media-write Coordination and Index Consistency

Phase 4-M4 adds one cross-process media-operation lock in the fixed application
data directory. The lock is outside the media root, never derives from request
input, and is opened relative to a verified directory descriptor. Symlinks,
directories, special objects, wrong ownership, unsafe permissions, hard-linked
lock files, and path replacement are rejected. A bounded timeout returns
`media_busy` before the requested media or business database mutation begins.

Uploads, single rename and move, current-page batch operations, hardlink-alias
normalization, duplicate and damaged cleanup, recovery, cleanup-anchor and
upload-residue deletion, and media-root initialization all hold this lock for
the business operation and its post-operation index handling. Manual
incremental refresh and confirmed full verification use the same lock, so an
application scan cannot commit across an in-app media write. GET requests never
acquire the lock or create its file.

Every operation is classified as `no_filesystem_change`,
`filesystem_changed_known`, `filesystem_changed_partial_known`, or
`filesystem_outcome_unknown`. Known and partial-known final states receive one
incremental refresh after the business transaction; a batch never scans once
per item. Unknown commit or cleanup outcomes never drive a guessed refresh and
instead invalidate the old snapshot with `filesystem_outcome_unknown`.

If a completed mutation is followed by a failed refresh, its file and business
result remain committed while the index is invalidated with
`post_mutation_refresh_failed`. The UI gives an explicit manual-refresh warning
and read pages fall back to the FD-safe filesystem scan. Setting, replacing, or
clearing only a cover/avatar reference does not scan because it changes no
media path. All original live filesystem, reference, snapshot, POST, and
confirmation checks remain authoritative; the derived index is never used to
authorize a write.

The scan center now records whether its latest attempt was manual or followed
an upload, rename, move, batch, cleanup, recovery, or root initialization.
There is still no background worker, timer, watcher, network request, new
dependency, backup-format change, tag, Release, or N100 deployment. Application
version remains `1.0.6` and Schema remains `3`.

Local M4 acceptance passes `89` focused coordination/rename/move/batch tests,
`457` core media/index/migration/backup tests, and all `735` tests. `pip check`
reports no broken requirements. The isolated production image builds and both
container lifecycles become healthy as UID/GID `10001:10001` with a read-only
root filesystem. `/login` returns HTTP 200; the private lock remains the same
regular `0600` UID/GID-10001 file after container removal, can be reacquired,
and a coordinated write refreshes the persisted index from one to two entries
with source `post_upload`. Temporary Docker resources are removed afterward.

Implementation commit `5899588` is pushed to `main`. GitHub Actions run
[`29519131776`](https://github.com/choneer/nsfwtrack/actions/runs/29519131776)
completed successfully for both `test` and `Docker production smoke`. No tag,
Release, or N100 deployment was created.

## Phase 4-M3 Incremental Media Index and Scan Center

Phase 4-M3 upgrades the local database from Schema 2 to Schema 3 through an
explicit `create_media_index` migration. The two new tables contain only a
rebuildable derived cache and scan status; fresh databases start at Schema 3,
while the 2 → 3 migration creates an empty invalid index without scanning the
filesystem or changing any existing business row.

`/media-library/index` is a login-protected scan center. Its GET view reads only
stored status and never writes the database or filesystem. Incremental refresh
is an explicit POST. Full verification first uses a write-free preview, then a
confirmed POST that ignores cached content facts and safely reads, validates,
and hashes every ordinary media file again.

Incremental reuse requires an HMAC-valid cache row plus exact mode, size,
device, inode, mtime, ctime, and root/parent directory mapping. A parent
replacement, inode replacement, changed identity, forged row, invalid
signature, or index corruption forces safe re-reading or a full fallback.
Traversal, opening, reading, and final mapping checks retain the existing
descriptor-based `O_NOFOLLOW` semantics.

Each refresh builds media, directory, skip, statistics, and change snapshots
before replacing the index in one SQLite transaction. A scan or commit failure
leaves the previous complete snapshot intact. The media library, directory
browser, duplicate groups, hardlink aliases, matching candidates, and skipped
paths prefer the complete index and visibly identify its timestamp and
point-in-time nature. Every operation that changes files or references still
performs immediate filesystem and database revalidation.

The index is excluded from JSON backup and restore. Successful restore marks
it invalid in the same transaction, after which it can be rebuilt manually.
No background worker, scheduled scan, network request, dependency, media-file
change, tag, Release, or N100 deployment is part of M3. Application version
remains `1.0.6`.

Final local M3 acceptance passes `16` focused index/i18n tests, `45` migration
and schema-version tests, `141` core media/index/backup tests, and all `717`
tests. `pip check` reports no broken requirements. The isolated production
image builds and remains healthy as UID/GID `10001:10001` with a read-only root
filesystem; `/login` returns HTTP 200, fresh initialization reports Schema 3,
and a complete one-file index remains valid after the container is removed and
recreated against the same isolated data mount.

Implementation commit `cb7561f` is pushed to `main`. GitHub Actions run
`29510396534` completed successfully for both `test` and
`Docker production smoke`; no tag, Release, or N100 deployment was created.

## Phase 4-A1 Local Media File Details

Phase 4-A1 adds `/media-library/detail` as the unified, login-protected,
read-only view for one ordinary local media file. The page accepts only a
normalized `/media/` path represented by the existing ordinary-media scan;
external paths, traversal, missing entries, symlinks, special files, unsupported
files, scan races, and internal `.cleanup-anchor-*` records fail closed.

The view consumes the existing identity-checked directory/file FD scan result
instead of reopening the target through `Path.stat` or `Path.read_bytes`. It
shows the logical path, basename, extension, safely confirmed MIME, size,
complete SHA-256 when available, validity, recovered status, exact item-cover
and creator-avatar references, and current complete-SHA duplicate-group totals.
Damaged references link only to the existing C1 flow, while damaged files link
only to the existing C4 preview; A1 adds no write route or operation.

Media-library cards, duplicate-group members, and recovered ordinary-media rows
link to the detail page. Their normalized search, status, sort, and pagination
state is carried in a restricted local return URL. Focused A1 tests pass `17`
cases, the media/Data Health/backup/UI regression passes `252` tests, and the
full suite passes all `601` tests. `pip check` is clean. The production image
builds; isolated Compose is healthy with the existing non-root/read-only/
capability boundaries, `/login` returns 200, anonymous detail access redirects,
and authenticated detail/library pages return 200. Implementation commit
`c8cfb99` is pushed, and GitHub Actions run `29389862206` passed both `test`
and `Docker production smoke`.

## Phase 4-A2 Safe Ordinary-Media Rename

Phase 4-A2 adds a safe-rename entry to each eligible A1 detail page. Only the
same-directory basename may change; the source extension and its letter case
must remain exact. Empty, unchanged, path-bearing, control-character,
percent-encoded, reserved-prefix, overlong, external, damaged, skipped,
symlink, special-file, upload-residue, and cleanup-anchor requests fail closed.
Any existing target file, hard link, symlink, directory, FIFO, other object, or
database reference blocks the operation without overwrite.

The authenticated GET preview is write-free and shows both logical paths,
complete SHA-256 and file identity, every item-cover / creator-avatar
reference, and consequences. The confirmed POST revalidates that snapshot
under `BEGIN IMMEDIATE`, creates the target with `os.link` through a retained
verified parent-directory FD, migrates every exact source reference, verifies
both directory entries and open FDs, and commits before attempting the
identity-bound source unlink. Database failure rolls references back and
removes only the self-created target when an independent Session proves all
expected references still point to the source and the target has zero
references. If the commit call raises after the database actually commits, the
verified target and source are both retained and the UI reports the committed
result accurately. Mixed references, an unreferenced ambiguous transaction, or
a failed independent query are treated as unknown: both files remain and the
UI does not claim success. If source unlink fails after a normal commit, the
valid target and committed references remain, the source is retained, and the
UI reports both paths for review.

The original focused A2 coverage passed 43 tests, including valid referenced and
unreferenced/recovered files, strict `CONFIRM`, exact reference changes,
target claims and same-inode links, source/target/parent replacements,
commit-failure cleanup, source-delete failure, SHA/content/duplicate-group
preservation, and prohibition of target `Path.stat` / `Path.read_bytes` reopens.
The commit-outcome correction expands the rename suite to 49 tests; rename plus
i18n passes 50, the core media chain passes 193, and the broad media/Data
Health/backup/UI regression passes 315. The full suite passes all 650 tests and
`pip check` is clean. The production image rebuilds; isolated Compose is
healthy with the existing runtime security boundaries, `/login` returns 200,
and temporary resources are removed. Correction commit `09be556` is pushed,
and GitHub Actions run
[`29399210087`](https://github.com/choneer/nsfwtrack/actions/runs/29399210087)
passed both `test` and `Docker production smoke`.
The original implementation commit `b32e848` is
pushed, and GitHub Actions run
[`29396021693`](https://github.com/choneer/nsfwtrack/actions/runs/29396021693)
passed both `test` and `Docker production smoke`.

## Phase 4-M1 Media Management Enhancements

Phase 4-M1 adds authenticated `/media-library/directories` and
`/media-library/aliases` read-only views. Directory browsing uses only verified
ordinary directories beneath the media root and retains breadcrumbs, direct
statistics, search, status, sort, pagination, and detail return state. Alias
audit groups multiple logical paths by exact `device/inode`, reports every
cover/avatar reference per path, and separately labels same-SHA files with a
different identity. Neither view writes SQL or offers automatic cleanup.

Eligible media details now offer a cross-directory move preview. The target
must be an existing ordinary directory under the same media root; symlink,
missing, internal-reserved, escaping, and replaced directories fail closed.
The optional basename preserves the exact extension, and every occupied target
object blocks execution. M1 extends the A2 path-change engine rather than
duplicating it: separate verified source/target FD chains, no-overwrite
hardlink creation, exact item-cover/creator-avatar migration, independent
commit inspection, identity-bound cleanup, and post-commit source removal use
the same safety semantics for rename and move.

The same detail page can preview setting, replacing, or clearing one
`Item.cover_path` or `Creator.avatar_path`. Confirmed POST uses the configured
standard/strict confirmation policy, validates the complete object snapshot
and media identity under `BEGIN IMMEDIATE`, and executes one conditional SQL
field update. Titles, names, types, summaries, dates, extra data, timestamps,
relationships, other objects, and all media files remain unchanged. Commit
exceptions are rechecked through an independent session; an unknown result is
reported without a false success claim.

M1 creates or deletes no directory, performs no bulk operation, selects no
alias keeper, and adds no automatic merge. It leaves version 1.0.6, Schema 2,
migrations, indexes, dependencies, Docker/CI, tags, Releases, N100 deployment,
network access, recognition, recommendation, and AI behavior unchanged.

Current M1 local acceptance: the four focused suites pass `29` tests, the
local-media/A2/A1/M1/i18n combination passes `140` tests, the full suite passes
`679` tests, and `pip check` reports no broken requirements. The production
Docker image builds, Compose reaches healthy, `/login` returns HTTP `200`, and
the stack shuts down cleanly. Implementation commit `4e350bf` is pushed, and
GitHub Actions run
[`29405923933`](https://github.com/choneer/nsfwtrack/actions/runs/29405923933)
passed both `test` and `Docker production smoke`.

## Phase 4-M2 Batch Organization and Alias Normalization

Phase 4-M2 adds current-page multiselect controls to both the media library and
directory browser. Only valid ordinary media rows are selectable, with a hard
20-file limit and no cross-page select-all. The server reconstructs the source
page from its normalized search, status, sort, directory, and pagination state;
paths outside that recomputed page, duplicates, damaged or reserved media, and
invalid paths are rejected before preview.

Batch move and rename use write-free authenticated GET previews. Users can edit
each basename before confirmation. Move accepts only an existing ordinary
directory beneath the media root; rename stays in each source directory. Exact
extension spelling is preserved, and duplicate targets, occupied paths, name
swaps, cycles, traversal, reserved names, and forged signed snapshots fail
closed. The confirmed POST processes each file independently through the M1
verified source/target directory FDs, no-overwrite hardlink publication, exact
item-cover and creator-avatar migration, transaction outcome inspection, and
identity-bound source removal. The result page distinguishes success, failure,
committed-with-source-retained, and unknown outcomes for every file.

The hardlink alias audit now offers an explicit keeper selector for one complete
device/inode group. Its GET preview rescans every path and reference without
writing. Confirmed normalization migrates all non-keeper cover/avatar references
to the keeper in one transaction, independently verifies the commit, then
deletes only still-matching zero-reference aliases. Unknown commits, query
failure, or mixed references retain every path. Files with the same complete
SHA-256 but a different device/inode identity are listed as independent and are
never migrated or deleted.

M2 adds no task table, schema, migration, dependency, version, tag, Release,
network access, automatic merge, recommendation, recognition, AI behavior, or
N100 deployment. The 21 focused service and HTTP cases pass; the complete
local-media/A1/A2/M1/M2/i18n core passes `165` tests, and the full suite passes
`700` tests. `pip check` is clean. The production image builds, Compose reaches
healthy with user `10001:10001`, read-only root and `cap_drop: ALL`, `/login`
returns HTTP `200`, and the stack shuts down cleanly. Implementation commit
`a6b2d7b` is pushed, and GitHub Actions run
[`29432471537`](https://github.com/choneer/nsfwtrack/actions/runs/29432471537)
passed both `test` and `Docker production smoke`.

## v1.0.6 Release

The `v1.0.6` release contains only the read-only Phase 3-B1 and B2 duplicate
media workflow:

- B1 adds stable complete-SHA-256 duplicate grouping, library totals,
  `media_status=duplicate`, SHA-prefix search, and per-file group context.
- B2 adds the authenticated `/media-library/duplicates` group view with group
  sizes, reclaimable-space totals, member references, group search/sort,
  20-group pagination, and exact links back to B1.
- Both phases share one valid-media, complete-SHA-256 grouping implementation.
  Damaged files, empty or malformed hashes, single-path content, and duplicate
  records for one path remain excluded.
- Both phases are read-only. They do not delete, move, rename, overwrite, or
  choose a media file; migrate or clear a cover/avatar reference; change A3/A4
  candidates; request an external resource; or use AI/image recognition.

Release preparation changed only application version metadata, its regression
assertion, and release documentation. It does not change Schema 2, the existing
1 to 2 migration, dependencies, Docker/CI security configuration, or any old
tag or Release.

Local release-candidate acceptance passed all 441 tests and `pip check`. An
isolated production-image Docker smoke passed two complete container
lifecycles; both reported healthy, `/login` HTTP 200, application version 1.0.6,
and Schema 2, while the same SQLite file retained an unchanged checksum across
container recreation.

- Annotated tag object: `d4d5c31cd5b2fed9a90ad69742d54b4c9dbed0b4`
- Peeled release commit: `961a3d0cc169e82b261d83207b0ec802007e292b`
- Release: [NSFWTrack v1.0.6](https://github.com/choneer/nsfwtrack/releases/tag/v1.0.6)

### Phase 3-B3 Manual Duplicate Media Cleanup

The current Unreleased Phase 3-B3 extends the duplicate-group page with an
explicit, one-group-at-a-time cleanup flow:

- The group view provides no default or recommended keeper. The user must
  explicitly choose one current member before opening the read-only preview.
- Preview lists every cover/avatar reference migration, redundant path, and
  expected released byte count without changing SQLite or media files.
- Confirmed POST uses the existing standard/strict danger policy and rescans
  the shared B1/B2 complete-SHA-256 group before writing anything.
- Missing, damaged, symbolic-link, escaping, forged, hash-changed, or stale
  members are rejected. The keeper is never deleted and no other group is
  processed.
- Before any redundant file is removed, affected cover/avatar references commit
  to a verified same-filesystem safety anchor. The anchor remains a valid
  same-SHA-256 copy throughout every deletion and is removed after references
  safely commit to the final keeper path.
- If the selected keeper disappears, it is restored from the anchor without
  overwriting another file. If its path is replaced or occupied, the external
  file remains untouched and references move to a unique verified recovery
  path. Identity-checked deletion failures remain safe and retryable.
- Tests cover keeper loss before the first deletion, after half the removals,
  and during the final deletion. At every observed stage, database references
  resolve to an existing legal file with the expected complete SHA-256, and
  success, exception, deletion-failure, and retry paths leave no temporary
  anchor residue.

Phase 3-B3 does not change the A3/A4 candidate algorithms, application version
1.0.6, Schema 2, the existing migration, dependencies, or Docker/CI security
configuration. It makes no external request and adds no automatic keeper
selection, AI/image recognition, tag, or Release.

Local acceptance passes all 459 tests and `pip check`. An isolated Docker image
passes two complete healthy lifecycles with `/login`, authentication, and the
duplicate-group page returning HTTP 200, version 1.0.6, Schema 2, unchanged
SQLite checksum, fixed non-root identity, read-only root, zero capabilities,
and no-new-privileges. All temporary resources were removed.

### Phase 3-B4 Media Cleanup Recovery Center

The current Unreleased Phase 3-B4 makes B3 fallback artifacts observable while
keeping every B4 query read-only:

- Only a file basename beginning exactly and case-sensitively with
  `.cleanup-anchor-` is an internal safety anchor. A path that merely contains
  that text, or a directory with that prefix, remains ordinary media.
- Internal anchors are absent from the ordinary media library, B1/B2 duplicate
  groups, upload deduplication, and A3/A4 candidates. Non-anchor A3/A4 candidate
  IDs remain unchanged when an anchor appears.
- A basename beginning exactly with `recovered-` remains ordinary media. It
  participates in existing duplicate/candidate behavior and has a dedicated
  media-library filter and badge.
- The authenticated `/media-library/recovery` page separates referenced,
  unreferenced, and damaged anchors from recovered files. It shows path, byte
  size, complete SHA-256 when valid, validity, and item-cover / creator-avatar
  references with path/SHA search, stable sorting, and 20-row pagination.
- Data Health reports referenced, unreferenced, and damaged anchor residue and
  links to the recovery center. Every GET is write-free; the later B5 restore
  operation is isolated behind its own preview and confirmed POST, with no
  movement, renaming, or automatic repair.

Phase 3-B4 does not change B1/B2 grouping semantics, the B3 cleanup operation,
version 1.0.6, Schema 2, migrations, dependencies, Docker/CI, tags, or Releases.

B4/i18n focused acceptance passes 16 tests, the complete media-chain regression
passes 120 tests, and the full suite passes 474 tests with `pip check` clean.
An isolated production image passes two healthy lifecycles with `/login`, the
authenticated recovery center, ordinary media library, and Data Health all
returning HTTP 200; version 1.0.6, Schema 2, runtime hardening, and the SQLite
checksum across recreation remain unchanged. All temporary resources are
removed.

### Phase 3-B5 Safe Single Anchor Restore

The current Unreleased Phase 3-B5 turns a deliberately selected, valid B3
safety anchor into an ordinary recovered media file without adding automatic
or bulk cleanup:

- Each valid anchor row links to an authenticated, write-free GET preview that
  displays its full path and SHA-256, MIME type, size, device, inode, mtime,
  ctime, current cover/avatar references, and exact consequences.
- Confirmed execution is a separate POST using the existing standard/strict
  danger policy. It rescans the internal media view and compares every identity
  field from the preview before creating or updating anything.
- Publication creates a unique `recovered-*` path in the same directory with
  no overwrite. The valid anchor and recovery path are the same verified inode
  and SHA-256, and both file and directory durability are synchronized.
- Every current item-cover and creator-avatar reference moves in one database
  transaction. The original anchor is removed only after the transaction has
  committed, the recovery identity is still valid, and a locked zero-reference
  recheck succeeds.
- A database failure rolls back all references and removes the newly published
  recovery path. An anchor-delete failure leaves every reference on the valid
  recovery file and reports the retained anchor for manual inspection.
- Damaged, symlinked, wrong-extension, missing, changed, stale, forged,
  ordinary, and `recovered-*` requests are rejected. Ordinary interactive
  cover/avatar writes cannot create new internal-anchor references.

B5 does not batch-restore or discard content, operate on `recovered-*`, change
backup restore or B3 internals, alter B1/B2/A3/A4 behavior, request a network
resource, or add AI/image recognition. Version 1.0.6, Schema 2, migrations,
dependencies, Docker/CI, tags, Releases, and N100 deployment remain unchanged.

B5 focused acceptance passes 12 tests, the full suite passes 486 tests, and
`pip check` reports no conflicts. An isolated production image passes two
healthy lifecycles with `/login`, authentication, the recovery center, and a
valid single-anchor preview returning HTTP 200. Runtime hardening remains
active and the SQLite checksum is unchanged across recreation; all temporary
Docker resources are removed.

### Phase 3-B6 Unreferenced Safety Anchor Delete

The current Unreleased Phase 3-B6 provides a deliberately narrow way to remove
one valid cleanup-anchor residue only when no item cover or creator avatar
references it:

- Only an `anchor_unreferenced` recovery-center row exposes the permanent-delete
  preview. Referenced, damaged, symlinked, wrong-extension, ordinary, and
  `recovered-*` rows have no eligible delete action.
- The authenticated GET preview is write-free and displays full path, SHA-256,
  MIME type, size, device, inode, mtime, ctime, and the irreversible outcome.
- Confirmed POST uses the existing standard/strict danger policy, rescans the
  internal media view, and rejects any submitted identity snapshot that no
  longer exactly matches.
- Before unlink, the service ends the preview read transaction, acquires SQLite
  `BEGIN IMMEDIATE`, and rechecks both item-cover and creator-avatar counts.
  A reference added after preview therefore rejects deletion while the file and
  database remain intact.
- Under the same lock it validates complete identity and SHA again, then uses
  identity-bound unlink and directory fsync. It deletes only the selected path,
  creates no recovery file, and never migrates or clears a database reference.
- Unlink/identity/lock failures report a specific reason and retain the target.
  If unlink succeeds but directory durability reports an error, the result
  accurately reports that the file was removed with a persistence warning.

B6 performs no batch or automatic cleanup and does not alter B3, B4, B5,
B1/B2/A3/A4, Data Health fix behavior, or backup compatibility. Version 1.0.6,
Schema 2, migrations, dependencies, Docker/CI, tags, Releases, and N100
deployment remain unchanged.

B6 focused acceptance passes 15 tests, the B3-B5 media-chain regression passes
156 tests, the full suite passes 501 tests, and `pip check` reports no
conflicts. An isolated production image passes two healthy lifecycles; login,
authentication, recovery center, delete preview, and confirmed deletion all
return HTTP 200. The target disappears without a `recovered-*` file, SQLite's
checksum remains unchanged through GET, POST, and recreation, and all temporary
Docker resources are removed.

### Phase 3-C1 Broken Media Reference Repair

The current Unreleased Phase 3-C1 gives each invalid item-cover or
creator-avatar finding in Data Health a deliberately narrow manual repair flow:

- Missing, damaged, symbolic-link, invalid/escaping-path, and damaged internal
  anchor references expose an authenticated single-object preview. Healthy
  references and non-media findings have no repair action.
- GET displays the object, exact original path, issue type, consequences, and
  a snapshot token without writing to SQLite or the media directory.
- The user must either explicitly clear that one reference or choose one
  existing fully validated local image. Replacement candidates support
  path/SHA search, stable path ordering, and fixed 20-row pagination.
- Valid `recovered-*` images remain ordinary replacement candidates. Internal
  `.cleanup-anchor-*` files, damaged media, symlinks, and unsupported paths are
  excluded and rejected again by the service.
- Confirmed POST uses the existing standard/strict danger policy. It ends the
  preview transaction, acquires `BEGIN IMMEDIATE`, and revalidates the object,
  original reference, issue type, and replacement SHA, size, device, inode,
  mtime, and ctime.
- Exactly one conditional `item.cover_path` or `creator.avatar_path` update is
  attempted. The replacement identity is checked again before commit; stale,
  forged, changed, or racing requests roll back.
- A database or commit failure rolls back the complete reference update. C1
  never deletes, writes, moves, renames, or otherwise modifies a media file.

C1 does not auto-recommend, auto-clear, batch-repair, or process any other Data
Health category. It makes no network request and adds no AI/image recognition.
Version 1.0.6, Schema 2, migrations, dependencies, Docker/CI, tags, Releases,
backup formats, and N100 deployment remain unchanged.

C1 focused acceptance passes 7 tests, the B3-B6/media-library/Data
Health/backup/import regression passes 232 tests, the full suite passes 508
tests, and `pip check` reports no conflicts. An isolated production image
passes two healthy lifecycles with login, authentication, Data Health, preview,
confirmed replacement, and confirmed clearing returning HTTP 200. The repaired
references persist across recreation, every media checksum remains unchanged,
the SQLite checksum is stable, and runtime hardening remains active.

### Phase 3-C2 Upload Residue Manual Cleanup

The current Unreleased Phase 3-C2 gives each exact `media_upload_residue`
finding in Data Health a deliberately narrow, manual permanent-delete flow:

- Only a regular, non-symlink file whose basename case-sensitively matches
  `.upload-*.tmp` is eligible. Empty-middle names, lookalikes, directories,
  symbolic links, missing paths, escaping paths, and forged targets are denied.
- The authenticated GET preview displays the relative path, size, device,
  inode, mtime, ctime, current cover/avatar references, and exact consequences.
  It writes nothing and never reads, parses, restores, or copies temporary-file
  content.
- A referenced residue exposes C1 guidance rather than a delete form. C2 never
  migrates, clears, or otherwise changes a database reference.
- Confirmed POST uses the existing standard/strict danger policy and compares
  every submitted identity field against a fresh observation.
- The service ends the preview transaction, acquires `BEGIN IMMEDIATE`, and
  checks both item-cover and creator-avatar references again under the write
  lock. A reference added after preview rejects the operation before unlink.
- It revalidates the complete identity under the same lock, unlinks only the
  selected directory entry by directory fd, then fsyncs the containing
  directory. No `recovered-*` copy is created.
- A lock, reference-query, identity, or unlink failure retains the target and
  leaves the database unchanged. If unlink succeeds but directory fsync fails,
  the result explicitly reports that the file was removed with a durability
  warning.

C2 adds no automatic or batch cleanup, content recovery, network request,
AI/image recognition, dependency, database change, or migration. Application
version 1.0.6, Schema 2, Docker/CI, tags, Releases, backup formats, and N100
deployment remain unchanged.

C2 focused acceptance passes 22 tests. The explicit C1/B3-B6/upload/Data
Health/backup/import regression passes 253 tests, the full suite passes 530
tests, and `pip check` reports no conflicts. The production Docker image builds
successfully; Compose reaches healthy state, `/login` returns HTTP 200, and the
acceptance stack is removed cleanly.

Feature commit `ab373b3` is pushed to `main`. GitHub Actions run
[`29317914417`](https://github.com/choneer/nsfwtrack/actions/runs/29317914417)
completed successfully for both `test` and `Docker production smoke`.

### Phase 3-C3 Media Scan Skip Location Center

The current Unreleased Phase 3-C3 makes the existing scan-skip summaries
individually observable without turning them into write operations:

- Each skipped entry has one deterministic safe relative display path and one
  stable reason: `symlink`, `unsupported_extension`, `special_file`,
  `directory_unreadable`, or `entry_error`.
- Safe lstat size, device, inode, mtime, and ctime values are recorded when
  available. Extensions are shown separately; raw system errors and absolute
  host paths are never retained or rendered.
- Directory traversal uses directory fds with `O_DIRECTORY|O_NOFOLLOW`.
  Symbolic links are identified by lstat and never followed, including when a
  directory is replaced by a link after its initial inspection.
- Valid media candidates retain traversal-time device, inode, size, mtime, and
  ctime identities for the root, every parent, and the file. Reading reopens
  the complete directory chain through verified fds and opens the final file
  through `dir_fd|O_NOFOLLOW`; it never falls back to `Path.stat/read_bytes`.
- The open descriptors and current root-relative name mapping are revalidated
  before parsing or hashing. Parent symlink replacement, file replacement, or
  any identity drift becomes a safe `entry_error` and cannot enter the media
  list or expose replacement content.
- Skipped file content is never opened, read, parsed, validated, or hashed.
  One directory or entry failure creates a bounded reason record and does not
  interrupt sibling scanning.
- The authenticated `/media-library/skipped` GET page supports path search,
  exact reason filters, the legacy non-symlink unsupported scope, stable
  path/type ordering, and fixed 20-row pagination.
- Data Health links `media_scan_skipped_symlinks` directly to the symlink filter
  and `media_scan_skipped_unsupported` to the four compatible non-symlink
  reason classes.
- `skipped_symlinks` exactly equals the symlink-record count;
  `skipped_unsupported` exactly equals all other skip records. The per-entry
  list is deduplicated and deterministically sorted.

C3 provides no POST route, delete, move, rename, recovery, association,
automatic action, external request, or AI/image recognition. Ordinary media,
cleanup anchors, `recovered-*`, upload residues, database structure, backup
formats, version 1.0.6, Schema 2, migrations, dependencies, Docker/CI, tags,
Releases, and N100 deployment remain unchanged.

Local C3 acceptance passes 10 focused tests, including parent-directory and
same-file identity replacement races, 263 regression tests covering
Phase 3-A3 through A6, B1 through B6, C1 through C2, media library, upload,
Data Health, backup, and import, and all 540 tests. `pip check` reports no
broken requirements. The production image builds, Compose reaches healthy,
`/login` returns HTTP 200, the protected skip page redirects unauthenticated
requests, and the isolated acceptance stack is removed cleanly.

Feature commit `c591ca4` is pushed to `main`. GitHub Actions run
[`29321642902`](https://github.com/choneer/nsfwtrack/actions/runs/29321642902)
completed successfully for both `test` and `Docker production smoke`.

Parent-path race fix commit `c27676f` is pushed to `main`. The new regression
proves that replacing an already opened child-directory path with an external
symlink never reads or hashes the same-name external image and never adds it to
`scan.entries`. GitHub Actions run
[`29332762558`](https://github.com/choneer/nsfwtrack/actions/runs/29332762558)
completed successfully for both jobs.

### Phase 3-C4 Damaged Media Manual Cleanup

The current Unreleased Phase 3-C4 provides a deliberately narrow manual
permanent-delete path for ordinary local-media files that fail image
validation:

- Data Health reports one `media_damaged_file` finding per eligible file, and
  each matching invalid media-library card links to the same single-file
  preview. Valid images, cleanup anchors, upload residues, symbolic links,
  unsupported/special files, and scan skips are excluded. A damaged
  `recovered-*` file remains eligible as ordinary media.
- The authenticated GET preview shows the safe `/media/...` path, original
  complete SHA-256, size, device, inode, mtime, ctime, current item-cover and
  creator-avatar references, and irreversible consequences. GET performs no
  file or database write.
- Candidate content is opened only through the C3 verified root/parent/file FD
  chain with `O_DIRECTORY|O_NOFOLLOW`; it is never opened through a
  re-resolved `Path.stat/read_bytes` sequence.
- A referenced target shows direct C1 repair links and no delete form. C4 never
  clears, migrates, or rewrites a reference.
- Confirmed POST uses the existing standard/strict danger policy. It rechecks
  the original SHA, damaged state, and complete size/device/inode/mtime/ctime
  identity, then acquires `BEGIN IMMEDIATE` and verifies both cover and avatar
  reference counts are still zero before unlink.
- Parent/symlink replacement, a changed SHA or identity, a file that becomes a
  valid image, and a racing reference are rejected before deletion. Unlink
  failure retains the file; directory fsync failure reports that the file was
  deleted with a durability warning.
- Only the selected directory entry is removed. No recovery copy is created,
  no other media is touched, and there is no automatic, batch, scheduled,
  network, AI, or image-recognition behavior.

C4 does not change application version 1.0.6, Schema 2, migrations,
dependencies, Docker/CI, backup/import formats, tags, Releases, or N100
deployment.

C4 focused acceptance passes 17 tests; the explicit B3-B6/C1-C3/media-library/
upload/recovery/Data Health/backup/import regression passes 280 tests; and the
full suite passes 557 tests. `pip check` reports no broken requirements. The production image builds,
Compose reaches healthy state, `/login` returns HTTP 200, and the acceptance
container and network are removed cleanly.

Feature commit `1e686f3` is pushed to `main`. GitHub Actions run
[`29336790587`](https://github.com/choneer/nsfwtrack/actions/runs/29336790587)
completed successfully for both `test` and `Docker production smoke`.

### Phase 3-C5 Media Root Diagnostic And Safe Initialization

The current Unreleased Phase 3-C5 gives `media_root_unavailable` a narrow local
diagnostic and initialization workflow:

- The authenticated GET page shows only logical `/media/`, the safe root
  status, parent/root kind, size, device, inode, mtime, ctime, current local
  item-cover and creator-avatar reference counts, and handling consequences.
  It never displays an absolute host path, UID, mount detail, or raw exception.
- GET is entirely write-free. It does not create directories, repair
  references, touch files, or modify SQLite.
- Only a genuinely missing root with an existing safely verified parent shows
  the initialization form. Symlink, non-directory, unreadable, scan-failed,
  ready, unsafe configuration, and missing-parent states provide explanation
  only.
- Confirmed POST uses the existing standard/strict danger policy. Starting at
  the working-directory FD, it opens each configured parent with
  `O_DIRECTORY|O_NOFOLLOW`, rechecks complete parent identities and current
  path mappings, and confirms the final target remains absent.
- The operation atomically creates only the configured final directory through
  `mkdir(dir_fd=...)`, then fsyncs the new empty directory and its parent. It
  never recursively creates parents, overwrites an object, chmods/chowns,
  creates/restores media, or changes a database reference.
- Parent replacement, parent symlink, target occupation, target symlink race,
  forged identity, and mkdir failure are rejected. A durability failure after
  mkdir accurately reports that the directory exists with an fsync warning.
- After success, the root-level Data Health issue disappears. Any missing cover
  or avatar remains a C1 per-reference issue because an empty directory cannot
  restore old media.

C5 does not change application version 1.0.6, Schema 2, migrations,
dependencies, Docker/CI, backup/import formats, tags, Releases, or N100
deployment. The previously documented C4 explicit regression baseline is
corrected from 281 to 280 tests.

C5 focused acceptance passes 16 tests, including a parent replacement injected
during `mkdir`. The explicit C1-C4, upload, scan, Data Health, recovery,
backup, validator, and import regression passes 240 tests; the full suite
passes 573 tests; and `pip check` reports no broken requirements. The
production image builds, Compose reaches healthy state, and `/login` returns
HTTP 200. A separate non-root, read-only acceptance container initialized the
missing `/app/data/media` inside a named volume; after container recreation the
same empty directory remained, the diagnostic returned root-available HTTP
400, and no second initialization form was exposed. All temporary containers,
networks, volumes, cookies, and response files were removed.

Feature commit `9a3a546` is pushed to `main`. GitHub Actions run
[`29343264820`](https://github.com/choneer/nsfwtrack/actions/runs/29343264820)
completed successfully for both `test` and `Docker production smoke`.

## Features in v1.0.5

`v1.0.5` publishes the complete local-only Phase 3-A line while preserving the
fixed non-root Docker runtime and explicit Schema 2 migration boundary:

- A1 stores user-provided source links and imports local text/bookmark files
  without requesting any URL.
- A2 adds the safe local media library and atomic, rollback-safe image uploads.
- A3 adds explainable, manually confirmed cover/avatar filename matching.
- A4 creates items from explicitly confirmed unmatched local images.
- A5 adds local media search, filtering, sorting, and independent pagination.
- A6 adds report-only media integrity checks to `/data-health`.
- Source import now rejects ambiguous case-folded existing titles, and media
  upload publication now uses same-directory temporary files, flush/fsync,
  no-overwrite atomic publication, race revalidation, and batch rollback.

The release preparation changed only application version metadata, its
regression assertion, and release documentation. Local release acceptance
passed all 433 tests, `pip check`, and an
isolated two-lifecycle Docker smoke with version 1.0.5 and Schema 2. GitHub
Actions test and Docker production smoke also passed.

- Annotated tag object: `6a4def572e100198a446ad56353400138c573f66`
- Peeled release commit: `3c4fee62891ff2826f0b8bc97b33bf3a4d08aa73`
- Release: [NSFWTrack v1.0.5](https://github.com/choneer/nsfwtrack/releases/tag/v1.0.5)

### Phase 3-B2 Duplicate Media Group View (Released in v1.0.6)

The authenticated `/media-library/duplicates` page provides one stable,
read-only row per duplicate SHA-256 group. It uses the same shared group builder
as B1, so damaged files, malformed or empty hashes, single-path content, and
repeated records for one path remain excluded everywhere.

- Every group shows its complete SHA-256, member count, per-file byte size,
  total bytes, and potentially reclaimable bytes. Members are ordered by their
  normalized media paths.
- Every member shows its local path, available status, item-cover references,
  and creator-avatar references. Reference queries are limited to groups on the
  current page and remain deterministically ordered.
- `duplicate_q` performs bounded NFKC/case-insensitive filename and path
  matching plus complete SHA-256 or prefix matching.
- `duplicate_sort` supports member count, reclaimable space, and SHA-256 in
  both directions with SHA tie breaking. Invalid search, sort, and page values
  safely fall back, and `duplicate_page` contains at most 20 groups.
- Each group links to `/media-library` with its complete SHA-256 and
  `media_status=duplicate`, preserving an exact B1 file-level view.
- B2 browsing remains read-only. Its GET does not change the database,
  cover/avatar references, media paths or bytes, or A3/A4 candidates; B3 uses
  separate preview and confirmed execution routes.

Phase 3-B2 adds no table, Schema 2 change, migration, dependency, version,
Docker change, tag, Release, external request, AI/image recognition, automatic
keep recommendation, reference migration, or physical media operation. The
full local suite contains 441 passing tests and `pip check` reports no broken
requirements.

### Phase 3-B1 Duplicate Media Location (Released in v1.0.6)

The authenticated `/media-library` now turns the duplicate-content warnings
introduced by A6 into a stable, read-only browsing workflow. It groups only
validated files at different paths whose complete SHA-256 digests are equal.

- The media summary reports duplicate group count, involved file count, and
  the byte size potentially reclaimed by retaining one file from each group.
- `media_status=duplicate` shows only members of valid duplicate groups.
  Damaged files, empty or malformed digests, and hashes with only one path are
  never marked as duplicates.
- `media_q` keeps NFKC-normalized, case-insensitive filename and path matching
  and additionally accepts a complete SHA-256 digest or any case-insensitive
  prefix of it.
- Every duplicate card shows its stable group size and all other media paths in
  the same group. Existing filename/size sorting and 20-row pagination remain
  deterministic.
- `media_page`, `match_page`, `create_page`, search, status, and sort state are
  retained across all three pagers and existing media-library forms.
- The complete original scan still feeds the unchanged A3 cover/avatar matching
  and A4 item-candidate logic. Browsing performs no database, reference, or
  media-file write.

Phase 3-B1 adds no table, Schema 2 change, migration, dependency, version
change, Docker change, tag, Release, external request, AI/image recognition, or
physical media operation. The full local suite contains 435 passing tests and
`pip check` reports no broken requirements.

### Phase 3-A6 Local Media Integrity Audit

The authenticated `/data-health` report now includes a read-only Media
Integrity category for app-owned item-cover and creator-avatar files. It audits
the existing database references and local `data/media` tree without changing
either one.

- Referenced `/media/...` paths report invalid values, attempts to escape the
  media root, symbolic-link traversal, missing files, and damaged or unsafe
  images as problems. External URLs are classified as invalid local references
  and are never requested.
- A missing media root is reported when a valid reference depends on it. A
  symlinked, non-directory, unreadable, or otherwise unscannable root is also
  reported without failing the page. An uninitialized missing root with no
  local reference remains healthy.
- Stale `.upload-*.tmp` files and different paths with identical SHA-256 image
  content are warnings. The report also summarizes symbolic links and
  unsupported files skipped by the safe local scan.
- Valid unreferenced images are normal library content and are not issues. The
  existing global 200-detail limit still applies while category and issue totals
  retain complete counts.
- Media findings are report-only. They add no fix option, and forged media fix
  submissions are rejected without clearing a reference or changing a file.

Phase 3-A6 GET reporting performs no database or media write and adds no table,
Schema change, migration, dependency, external request, media operation,
version change, Release, or deployment. The A3 matching, A4 item-candidate, and
A5 media-query services remain unchanged.
The full local suite contains 433 passing tests after this phase.

### Phase 3-A5 Media Library Search and Pagination

The media-file card list under `/media-library` now has an independent,
read-only query layer for larger local libraries. The complete scan still feeds
the unchanged A3 matching and A4 item-candidate flows; only the browsed media
cards are searched, filtered, sorted, and paged.

- `media_q` performs local NFKC-normalized, case-insensitive substring matching
  against both the relative filename/path and the `/media/...` path. Searches
  longer than 200 characters safely fall back to an empty search.
- `media_status` supports all, available, damaged/unavailable, used, and unused.
  Used status is derived from current item-cover and creator-avatar references;
  no media or association is changed while filtering.
- `media_sort` supports filename ascending/descending and byte size
  ascending/descending, with deterministic filename/path tie breaking.
- `media_page` always displays at most 20 cards and safely falls back or clamps
  invalid, negative, non-numeric, empty, and out-of-range values.
- Media pagination preserves the canonical search/filter/sort state plus the
  current `match_page` and `create_page`. A3 and A4 pagination preserve each
  other, `media_page`, and all media filters. Upload, manual assignment, and
  candidate-confirmation redirects retain the same canonical state.
- Empty scans and empty filtered results have distinct bilingual states. Invalid
  status or sort values fall back to all media and filename ascending without a
  500 response or database write.

Phase 3-A5 performs no POST or mutation of its own and adds no table, Schema
change, migration, dependency, external request, AI/image recognition, media
file operation, version change, Release, or deployment.
The full local suite contains 424 passing tests after this phase.

### Phase 3-A4 Create Items from Unmatched Media

The local media library now offers a second read-only candidate flow for valid,
unused images that have no existing A3 item-cover or creator-avatar match.
Nothing is created until an authenticated manual confirmation is submitted.

- Suggested titles come from the filename without its image extension. The
  cover convention is removed from the title, while avatar-convention files are
  excluded from item creation entirely.
- Suggested titles remain editable until confirmation. The preview marks empty
  or oversized defaults, exact existing titles, normalized existing titles, and
  normalized conflicts among default candidate titles so they can be corrected.
- Single and current-page bulk POSTs regenerate the complete candidate set,
  enforce the current 20-row page, validate every local file again, and use only
  the submitted final titles. Forged, stale, occupied, missing, invalid, or
  cross-page candidates are rejected.
- Final titles must contain 1–255 characters and must not exactly or normally
  collide with an existing item or another title selected in the same batch.
  Any validation, file, insert, flush, or commit failure rolls back the entire
  batch, leaving no partially created items.
- A successful confirmation creates each item and assigns the candidate's
  existing local path as `cover_path`. It does not create, download, inspect,
  move, rename, overwrite, or delete any media file.

Standard mode requires browser and server confirmation; strict mode also
requires exact `CONFIRM`. Phase 3-A4 adds no table, Schema change, migration,
dependency, external request, AI/image recognition, version change, Release,
or deployment.
The full local suite contains 416 passing tests after this phase.

### Phase 3-A3 Local Media Candidate Matching

`/media-library` now generates explainable item-cover and creator-avatar
candidates from validated, unused local media filenames. Candidate generation
is read-only: opening or paging the screen never changes an association.

- Matching first compares NFKC-normalized, case-insensitive names exactly, then
  compares normalized names containing only letters and numbers. A final
  `.cover`, `-cover`, `_cover`, or space-separated `cover` suffix limits the
  target to items; the equivalent `avatar` suffix limits it to creators.
- Every candidate displays its target type, exact or normalized matching reason,
  and high or medium confidence. A media file matching multiple targets, or a
  target matching multiple files, is marked as an ambiguous conflict and cannot
  be selected or applied.
- Only available media with no current reference, items without covers, and
  creators without avatars are considered. Single and current-page bulk POSTs
  regenerate the candidate set before writing and reject stale, conflicting,
  cross-page, unavailable, or newly occupied targets.
- Standard mode requires browser and server confirmation. Strict mode also
  requires the exact text `CONFIRM`. A valid bulk operation assigns only the
  manually selected candidates from its current 20-row page in one transaction.
- Matching only updates existing `cover_path` or `avatar_path` fields. It never
  creates, downloads, recognizes, renames, moves, overwrites, or deletes a media
  file and never overwrites an existing cover or avatar association.

Phase 3-A3 adds no table, Schema change, migration, dependency, external network
request, AI, image-recognition, recommendation, version change, or deployment.
The full local suite contains 407 passing tests after this phase.

### Phase 3-A2 Local Media Library

`/media-library` scans app-owned images under `data/media`, shows whether each
image is used by an item cover or creator avatar, and accepts one or multiple
local uploads. Each batch is limited to 20 files and each file to 10 MB.

- AVIF, GIF, JPEG, PNG, and WebP are accepted only when extension, declared
  MIME type, and file structure agree. SVG, HTML, disguised, truncated, and
  unsupported files are rejected.
- Uploaded bytes are named and deduplicated by SHA-256 under
  `data/media/library`; repeated content is not saved twice. Each new file is
  fully written and fsynced through a random same-directory temporary file,
  then atomically published. A failed batch removes all of its temporary and
  newly published files.
- Directory scanning never follows symbolic links. Serving and assignment also
  reject symlinked, missing, oversized, invalid, or escaping paths.
- A valid library image can set or replace an item cover or creator avatar.
  Clearing either association uses a confirmed authenticated POST and leaves
  the media file intact; strict mode also requires `CONFIRM`.
- Missing or damaged assigned files render as the existing safe empty state and
  return 404 from `/media/...` instead of causing a page error.

The feature uses the existing `cover_path` and `avatar_path` columns and the
existing `./data:/app/data` mount. It adds no table, Schema change, dependency,
external request, image recognition, recommendation, or AI capability.
JSON/CSV backups preserve media path references but do not embed image bytes;
back up the stopped `data` directory to preserve both SQLite and media files.

### Phase 3-A1 Source Links and Local Bookmark Import

Phase 3-A1 stores user-provided source URLs without requesting them. One item
can have multiple sources, and each source stores the original URL, a globally
unique normalized URL, an optional title, and its creation time.

- Item detail pages list sources and support adding one URL or deleting one
  source after explicit confirmation. Deleting a source never deletes its item.
- `/sources/import` accepts pasted text with one URL per line,
  `title<TAB>URL`, or a user-uploaded local browser bookmarks HTML file.
- Every bulk operation is read-only until its preview reports new, duplicate,
  invalid, and conflicting rows. Confirmed writes revalidate the same data and
  commit all new items and sources in one transaction; failures roll back the
  batch.
- HTTP/HTTPS URLs are normalized by scheme, IDNA host, default port, percent
  escapes, root path, and fragment removal. URLs containing credentials,
  control/space characters, unsupported schemes, or no host are rejected.
- When no title is supplied, a readable host/path title is created locally.
  No title, metadata, image, or webpage is fetched from the URL.
- JSON backups include the optional `item_sources` table. CSV item export and
  CSV/JSON item import include a `sources` field; old backups and imports that
  omit sources remain compatible.

Schema 2 adds only `item_sources`. Existing Schema 1 databases do not migrate
at startup: open `/schema-upgrade`, review the read-only dry-run, confirm a
fresh backup, and explicitly apply `create_item_sources`. Existing items and
all prior tables remain unchanged.

The network boundary remains strict: NSFWTrack does not request external
webpages, fetch remote images, crawl, use site adapters, synchronize sources,
recommend content, or run AI analysis.

## Features in v1.0.4

`v1.0.4` publishes the Phase 2-L8 fixed non-root Docker runtime identity and
data-ownership migration. It adds no product feature, dependency, database
change, schema migration, or security-configuration relaxation.

- The production image creates the `nsfwtrack` user with fixed UID/GID
  `10001:10001`. Dockerfile `USER` makes both the application and image
  `HEALTHCHECK` run as that non-root identity.
- The v1.0.3 read-only root filesystem, all-capability drop,
  `no-new-privileges`, `/tmp` tmpfs, and `/app/data` writable mount remain in
  force. CI verifies the configured and actual identity plus these boundaries.
- Before upgrading v1.0.3 or any earlier deployment, stop the service, complete
  a verified backup, then migrate `data` ownership to `10001:10001` while
  keeping mode `0700`. The exact commands are in the upgrade checklist below.
- SQLite creation, Schema 1, healthy HTTP/security headers, and persistence
  across container removal and recreation are verified in CI.

## Features in v1.0.3

`v1.0.3` publishes the Phase 2-L7 Docker runtime security baseline and the
matching deployment-permission guidance. It adds no product feature,
dependency, database change, schema migration, or container-user change.

- Production and CI Compose run with a read-only root filesystem, drop all
  Linux capabilities with `cap_drop: ALL`, and enable `no-new-privileges`.
- `/tmp` is a bounded tmpfs while `/app/data` remains the only persistent
  writable application mount; CI verifies both writable and read-only paths.
- Rootful Docker deployments must prepare the host data directory ownership
  and permissions before startup. Existing installations should stop the
  service and take a verified backup before changing that ownership.

## Features in v1.0.2

`v1.0.2` publishes Phase 2-L1 through L6 maintenance and CI hardening. It adds
no product feature, database change, schema migration, or external integration.

- TestClient uses the supported `httpx2` path, and direct runtime/development
  dependencies are pinned to the versions verified on Python 3.12.
- CI runs `pip check` and full pytest, applies minimal browser security headers,
  and performs an isolated production-image Docker smoke test.
- The workflow token is limited to read-only repository contents, while stale
  runs for the same workflow/ref are cancelled automatically.
- The production image uses a Python-standard-library `/login` health check;
  Docker smoke waits for `healthy` before the existing HTTP and security-header
  assertions, with failure logs and unconditional cleanup retained.

## Features in v1.0.1

`v1.0.1` publishes the Phase 2-K1 completion audit and Phase 2-K2 use-before
boundary closure. It adds no product feature, dependency, database structure,
schema-version change, production migration, or external request.

### Phase 2-K2 Use-Before Boundary Closure

- `cover_path` and `avatar_path` accept only app-owned `/media/...` raster
  image paths. External URLs, protocol-relative paths, data URLs, traversal,
  encoded or backslash separators, query strings, fragments, and unsupported
  file types are rejected by API, page, and backup-restore boundaries.
- Item templates revalidate stored cover paths before rendering, so legacy
  external values cannot trigger a browser request.
- Every current-page bulk write, state clear, and relationship detach requires
  browser confirmation plus a server `confirm=1` marker. Strict mode also
  requires exact `CONFIRM` before any write.
- Bulk writes and state clearing are guarded modifications that may affect
  multiple records or erase state fields. Single relationship detach is a
  lower-impact guarded modification because both entities remain and can be
  linked again. Both classes honor strict mode; entity deletion and merge keep
  their existing destructive notices and backup guidance.
- Startup rejects the exact password and secret placeholders shipped in
  `.env.example` without echoing their values.
- Focused F4 tests cover complete Chinese / English warnings, backup links,
  `dangerous_only`, `always`, strict confirmation, and the clean-report state.

## Features in v1.0.0

`v1.0.0` publishes Phase 2-I1 through I4: reproducible performance auditing,
bounded query and pagination improvements, unified safe errors and request
logs, and the final security and compatibility audit. It adds no external
content source, dependency, index, database structure, schema-version change,
or production migration.

### Phase 2-I4 Release-Freeze Audit

- Every non-public page and API route is covered by the existing session
  authentication boundary. Public access remains limited to login and local
  language selection.
- Unsafe browser requests with an `Origin` or `Referer` header must match the
  request origin. Headerless local API clients remain compatible, while the
  session cookie keeps `SameSite=Lax` as a second browser-side boundary.
- Login clears pre-authentication session state except the selected language.
  Logout invalidates previously signed authenticated cookies for the running
  application instance, and an application restart also invalidates them.
- Dangerous page operations require a server-validated confirmation marker in
  addition to browser confirmation. Strict mode still requires the exact text
  `CONFIRM`.
- Item detail GET is read-only; its existing local activity count is recorded
  by an authenticated same-origin POST after the page loads.
- Session cookies are `HttpOnly` and `SameSite=Lax`. Deployments that terminate
  HTTPS at the application can set `SESSION_COOKIE_SECURE=true`.
- Local redirect targets reject external, protocol-relative, backslash, and
  control-character forms. Malformed login JSON returns a bounded 400 response.
- CSV / JSON imports have a configurable upload limit and fail before parsing
  or writing when the limit is exceeded.
- Five isolated database compatibility scenarios, rollback paths, bilingual
  behavior, safe errors and logs, and the 100 / 1,000 / 10,000 performance
  matrix were rerun without touching the default data volume.
- `CURRENT_SCHEMA_VERSION` remains `1`, and the production migration registry
  remains empty. No production migration is invented for the release.

### Phase 2-I3 Error Handling And Request Logs

Phase 2-I3 provides one safe error boundary for page and API requests without
changing business operations, transactions, the database schema, or project
dependencies.

- Page requests use one bilingual error template for 400, 403, 404, 405, 409,
  422, and 500 responses and retain the original status code.
- `/api/` requests and explicit JSON clients receive `error`, `message`, and
  `request_id`. The existing `detail` field remains available for compatible
  expected errors and validation details.
- 405 responses preserve `Allow`. FastAPI validation errors retain type,
  location, and message while submitted values are not echoed.
- Every HTTP response includes `X-Request-ID`. A client value is accepted only
  when it is a canonical UUID or 32-character UUID hex value; every other
  value, including credential-shaped strings, is replaced with generated UUID
  hex before the response or log is written.
- Local request logs contain request ID, method, sanitized route path, status,
  duration, and exception type for failures. They do not record query strings,
  request headers, cookies, authorization values, forms, passwords, or upload
  bodies.
- Matched requests log only their application-owned route template. Unmatched
  routes use the fixed value `/[unmatched]` instead of the raw request path.
- Unhandled exceptions return a generic 500 response and request ID. Exception
  values, traceback text, SQL, server paths, environment values, and secrets
  are not returned or written by the application request logger.
- Expected business errors remain normal 4xx responses or existing page flash
  results. Backup, import, merge, health repair, settings, and schema upgrade
  keep their existing transaction and rollback behavior.
- Login protection, POST-only mutations, browser confirmation, server-side
  confirmation, and strict `CONFIRM` checks are unchanged.
- No external logger, telemetry service, monitoring dependency, schema change,
  tag, or GitHub Release is included.

### Phase 2-I2 Query And Pagination Optimization

Phase 2-I2 applies the verified I1 findings without adding indexes, changing
the schema, increasing the schema version, or adding dependencies.

- Item pages load tag, creator, collection, and state relationships only for
  the current result page. Filter metadata no longer recursively loads related
  item graphs.
- Cleanup candidates use scalar metadata fields and relation counts. Duplicate
  and cleanup comparison pairs are paged while compare / merge behavior stays
  manual and unchanged.
- Tags, creators, and collections use 50-row pages.
- Collection detail uses separate 20-row pages for members and available
  items. Available items support local title search, and the previous N+1 is
  removed.
- Data-health keeps exact total and fix counts while rendering at most 200
  issue details.
- Shared page context reads settings once per request. Workbench saved views
  are limited in SQL before rendering.
- Stats uses consolidated aggregates and SQL date buckets while preserving the
  existing dashboard and API structures.
- At 10,000 fixture items, measured queries fell from 258 to 11 for items, 249
  to 4 for cleanup, 165 to 9 for collection detail, and 28 to 11 for stats.

See [PERFORMANCE.md](PERFORMANCE.md) for the complete I1 / I2 comparison and
remaining scan paths that require a separately approved real migration.

### Phase 2-I1 Performance Baseline

Phase 2-I1 adds analysis and test tooling only. It does not change existing
queries, business behavior, database structure, indexes, or dependencies.

- `scripts/profile_queries.py` creates disposable SQLite fixtures with 100,
  1,000, and 10,000 items and removes them after the audit.
- `app/services/performance_audit.py` runs fixed project operations through a
  SQLite `query_only` connection, blocks writes, counts SQL statements, records
  repeated fingerprints and elapsed time, and captures
  `EXPLAIN QUERY PLAN` summaries.
- Coverage includes item list pagination / filters / sorting, workbench, stats,
  metadata pages, collection detail, saved views, activity, duplicates,
  cleanup, data health, backup preview / validation, and import dry-run.
- The baseline confirms item-page and cleanup query amplification, one
  collection-detail N+1, unpaginated metadata / candidate paths, and repeated
  stats scans. These findings are documented but intentionally not fixed in
  I1.
- [PERFORMANCE.md](PERFORMANCE.md) contains the measured matrix, verified
  findings, unaffected paths, I2 priorities, and migration-required index
  suggestions.

Run the complete isolated audit with:

```bash
.venv/bin/python scripts/profile_queries.py \
  --sizes 100 1000 10000 \
  --output /tmp/nsfwtrack-performance-i1.json
```

## Features in v0.9.0

`v0.9.0` adds Phase 2-H1 database version preflight and Phase 2-H2 explicit
migration planning, dry-run, and apply flows on top of `v0.8.0`.

### Phase 2-H2 Explicit Migration Framework

Phase 2-H2 adds a lightweight, code-only SQLite migration framework. The
production migration registry is currently empty and
`CURRENT_SCHEMA_VERSION` remains `1`; this phase does not invent a production
migration or change an existing business table.

- Every code migration declares `from_version`, `to_version`, `name`, a
  read-only preview, an apply function, a source-version pre-check, and a
  target-version post-check.
- Registry construction rejects duplicate, disconnected, skipped, reversed,
  or cyclic paths. Upgrade planning reads the database version before resolving
  the continuous path to the application-owned target version.
- A recorded lower-version database may start in upgrade-required mode without
  first matching the newest structure. Each migration owns its old-structure
  pre-check, and each target structure is checked after apply.
- `GET /schema-upgrade` shows the current state without migrating.
- `POST /schema-upgrade/preview` runs a protected read-only dry-run. SQLite
  `query_only`, a read-only authorizer, and rollback prevent table, business
  data, and version-record writes, including accidental writes in preview code.
- Dry-run lists current / target versions, ordered steps, expected changes,
  warnings, errors, and pre-check status. Later-step checks are marked deferred
  because preview never applies earlier steps; apply runs every check in order.
- `POST /schema-upgrade/apply` rereads the current version and resolves the path
  inside one transaction. Each step, post-check, and `schema_migrations` insert
  commits atomically; any exception or failed post-check rolls back the chain.
- Apply requires login, POST, browser confirmation, existing server-side danger
  confirmation, and explicit acknowledgement of the pre-upgrade JSON backup.
  Strict mode still requires the exact text `CONFIRM` on the server.
- The routes accept no SQL, table name, target version, downgrade, check bypass,
  or arbitrary migration operation from the user.
- Startup never runs the migration registry. Upgrades are always explicit.
- `schema_migrations` remains outside JSON backup and restore.

### Phase 2-H1 Database Version Preflight

Phase 2-H1 adds an internal schema version record and startup compatibility
check. The current application schema version is `1`.

- `schema_migrations` is an internal SQLite table with unique `version`,
  descriptive `name`, and `applied_at` fields.
- A new empty database creates all current tables and registers baseline
  version `1` in the same initialization transaction.
- A legacy database without `schema_migrations` must already contain every
  required current business table and column before baseline registration.
  Missing structure stops initialization and does not create a version record.
- A database at the current version starts normally.
- A lower database version is reported as requiring an upgrade. NSFWTrack does
  not change the recorded version or execute a migration in this phase.
- A database version higher than the application refuses startup and gives a
  safe compatibility and backup message.
- The login-protected `/settings` page shows the application version, database
  version, status, latest registration time, and a JSON backup reminder.
- The status area is read-only. There is no page, URL, form, downgrade action,
  or bypass action that can change a schema version.
- `schema_migrations` is not exported, previewed, validated as restorable data,
  or restored from JSON backups. A backup cannot overwrite the local schema
  version.

Phase 2-H1 does not modify, delete, or rebuild existing business tables or
fields. It does not run a real migration, add Alembic, add a dependency,
automatically upgrade or downgrade data, or restore a backup.

The v0.9.0 application keeps `CURRENT_SCHEMA_VERSION = 1` and an empty
production migration registry. There is no invented `1 -> 2` production
migration. Startup performs compatibility checks only and never runs an
upgrade; any future upgrade must be explicitly triggered after reviewing the
dry-run and creating a fresh JSON backup.

## Features in v0.8.0

`v0.8.0` adds Phase 2-G1 local settings and Phase 2-G6 safer,
consistent dangerous-operation confirmations on top of `v0.7.0`.

Phase 2-G1 adds a login-protected local settings page at `/settings`.

- Settings are stored in the local SQLite `app_settings` table.
- Supported basic keys are `default_language`, `default_page_size`,
  `default_sort`, `default_sort_dir`, and `default_home`.
- Setting keys and values are validated through fixed allowlists. Unknown keys,
  external URLs, script-like arbitrary values, and unsupported values are
  rejected without writing to the database.
- `POST /settings` saves settings, and `POST /settings/reset` restores defaults
  only with explicit confirmation.
- Default page size and default sorting apply to `/items` only when the URL does
  not provide `page_size` or `sort`.
- Explicit URL parameters and saved view query strings keep priority over local
  defaults.
- Default language applies only when the session has no explicit language
  choice from `/set-language`.
- The dashboard workbench shows the configured default-home entry and highlights
  matching local entries such as items, stats, or recent activity.
- JSON backup export, preview, validation, and restore include `app_settings`.
  Older JSON backups without `app_settings` remain compatible.

Phase 2-G6 reuses `app_settings` to unify dangerous-operation preferences.

- `danger_confirmation_mode` accepts only `standard` or `strict`.
- `backup_reminder_mode` accepts only `always` or `dangerous_only`; safety
  notices cannot be disabled.
- `danger_result_detail` accepts only `summary` or `detailed` and changes only
  result presentation.
- Standard mode preserves the existing login, write-method, browser confirm,
  server confirmation, and rollback behavior.
- Strict mode adds an exact server-validated `CONFIRM` text requirement. A
  missing, wrong, invalid, or unreadable setting never disables confirmation;
  invalid confirmation settings safely fall back to standard mode.
- Unified notices show the operation object, consequence, deletion scope,
  recoverability, applicable JSON backup recommendation, and current mode.
- Coverage includes item and current-page bulk deletion, tag / creator /
  collection deletion, item and metadata merge, recent activity clearing,
  backup restore, data health manual fixes, and settings reset.
- JSON backup export, preview, validation, and restore include the three G6
  settings. Older backups without them continue to use safe defaults.
- No setting can add one-click delete / merge / repair, bypass login, change a
  mutation into GET, skip browser or server confirmation, widen an operation's
  data scope, or weaken rollback behavior.

This settings center is local-only. It does not add multi-user preferences,
cloud sync, external accounts, plugins, AI recommendations, external content
sources, new dependencies, or changes to existing database fields.

## Features in v0.7.0

`v0.7.0` adds local Phase 2-F data health and validation capabilities on top of
`v0.6.0`:

- Phase 2-F1 data health check / local data self-check.
- Phase 2-F2 backup file validation, restore dry-run, and import dry-run
  reporting.
- Phase 2-F3 low-risk manual data health fixes.

Phase 2-F3 adds low-risk manual data health fixes on `/data-health`.

- Fixes are limited to orphaned and duplicate `item_tags`, `item_creators`, and
  `item_collections` rows; orphaned `item_activity`; negative
  `view_count` / `edit_count`; and risky or unknown
  `saved_views.query_string` parameters.
- The page only shows a fix button when the matching issue exists in the
  current health report.
- Each fix requires login, `POST`, browser confirmation, and a server-side
  `confirm=1` check.
- The server accepts only whitelisted `fix_type` values and does not accept
  table names, column names, SQL, or `fix_all`.
- Fix failures are rolled back before returning an error flash message.
- Result summaries report deleted, corrected, and skipped row counts.
- These fixes do not delete items, tags, creators, or collections. They only
  remove relation/helper rows or normalize saved views query strings.
- Export a JSON backup from `/backup` before running any manual fix.

Phase 2-F2 adds backup validation, restore dry-run reporting, and import
dry-run reporting.

- The `/backup` page can validate a local JSON backup before restore and show a
  structured report with `error`, `warning`, and `info` levels.
- Backup validation checks schema, supported tables, unknown top-level fields,
  required fields, unknown row fields, duplicate ids, invalid `status` /
  `rating`, invalid `extra` JSON, orphaned relations, duplicate relations,
  saved views parameters, and item activity references.
- Older JSON backups that do not contain newer optional tables such as
  `saved_views` or `item_activity` remain compatible and are treated as empty
  optional tables during validation / preview.
- Restore dry-run reports table counts, relation counts, expected skipped rows,
  and whether the current database already has data that a real restore would
  append / merge with.
- CSV / JSON import previews now include a dry-run report with importable rows,
  skipped rows, row errors, unknown fields, invalid `rating` / `status`,
  abnormal `tags` / `creators` fields, duplicate title candidates, and
  existing-title warnings.
- Dry-run reports do not write to the database, delete business data, restore
  backups, import rows, auto-create tags / creators / collections, modify saved
  views / activity, auto-fix files, auto-merge data, or call external services.
- Before a real restore or import, export a fresh JSON backup from `/backup`.

Phase 2-F1 adds a local data health check page at `/data-health`.

- The page requires login and is linked from the authenticated top navigation
  and the dashboard workbench.
- The report is read-only. It does not modify the database, delete business
  data, repair records, merge records, import data, or call external services.
- The summary shows the overall status, total issue count, warning / problem
  counts, and issue counts grouped by items, relations, duplicate relations,
  saved views, and activity.
- Item checks report empty titles, invalid status / rating values, missing or
  invalid timestamps, updated-before-created timestamps, and invalid `extra`
  JSON.
- Relation checks report orphaned `item_tags`, `item_creators`, and
  `item_collections` rows that point to missing items, tags, creators, or
  collections.
- Duplicate relation checks report repeated item-tag, item-creator, and
  item-collection links.
- Saved views checks report empty names, empty or malformed `query_string`
  values, unknown parameters, blocked `page` / `next` / `redirect` parameters,
  and external URL values.
- Activity checks report `item_activity` rows that point to missing items,
  negative `view_count` / `edit_count` values, and invalid activity timestamps.

When the page reports issues, export a JSON backup from `/backup` before doing
any manual cleanup. The data health flow does not provide automatic repair,
one-click repair, automatic deletion of core entities, automatic merge, AI
judgment, external lookup, URL import, crawler / adapter integration, cloud
sync, or multi-user features.

## Features in v0.6.0

`v0.6.0` adds local Phase 2-E usage efficiency enhancements on top of
`v0.5.0`:

- Phase 2-E1 saved item-list views / common views.
- Phase 2-E2 recent views and recent edits.
- Phase 2-E3 quick action entry points and workbench improvements.

These features stay local-only. They do not add AI recommendations, smart
analysis, automatic classification, external content sources, URL import,
crawlers, adapters, cloud sync, multi-user sharing, third-party analytics, new
dependencies, or changes to existing database fields.

### Phase 2-E3 Quick Actions And Workbench

Phase 2-E3 organizes local navigation entry points on the dashboard and item
list:

- The dashboard now includes a workbench quick action grid for creating an
  item, opening the item list, saved views, recent activity, stats,
  collections, duplicate item detection, metadata cleanup, import, and backup.
- The dashboard shows a small saved views panel so local saved filters can be
  opened from the workbench without saving or updating anything automatically.
- Recent views and recent edits remain visible from the dashboard with links to
  the full recent activity page.
- The item list now has a quick action section for creating items, jumping to
  saved views / save-current-view controls, recent activity, duplicate
  detection, metadata cleanup, import, and backup.
- Quick action entries are navigation links only. They do not delete, merge,
  clear activity, restore backups, or run any dangerous action directly.
- Existing login protection, POST-only mutations, browser confirmation prompts,
  saved views, filters, sorting, pagination, and current-page bulk editing are
  preserved.
- The quick action layout uses existing Jinja2 templates and CSS, remains
  mobile-friendly, and adds no front-end framework or build step.

Phase 2-E3 does not add database tables, change existing database fields, add
dependencies, external content sources, URL import, crawlers, adapters, AI
recommendations, smart analysis, automatic classification, cloud sync,
multi-user sharing, third-party analytics, or activity trend charts.

### Phase 2-E2 Recent Activity

Phase 2-E2 adds local recent activity for item records:

- Item detail visits are recorded as recent views with `last_viewed_at` and
  `view_count`.
- User-driven item edits are recorded as recent edits with `last_edited_at` and
  `edit_count`.
- Recent edit tracking covers basic item edits, state / rating / review
  updates, tag changes, creator changes, collection changes, and current-page
  bulk edits.
- `/activity` shows recent views and recent edits, requires login, and is
  read-only.
- `POST /activity/clear` clears only `item_activity` records after browser
  confirmation. It does not delete items, tags, creators, collections, or saved
  views.
- The dashboard shows recent views and recent edits, the item list links to the
  activity page, and item detail pages show local activity counts and
  timestamps.
- JSON backup export / preview / restore includes `item_activity` while
  remaining compatible with older backups that do not contain this table.

Activity is stored only in the local SQLite `item_activity` table. NSFWTrack
does not record IP addresses, User-Agent values, device fingerprints, external
referrers, or off-site URLs. This feature does not add recommendations, AI
analysis, automatic classification, external content sources, URL import,
crawlers, adapters, cloud sync, third-party analytics, multi-user activity
feeds, new dependencies, or changes to existing database fields.

### Phase 2-E1 Saved Views

Phase 2-E1 adds local saved views for the item list page:

- The item list can save the current keyword, status, tag, creator, collection,
  minimum rating, time range, sort, and page-size settings as a named view.
- Saved views are stored locally in the SQLite `saved_views` table.
- Saved views can be applied with one click, updated to the current filter
  state, or deleted with browser confirmation.
- Create, update, and delete actions require login and POST.
- Applying a saved view is a GET redirect back to `/items` and does not modify
  the database.
- Saved view query strings are filtered through a whitelist, normalized, and
  stored in stable order.
- Unknown parameters, page numbers, session data, cookies, CSRF values, and
  external redirect targets are not stored.
- JSON backup export / preview / restore includes saved views while remaining
  compatible with older backups that do not contain `saved_views`.

This feature stays local-only. It does not add AI recommendations, smart
classification, external content sources, URL import, crawlers, adapters, cloud
sync, multi-user shared views, new dependencies, or changes to existing
database fields.

## Features in v0.5.0

`v0.5.0` adds local Phase 2-D data cleanup and manual merge support on top of
`v0.4.0`:

- Phase 2-D1 duplicate item detection and manual merge.
- Phase 2-D2 tag / creator / collection cleanup and manual merge.

These features stay local-only. They do not add automatic merging, AI judgment,
external content sources, URL import, crawlers, adapters, recommendation
systems, cloud sync, multi-user support, new dependencies, or database schema
changes. Export a JSON backup before merging duplicate items or metadata.

### Phase 2-D1 Duplicate Detection

Phase 2-D1 adds local duplicate candidate detection and manual merge support on
top of `v0.4.0`:

- `/duplicates` lists read-only duplicate candidate groups.
- Exact title matching trims leading and trailing whitespace for detection only.
- Normalized title matching uses Unicode NFKC, trimming, casefolding, and
  whitespace collapsing for detection only.
- Candidate groups show the match type, match key, item count, title, state,
  rating, and tag / creator / collection counts.
- `/duplicates/compare` shows a side-by-side comparison of the primary item and
  duplicate item before merge.
- Manual merge keeps the primary item and deletes the duplicate item only after
  a POST submission and browser confirmation.
- Tags, creators, and collections are transferred to the primary item without
  creating duplicate relations and without deleting tag, creator, or collection
  records.
- Missing primary summary / state / rating / review values can be copied from
  the duplicate; conflicting values keep primary by default unless the user
  explicitly chooses the duplicate value.
- `extra` JSON merges non-conflicting duplicate keys into the primary item and
  keeps primary values for conflicting keys.
- Merge results summarize relation transfers, field handling, `extra` merge
  counts, conflict counts, and duplicate deletion.

Phase 2-D1 is still local-only. It does not add external content sources, URL
import, crawlers, adapters, AI dedupe, image similarity, automatic bulk merge,
recommendation systems, cloud sync, multi-user support, database schema changes,
or new dependencies.

### Phase 2-D2 Metadata Cleanup

Phase 2-D2 adds local duplicate metadata candidate detection and manual merge
support for tags, creators, and collections:

- `/cleanup` lists read-only duplicate metadata candidate groups for tags,
  creators, and collections.
- Exact name matching trims leading and trailing whitespace for detection only.
- Normalized name matching uses Unicode NFKC, trimming, casefolding, and
  whitespace collapsing for detection only.
- Candidate groups show metadata type, match type, match key, object names, and
  related item counts.
- `/cleanup/compare` shows the primary object that will be kept and the
  duplicate object that will be deleted after merge.
- Manual merge keeps the primary tag / creator / collection and deletes the
  duplicate object only after a POST submission and browser confirmation.
- Related item links are transferred to the primary object without creating
  duplicate relations and without deleting any items.
- Collection description handling is conservative: duplicate description is
  copied only when primary is empty, conflicts keep primary by default, and the
  duplicate description overwrites primary only when explicitly selected.
- Merge results summarize the metadata type, kept object, deleted object,
  transferred relations, skipped duplicate relations, description handling, and
  duplicate deletion.

Before merging duplicate metadata, export a JSON backup from the Backup page.
This first version only supports manual confirmed merges. It does not support
automatic batch merging, merge-all actions, AI synonym detection, fuzzy
matching, external information lookup, external content sources, URL import,
crawlers, adapters, recommendation systems, cloud sync, multi-user support,
database schema changes, or new dependencies.

## Features in v0.4.0

`v0.4.0` adds local Phase 2-C collection management and completes collection
data coverage in backup / import flows on top of `v0.3.0`:

- Phase 2-C1 collections / list management.
- Phase 2-C2 backup / import support for collection data.

These features stay local-only. They do not add external content sources, URL
import, crawlers, adapters, recommendation systems, AI assistants, cloud sync,
multi-user support, new dependencies, or front-end build tooling.

### Phase 2-C1 Local Collections

`v0.4.0` includes local collections / list management. Collections are manual
local lists for grouping existing items into long-term watch lists, topic
lists, review queues, or any other personal organization scheme.

- Collections are stored in local SQLite tables `collections` and
  `item_collections`.
- The Collections page supports creating, editing, deleting, listing, and
  opening collection detail pages.
- Collection detail pages show the items in a collection and allow adding or
  removing existing local items.
- Item detail pages show linked collections and allow adding or removing one
  existing collection.
- The item list can filter by collection while preserving existing keyword,
  tag, creator, status, sorting, and pagination query-string state.
- Current-page bulk editing can add selected items to one existing collection
  or remove selected items from one existing collection.
- The stats page includes total collections, items with collections, items
  without collections, and a local collection ranking.
- Deleting a collection deletes only the collection and its item links. It does
  not delete any items.

### Phase 2-C2 Collection Backup And Import

`v0.4.0` also closes the local data loop for collections:

- JSON backups include `collections` and `item_collections` alongside the
  existing items, tags, creators, relations, and state records.
- JSON backup preview reports collection counts, item-collection relation
  counts, collections to create or merge, restorable collection links, skipped
  collection links, and collection-related errors.
- JSON restore merges collections and item-collection links. It does not delete
  existing items, does not overwrite the database, and skips bad collection
  links with a readable result summary.
- Old JSON backups without `collections` or `item_collections` remain
  compatible and restore as backups with no collection data.
- CSV export includes a `collections` field. Multiple collection names are
  separated with semicolons.
- CSV import and JSON import support an optional `collections` field. CSV uses
  semicolon-separated names, while JSON requires an array of strings.
- Import preview and import results include collection creation, collection
  link, skipped collection, and collections field error counts.
- Old CSV / JSON import files without a `collections` field remain compatible.

Collections in import files are still local user-provided data from uploaded
files. Phase 2-C2 does not add URL import, external content sources, crawlers,
adapters, recommendation systems, AI assistants, cloud sync, multi-user
support, new dependencies, or database schema changes.

## Features in v0.3.0

`v0.3.0` adds local Phase 2-B UI and stats enhancements on top of `v0.2.0`:

- Phase 2-B1 mobile / responsive UI polish.
- Phase 2-B2 local SQLite stats dashboard enhancements.

These features do not add external content sources, URL import, crawlers,
adapters, recommendation systems, AI analysis, prediction models, chart
libraries, new dependencies, database schema changes, cloud sync, or multi-user
support.

### Phase 2-B2 Stats Dashboard Enhancements

`v0.3.0` includes local SQLite statistics dashboard enhancements:

- The stats page now has overview cards for total items, tags, creators, items
  with state, items with rating, average rating, and recent 7 / 30 day created
  counts.
- Status and rating distributions use pure HTML / CSS bars, with empty states
  when there is no local data.
- Tag usage and creator link rankings show the top 10 local associations and
  their share of all local links.
- Recent activity shows 7 / 30 day created and updated counts plus a 7-day
  local trend block.
- Data completeness shows neutral counts for items without tags, creators,
  state records, ratings, or summaries.

These stats are generated only from local SQLite data. They do not add external
content sources, URL import, crawlers, adapters, recommendation systems, AI
analysis, prediction models, chart libraries, new dependencies, database schema
changes, cloud sync, or multi-user support.

### Phase 2-B1 Responsive UI Polish

`v0.3.0` also includes responsive UI polish on top of `v0.2.0`:

- The shared layout, cards, grids, forms, buttons, pills, and flash messages are
  tuned for narrow screens without changing backend behavior.
- The top navigation wraps into readable groups on mobile while keeping
  NSFWTrack, language switching, and login / logout access visible.
- The item list keeps advanced filters, current-page bulk editing, item cards,
  and pagination usable on phones and tablets.
- The detail page, import page, item / tag / creator forms, backup page, and
  stats page use mobile-friendly stacking or local table scrolling where needed.
- Long local titles, tags, creator names, and JSON / table content are contained
  with wrapping or section-level scrolling instead of creating whole-page
  horizontal overflow.

This polish does not add business features, database fields, dependencies,
external content sources, URL import, crawlers, adapters, recommendation
systems, AI assistants, cloud sync, or multi-user support.

## Features in v0.2.0

`v0.2.0` adds local Phase 2 enhancements on top of the Phase 1 MVP:

- Phase 2-A1 advanced local filters, sorting, and pagination.
- Phase 2-A2 current-page bulk editing.
- Phase 2-A3 item detail page enhancements.
- Phase 2-A4 CSV / JSON import enhancements.

These features continue to use only the local SQLite database. They do not add
external content sources, URL import, crawlers, adapters, remote image fetching,
recommendations, AI assistants, cloud sync, or multi-user support.

## Phase 2 Local Enhancements

### Phase 2-A1 Advanced List Filters

`v0.2.0` includes local list page improvements for finding and reviewing
existing records:

- Advanced local filters by keyword, status, one tag, one creator, minimum
  rating, and created / updated time range.
- Sorting by created time, updated time, title, or rating.
- Page size selection with `10`, `20`, `50`, or `100` items per page.
- Query-string based filters, sorting, and pagination so refreshes and copied
  links keep the same list state.
- Current filter summary, clear filters action, and clearer empty results.
- Chinese / English UI text for the new list controls.

These enhancements still only query the local SQLite database. They do not add
external content sources, crawlers, adapters, remote image fetching,
recommendations, AI assistants, cloud sync, or multi-user support.

### Phase 2-A2 Bulk Editing

`v0.2.0` also includes local bulk management for items on the current list page:

- Select individual items, select the current page, or clear the current
  selection.
- Bulk update status, add one existing tag, remove one existing tag, and set
  rating.
- Bulk delete selected items with browser confirmation and a visible dangerous
  action warning.
- Return to the previous list URL after bulk actions so filters, sorting, and
  page size are preserved where possible.
- Unified Chinese / English success and error messages showing processed and
  skipped counts.

Bulk editing only affects selected local SQLite records. It does not select
items across pages and does not add external sources, crawlers, adapters,
recommendations, AI assistants, cloud sync, or multi-user support.

### Phase 2-A3 Detail Page Enhancements

`v0.2.0` also improves the local item detail page:

- Detail information is split into basic information, state information, tags,
  creators, and actions.
- The page shows title, description, created / updated time, readable
  `extra JSON`, current state, rating, short review, linked tags, and linked
  creators.
- The detail page can update status, rating, and short review without opening
  the full item edit form.
- The detail page can add or remove one existing tag and attach or detach one
  existing creator.
- Item links from the list page carry a safe `next` value so returning from the
  detail page preserves filters, sorting, page, and page size where possible.
- Chinese / English UI text and flash messages cover the new detail actions.

Detail enhancements only operate on local SQLite records. They do not create
external content sources, crawlers, adapters, remote image fetching, automatic
sync, recommendations, AI assistants, cloud sync, or multi-user support.

### Phase 2-A4 Import Enhancements

`v0.2.0` also improves local CSV / JSON import:

- The import page provides downloadable CSV and JSON templates for the supported
  local import structure.
- The import page explains supported fields, required and optional fields, valid
  internal status values, rating rules, tag / creator handling, and local-only
  boundaries.
- CSV preview now shows a one-time field mapping table so custom source columns
  can map to `title`, `summary`, `status`, `rating`, `note`, `tags`,
  `creators`, `extra`, or be ignored.
- Import preview shows total rows, importable rows, error rows, tags to create,
  creators to create, the first five recognized rows, and readable error rows.
- Confirmed import shows a result summary with imported, skipped, created tag,
  created creator, tag link, creator link, state record, and error counts.
- Chinese / English UI text and tests cover templates, mapping, preview errors,
  partial valid imports, result summaries, and local-only import boundaries.

Import enhancements only accept uploaded local CSV / JSON files and only write
to the local SQLite database after confirmation. They do not add URL import,
external content sources, crawlers, adapters, remote image fetching, automatic
sync, recommendations, AI assistants, cloud sync, or multi-user support.

## Features in v0.1.0

- Single-user login protection with session cookies
- Chinese / English UI switching
- Local item CRUD
- Tag management
- Creator management
- Item state tracking
- Local title / tag / state search
- Simple stats
- CSV / JSON import
- Complete JSON backup export
- Readable CSV export
- JSON backup restore
- Backup preview before restore
- Configurable backup upload size limit
- Docker Compose deployment
- SQLite local persistence under `./data`
- GitHub Actions CI
- Basic test coverage

## Local Boundaries

The stable v1.1.0 application remains local and single-user. Its production
Provider Registry is empty, so it performs no external metadata request.
Page GETs, backup and restore, CSV/JSON import, bookmark import, and URL-list
import remain zero-network paths.

Future GOALs may authorize fixed Provider authentication, Provider-specific
parsing, controlled downloads, local recommendations, optional AI, or visible
default-off background sync. They may never authorize arbitrary URL fetching,
user-defined hosts or base URLs, unrestricted crawling, access-control bypass,
credential theft/leakage, hidden network activity, or unconfirmed bulk writes,
overwrites, and downloads. See `PRODUCT_VISION.md` and `RULE.md` for the full
split between permanent prohibitions and stage-authorized capabilities.

## Local Development

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
export APP_PASSWORD='change-me'
export SECRET_KEY='change-this-secret'
export DATABASE_URL='sqlite:///data/nsfwtrack.db'
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` and log in with `APP_PASSWORD`.

For a runtime-only environment, `pip install -r requirements.txt` is enough.
For development and CI, use `requirements-dev.txt` to add `pytest`; it inherits
the runtime requirements, including `httpx2`, for Starlette TestClient and the
controlled outbound foundation. Direct dependency versions are pinned; this is
not a full transitive lockfile.

## Configuration

Create a local `.env` from `.env.example` for Docker Compose, or export the same
variables before running `uvicorn` locally.

- `APP_PASSWORD`: the single local login password. Use a strong value on any
  LAN.
- `SECRET_KEY`: signs the session cookie. Use a long random value and rotate it
  if it leaks.
- `DATABASE_URL`: defaults to the SQLite database under `data/nsfwtrack.db`.
- `MAX_BACKUP_UPLOAD_MB`: maximum uploaded JSON backup size. The default is `5`.
- `MAX_IMPORT_UPLOAD_MB`: maximum uploaded CSV / JSON import size. The default
  is `5`.
- `SESSION_COOKIE_SECURE`: set to `true` only when the application receives
  HTTPS requests directly. It defaults to `false` for local HTTP and LAN use.

Do not commit `.env`. It is intentionally ignored by git.

The exact placeholder `APP_PASSWORD` and `SECRET_KEY` values from
`.env.example` are startup errors. Replace both before starting the app.

## Local Media

Prepare `./data/media` only after the rootful Docker data-directory ownership
step in the Docker Compose section below. The production image runs as fixed
UID/GID `10001:10001`, and the data mount makes this directory available inside
the container without another volume or dependency.

```bash
sudo install -d -m 0700 -o 10001 -g 10001 data/media
```

For `./data/media/covers/example.webp`, store this value in `cover_path`:

```text
/media/covers/example.webp
```

The accepted extensions are `.avif`, `.gif`, `.jpeg`, `.jpg`, `.png`, and
`.webp`. Media is served only after login. Use `/media-library` to upload,
scan, deduplicate, and associate local images. NSFWTrack never fetches, proxies,
or imports images from URLs; creator avatars follow the same local storage and
authenticated-serving rule as item covers.

## Docker Compose

Before the first rootful Docker start, prepare `./data` for the fixed container
UID/GID `10001:10001`. Existing v1.0.3 installations must use the stopped,
verified-backup migration procedure below before changing ownership.

```bash
cp .env.example .env
sudo install -d -m 0700 -o 10001 -g 10001 data
sudo install -d -m 0700 -o 10001 -g 10001 data/media
docker compose build
docker compose up -d
```

The service listens on port `8000` by default:

```text
http://localhost:8000
```

Stop it with:

```bash
docker compose down
```

Production Compose runs with a read-only container root filesystem, drops all
Linux capabilities, enables `no-new-privileges`, and mounts a 64 MiB tmpfs at
`/tmp`. The existing `./data:/app/data` mount remains writable and persistent
for SQLite and local media; other image paths remain read-only. This hardening
is combined with a fixed `nsfwtrack` UID/GID `10001:10001`; both the application
and image health check run as that non-root identity.

With rootful Docker, UID/GID `10001:10001` must own `./data` and its existing
contents because all capabilities, including `DAC_OVERRIDE`, are dropped. Keep
the data directory at mode `0700`; do not use `chmod 777`, a root startup
script, sudo/gosu in the container entry point, or startup-time automatic
`chown`.

## Install, Upgrade, And Rollback Checklist

Use this single checklist for the current local deployment line.

### First Install

1. Copy `.env.example` to `.env`, replace both shipped credential placeholders
   with a unique strong password and a long random secret, and keep `.env`
   outside version control.
2. Before the first rootful Docker start, create and secure the writable data
   and media directories for container UID/GID `10001:10001`:

   ```bash
   sudo install -d -m 0700 -o 10001 -g 10001 data
   sudo install -d -m 0700 -o 10001 -g 10001 data/media
   ```

3. Only after that preparation, run `docker compose build` and
   `docker compose up -d`.
4. Confirm
   `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/login`
   returns `200`, log in from the intended LAN device, and keep the service off
   the public internet.
5. Export and validate a JSON backup after entering important data; also copy
   `data/nsfwtrack.db` only while the container is stopped.

### Upgrade From v0.9.x Or v1.0.x

The previous stable `v1.0.6` database is Schema 2. Current stable `v1.1.0` uses
Schema 3.
NSFWTrack has no standalone migration CLI: the supported migration interface
is the authenticated `/schema-upgrade` Web flow.

1. Export a fresh JSON business-data backup from `/backup`, run its preview /
   validation, and retain the verified file outside the deployment directory.
   JSON backup does not contain media files, `schema_migrations`, or the
   rebuildable media-index tables. Protect the media directory separately.
2. Stop the service and make a dated byte-for-byte copy of the SQLite database
   before changing code or images:

   ```bash
   docker compose down
   upgrade_backup_dir="../nsfwtrack-upgrade-$(date +%Y%m%d-%H%M%S)"
   install -d -m 0700 "${upgrade_backup_dir}"
   cp -p data/nsfwtrack.db "${upgrade_backup_dir}/nsfwtrack.db"
   test -s "${upgrade_backup_dir}/nsfwtrack.db"
   cmp -s data/nsfwtrack.db "${upgrade_backup_dir}/nsfwtrack.db"
   ```

   Back up `.env` or equivalent deployment configuration separately with
   appropriately restricted permissions. For a customized named-volume
   deployment, use that volume's documented stopped-backup procedure instead
   of assuming the standard `./data` bind mount.
3. If the existing deployment is v1.0.3 or earlier and `./data` is not already
   owned by `10001:10001`, complete the ownership migration below while the
   service remains stopped.
4. Fetch the reviewed target tag or commit, verify its release notes, then run
   `docker compose build` and `docker compose up -d`.
5. Confirm `/login` returns `200`, log in, and inspect the schema status in
   `/settings`.
6. Open `GET /schema-upgrade`, then submit the page's
   `POST /schema-upgrade/preview` action. This is the supported dry-run: SQLite
   `query_only`, a read-only authorizer, and rollback prevent database, DDL, and
   version writes. The first step's precheck runs; later-step prechecks are
   marked deferred because dry-run never applies an earlier step.
7. Review the ordered path and expected changes:

   - Schema 2 (`v1.0.6`) resolves to `2 → 3 create_media_index`.
   - Schema 1 resolves continuously to `1 → 2 create_item_sources`, then
     `2 → 3 create_media_index`.

   Do not continue if preview is blocked, a precheck fails, the path is
   missing, or the database version is newer than the application.
8. After rechecking the stopped SQLite copy and JSON backup, submit the page's
   `POST /schema-upgrade/apply` form with the normal confirmation and the
   explicit pre-upgrade-backup acknowledgement. Strict confirmation mode also
   requires the exact text `CONFIRM`. The route accepts no SQL, table name,
   target version, skipped check, or downgrade parameter.
9. Apply rereads the database version, resolves the code-owned path, runs every
   precheck, migration, postcheck, and version insert inside one transaction
   (`BEGIN IMMEDIATE` on SQLite). Any exception or failed check rolls back the
   complete chain rather than leaving a partial Schema.
10. Confirm `/settings` reports Schema 3. Schema 3 adds only the empty invalid
    `media_index_entries` and `media_index_state` derived-index structures;
    existing business rows remain intact. Open `/media-library/index`, review
    the invalid state, then use its confirmed full rebuild to construct the
    index from the current media filesystem.

A successful JSON business-data restore does not restore media files or index
rows. It marks the existing media index invalid; restore/protect media files
separately and rebuild the index manually afterward.

### Migrate Existing v1.0.3 Data Ownership

Do not change a live data directory. First export and validate a fresh JSON
backup, then stop the service and make a byte-verified stopped copy outside the
deployment directory. Only after `cmp` succeeds should ownership change:

```bash
docker compose down
backup_dir="../nsfwtrack-data-v1.0.3-$(date +%Y%m%d-%H%M%S)"
sudo cp -a data "${backup_dir}"
sudo test -s "${backup_dir}/nsfwtrack.db"
sudo cmp -s data/nsfwtrack.db "${backup_dir}/nsfwtrack.db"
sudo chown -R 10001:10001 data
sudo chmod -R u+rwX,go-rwx data
sudo chmod 0700 data
sudo install -d -m 0700 -o 10001 -g 10001 data/media
docker compose build
docker compose up -d
```

After startup, confirm `/login` returns `200`, complete the explicit continuous
Schema 1 → 2 → 3 preview/apply flow, verify Schema 3 in `/settings`, and retain
the stopped backup until application data has been checked. Do not replace this procedure
with world-writable permissions, a root container, or an entry point that
changes ownership automatically.

### Rollback

1. Run `docker compose down` before replacing code or SQLite data.
2. There is no automatic Schema downgrade. In particular, do not give a
   Schema 3 database to stable `v1.0.6`, whose supported database is Schema 2.
3. To return to `v1.0.6`, restore the matching stopped Schema 2 SQLite copy
   made before upgrade, then return to the reviewed `v1.0.6` tag/image. A JSON
   merge restore is not a schema downgrade and does not replace this database
   rollback copy.
4. Rebuild, start, verify `/login`, confirm Schema 2 in `/settings`, and inspect
   business data and separately protected media before resuming use.
5. Never edit `schema_migrations` by hand, delete index tables as a substitute
   for downgrade, or expect database migration/JSON backup to restore media.

## N100 LAN Deployment

On an N100 mini PC or similar home server, keep the app on the local network and
bind the Compose port mapping to `8000:8000`. After `docker compose up -d`, open
the service from another LAN device with:

```text
http://N100局域网IP:8000
```

Recommended local setup:

- keep `.env` only on the N100 host
- set a strong `APP_PASSWORD`
- set a long random `SECRET_KEY`
- keep `./data` on persistent storage
- back up `./data/nsfwtrack.db` and exported JSON backups regularly

## Data Persistence

Docker Compose mounts the host `./data` directory into the container at
`/app/data`. With the default `DATABASE_URL=sqlite:///data/nsfwtrack.db`, the
SQLite file is stored at:

```text
./data/nsfwtrack.db
```

Keep this directory out of git. For backups, prefer exporting JSON from
`/backup` and also copying the SQLite file while the container is stopped.

## Security Notes

NSFWTrack is a local single-user app. Do not expose it directly to the public
internet. If you put it behind a reverse proxy, frpc, VPN, or any other remote
access layer, confirm `APP_PASSWORD` is strong first and keep the remote access
layer protected as well.

NSFWTrack does not need third-party cookies, tokens, crawlers, or external
content source credentials in this release.

All authenticated browser writes use session authentication, same-origin
checking, and `SameSite=Lax`. Dangerous operations and guarded bulk / clear /
detach writes also require server-validated confirmation; strict mode adds
exact `CONFIRM`. These controls do not make the application suitable for direct
public-internet exposure. When using HTTPS directly, enable
`SESSION_COOKIE_SECURE=true`; with a reverse proxy, verify its scheme and host
forwarding before enabling that setting.

## Import

Open `/import` after logging in.

Available local-only actions:

- Download the CSV template: `GET /api/import/template/csv`
- Download the JSON template: `GET /api/import/template/json`
- Preview a local CSV upload on `/import`
- Preview a local JSON upload on `/import`
- Confirm import only after reviewing the preview

The CSV template uses these headers:

```text
title,summary,status,rating,note,tags,creators,collections,sources,extra
```

The JSON template uses an `items` array with the same field names. Field names
are not translated. `title` is required. `status` must be one of the internal
values `wish`, `watching`, `watched`, `like`, `dislike`, or `ignore`.
`rating` must be `1` to `5`. `tags`, `creators`, and `collections` are created
or linked using the current local import logic. `sources` accepts a JSON array
of `{title, url}` objects in JSON or a JSON-encoded CSV cell; semicolon-separated
URLs are also accepted in CSV.

CSV preview includes a field mapping table. If a source CSV has custom column
names, choose which source column maps to `title`, `summary`, `status`,
`rating`, `note`, `tags`, `creators`, `collections`, `sources`, or `extra`; columns can
also be ignored. The mapping is used only for the current import and is not
saved.

Preview does not write to the database. It shows total rows, importable rows,
error rows, tags / creators / collections that would be created, collection
links that would be created, the first five recognized rows, and error rows
with row number, reason, and brief source content. If some rows are invalid,
confirmation imports only valid rows and reports the skipped rows. If every row
is invalid, confirmation is disabled.

General item import only accepts uploaded local files. The separate source
import saves URL strings supplied by the user but never requests those URLs.
Neither flow uses crawlers, adapters, cloud sync, or remote fetchers.

## Backup And Export

Open `/backup` after logging in.

Available local-only actions:

- Export a complete JSON backup: `GET /api/backup/export/json`
- Export a readable items CSV: `GET /api/backup/export/csv`
- Preview a JSON backup without writing data: `POST /api/backup/preview/json`
- Restore a JSON backup exported by NSFWTrack: upload the file on `/backup`, or
  use `POST /api/backup/restore/json`

JSON backups include `items`, `tags`, `creators`, `collections`, `item_tags`,
`item_creators`, `item_collections`, `user_item_states`, `saved_views`,
`item_activity`, `app_settings`, and optional `item_sources`. Restore uses an append / merge strategy;
it is not an overwrite restore and does not clear the current database.
Collection restore merges by collection name, saved views merge by name,
recent activity rows merge only for existing local items, and supported local
settings and normalized source URLs are validated before restore. Old backups
without `item_sources` remain compatible.

Backup restore only accepts uploaded local JSON files exported by NSFWTrack. It
never restores from a URL, cloud sync, or an external data source. Uploaded JSON
backup files are limited to 5 MB by default.

CSV and JSON import files are also limited to 5 MB by default. Oversized files
are rejected before parsing or database writes.

Configure the upload limit with:

```bash
export MAX_BACKUP_UPLOAD_MB=5
export MAX_IMPORT_UPLOAD_MB=5
```

## Language

The default UI language is Chinese unless changed in local settings.

Use the language switch in the top bar to change between `中文` and `English`.
The preference is saved in the session, so refreshing the page keeps the chosen
language. A session language choice takes priority over the local default
language stored in `/settings`.

Direct routes are also available:

```text
/set-language?lang=zh
/set-language?lang=en
```

## Tests And CI

```bash
pip install -r requirements-dev.txt
python -m pip check
python -m pytest
```

GitHub Actions runs two jobs:

1. `test` — Python 3.12, install `requirements-dev.txt`, `python -m pip check`,
   then `python -m pytest`.
2. `docker-smoke` — build the production image with temporary CI credentials
   and an isolated data directory, wait for the container to become `healthy`,
   then verify `/login` HTTP 200 and baseline security response headers, dump
   container logs on failure, and always clean up containers and temporary files.

The production image health check uses Python's standard library against the
existing `/login` route. After `docker compose up -d`, `docker compose ps`
shows `healthy` when the application is ready; no curl package is required.

Phase 2-L1 introduced `httpx2` for the Starlette TestClient path used by
`fastapi.testclient`; Phase 5-N1 promotes the same pinned 2.5.0 version to
runtime for the controlled outbound foundation. Phase 2-L2 continues to pin
the verified direct runtime and test dependency versions. A complete transitive
lockfile is still not generated.

Phase 2-L3 adds a minimal browser security-header baseline to every HTTP
response: `X-Content-Type-Options: nosniff`,
`Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`,
and a restricted `Permissions-Policy`. HSTS and aggressive CSP are not
enabled, so existing local HTTP, forms, and inline scripts remain intact.
`X-Request-ID` and 405 `Allow` behavior are unchanged.

## Known Limitations

- Only one local user is supported.
- The app is intended for local network / LAN deployment.
- Direct public internet exposure is not recommended.
- Backup restore is append / merge based, not an overwrite restore.
- The controlled adapter foundation is present, but the production registry is
  empty and no external content source, search UI, or network route exists.
  Provider authentication, downloads, synchronization, recommendations, and
  optional AI remain unimplemented and require separate explicit phases.
- Arbitrary URL fetching, unrestricted crawling, access-control bypass,
  credential theft/leakage, hidden network activity, and unconfirmed bulk
  writes or downloads remain permanently prohibited.
