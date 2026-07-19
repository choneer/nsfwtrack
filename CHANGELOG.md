# Changelog / 变更记录

## Unreleased

### Fixed

- Fixed the N4D-B merge-plan gap where a valid non-empty `VideoRating` was rejected
  as an unsupported merge snapshot value. The corrective allowlist is explicit and
  keeps mutable Mapping/list/set/frozenset and arbitrary-object rejection unchanged.
- Added the rating merge state matrix for local/user/provider ownership, same-provider
  updates, priority selection, equal-priority conflicts, equal values, determinism,
  and immutable-input boundaries. All other N4D-B and release boundaries remain unchanged.

### Added

- Added the Phase 5-N4D-B provider-neutral video metadata contract framework:
  frozen/slots DTOs, an async search/detail/asset-list Protocol, strict field and
  provenance validation, deterministic zero-write merge planning, and a tests-only
  static fixture adapter with synthetic JSON fixtures. No real Provider, network,
  Registry entry, Schema, Backup, dependency, Docker, or CI behavior was added.

- Added the Phase 5-N4D-A typed Approval policy closure: immutable fixed
  non-secret headers, exact canonical Header matching, shared-client timeout
  policy, bounded error mapping, and raw-payload retention policy. Approval
  format remains version `1` with deny-safe defaults.
- Added 64 deterministic N4D-A tests covering Header grammar/sensitivity,
  exact-match changes, timeout edge cases, shared constants, error profile,
  production/test raw retention, scope, and empty Production Registry behavior.
- Added seven Phase 5-N4C research documents covering video metadata,
  subscription catalogs and future playback, comic sources, three
  placeholder-only Approval drafts, and the fixed N4D-N7 Provider roadmap.
- Defined Provider-neutral video DTOs and separate search/detail/asset-list
  operations with field provenance, deterministic conflict/merge rules, and
  local user-state protection.
- Defined subscription Candidate/Revision/Diff/Validation models, explicit
  user-triggered refresh and review, future playback DTOs/state machines, and a
  fixed-Python-adapter comic reading model. Every technical study includes
  operation, network, database, permission, authentication, error, and unknown
  matrices.
- Added Phase 5-N4B frozen Provider Approval models and a pure local Validator
  that compares Provider identity, capability/operation sets, exact hosts,
  endpoint request/response policy, auth/cookies, redirects, asset hosts, rate,
  and size limits without constructing or registering a Provider.
- Added a separate activation gate that rejects fixture approvals and runtime
  capabilities not implemented by the shared client. Stable validation errors
  contain only bounded codes, and a bounded secret-field scanner rejects
  password/token/cookie/secret value fields without echoing their contents.
- Added 27 deterministic N4B tests using only in-memory objects and reserved
  `.invalid` hosts. The Production Provider Registry remains empty.
- Added the Phase 5-N4A provider-neutral foundation: immutable five-layer
  `ProviderCapabilities`, typed layer Protocols, `SourceAsset`, five auth modes,
  seven auth states, and stable redacted Provider errors. No credential or
  Secret Vault implementation is included.
- Extended immutable Endpoint operations with typed standard operations,
  GET/POST, code-owned JSON/form business-parameter bodies, auth/cookie
  requirements, response kinds/content types, non-secret fixed headers,
  redirect policy, and exact Asset Host allowlists. Provider endpoints now bind
  the same-key capability manifest and require exact endpoint/capability parity.
- Added a test-only synthetic Reference Provider for search, detail, and asset
  list using static fixtures, reserved `.invalid` hosts, Fake Resolver, Fake
  Clock, MockTransport, and Fake Network Backend. It is absent from the
  Production Provider Registry.
- Added Schema 4 source tracking with nullable `provider_key`, `external_id`,
  `last_checked_at`, and versioned `metadata_hash` fields on `ItemSource`.
  A SQLite partial unique index enforces provider/external-ID uniqueness only
  when both identity values are non-null; legacy URL-only sources remain valid.
- Added the continuous Schema `3 -> 4` migration, completing the production
  `1 -> 2 -> 3 -> 4` chain. Fresh databases create Schema 4 directly, while
  migrated historical source rows preserve all existing values and receive
  null tracking metadata.
- Added `nsfwtrack.backup.v2` export and restore support with explicit source
  identity validation, payload duplicate/contradiction detection, exact local
  reuse, hard-conflict blocking, transaction-internal reclassification, and
  independent post-error database outcome review. Backup v1 remains supported.
- Added the Phase 5-N1 provider-neutral source-adapter foundation: async
  `SourceAdapter`, frozen source DTOs, an immutable code-owned endpoint
  registry, stable outbound errors, recursively immutable JSON results, and a
  shared bounded HTTP client. The production registry is empty and contains no
  real provider, hostname, or endpoint.
- Added connection-bound DNS/IP protection through the public httpx2/httpcore2
  transport APIs. Every request validates the complete A/AAAA set, connects
  once to the selected numeric IP, keeps TLS certificate hostname/SNI/Host on
  the allowlisted hostname, and verifies the TCP and post-TLS peer address.
- Added deterministic fake-resolver, fake-clock, MockTransport, and fake public
  network-backend coverage for registry/input boundaries, DNS classes, mixed
  answers, pinning, TLS/peer mismatch, redirects, timeout, streaming limits,
  content types, JSON, status errors, concurrency, cancellation, cookies,
  proxies, logs, immutable DTOs, canonical URL validation, duplicate JSON keys,
  non-finite numbers, and the empty production registry.

### Changed

- Strengthened `SourceAsset.asset_id` to an ASCII opaque-identifier allowlist.
  URL/URI, absolute or relative path, slash/backslash, dot-segment, whitespace,
  control-character, non-ASCII, leading/trailing-dot, and repeated-dot forms are
  rejected. Existing `external_id` semantics are unchanged.
- Changed the current database schema version from 3 to 4 without changing the
  application version (`1.1.0`). Backup restore now acquires `BEGIN IMMEDIATE`,
  treats source conflicts as whole-restore blockers, and preserves local source
  title/check/hash values on exact reuse.
- Promoted the existing pinned `httpx2==2.5.0` package from development-only to
  runtime requirements without changing its version or adding another direct
  dependency. Development requirements now inherit it from
  `requirements.txt`; httpx2 continues to pin `httpcore2==2.5.0`.

### Security

- N4D-A rejects forbidden and credential-like fixed Header names and
  Bearer/Basic/Token/ApiKey values. Fixed headers cannot inject authentication;
  production timeout is exactly shared `3.0` connect / `10.0` total seconds,
  error mapping is only `shared_outbound_v1`, and production raw payload
  retention is only `discard`. No runtime network or payload persistence changed.
- N4D-A verification passed 64 focused tests, 211 combined
  N4A/N4B/N4D-A/Adapter/Outbound tests, all 1029 pytest tests, `pip check`, and
  `git diff --check`. The Production Registry remains empty.
- N4C is documentation-only. Subscription candidate addresses were not
  contacted, no script or remote JavaScript was executed, and no real Provider,
  host, endpoint, credential, authentication, playback, download, or Registry
  entry was added. Ordinary and `premium` catalog groups confer no authority.
- All N4C Approval drafts remain `draft / not approved` and contain placeholders
  only. Missing user subscription JSON and standalone userscript details are
  recorded as blockers rather than inferred.
- N4C local verification passed all 965 pytest tests, `pip check`, and
  `git diff --check` while leaving application `1.1.0`, Schema `4`, Backup v2,
  dependencies, runtime code, Docker/CI, and the Production Registry unchanged.
- Approval and runtime policy remain separate: no Approval API writes a file or
  database, performs DNS/network access, loads code, or creates an
  `EndpointRegistry`. N4B passed 27 focused tests, 120 N4A/Adapter/Outbound
  regressions, all 965 pytest tests, `pip check`, and `git diff --check`.
- `OutboundRequest` still exposes no URL, host, path, method, body, header,
  cookie, token, password, or locator. Typed bodies and fixed headers are
  generated only from Registry-owned definitions; declared auth/cookie,
  non-JSON, and redirect policies that N4A does not implement fail before DNS.
- Fixture payloads that suggest new operations, hosts, endpoints, locators, or
  downloadable state cannot expand immutable capabilities or Registry policy.
  Initial N4A verification passed 17 focused tests, 116 combined N4A/N1 tests,
  46 N2/source regressions, and all 934 pytest tests. The final security audit
  added four pre-DNS operation-policy regressions and passed 21 focused tests,
  all 938 pytest tests, and `pip check` without contacting a real Provider or
  network service.
- Schema 4 startup validates the exact provider-identity partial-index columns,
  uniqueness, and predicate. Invalid or missing current-schema structure fails
  closed. Stable `v1.1.0` refuses Schema 4 as `application_outdated` without
  modifying the database.
- Migration, backup preview, and restore remain zero-network. Restore exceptions
  no longer imply rollback: a separate Session compares the complete affected
  database state and reports committed-after-error, confirmed rollback, or an
  unknown outcome when independent proof is unavailable.
- Phase 5-N2 acceptance passed 33 focused tests, 164 targeted tests, all 917
  pytest tests, `pip check`, stable-version checksum verification, and isolated
  network-disabled Docker fresh/migration/backup lifecycles. Commit `df90473`
  and Actions run `29637868492` completed both `test` and
  `Docker production smoke` successfully. The production registry remains
  empty and existing `data/` was not used.
- The outbound client accepts no URL, host, port, base URL, arbitrary path,
  header, proxy, cookie, or auth input. It uses `trust_env=False`, HTTP/1.1,
  zero redirects/retries, 3-second connect and 10-second total deadlines,
  1-MiB streamed bodies, JSON-only content types, and bounded query/page/
  concurrency values.
- Fixed endpoint paths accept printable ASCII only. Source DTO canonical URLs
  reject credentials, fragments, literal whitespace, and backslashes; JSON
  responses reject duplicate object keys and non-finite numeric values.
- Provider logs contain only sanitized provider/operation/outcome, bounded
  status class, latency bucket, and request ID. Query values, URLs, external
  IDs, response data, headers, DNS addresses, and raw exception text remain
  excluded.
- Phase 5-N1 local verification passed 99 focused tests, 66 related security
  regressions, `pip check`, and an isolated production Docker smoke. Application
  version remains `1.1.0`, Schema remains `3`, and no real provider, UI, model,
  migration, backup v2, tag, Release, N100 deployment, or Hermes work was added.

### Documentation

- Recorded exact reviewed snapshots and licensing boundaries for JavdBviewed
  `e26dfdf97c1a68a8f27035ecf8e982208bdc79e0`, JavSP
  `c4cfe61188234dd24c75b53b42b054327fef3e58`, FnDepot
  `e565623a1797aaf40b6b376720046d9451bc6a0d`, and Venera
  `a0eba914f4c2a84ac1bc925adec2baabe920b9be`. Architecture concepts only were
  retained; no reference implementation code was copied.
- Fixed follow-up sequencing as N4D video metadata, N4E subscription catalog,
  N4F streaming playback, N4G comics, N5 unified search/manual import, N6
  controlled resource saving, and N7 controlled multi-source updates. Every
  real Provider phase still requires a separate complete explicit Approval.
- Updated the Provider contract and approval template with the N4B
  machine-checkable gate while preserving the requirement for a separate,
  complete user approval before any real N4 Provider work.
- Updated the Provider contract and project state for N4A while preserving the
  real-N4 Provider Approval gate. Application version remains `1.1.0`, Schema
  remains `4`, Backup remains `nsfwtrack.backup.v2`, and no real Provider,
  credential, dependency, configuration, UI, database import, download,
  recommendation, synchronization, Docker, or CI behavior was added.
- Added `PROVIDER_CONTRACT.md` as the Phase 5-N3 planning contract. It records
  the current search/detail-only Adapter, fixed GET+JSON outbound boundary,
  Registry gaps, Schema 4 source tracking, empty production Registry, and the
  existing local-media lock, safe-publication, exact-reference, independent-
  review, and index-coordination patterns without claiming a download exists.
- Defined immutable, code-owned Metadata, Auth, Discovery, Asset, and Download
  capability layers; `none`, API-token, OAuth, username/password, and session-
  cookie authentication contracts; a separate `PROVIDER_SECRET_KEY` and local
  versioned AEAD Secret Vault plan; and typed fixed method/body/auth/header/
  cookie/response/redirect extensions that continue to deny arbitrary inputs.
- Defined the provider-neutral `SourceAsset` plan, separate asset-list and
  asset-resolve operations, exact no-wildcard Asset Host allowlists, and strict
  short-lived locator validation that retains DNS/IP pinning, TLS/SNI/Host,
  peer, path/query, expiry, authentication-scope, and redirect controls.
- Defined the `v1.2.0` request-bound controlled-download MVP: explicit single
  or bounded selected-batch confirmation, temporary isolation, streamed byte
  limits, MIME/magic/hash checks, no-overwrite publication, exact relationship
  writes, cancellation, independent commit-error review, and one media-index
  coordination per request. Hidden workers, queues, pause/resume, schedules,
  automatic retry/recovery, recommendation downloads, and unlimited batches
  remain outside scope.
- Added a blank `PROVIDER_APPROVAL_TEMPLATE.md` requiring explicit user approval
  of Provider identity and NSFW-core relevance, legal/attribution basis, every
  metadata/auth/asset host and operation, authentication lifecycle, field and
  asset mappings, locator/download policy, deterministic fixtures and complete
  fault matrix, dependency/Schema/backup implications, and the final N4 scope.
  N3 names or approves no real Provider, host, endpoint, or credential and
  changes no runtime code, test, dependency, configuration, Schema, migration,
  backup, Adapter, Registry, outbound service, Docker, or CI behavior.
- Added `PRODUCT_VISION.md` as the long-term NSFW-first, local-first,
  privacy-first, single-user, self-hosted product baseline. It separates
  metadata, user records, and local content, and defines controlled downloads,
  Provider authentication, Provider-specific fetching, local recommendations,
  default-off visible background sync, and search/preview/write/download
  separation.
- Split permanent prohibitions from default-denied capabilities that a future
  explicit GOAL may authorize. Arbitrary URL fetching, unrestricted crawling,
  access-control bypass, credential theft/leakage or cross-Provider sharing,
  hidden network activity, unconfirmed bulk writes/overwrites/downloads, and
  default upload of local user data remain permanently prohibited.
- Recorded Provider authentication, Provider-specific parsing, cover/preview/
  media downloads, a second Provider, controlled background sync, local
  recommendations, optional AI, download queues, and scheduled checks as
  formal future capabilities that remain disabled until separately authorized.
- Replaced the previous P1 route with P2 product alignment, N3 core-Provider
  contract/auth/content/download planning without Provider selection, N4 the
  first user-approved NSFW core Provider, N5 search/detail/manual import, N6
  explicitly confirmed controlled download, N7 manual checking/update plus
  security and UX, followed by I1, R1, and R2.
- Cancelled TVmaze as the planned first Provider, the MediaTrack rename, and
  the ordinary-film/television-led roadmap. Ordinary all-ages content remains
  only an incidental compatibility of the generic model.
- Preserved the completed N1/N2 implementation and acceptance history, updated
  N2 to its successful Actions state, and kept the production Provider Registry
  empty. P2 changes documentation only: application version remains `1.1.0`,
  Schema remains `4`, backup remains `nsfwtrack.backup.v2`, and no code, test,
  dependency, migration, Adapter, Docker, CI, tag, Release, N100 deployment, or
  Hermes work changed.

## [1.1.0] - 2026-07-17

### Changed

- Prepared the current Unreleased code as a `v1.1.0` release candidate by
  updating the FastAPI application metadata from `1.0.6` to `1.1.0` and its
  existing release-version assertion.
- Kept Schema `3`, migrations, dependencies, backup format, Docker/CI behavior,
  and all application features unchanged. Phase 4-R2 acceptance remains the
  release-candidate evidence baseline.
- At candidate freeze, the latest formal stable version and Release remained
  `v1.0.6`; no `v1.1.0` tag or Release had yet been created, and N100 had not
  been deployed.
- Release-candidate verification passed the existing version assertion, all
  `785` pytest tests, `pip check`, and an isolated production Docker smoke with
  application version `1.1.0`, Schema `3`, `/login` HTTP 200, and unchanged
  runtime-security boundaries; temporary resources were removed.
- Cloud diff review, Actions run `29586484449`, and Hermes independent
  acceptance passed on candidate commit
  `b565ef1ca96b2b42315e1ef322c19f9e8ac227ea` without a corrective change. The
  `v1.1.0` candidate was frozen without a tag or Release before this formal
  release.

### Fixed

- Fixed the authenticated media-directory delete preview HTTP 500 caused by an
  undefined `local_media` module reference, using the existing
  `validate_local_media_directory` validation path.
- Added real route regressions for the delete preview and confirmed POST,
  including the initial `303` response and safe rejection cases.

### Documentation

- Completed Phase 4-R2 release-candidate acceptance on corrective candidate
  `b7c5a634ad8c2b79ced74da9dcf0247d7af06a4b`. The full suite passed `785`
  tests, and Actions run `29577588841` completed both `test` and
  `Docker production smoke` successfully.
- Validated the real Schema 1 → 2 → 3 and stable-v1.0.6 Schema 2 → 3 paths,
  stable JSON backup preview/restore and failure atomicity, post-restore index
  invalidation/rebuild, real HTTP media-directory operations, the outcome/index
  fault matrix, and two persisted Docker lifecycles.
- Corrected the user upgrade and rollback guide for the real code-owned
  Schema 1 → 2 → 3 path, including the authenticated dry-run/apply Web flow,
  Schema 2 → 3 migration, backup/media separation, transactional rollback,
  derived-index rebuild, and the prohibition on using a Schema 3 database
  directly with stable `v1.0.6`.
- The recommended next version remains `v1.1.0`, but this documentation closeout
  changes no application code, tests, runtime behavior, dependency, migration,
  Schema, application version, workflow, tag, Release, or N100 deployment state.

### Added

- Added Phase 4-M5 secure media-directory management: authenticated creation,
  no-overwrite directory rename/move, and deletion of truly empty ordinary
  directories. Signed snapshots bind stable directory identities, mapping
  tokens, subtree manifests, and exact cover/avatar reference sets; M4 locking,
  `BEGIN IMMEDIATE`, independent outcome review, and one `post_directory`
  refresh preserve existing filesystem safety boundaries.
- Final Phase 4-M5 verification passed targeted 60, M5 62, related regression
  146, core 152, and full 777 pytest tests; `pip check` was clean and Actions
  run `29563883918` completed `test` and `Docker production smoke` successfully.
- Hardened Phase 4-M5 after cloud review: bounded manifest traversal and
  streaming identity checks, lock-before-final-snapshot ordering, exact ID-bound
  independent commit review, precise directory outcome classification, stale
  reason preservation, and dedicated partial/rollback/unknown warnings.
- Cloud-review corrective commits were `d00d059701ae767094e5cb07babb58844c2be322`
  (bounded/streaming manifests, final locked snapshot, exact-reference outcome
  review), `d651d1f649972c39ce7a3bd8af44b715b9c705cd` (post-create/delete
  failures, quiet rollback, lock-result unknown handling), and
  `090eb61e10f0974bfed3f8379a7ba50a91f29207` (outcome/index-status messages,
  invalidation-failure accuracy, directory-specific stale reasons).
- Hermes independently accepted final create/rename/move/empty-delete,
  exact Item/Creator migration, single `post_directory` incremental refresh,
  unknown-result behavior, and isolated Docker persistence/security. Existing
  `data/` remained untouched; no tag, Release, or N100 deployment was created.

- Added a fixed application-data-directory media-operation lock shared by all
  in-app media writes, manual incremental scans, and confirmed full rebuilds.
  It uses cross-process `flock`, bounded acquisition, directory-relative secure
  opening, `O_NOFOLLOW`, ownership/mode/link-count checks, and mapping
  revalidation; symlinks, directories, special objects, unsafe permissions,
  hard links, and replaced lock objects fail closed.
- Added unified post-mutation outcomes: `no_filesystem_change`,
  `filesystem_changed_known`, `filesystem_changed_partial_known`, and
  `filesystem_outcome_unknown`. Known final states receive one incremental
  refresh after the business transaction while the same operation lock remains
  held; unknown outcomes invalidate the old index without a guessed refresh.
- Added automatic index synchronization for upload, rename, move, batch,
  hardlink-alias normalization, duplicate/damaged cleanup, recovery,
  cleanup-anchor and upload-residue deletion, and media-root initialization.
  Multi-item batches refresh at most once and pure cover/avatar reference
  changes do not scan.
- Added persisted refresh-source status for manual scans and post-upload,
  post-rename, post-move, post-batch, post-cleanup, post-recovery, and
  post-root-initialization refreshes, with matching Chinese and English scan
  center labels and operation-result messages.
- Added Docker smoke coverage for the private regular lock file, non-root
  ownership, lock reacquisition after container recreation, and a coordinated
  post-write index refresh that remains valid on the persisted data mount.
- Added Schema 3 rebuildable `media_index_entries` and singleton
  `media_index_state` tables. The real 2 → 3 migration has read-only dry-run,
  precheck, postcheck, transactional version recording, and an empty invalid
  initial index; fresh databases start directly at Schema 3.
- Added an authenticated media scan center with read-only status, timestamps,
  duration, valid/damaged/recovered/skipped totals, reused/rehashed/new/changed/
  removed statistics, recent path changes, explicit incremental refresh, and a
  write-free preview plus confirmed full verification/rebuild.
- Added FD-safe incremental media scanning. Exact file mode, size, device,
  inode, mtime, ctime, and stable root/parent directory mapping must all match
  before signed SHA/MIME/validity facts can be reused. New, changed, unsigned,
  damaged, or corrupted cache records are read and hashed through the existing
  `O_NOFOLLOW` descriptor chain.
- Added persisted directory and skipped-entry snapshots so the indexed media
  library preserves directory browsing and scan-skip statistics, including
  empty ordinary directories and recovered-media semantics.
- Added authenticated current-page multiselect controls to the media library
  and directory browser, with a 20-file batch limit and write-free GET previews
  for batch move and same-directory batch rename. The server recomputes the
  complete current page from normalized filter, sort, and pagination state;
  duplicate, outside-page, missing, damaged, reserved, or forged selections
  fail closed.
- Added per-file batch target editing and HMAC-signed snapshots. Batch moves
  accept only existing ordinary directories beneath the media root and allow
  each basename to change while preserving its exact extension. Batch renames
  stay in the source directory and reject duplicate targets, occupied targets,
  name swaps, and cycles without temporary names.
- Added independent per-file batch execution and results. Every item reuses the
  M1 verified-directory-FD, no-overwrite hardlink, exact cover/avatar migration,
  transaction, commit-outcome, and identity-bound source-removal path; one
  failure never rolls back a completed item, and retained-source or unknown
  outcomes remain explicit.
- Added manual hardlink-alias keeper normalization. Users explicitly select one
  keeper from a complete group revalidated by exact device/inode identity. A
  confirmed POST migrates every non-keeper item-cover and creator-avatar
  reference to the keeper before attempting identity-bound deletion of each
  zero-reference alias.

- Added the authenticated Phase 4-M1 media directory browser. It exposes only
  existing ordinary directories beneath the media root, with breadcrumbs,
  direct-child directory summaries, current-directory file/byte/damaged/
  duplicate/unreferenced totals, search, status filtering, stable sorting,
  fixed pagination, and restricted return-state links to media details.
- Added a safe cross-directory move entry for eligible ordinary media. Users
  choose an existing verified target directory and may preserve the filename
  or supply a basename with the exact original extension. The shared A2 path
  change engine performs no-overwrite hard linking, exact migration of every
  item-cover and creator-avatar reference, commit-outcome inspection, and
  identity-bound source removal across separate retained directory-FD chains.
- Added single-reference management from valid media details. A write-free GET
  preview classifies setting an empty field, replacing an existing field, or
  clearing the current field; confirmed POST changes exactly one
  `Item.cover_path` or `Creator.avatar_path` and leaves every other object field,
  relationship, timestamp, and media file unchanged.
- Added the read-only hardlink alias audit. It groups logical media paths by
  `device/inode`, lists exact item-cover and creator-avatar references for every
  path, and labels complete-SHA matches with different identities as independent
  duplicate files rather than hardlink aliases.
- Added the authenticated Phase 4-A2 ordinary-media safe-rename flow from the
  A1 detail page. Its write-free GET preview reports source and target logical
  paths, MIME, complete SHA-256, mode, size, device, inode, mtime, ctime, every
  item-cover / creator-avatar reference, and the exact operation consequences.
- Added a confirmed same-directory basename rename for valid ordinary and
  `recovered-*` media. The POST revalidates the complete source identity,
  absent and unreferenced target, and exact reference-ID snapshot under
  `BEGIN IMMEDIATE`, then creates the target as a no-overwrite hard link
  through the retained verified parent-directory FD.
- Added transactional migration of every source cover/avatar reference to the
  target, database-failure target cleanup by held-FD inode identity, and
  post-commit source unlink only while the source, target, and parent mapping
  still match. A failed source unlink retains both paths and reports the
  outcome without invalidating the committed target references.
- Added the authenticated, read-only Phase 4-A1 ordinary local-media file
  detail page. It reports the logical `/media/` path, basename, extension,
  safely confirmed MIME, size, complete SHA-256 when available, valid/damaged,
  recovered/ordinary, referenced/unreferenced, and duplicate/unique status.
- Added complete item-cover and creator-avatar reference lists with object
  links, plus exact complete-SHA duplicate-group counts, file/total/reclaimable
  bytes, member paths, and a link to the matching duplicate group.
- Added the authenticated Phase 3-B3 manual duplicate-media cleanup flow.
  Duplicate-group rows require an explicit keeper with no default or automatic
  recommendation, followed by a read-only preview of reference migrations,
  redundant paths, and expected reclaimed bytes.
- Added detailed cleanup results for migrated item covers and creator avatars,
  deleted paths, actual released bytes, per-path failures, durability warnings,
  and a fresh-preview retry path for files that remain safely on disk.
- Added the authenticated, read-only Phase 3-B4 media cleanup recovery center.
  It reports exact cleanup-anchor and recovered-file paths, byte sizes, complete
  SHA-256 values when valid, validity, item-cover / creator-avatar references,
  path/SHA search, stable sorting, status filters, and 20-row pagination.
- Added data-health findings for referenced, unreferenced, and damaged cleanup
  anchors, with a direct link to the recovery center and no automatic fix.
- Added the authenticated Phase 3-B5 single-anchor restore preview. It shows
  the complete SHA-256, path, device, inode, size, mtime, ctime, current item
  cover / creator avatar references, and explicit restore consequences without
  writing on GET.
- Added manually confirmed restoration of one valid cleanup anchor to a unique
  no-overwrite `recovered-*` ordinary-media path, including transactional
  migration of every current cover/avatar reference.
- Added the authenticated Phase 3-B6 single-anchor permanent-delete preview for
  valid, unreferenced cleanup anchors. GET shows complete SHA-256, path, MIME,
  size, device, inode, mtime, ctime, and irreversible consequences without
  writing to files or the database.
- Added manually confirmed deletion of exactly one unreferenced cleanup anchor
  with a SQLite `BEGIN IMMEDIATE` reference recheck, final complete-identity
  validation, identity-bound unlink, and containing-directory fsync.
- Added the authenticated Phase 3-C1 single-reference repair preview for Data
  Health item-cover and creator-avatar findings covering missing, damaged,
  symlinked, invalid/escaping paths, and damaged cleanup-anchor references.
- Added explicit clear or manual replacement with existing validated local
  media. Replacement candidates support path/SHA search, stable ordering, and
  fixed 20-row pagination; valid `recovered-*` remains eligible while cleanup
  anchors are excluded.
- Added the authenticated Phase 3-C2 single-upload-residue delete preview for
  Data Health `media_upload_residue` findings. GET shows the exact relative
  path, size, device, inode, mtime, ctime, current cover/avatar references, and
  irreversible consequences without reading temporary-file content or writing
  to the file system or database.
- Added manually confirmed deletion of exactly one regular non-symlink file
  whose basename case-sensitively matches `.upload-*.tmp`, including a locked
  zero-reference recheck, complete-identity revalidation, identity-bound
  unlink, and containing-directory fsync.
- Added deterministic per-entry Phase 3-C3 media-scan skip records for symbolic
  links, unsupported extensions, special files, unreadable directories, and
  entry-inspection errors. Records contain only safe media-root-relative paths,
  stable reason codes, extensions, and lstat metadata when available.
- Added the authenticated, read-only `/media-library/skipped` location page
  with path search, reason filtering, stable path/type sorting, and fixed
  20-row pagination. Data Health scan-skip warnings link directly to matching
  symlink or legacy-unsupported filter results.
- Added a Phase 3-C4 `media_damaged_file` Data Health finding and media-library
  action for each ordinary allowed-extension file that has an original
  SHA-256 but fails local image validation. Valid media, cleanup anchors,
  upload residues, symlinks, and scan skips remain excluded; `recovered-*`
  remains ordinary media.
- Added an authenticated single-file C4 preview showing the safe media path,
  original SHA-256, size, device, inode, mtime, ctime, current cover/avatar
  references, and irreversible consequences without writing on GET.
- Added manually confirmed deletion of exactly one still-damaged,
  zero-reference ordinary-media file after complete identity/SHA revalidation,
  a locked reference recheck, identity-bound unlink, and directory fsync.
- Added the authenticated Phase 3-C5 read-only media-root diagnostic for
  `media_root_unavailable`. It shows only the logical `/media/` path, safe
  status, parent/root size-device-inode-mtime-ctime identities, local cover and
  avatar reference counts, and handling consequences without host paths or raw
  exceptions.
- Added missing-only manual media-root initialization. A confirmed POST creates
  only the configured final directory through its verified parent FD, then
  fsyncs the new directory and parent without creating media or changing a
  reference.

### Fixed

- A successful media mutation whose follow-up scan fails now keeps its business
  result, invalidates the old snapshot with `post_mutation_refresh_failed`,
  warns the user explicitly, and makes read pages fall back to the filesystem.
- Commit-unknown, independent-verification, ambiguous cleanup, and lock-object
  replacement outcomes no longer leave an old index marked valid or attempt a
  speculative path update. Lock timeout is reported before media or business
  database changes begin.
- Media mutation and manual scan commits can no longer overlap across app
  processes. Existing live file identity, directory mapping, reference,
  signed-preview, POST, and confirmation validation remains the write authority.
- Added stable directory-mapping snapshots for multi-item execution. Directory
  timestamp changes caused by an earlier completed item do not stale later
  items, while replaced root/parent mappings still reject the affected item.
- Alias deletion now requires a confirmed committed reference state before any
  unlink. Unknown commit outcomes, independent verification failures, and mixed
  reference states retain every path; per-alias unlink or fsync failures retain
  that path without invalidating keeper references or blocking other aliases.
- Same-SHA files with different device/inode identities remain independent and
  are never included in keeper normalization, reference migration, or deletion.
- Added batch and alias race coverage for target claims, parent replacement,
  reference drift, forged snapshots, post-commit exceptions, independent-query
  failure, mixed references, fsync failure, and unlink failure.

- Generalized the A2 verified-parent hardlink primitive to independent source
  and target directory chains. Source, target, and every parent mapping are
  revalidated before link creation and reference commit; cleanup uses retained
  directory FDs plus exact inode ownership, so a raced target claim or replaced
  directory is never overwritten or removed.
- Added directory-chain preview tokens for cross-directory moves and explicit
  commit-ambiguity inspection for single-reference updates. Unknown outcomes
  retain safe file paths or report the reference as unknown without deleting or
  modifying any media object.
- Fixed the Phase 4-A2 ambiguous-commit failure path. If `db.commit()` raises,
  a new independent database session now reloads every item-cover and
  creator-avatar reference for both source and target before any file cleanup.
- A target hard link is removed after a commit exception only when the
  independent check proves that every expected reference remains on the source
  and the target has zero references. A fully committed target keeps both hard
  links and reports `committed_source_retained`; mixed, unreferenced, failed,
  or otherwise indeterminate checks keep both files and report
  `commit_outcome_unknown` without claiming success.
- Added Phase 4-A2 race rejection for target claims by any object (including a
  same-inode hard link), source/target identity replacement, ordinary-directory
  or symlink parent replacement, changed reference snapshots, and database
  commit failure. Rollback never follows or deletes a mismatched external
  target and removes its own hard-link target even if concurrent link-count
  changes update the shared inode ctime.
- Closed the final safety-anchor create/publish parent replacement gap. A newly
  created anchor, refreshed anchor, and published target must retain the
  original root, logical parent parts, and stable directory type/device/inode
  chain before success can be returned, followed by a fresh mapping check.
- Added exact post-create and post-link race coverage using an ordinary external
  replacement directory populated with same-inode hard links. Both paths fail
  closed while preserving the moved original directory, external entries,
  unrelated media, and database references. Expected hard-link ctime changes
  are not treated as immutable pre/post file identity.
- Closed D1 read-side namespace races in Data Health. Media-root readability
  and unscanned-reference classification now use identity-checked directory
  fds with `O_NOFOLLOW`, while upload-residue findings are derived only from
  C3's already verified skip records instead of an independent path rewalk.
- Authenticated media responses now read and validate bounded image bytes
  inside the verified root/parent/file fd chain and return them directly. They
  no longer validate one path and let `FileResponse` reopen a potentially
  replaced parent path.
- Closed shared B3-B6 validated-media parent replacement races. Validation now
  retains the configured root and every parent directory identity; content
  reads, safety-anchor creation, recovery publication, and identity-bound
  deletion reopen and recheck that fd chain before reading, linking, or
  unlinking.
- Closed the C2 observation/deletion parent-chain gap. Upload residue snapshots
  retain each parent identity and reject a changed current mapping before the
  final unlink, including an external symlink with a same-inode hard link.
- Closed the Phase 3-C3 scan-candidate parent-path replacement race. Media
  candidates now retain traversal-time device, inode, size, mtime, and ctime
  identities for the root, every parent directory, and the final file; reads
  reopen each directory through verified fds with `O_DIRECTORY|O_NOFOLLOW` and
  open the final file through `dir_fd` with `O_NOFOLLOW`.
- A parent replaced by a symlink, a replaced file, or any identity change now
  becomes a safe `entry_error` skip before parsing or hashing. The scanner
  revalidates the complete fd chain and current name mapping after reading, so
  no external replacement content can enter the media list.
- Closed the keeper deletion/replacement race during redundant-file removal.
  A verified same-filesystem safety copy now remains available for the complete
  deletion window, and affected database references point to that valid anchor
  until a final safe media path is committed.
- A missing keeper is restored without overwrite from the anchor. If the
  selected path is occupied or replaced, the external file is preserved and
  references move to a unique verified recovery path instead. Successful,
  failed-deletion, exception, and retry paths clean temporary anchors.

### Changed

- Media library, directory browser, duplicate groups, hardlink aliases, scan
  skips, media matching, and unmatched-item candidates now prefer a complete
  signed index snapshot. Missing, invalid, pre-Schema-3, or corrupted indexes
  fall back to the existing safe full scan without writing during GET.
- Every indexed read page now shows the snapshot time, source, and point-in-time
  staleness boundary. Rename, move, batch operations, alias normalization,
  duplicate/damaged cleanup, recovery, anchors, reference repair, and every
  mutating POST continue to perform immediate filesystem and reference
  revalidation rather than authorizing from the index.
- JSON backup/export remains restricted to business tables. Media index rows
  and state are never exported or restored, and a successful restore marks any
  existing derived index invalid in the same database transaction.
- Media details now link to M1 safe move and single-reference previews for valid
  ordinary media. The media library links to directory browsing and hardlink
  alias audit; all new GET views remain read-only and preserve normalized local
  return state.
- M1 does not create, delete, or rename directories; perform bulk operations;
  choose an alias keeper; automatically merge references; change application
  version 1.0.6 or Schema 2; add a migration, index, dependency, tag, Release,
  deployment, network source, recognition, recommendation, or AI behavior.
- Media-library cards, duplicate-group members, and recovered ordinary-media
  rows now link to the A1 detail page while preserving each source page's
  normalized search, status, sort, and pagination state. Internal cleanup
  anchors and scan-skipped entries never receive an ordinary-detail link.
- A1 consumes the existing identity-checked scan/FD result and performs only
  exact reference queries. It does not reopen the target through `Path.stat`
  or `Path.read_bytes`, and damaged/reference actions remain the existing C4
  preview and C1 single-reference flows rather than new writes.
- Data Health `media_duplicate_content` rows now link by complete SHA-256 to
  the exact B2 duplicate group, preserving the explicit B3 keeper workflow.
- Phase 3-D1 keeps the B3-C5 Unreleased scope closed to new development after
  route, finding, GET/POST, file/reference identity, backup/import, Schema 2,
  settings, i18n, Docker, and integration regression review. The final freeze
  is recorded after the parent-chain repair and its GitHub Actions gates passed;
  the detailed matrix is recorded in `PHASE3_COMPLETION_AUDIT.md`.
- Confirmed cleanup commits every affected cover/avatar reference to the
  verified safety anchor before removing redundant files, then commits them to
  the final safe keeper/recovery path. Each deletion revalidates the path,
  complete SHA-256, device, inode, size, modification time, and change time.
- The duplicate-group view remains write-free while exposing the separate B3
  preview. B1/B2 grouping and A3/A4 candidate algorithms remain unchanged.
- Ordinary media scans now exclude only files whose basename starts exactly
  with `.cleanup-anchor-`. This isolates internal anchors from the media
  library, B1/B2, upload deduplication, and A3/A4 while preserving every
  non-anchor candidate ID.
- Files whose basename starts exactly with `recovered-` remain ordinary media,
  participate in existing duplicate/candidate behavior, and gain a dedicated
  library filter, badge, and recovery-center status.
- Recovery publication now verifies the submitted anchor's complete identity,
  fsyncs the published file and containing directory, rechecks both hard-link
  identities around the database transaction, and removes the original anchor
  only after a final zero-reference check.
- Ordinary interactive item/creator create, edit, and media-assignment paths
  cannot create new references to internal cleanup anchors. Existing internal
  references and backup/B3 compatibility remain intact.
- Only valid anchors classified as unreferenced expose the B6 delete preview.
  The operation never creates `recovered-*`, migrates or clears references,
  touches another file, or performs batch/automatic cleanup; recovery-center
  and Data Health scans naturally stop reporting a successfully deleted path.
- Data Health media scanning remains read-only on GET. C1 repair is isolated
  behind its own single-object preview and confirmed POST. Submission uses a
  conditional update for exactly one `item.cover_path` or
  `creator.avatar_path`; no media file operation is part of the transaction.
- Data Health now exposes a separate C2 action only for exact upload-residue
  findings. Referenced residues show C1 guidance and no delete form; C2 never
  reads, parses, restores, or copies temporary content, changes a reference,
  creates `recovered-*`, or performs automatic or batch cleanup.
- Existing `skipped_symlinks` remains the exact symbolic-link record count and
  `skipped_unsupported` remains the sum of unsupported-extension, special-file,
  unreadable-directory, and entry-error records. Existing media candidates,
  cleanup-anchor isolation, `recovered-*`, upload residues, and invalid-image
  behavior are unchanged.
- Referenced C4 targets expose only direct Phase 3-C1 repair links and no delete
  form. C4 never migrates, clears, or rewrites a database reference, creates a
  recovery file, touches another media path, or performs automatic/batch work.
- C5 offers initialization only for a genuinely `missing` root with a safely
  verified existing parent. Symlink, non-directory, unreadable, scan-failed,
  ready, unsafe-configuration, and missing-parent states remain diagnostic-only
  and never trigger recursive creation, replacement, chmod, or chown.

### Security

- Media cache rows and complete snapshots are HMAC-authenticated with the local
  application secret. Forged facts, altered signatures, impossible row shapes,
  parent mapping substitutions, inode replacements, and incomplete snapshots
  cannot produce cache hits.
- A successful scan builds its full media, directory, skip, and statistics
  snapshot before one transactional table replacement. Scan, mapping, hashing,
  or commit failures preserve the previous complete index; no background
  thread, queue, timer, implicit startup scan, or GET-side index write was
  added.
- Parent-directory rename/symlink races are now fail-closed across Data Health,
  authenticated media serving, shared validated-media create/publish/delete
  operations, and C2 residue deletion. Regression injection with external
  same-name and same-inode hard links proves that external content is not
  returned or parsed and external directory entries are not created,
  overwritten, or unlinked.
- Cleanup requires login, POST, browser confirmation, server confirmation, and
  exact `CONFIRM` text in strict mode. Submission rescans the shared B1/B2 group
  and rejects stale membership, changed hashes, missing or damaged files,
  symbolic links, escaping paths, forged paths, and keeper replacement.
- Database failure removes no file. Deletion failure leaves references safely
  on a verified keeper/recovery path and preserves the failed duplicate for an
  explicit retry; the keeper, unrelated groups, and unselected paths are never
  deleted.
- Keeper loss before the first deletion, midway through deletion, or during the
  final deletion cannot remove the last valid copy or leave a reference on a
  missing/wrong-hash path. Anchor creation, publication, removal, and directory
  durability use exclusive creation, identity/hash validation, and fsync.
- B4 classification is anchored to the case-sensitive basename prefix rather
  than a fuzzy contains check; lookalike filenames and prefix-named directories
  remain ordinary media. Recovery-center and data-health GET requests perform
  no file or database mutation. B5 restoration is isolated behind its own
  preview and confirmed POST; neither view adds move, rename, or automatic
  repair.
- B5 restore execution requires login, POST, browser/server confirmation, and
  exact `CONFIRM` in strict mode. Submission rescans and rejects damaged,
  symlinked, wrong-extension, stale, forged, changed, non-anchor, and
  `recovered-*` targets before publication or reference migration.
- Database failure rolls back every reference and identity-check deletes the
  newly published recovery path. If final anchor deletion fails, references
  remain committed to the valid same-SHA recovery file and the retained anchor
  is reported instead of discarding content or retrying automatically.
- B6 deletion requires login, POST, browser/server confirmation, and exact
  `CONFIRM` in strict mode. Submission rescans and rejects referenced, damaged,
  symlinked, wrong-extension, recovered, missing, stale, forged, or changed
  targets before unlink.
- B6 releases its preview read transaction before acquiring `BEGIN IMMEDIATE`.
  Under that write lock it rechecks both cover and avatar reference counts,
  verifies every file identity field again, and then deletes and fsyncs the
  directory. A racing reference or delete failure leaves the file and database
  unchanged; post-unlink durability warnings report the actual removed state.
- C1 repair requires login, POST, browser/server confirmation, and exact
  `CONFIRM` in strict mode. Under `BEGIN IMMEDIATE`, it revalidates the target
  object snapshot, original reference, current issue, and replacement's full
  SHA-256/device/inode/size/mtime/ctime identity before and after the
  conditional update. Stale, forged, healthy-target, changed-file, and cleanup
  anchor requests are rejected; database failure rolls back the update and no
  file is modified, deleted, moved, or renamed.
- C2 deletion requires login, POST, browser/server confirmation, and exact
  `CONFIRM` in strict mode. It accepts only a Data Health-reported exact
  `.upload-*.tmp` basename and rejects lookalikes, illegal/escaping paths,
  directories, symlinks, missing files, forged snapshots, and stale identity.
- C2 releases the preview transaction before `BEGIN IMMEDIATE`, then rechecks
  both relative and `/media/` cover/avatar reference forms under the write
  lock. A racing reference, lock/query failure, identity change, or unlink
  failure leaves the target and database unchanged. If unlink succeeds but
  directory fsync fails, the response accurately reports the removed file and
  durability warning.
- C3 traversal opens each directory with `O_DIRECTORY` and `O_NOFOLLOW`, uses
  lstat-only entry inspection, and reclassifies a directory replaced by a
  symlink without entering its target. Skipped entries are never opened for
  content, parsed, or hashed; one directory or entry error cannot stop sibling
  scanning.
- Skip paths are deterministically escaped relative display paths. The page
  exposes no absolute host path, raw `OSError`, deletion, movement, recovery,
  association, POST endpoint, automatic action, or external request.
- C4 reads damaged candidates only through the C3 verified directory/file FD
  chain with `O_NOFOLLOW`; parent-path replacement, symlink substitution,
  valid-image replacement, changed SHA, or any size/device/inode/mtime/ctime
  drift is rejected before unlink.
- C4 deletion requires login, POST, browser/server confirmation, and exact
  `CONFIRM` in strict mode. It releases the preview transaction, acquires
  `BEGIN IMMEDIATE`, and rechecks item-cover and creator-avatar references.
  A racing reference, lock/query failure, identity change, or unlink failure
  leaves the file and database unchanged. A post-unlink directory fsync error
  accurately reports that deletion occurred with a durability warning.
- C5 initialization requires login, POST, browser/server confirmation, and
  exact `CONFIRM` in strict mode. It opens the configured parent chain from the
  application working-directory FD with `O_DIRECTORY|O_NOFOLLOW`, revalidates
  complete parent identities and current name mappings, confirms the target is
  still absent, and uses atomic `mkdir(dir_fd=...)`. Parent replacement,
  symlink races, target occupation, forged identity, or mkdir failure is
  rejected without overwriting any object. After creation it fsyncs both the
  new directory and parent, then reopens the configured chain and verifies the
  current parent/root mapping; a post-mkdir replacement is rejected while
  accurately reporting that an empty directory was already created through the
  original safe parent FD.

## [1.0.6] - 2026-07-13

### Added

- Added Phase 3-B1 stable duplicate-media groups based only on complete SHA-256
  digests from validated files at different paths, with library-wide group,
  involved-file, and potentially reclaimable-byte totals.
- Added `media_status=duplicate`, case-insensitive SHA-256 prefix search, and
  per-card duplicate group size plus stable other-media-path details.
- Added the authenticated, read-only Phase 3-B2
  `/media-library/duplicates` group view using the shared B1 SHA-256 boundary.
  Each group reports member count, file size, total and reclaimable bytes, its
  complete digest, stable member paths, and item-cover / creator-avatar references.
- Added bounded filename/path/SHA-256 group search, member/reclaimable/SHA
  ascending and descending stable sorts, 20-group pagination, and a complete
  SHA link back to the exact B1 duplicate filter.

### Changed

- Media filename/path search, deterministic filename/size sorting, 20-row
  pagination, and canonical `media_page` / `match_page` / `create_page` state
  preservation now include the duplicate-content view without changing A3/A4
  candidate inputs or behavior.
- B1 file cards and B2 group rows now consume one shared complete-valid-SHA-256
  group builder, preserving B1 results while preventing boundary drift.

### Security

- Duplicate browsing is authenticated and read-only. Damaged files, empty or
  malformed hashes, and single-path content are excluded; GET performs no
  database, reference, or media-file write and no external request, AI/image
  recognition, or physical media operation.
- The B2 page exposes no media mutation or automatic keep recommendation. It
  performs current-page reference reads only and never deletes, moves, renames,
  overwrites, migrates references, or changes A3/A4 candidates.

## [1.0.5] - 2026-07-13

### Fixed

- Local media uploads now stage each image in a random same-directory temporary
  file, flush and fsync it before atomic no-overwrite publication, revalidate a
  raced final path, and roll back every temporary or newly published file when
  any file in the batch fails.
- Source import now treats multiple existing items with the same case-folded
  title as an explicit conflict in preview and apply instead of silently
  attaching the source to an arbitrary item.

### Added

- Added a read-only Phase 3-A6 Media Integrity category to `/data-health` for
  item-cover and creator-avatar references, reporting invalid and escaping
  paths, symbolic links, missing files, damaged images, and unavailable media
  roots without failing the page.
- Added warning-only reporting for `.upload-*.tmp` residue, duplicate SHA-256
  image content at different paths, and summary counts for symbolic links and
  unsupported files skipped by the local scan. Valid unused media remains a
  normal library state.
- Added Phase 3-A5 local media filename/path search, all/available/damaged/used/
  unused filtering, deterministic filename/size sorting in both directions, and
  independent 20-row `media_page` pagination for the media-file card list.
- Added canonical query-state preservation across `media_page`, `match_page`,
  `create_page`, filter submissions, uploads, manual assignments, and A3/A4
  confirmation redirects, with distinct bilingual empty-scan and no-result states.
- Added Phase 3-A4 read-only new-item candidates for validated, unused local
  images that have no A3 media match. Suggested titles come from filenames with
  the image extension and cover convention removed; avatar-convention files are
  excluded, and titles remain editable until confirmation.
- Added authenticated single and current-page bulk item creation. Confirmed
  writes rescan candidates, revalidate each media file and final title, create
  items with their local `cover_path`, and commit the complete batch together.
- Added Phase 3-A3 explainable local media candidates for empty item covers and
  creator avatars using deterministic exact, normalized, `.cover`, and
  `.avatar` filename rules. Candidate previews are read-only and display their
  target type, matching reason, confidence, and ambiguity conflicts.
- Added authenticated single and current-page bulk candidate confirmation.
  Confirmed writes regenerate candidates, reject stale or cross-page input,
  and apply only selected valid associations in one transaction.
- Added the authenticated Phase 3-A2 `/media-library` for safe local scanning,
  multi-image uploads, reference visibility, and item-cover / creator-avatar
  assignment using the existing media path fields and data mount.
- Added 20-file batch and 10 MiB per-file limits, extension/MIME/structure
  validation, SHA-256 content deduplication, and safe missing/corrupt-image
  fallback without adding a dependency or database object.

- Added Phase 3-A1 `item_sources` with one-to-many item sources, original and
  globally unique normalized HTTP/HTTPS URLs, optional titles, timestamps, and
  item-delete cascading.
- Added authenticated item-detail source listing, single-source add, confirmed
  source delete, and `/sources/import` for one-URL-per-line,
  `title<TAB>URL`, and user-uploaded local browser bookmarks HTML.
- Added read-only source import previews with new, duplicate, invalid,
  conflict, and new-item counts. Confirmed writes revalidate and commit new
  items/sources in one transaction with full rollback on failure.
- Added the real explicit Schema 1 → 2 `create_item_sources` migration with
  read-only preview, source/target checks, backup confirmation, and version
  registration through the existing migration framework.

### Changed

- Media health findings use the existing global 200-detail limit while complete
  issue and category totals remain available. A missing uninitialized media
  root is healthy when no valid local reference depends on it.
- The complete local scan continues to feed unchanged A3/A4 candidate logic;
  Phase 3-A5 search, status, sort, and pagination apply only to rendered media
  cards. Invalid query, status, sort, and page values safely fall back or clamp.
- New-item candidate previews identify invalid defaults, exact or normalized
  existing-title conflicts, and normalized candidate-batch conflicts. Final
  submitted titles are checked again, and any stale, forged, cross-page,
  conflicting, or failed row rejects or rolls back the entire selected batch.
- Media candidate matching considers only validated unused files and targets
  without an existing cover or avatar. One-media/multiple-target and
  one-target/multiple-media ambiguity is disabled rather than guessed.
- Item covers and creator avatars can now be set, replaced, or cleared from the
  local media library. Clearing an association never deletes its media file.

- JSON backup export, validation, preview, merge restore, CSV item export, and
  CSV/JSON item import now include sources. `item_sources` remains optional in
  old backup/import payloads for backward compatibility.
- RULE now explicitly allows saving user-provided URLs and parsing local
  bookmark HTML or plain-text URL lists while retaining the external-network
  prohibition.

### Security

- Phase 3-A6 performs only local database and filesystem reads. It never
  requests an external URL, follows a symbolic link, changes a reference or
  media file, or exposes a media fix option; forged media fix submissions are
  rejected by the existing server-side whitelist.
- Phase 3-A5 GET browsing is read-only and performs no database, association, or
  media-file write. Search is local and bounded, with no path interpretation,
  external request, AI, or image recognition.
- Phase 3-A4 never creates an item from GET or without confirmation. It performs
  no external request, AI/image recognition, or physical media-file operation;
  successful and failed batches leave every media byte and path unchanged.
- Phase 3-A3 never auto-applies a candidate or overwrites an existing cover or
  avatar. Every write is an authenticated confirmed POST; strict mode requires
  exact `CONFIRM`. Matching performs no network request, AI/image recognition,
  or physical media-file creation, move, rename, overwrite, or deletion.
- Media scanning and serving reject symlinks, path escape, unsupported and
  non-regular files. Only validated AVIF, GIF, JPEG, PNG, and WebP uploads are
  accepted; SVG, HTML, disguised files, remote fetching, recognition,
  recommendations, and AI remain out of scope.

- Source URL normalization accepts only credential-free HTTP/HTTPS URLs,
  canonicalizes scheme/IDNA host/default ports/percent escapes/root paths,
  removes fragments, and enforces database uniqueness on the normalized value.
- Source and bookmark import performs no external HTTP request and fetches no
  remote title, metadata, image, or page. Crawlers, site adapters, automatic
  synchronization, recommendations, and AI remain out of scope.

## [1.0.4] - 2026-07-12

### Security

- Phase 2-L8 runs the production application and image health check as the
  fixed non-root `nsfwtrack` UID/GID `10001:10001`. CI prepares the isolated
  bind mount for that identity and verifies container identity, the L7 runtime
  restrictions, writable boundaries, healthy HTTP/security-header behavior,
  and Schema 1 SQLite persistence across container recreation.
- Documented first-install ownership and the stopped, verified-backup migration
  from v1.0.3 root-owned data without world-writable permissions, a root entry
  point, sudo/gosu, or startup-time automatic ownership changes.

## [1.0.3] - 2026-07-12

### Security

- Phase 2-L7 runs production Compose and CI Docker smoke with a read-only root
  filesystem, all Linux capabilities dropped, `no-new-privileges`, and a
  dedicated `/tmp` tmpfs. `/app/data` remains the persistent writable mount;
  CI verifies both writable paths and rejects writes to other image paths.

## [1.0.2] - 2026-07-12

### Added

- Added a production-image `HEALTHCHECK` that uses only Python's standard
  library to request the existing `/login` route; no curl, package, dependency,
  or application endpoint was added.
- Added an independent GitHub Actions Docker production smoke job that builds
  the image with temporary CI credentials and an isolated data directory,
  waits for `/login` HTTP 200, checks baseline security response headers, dumps
  container logs on failure, and always cleans up containers and temporary data.
- Added CI concurrency grouped by workflow and ref with `cancel-in-progress`,
  so an older run for the same branch or pull-request ref is cancelled.
- Added a minimal `SecurityHeadersMiddleware` that applies consistent browser
  hardening headers to successful HTML, redirects, JSON, error, and local
  media responses without enabling HSTS or an aggressive CSP.
- Added focused security-header regression coverage for login, API JSON,
  redirects, 404 / 422 / 405, and authenticated media responses while
  preserving `X-Request-ID` and 405 `Allow`.

### Fixed

- Resolved the Starlette TestClient deprecation warning by installing the
  supported `httpx2` test client dependency instead of filtering warnings.
  Full pytest now runs without the `httpx` / `httpx2` deprecation message.

### Changed

- Clarified post-`v1.0.1` project status in planning docs: stable release is
  `v1.0.1`, code development and WSL acceptance are complete, and N100 /
  target-host deployment has not started and waits for explicit user
  authorization. K3 is no longer listed as an active development task.
- Development / CI test dependencies now declare `httpx2==2.5.0` instead of
  unpinned `httpx`.
- Phase 2-L2 pins direct runtime and development dependency versions that
  were already verified on Python 3.12. This is a direct-dependency baseline
  only; a full transitive lockfile is still not generated.
- CI now runs `pip check` after installing `requirements-dev.txt` and before
  pytest.
- Phase 2-L4 updated the checkout and Python setup actions, and uses fixed
  job-level smoke paths so failure and `always` cleanup target the same Compose
  project and temporary directory without changing test or smoke behavior.
- Phase 2-L6 makes the Docker smoke job wait for the image health status to
  become `healthy` before running the existing `/login` and security-header
  assertions; failure logs and unconditional cleanup remain unchanged.

### Security

- Phase 2-L5 explicitly limits the GitHub Actions token to read-only repository
  contents; the workflow requests no write permission or additional secret.

## [1.0.1] - 2026-07-11

### Added

- Added `COMPLETION_AUDIT.md` with the Phase 2-K1 implementation, documentation,
  test-gap, dead-entry, and F4 safety-prompt audit.
- Added an authenticated app-owned `/media/...` contract backed by
  `data/media`, with one shared validator for item covers, creator avatars,
  page forms, APIs, backup validation, preview, restore, and template rendering.
- Added focused configuration, local-media, confirmation-boundary, and F4
  safety-prompt regression coverage.
- Added a single first-install, v0.9/v1.0 upgrade, backup, and rollback checklist.

### Changed

- Reduced the pre-use roadmap to Phase 2-K2 boundary closure and Phase 2-K3
  target deployment acceptance. Historical completed phases remain archived.
- Corrected current planning language to describe the existing Jinja2 and
  lightweight vanilla JavaScript frontend rather than claiming active HTMX
  behavior.
- All current-page bulk writes, state clearing, and item relationship detach
  actions now require browser and server confirmation. Strict mode requires
  exact `CONFIRM` before these writes.
- Updated the FastAPI application version metadata from `1.0.0` to `1.0.1`.

### Security

- Closed the K1 local media-path, bulk / clear / detach confirmation, and
  shipped placeholder-secret findings without adding external media, upload,
  proxy, URL import, dependencies, schema changes, or migrations.
- Startup now rejects the exact `APP_PASSWORD` and `SECRET_KEY` placeholders
  shipped in `.env.example` without echoing either credential.
- Confirmed the F4 data-health warning flow already provides backup guidance,
  impact and deletion scope, manual single-fix limits, server confirmation,
  strict confirmation, and rollback coverage; focused bilingual and policy
  tests now close the remaining acceptance gap.
- Kept `CURRENT_SCHEMA_VERSION = 1`, the production migration registry empty,
  and all previously published tags unchanged.

## [1.0.0] - 2026-07-11

### Added

- Added Phase 2-I1 reproducible read-only SQLite performance auditing with
  disposable 100 / 1,000 / 10,000 item fixtures, SQL query counting,
  fingerprint repetition counts, elapsed-time observations, and
  `EXPLAIN QUERY PLAN` summaries.
- Added coverage for item list filtering / sorting / pagination, workbench,
  stats, tags, creators, collections, saved views, activity, duplicate items,
  metadata cleanup, data health, backup preview / validation, and JSON import
  dry-run.
- Added `PERFORMANCE.md` with the measured baseline, confirmed N+1 and query
  amplification findings, paths without a confirmed major issue, I2 priority
  order, and a separate list of index suggestions that require a real schema
  migration.
- Added performance-audit tests for read-only enforcement, connection-state
  cleanup, required operation coverage, stable paginated query counts, and the
  confirmed collection-detail N+1.
- Added Phase 2-I2 shared pagination for tags, creators, collections, duplicate
  comparison pairs, cleanup comparison pairs, collection members, and the
  searchable collection available-item selector.
- Added query-regression tests for pagination reachability, collection member
  preservation, bounded collection detail loading, complete data-health counts,
  single-request settings reuse, and I2 query-count ceilings.
- Added Phase 2-I3 unified bilingual HTML error pages and JSON error envelopes
  for 400, 403, 404, 405, 409, 422, and 500 responses.
- Added a request-context middleware that validates or generates a bounded
  `request_id`, returns it as `X-Request-ID`, and emits one sanitized local log
  line with method, route path, status, duration, and exception type when
  applicable.
- Added error-handling tests for HTML / JSON negotiation, `Allow` preservation,
  validation compatibility, request-id validation, safe 500 responses, log
  redaction, expected-error severity, and transaction rollback.
- Added static-review regression coverage proving `ghp_` / `github_pat_`
  request IDs are replaced, unmatched credential-shaped paths are never
  logged, and matched routes continue using route templates.
- Added Phase 2-I4 release-freeze coverage for authentication dependencies,
  same-origin enforcement, session renewal and invalidation, cookie flags,
  local redirects, HTML escaping, malformed login JSON, and bounded imports.
- Added configurable `MAX_IMPORT_UPLOAD_MB` and `SESSION_COOKIE_SECURE`
  deployment settings with safe local defaults.

### Changed

- Replaced recursive model-default relationship loading on item, metadata,
  activity, duplicate, and cleanup list paths with operation-specific
  `selectinload` / `noload` strategies. Current item-page relationships still
  load for rendering, while unrelated reverse graphs no longer load.
- Metadata cleanup candidates now select id, name, and relation count; compare
  and merge continue loading concrete objects only when explicitly opened.
- Collection detail now uses separate 20-row pages for current members and
  searchable available items. The confirmed per-member collection N+1 is
  removed without changing collection membership mutations.
- Metadata pages use 50-row pages. Duplicate and cleanup pages paginate 20
  comparison pairs while keeping every candidate reachable.
- Shared page context reuses one validated settings object, and workbench saved
  views apply `LIMIT 4` in SQL instead of slicing an unbounded result.
- Consolidated stats aggregates and seven-day buckets from 28 to 11 measured
  queries while preserving the existing response structure.
- Combined data-health orphan checks and limited rendered details to 200 while
  preserving complete totals and manual-fix issue counts.
- Updated the 100 / 1,000 / 10,000 performance matrix with I1-to-I2 results.
- API errors now retain the compatible `detail` field and status while also
  returning `error`, `message`, and `request_id`. Validation errors retain
  type, location, and message without echoing submitted input.
- Page errors use one responsive template with the original status code and a
  generic localized message. Redirects and successful responses also receive
  `X-Request-ID`; 405 responses retain `Allow`.
- Replaced Uvicorn's raw request-line access log with the application request
  log so query strings, headers, cookies, form values, and upload content are
  not recorded.
- Tightened accepted external request IDs to canonical UUID or 32-character
  UUID hex values. Every other value is replaced with server-generated UUID
  hex before it can reach a response or log.
- Unmatched routes now use the fixed log path `/[unmatched]`; only matched
  routes may contribute their application-owned route template to logs.
- Login now clears pre-authentication session state except the selected
  language. Authenticated sessions carry an application generation, so logout
  and application restart invalidate previously signed authenticated cookies.
- Dangerous page operations now require a server-validated confirmation marker
  in standard and strict modes. Strict mode continues to require exact
  `CONFIRM`; existing transaction and rollback boundaries are unchanged.
- Local redirect validation now rejects external, protocol-relative,
  backslash, encoded-backslash, and control-character targets. Malformed or
  non-object login JSON returns a safe 400 response.
- CSV and JSON import uploads now stop after the configured byte limit and are
  rejected before parsing or writing.
- Item detail GET is now read-only. Its existing local view activity is
  recorded by a login-protected, same-origin POST after the page loads.
- Corrected the internal FastAPI application metadata from the historical
  `0.1.0` value through the current published `1.0.0` release.
- Reran the isolated 100 / 1,000 / 10,000 matrix. Query counts remained 11 for
  items and filtered items, 9 for collection detail, 7 for duplicates, 4 for
  cleanup, 3 for metadata lists, and 11 for stats, with no N+1 regression.

### Security

- Performance fixtures are created only in disposable SQLite databases and
  removed after each run. The audit connection uses SQLite `query_only`,
  blocks write statements before execution, accepts no arbitrary SQL or table
  name, and does not access the default local data volume.
- Added no index, table, field, dependency, cache, background task, production
  migration, schema-version change, business-logic optimization, tag, or
  GitHub Release.
- Phase 2-I2 adds no index, table, field, dependency, production migration,
  schema-version change, cache, external service, tag, or GitHub Release. All
  performance acceptance data remains isolated and disposable.
- Unhandled exceptions now return only a generic message and request ID. The
  application logs the exception type without traceback text or exception
  values, and expected 4xx responses remain informational rather than system
  failures.
- Phase 2-I3 preserves existing login, POST, browser confirmation, strict
  `CONFIRM`, transaction, and rollback boundaries. It adds no external logging,
  telemetry, dependency, schema change, tag, or GitHub Release.
- Credential-shaped request IDs and raw unmatched paths are no longer trusted
  log fields. Query strings, headers, bodies, exception values, and raw
  unmatched paths remain excluded from the application request log.
- Unsafe requests that provide `Origin` or `Referer` must match the local
  request origin. Headerless local API clients remain compatible, with the
  `HttpOnly`, `SameSite=Lax` session cookie providing the browser boundary;
  HTTPS deployments can explicitly enable the `Secure` cookie flag.
- Phase 2-I4 verified protected route coverage, XSS escaping, upload and error
  boundaries, rollback behavior, and five isolated database compatibility
  scenarios. It adds no product feature, dependency, index, table, field,
  schema-version change, production migration, tag, or GitHub Release.

## v0.9.0 - 2026-07-10

### Added

- Added Phase 2-H2 explicit SQLite migration framework with code-only migration
  steps, strict registry validation, continuous path resolution, source-version
  pre-checks, target-version post-checks, and per-step version records.
- Added login-protected `GET /schema-upgrade`, read-only
  `POST /schema-upgrade/preview`, and explicit
  `POST /schema-upgrade/apply` flows. Apply requires browser confirmation,
  existing server-side dangerous-operation confirmation, explicit backup
  acknowledgement, and exact `CONFIRM` text in strict mode.
- Added protected upgrade dry-run reports with current / target versions,
  ordered migration steps, expected changes, warnings, errors, first-step
  pre-check results, and deferred later-step checks that are rerun during apply.
- Added test-only migration registries covering duplicate, gap, jump, reverse,
  and cyclic path rejection; continuous path resolution; read-only data and DDL
  enforcement; authentication and confirmation; missing paths; downgrades;
  two-step rollback; post-check rollback; and version-record atomicity.
- Added Phase 2-H1 internal database schema version tracking with a local
  `schema_migrations` table containing unique `version`, descriptive `name`,
  and `applied_at` fields. The current application schema baseline is version
  `1`.
- Added startup schema preflight handling for empty databases, compatible
  legacy databases without a version record, matching versions, lower database
  versions, higher database versions, missing required tables / columns, and
  unreadable version records.
- Added a login-protected, read-only database schema status area on `/settings`
  showing the application version, database version, compatibility status,
  latest registration time, and a pre-upgrade JSON backup recommendation.
- Added tests for new and legacy database registration, structure validation,
  initialization rollback safety, matching / lower / higher versions, real
  application lifespan refusal, status-page access and read-only behavior,
  backup isolation, version uniqueness, and Chinese / English copy.

### Changed

- Lower-version startup now reads and reports the recorded database version
  without requiring the old database to match the latest application structure.
  The migration step pre-checks own source-version requirements, and target
  structure is checked only after each step applies.
- Migration apply rereads the database version and resolves the code registry
  inside one transaction. All migration steps, post-checks, and version inserts
  commit together or roll back together.
- Replaced unconditional startup `create_all` with a schema-aware initializer.
  Empty databases create the current schema and baseline in one transaction;
  unversioned legacy databases must already contain every required business
  table and column before the internal baseline is registered.
- Database versions lower than the application are reported as requiring an
  upgrade without changing the recorded version or running migrations.
  Versions higher than the application refuse startup with a safe backup hint.

### Security

- Enforced dry-run read-only behavior with SQLite `query_only`, an authorizer
  that denies data / schema writes, and unconditional rollback. Preview never
  calls apply or writes `schema_migrations`.
- Kept the production migration registry empty and
  `CURRENT_SCHEMA_VERSION = 1`: no test-only production migration, schema bump,
  existing business-table change, dependency, automatic migration, downgrade,
  user SQL, table-name input, or target-version input was added.
- Kept `schema_migrations` outside JSON backup export, preview, validation, and
  restore data. Uploaded backup rows using that table name are ignored and
  cannot replace the local schema version.
- Added no page, URL parameter, form field, downgrade control, bypass control,
  automatic migration, automatic repair, Alembic integration, dependency, or
  change to an existing business table or field.

## v0.8.0 - 2026-07-10

### Added

- Added Phase 2-G6 dangerous-operation preferences by reusing the existing
  `app_settings` table, with allowlisted keys and values:
  `danger_confirmation_mode` (`standard` / `strict`),
  `backup_reminder_mode` (`always` / `dangerous_only`), and
  `danger_result_detail` (`summary` / `detailed`).
- Added a centralized dangerous-operation policy and server-side strict-mode
  validation. Strict mode requires the exact text `CONFIRM` in addition to
  the existing login, HTTP method, browser confirmation, service confirmation,
  and rollback behavior.
- Added unified bilingual safety notices that identify the operation object,
  consequence, deletion scope, recoverability, JSON backup recommendation,
  and current confirmation mode.
- Applied strict confirmation to item and current-page bulk deletion, tag /
  creator / collection deletion, item and metadata merge, recent activity
  clearing, JSON backup restore, data health manual fixes, and settings reset.
- Added summary / detailed result presentation without changing mutation
  logic, data scope, or transaction behavior.
- Added tests for setting allowlists, rejected disabling values, standard and
  strict confirmation, every covered dangerous route, GET safety, invalid and
  unreadable setting fallback, backup reminder behavior, result display
  independence, backup compatibility, and i18n symmetry.
- Added Phase 2-G1 basic local settings center at `/settings`.
- Added a local SQLite `app_settings` table for `default_language`,
  `default_page_size`, `default_sort`, `default_sort_dir`, and `default_home`.
- Added whitelist validation for setting keys and values so unknown settings,
  external URLs, and script-like arbitrary values are rejected without a 500.
- Added login-protected settings save and reset flows:
  `POST /settings` and `POST /settings/reset`, with reset requiring explicit
  `confirm=1`.
- Added setting application for item-list default page size, item-list default
  sort field / direction, default language fallback when no explicit session
  language exists, and dashboard default-home entry highlighting.
- Added JSON backup export / preview / restore compatibility for
  `app_settings`, while keeping older backups without `app_settings`
  compatible as an empty optional table.
- Added backup validation for `app_settings` key/value validity.
- Added Chinese / English settings UI and flash text.
- Added tests for settings login protection, valid save, invalid key/value
  rejection, default page size, default sorting, explicit URL override,
  language switching precedence, reset confirmation, default-home highlighting,
  `app_settings` backup compatibility, database table creation, and i18n
  coverage.

### Changed

- Centralized browser confirmation handling in the base template while keeping
  all dangerous mutations login-protected and write-only. Settings cannot turn
  confirmation, safety notices, or rollback off, and invalid confirmation
  settings safely fall back to `standard`.
- Extended existing JSON backup export, validation, preview, and restore for
  the three G6 settings. Older backups without those rows continue to use safe
  defaults.
- Kept Phase 2-G1 scoped to local single-user preferences only: no multi-user
  settings, cloud sync, external accounts, plugin system, AI recommendation,
  external content source, existing-table field change, or dependency change.

## v0.7.0 - 2026-07-09

### Added

- Added Phase 2-F3 low-risk manual data health fixes on `/data-health`,
  limited to relation tables, `item_activity`, and `saved_views.query_string`.
- Added a whitelisted data health fix service for orphaned `item_tags`,
  `item_creators`, and `item_collections` rows; duplicate relation rows in
  those same tables; orphaned `item_activity`; negative `view_count` /
  `edit_count`; and risky or unknown saved views query parameters.
- Added login-protected `POST /data-health/fix` with server-side confirmation
  checks, one-fix-type-at-a-time dispatch, rollback on failure, and flash
  summaries for deleted, corrected, and skipped rows.
- Added `/data-health` manual fix controls that appear only when the matching
  issue exists, include browser confirmation, link to JSON backup, and state
  that items, tags, creators, and collections are not deleted.
- Added tests for unauthenticated fix rejection, GET no-fix behavior, invalid
  `fix_type`, rejected `fix_all`, missing confirmation, orphan relation
  cleanup, duplicate relation cleanup for legacy schemas, orphan activity
  cleanup, negative activity count correction, saved views query cleanup, core
  entity preservation, rollback, and i18n coverage.
- Added Phase 2-F2 JSON backup file validation with a structured
  `error` / `warning` / `info` report for schema, tables, rows, required
  fields, unknown fields, duplicate ids, relation integrity, duplicate
  relations, saved views, and item activity.
- Added backup restore dry-run reporting on the `/backup` page, including
  table counts, relation counts, expected skipped rows, compatibility notices
  for older backups without newer optional tables, and a pre-write JSON backup
  recommendation.
- Added successful backup preview API reports at `/api/backup/preview/json`
  while preserving existing 400 responses for invalid backup files.
- Added import dry-run report details to CSV / JSON preview pages, covering
  importable rows, skipped rows, row errors, unknown fields, invalid
  `rating` / `status`, abnormal `tags` / `creators` fields, duplicate title
  candidates, existing-title warnings, and read-only backup prompts.
- Added tests for backup validation login protection, invalid / empty JSON,
  old backup compatibility, unknown fields, missing required fields, invalid
  values, orphaned relations, duplicate relations, saved views issues,
  item activity issues, dry-run no-write behavior, dry-run no-delete behavior,
  import dry-run reports, i18n coverage, and existing backup / import
  regressions.
- Added Phase 2-F1 local data health checking with a login-protected
  `/data-health` page.
- Added a read-only data health service that reports item data issues,
  relation integrity issues, duplicate relation issues, saved views parameter
  issues, and item activity issues without modifying SQLite data.
- Added item checks for empty titles, invalid `rating` values, invalid
  `status` values, missing / invalid item timestamps, updated-before-created
  timestamps, and invalid `extra` JSON.
- Added relation checks for orphaned `item_tags`, `item_creators`, and
  `item_collections` rows that point to missing items, tags, creators, or
  collections.
- Added duplicate relation checks for repeated item-tag, item-creator, and
  item-collection links, including legacy-schema test coverage where unique
  constraints may be absent.
- Added saved views checks for empty names, empty or malformed `query_string`
  values, unknown query parameters, blocked `page` / `next` / `redirect`
  parameters, and external URL values.
- Added `item_activity` checks for missing item references, negative
  `view_count` / `edit_count`, and invalid `last_viewed_at` /
  `last_edited_at` values.
- Added data health navigation from the authenticated top nav and dashboard
  workbench.
- Added Chinese / English data health UI text and tests for authentication,
  healthy state rendering, issue reporting, read-only behavior, no business
  data deletion, and language coverage.

### Changed

- Kept Phase 2-F3 scoped to manual low-risk maintenance: no items, tags,
  creators, or collections are deleted; no automatic fix-all, automatic merge,
  AI judgment, external content source, URL import, crawler, cloud sync,
  multi-user system, database schema change, dependency change, tag, or GitHub
  Release is added.
- Kept Phase 2-F2 strictly read-only: validation and dry-run reports do not
  restore backups, import data, create tags / creators / collections, modify
  saved views / activity, write SQLite data, delete business data, auto-fix,
  auto-import, auto-restore, auto-merge, request external network resources,
  add dependencies, or change database schema.
- Kept Phase 2-F1 strictly read-only: no auto-fix, one-click fix, automatic
  deletion, automatic merge, AI judgment, external information lookup, external
  content source, URL import, crawler, adapter, cloud sync, multi-user system,
  database schema change, new table, new field, or new dependency.

## v0.6.0 - 2026-07-09

### Added

- Added Phase 2-E3 dashboard / workbench quick action entry points for new
  items, the item list, saved views, recent activity, stats, collections,
  duplicate item detection, metadata cleanup, import, and backup.
- Added a dashboard saved views panel that shows a small set of local saved
  views and links to apply them without saving, updating, deleting, or
  modifying any data from the dashboard.
- Added an item-list quick action section for new items, save-current-view /
  saved views, recent activity, duplicate detection, metadata cleanup, import,
  and backup while preserving the existing filter, sort, pagination, saved
  views, and bulk edit areas.
- Added Chinese / English workbench and quick action UI text.
- Added tests for dashboard login protection, dashboard quick action rendering,
  navigation-only quick action sections, empty saved views / activity states,
  dashboard saved view and recent activity entries, item-list quick actions,
  existing filter and saved view preservation, and English quick action labels.
- Added Phase 2-E2 local item activity tracking backed by a new local SQLite
  `item_activity` table with one activity row per item.
- Added recent view recording for login-protected item detail visits, tracking
  `last_viewed_at` and `view_count` without recording list exposure,
  non-existent items, or unauthenticated requests.
- Added recent edit recording for user-driven item changes, including item
  basics, state / rating / review updates, tag changes, creator changes,
  collection changes, and current-page bulk edits.
- Added a login-protected `/activity` page with recent views, recent edits,
  empty states, item links, local activity counts, and a clear activity action.
- Added `POST /activity/clear` to clear only `item_activity` rows with browser
  confirmation, preserving items, tags, creators, collections, and saved views.
- Added dashboard and item-list entry points for recent views and recent edits,
  plus item detail activity metadata.
- Added Chinese / English recent activity UI and flash text.
- Added JSON backup export / preview / restore support for `item_activity`
  while keeping old backups without `item_activity` compatible and skipping
  activity rows that reference missing items.
- Added tests for activity login protection, empty states, recent view counts,
  unauthenticated and missing item no-write behavior, recent edit counts,
  relation changes, collection-side changes, current-page bulk edit activity,
  ordering, POST-only clear, clear safety, i18n coverage, table creation, and
  JSON backup compatibility.
- Added Phase 2-E1 local saved views for the item list page, backed by a new
  local SQLite `saved_views` table.
- Added login-protected saved view create, update, delete, and apply flows:
  `POST /saved-views`, `POST /saved-views/{id}/update`,
  `POST /saved-views/{id}/delete`, and `GET /saved-views/{id}/apply`.
- Added an item-list saved views panel for naming the current filter view,
  applying saved views, updating a saved view to the current filters, and
  deleting saved views with browser confirmation.
- Added saved view query-string normalization that stores only existing
  item-list filter / sort / page-size parameters, removes page numbers, ignores
  unknown parameters, and uses stable parameter ordering.
- Added Chinese / English saved view UI and flash text.
- Added JSON backup export / preview / restore support for saved views while
  keeping old backups without `saved_views` compatible.
- Added tests for saved view login protection, creation, validation, duplicate
  names, parameter filtering, apply redirects, no-write apply behavior, invalid
  IDs, update, POST-only delete, deletion, page rendering, i18n coverage, table
  creation, and JSON backup compatibility.

### Changed

- Kept Phase 2-E3 limited to local UI entry-point organization, with no
  database schema change, new table, dependency, dangerous one-click shortcut,
  login bypass, POST / confirm bypass, AI recommendation, smart analysis,
  automatic classification, external content source, URL import, crawler,
  adapter, cloud sync, multi-user sharing, third-party analytics, activity
  trend chart, tag, or GitHub Release.
- Kept Phase 2-E2 limited to local item activity, with no AI recommendation,
  smart analysis, automatic classification, external content source, URL
  import, crawler, adapter, cloud sync, multi-user activity feed, third-party
  analytics, IP logging, User-Agent logging, device fingerprinting, external
  referrer logging, database field changes, or new dependency.
- Kept Phase 2-E1 limited to local saved item-list views, with no AI
  recommendation, smart classification, external content source, URL import,
  crawler, adapter, cloud sync, multi-user shared views, database field
  changes, or new dependency.

## v0.5.0 - 2026-07-09

### Added

- Added Phase 2-D2 local metadata cleanup for tags, creators, and collections
  using exact trimmed name matches and normalized name matches with Unicode
  NFKC, trimming, casefolding, and whitespace collapsing.
- Added a login-protected `/cleanup` page showing read-only duplicate metadata
  candidate groups, match type, match key, object names, and related item
  counts across tags, creators, and collections.
- Added a login-protected `/cleanup/compare` page for manually comparing a
  primary metadata object and a duplicate metadata object before merge.
- Added manual metadata merge handling that keeps the primary tag / creator /
  collection, transfers related item links without duplicating relations,
  deletes the duplicate metadata object after confirmation, and never deletes
  items.
- Added collection description conflict handling: copy duplicate description
  when primary is empty, keep primary by default when both differ, and overwrite
  only when the user explicitly chooses the duplicate description.
- Added merge result flash summaries covering metadata type, kept object,
  deleted object, transferred relations, skipped duplicate relations,
  description handling, duplicate deletion, and a prompt to recheck cleanup.
- Added navigation, tag page, creator page, and collection page entry points for
  metadata cleanup.
- Added Chinese / English metadata cleanup and merge UI text.
- Added tests for cleanup login protection, empty states, tag / creator /
  collection exact and normalized candidate detection, comparison validation,
  POST-only merge, relation transfer, duplicate relation skipping, duplicate
  metadata deletion, item preservation, collection description copy / keep /
  overwrite handling, merge summaries, and i18n labels.
- Added Phase 2-D1 local duplicate candidate detection using exact trimmed title
  matches and normalized title matches with Unicode NFKC, trimming, casefolding,
  and whitespace collapsing.
- Added a login-protected `/duplicates` page showing read-only duplicate
  candidate groups, match type, match key, item counts, state, rating, and
  tag / creator / collection counts.
- Added a login-protected duplicate comparison page for manually choosing a
  primary item and a duplicate item before merge.
- Added manual duplicate merge handling that keeps the primary item, transfers
  tag / creator / collection relations without duplicating relations, merges
  safe fields, merges non-conflicting `extra` JSON keys, keeps primary values
  for conflicts by default, and deletes the duplicate item after confirmation.
- Added merge result flash summaries covering transferred relation counts,
  summary / status / rating / review handling, `extra` merge counts, `extra`
  conflict counts, and duplicate deletion.
- Added navigation, item list, and item detail entry points for duplicate
  detection.
- Added Chinese / English duplicate detection and merge UI text.
- Added tests for duplicate login protection, empty states, exact and
  normalized candidate detection, comparison validation, POST-only merge,
  relation transfer, conflict defaults, explicit overwrite choices, bad
  `extra` JSON handling, state copying, duplicate deletion, and i18n labels.

### Changed

- Kept Phase 2-D2 limited to local SQLite metadata duplicate detection and
  manual merge, with no AI synonym detection, fuzzy matching dependency,
  automatic bulk merge, external information lookup, external content source,
  URL import, crawler, adapter, recommendation system, cloud sync, multi-user
  system, database schema change, or new dependency.
- Kept Phase 2-D1 limited to local SQLite duplicate detection and manual merge,
  with no AI dedupe, image similarity, fuzzy matching dependency, automatic
  bulk merge, external content source, URL import, crawler, adapter,
  recommendation system, cloud sync, multi-user system, database schema change,
  or new dependency.

## v0.4.0 - 2026-07-09

### Added

- Added Phase 2-C2 collection data support for JSON backup export, JSON backup
  preview, JSON restore, CSV export, CSV import, JSON import, import preview,
  and import result summaries.
- Added `collections` and `item_collections` tables to JSON backup payloads
  while keeping old backups without those tables compatible.
- Added collection restore merge logic with duplicate collection protection,
  duplicate item-collection relation protection, bad relation skipping, and
  collection-specific restore counters.
- Added `collections` to CSV export and CSV / JSON import templates, with CSV
  semicolon-separated collection names and JSON collection arrays.
- Added import preview and result counters for collections to create,
  collection links, skipped collections, and collections field errors.
- Added tests for collection backup export / preview / restore, old backup
  compatibility, bad collection relation skipping, CSV export, CSV / JSON
  collection imports, template updates, preview no-write behavior, and
  Chinese / English collection backup copy.
- Added Phase 2-C1 local collections / list management backed by local SQLite
  tables `collections` and `item_collections`.
- Added collection create, edit, delete, list, and detail pages with login
  protection, empty states, duplicate-name handling, and Chinese / English UI
  text.
- Added item-to-collection management from both collection detail pages and item
  detail pages, including duplicate relation checks and safe removal of missing
  relations.
- Added item list filtering by collection, with query-string preservation across
  keyword, tag, creator, status, sorting, and pagination flows.
- Added current-page bulk add / remove collection actions using existing
  collections only.
- Added collection overview metrics and collection ranking to the local stats
  dashboard and stats summary payload.
- Added tests for collection login protection, CRUD, delete safety, detail
  rendering, item membership management, list filtering, bulk collection
  actions, stats, i18n coverage, and new table creation.

### Changed

- Backup and import pages now document that JSON backups include collection
  data, CSV exports include `collections`, JSON restore merges local collection
  data, and old backup / import files remain compatible.
- Kept Phase 2-C2 limited to local backup / import support for collection data,
  with no external content sources, URL import, crawlers, adapters,
  recommendation system, AI assistant, cloud sync, multi-user system, new
  dependency, or database schema change.
- Item detail pages now show linked collections and allow adding or removing one
  existing collection.
- Item API responses now include linked collection metadata for local clients.
- Kept Phase 2-C1 limited to local manual collections, with no external content
  sources, URL import, crawlers, adapters, recommendation system, AI assistant,
  cloud sync, multi-user system, new dependency, or front-end build flow.

## v0.3.0 - 2026-07-08

### Added

- Added a local SQLite stats service for overview metrics, status
  distribution, rating distribution, tag ranking, creator ranking, recent
  activity, and data completeness counts.
- Added an enhanced stats dashboard with pure HTML / CSS bars, local ranking
  lists, recent created / updated activity blocks, and empty data states.
- Added Chinese / English text and tests for empty stats, overview counts,
  status and rating distributions, tag / creator ranking order, recent activity
  counts, data completeness counts, and stats page rendering.
- Added lightweight responsive structure tests for the dashboard, item list,
  item detail, import preview, backup, stats, tags, and creators pages.

### Changed

- Kept Phase 2-B2 limited to local SQLite statistics, with no external content
  sources, URL import, crawlers, adapters, recommendation system, AI analysis,
  prediction model, chart library, new dependency, database structure change,
  cloud sync, or multi-user support.
- Polished shared responsive CSS for the top navigation, main content spacing,
  cards, grids, forms, buttons, pills, flash messages, pagination, and item
  selection controls.
- Improved narrow-screen layouts for the item list filters, current-page bulk
  editing panel, item cards, detail page sections, relation forms, import page
  preview / mapping tables, item forms, backup page, stats page, tag list, and
  creator list.
- Contained long local titles, tags, creator names, JSON blocks, and table
  content with wrapping or local table scrolling so mobile pages avoid obvious
  whole-page horizontal overflow.
- Kept Phase 2-B1 limited to responsive UI and page layout polish, with no new
  business features, dependencies, database structure changes, external content
  sources, URL import, crawlers, adapters, recommendation systems, AI
  assistants, cloud sync, or multi-user support.

## v0.2.0 - 2026-07-08

### Added

- Added Phase 2-A1 local list page advanced filtering for keyword, status, one
  tag, one creator, minimum rating, and created / updated time range.
- Added list sorting by created time, updated time, title, and rating in both
  directions.
- Added page size selection for `10`, `20`, `50`, and `100` items per page with
  query-string state preservation.
- Added current filter summary, clear filters action, and empty result prompt on
  the item list page.
- Added Chinese / English UI text and tests for the new list filters, sorting,
  pagination, retained form state, invalid pagination fallback, and empty state.
- Added Phase 2-A2 current-page item selection and local bulk actions for status
  updates, adding one existing tag, removing one existing tag, setting rating,
  and deleting selected items.
- Added browser confirmation and visible dangerous-action copy for bulk delete.
- Added bulk action success / error flash messages with processed and skipped
  counts in Chinese / English.
- Added tests for bulk login protection, missing selection, invalid inputs,
  tag handling, rating updates, delete cleanup, preserved list URLs, and i18n
  labels.
- Added Phase 2-A3 detail page sections for basic information, state
  information, tags, creators, and actions.
- Added detail page status, rating, and short review editing with safe invalid
  value handling.
- Added detail page management for adding / removing one existing tag and
  attaching / detaching one existing creator.
- Added safe detail-page `next` handling so returning to the item list can keep
  search, filters, sorting, page, and page size.
- Added Chinese / English UI text and tests for detail rendering, state edits,
  tag / creator relation management, safe `next`, and i18n labels.
- Added Phase 2-A4 CSV / JSON import template downloads with local-only example
  data and login protection.
- Added import field guidance for supported CSV / JSON fields, required
  `title`, valid internal `status` values, `rating` rules, tag / creator
  handling, preview flow, and local-only boundaries.
- Added CSV field mapping during preview, including `title`, `summary`,
  `status`, `rating`, `note`, `tags`, `creators`, `extra`, and ignored columns.
- Added enhanced import previews with total rows, importable rows, error rows,
  tags and creators to create, first five recognized rows, and readable error
  rows.
- Added import result summaries with imported, skipped, created tag, created
  creator, tag link, creator link, state record, and error counts.
- Added tests for import template auth and downloads, CSV automatic and manual
  mapping, mapping failures, CSV / JSON error paths, preview no-write behavior,
  partial valid imports, result summaries, and Chinese / English copy.

### Changed

- Moved item list query normalization and SQLAlchemy query construction into a
  dedicated local service.
- Moved bulk item mutation logic into a dedicated local service.
- Moved detail page mutation logic into a dedicated local service.
- Kept the Phase 2-A1 implementation local-only with no external content
  sources, crawlers, adapters, remote image fetching, recommendation system, AI
  assistant, cloud sync, or multi-user support.
- Kept the Phase 2-A2 implementation local-only and limited to selected items on
  the current page.
- Kept the Phase 2-A3 implementation local-only and limited to lightweight
  detail page display, state edits, relation management, and safe list-return
  context.
- Reworked the import service so parsing, preview validation, field mapping,
  error rows, and result summaries share one local-only code path.
- Kept the Phase 2-A4 implementation local-only and limited to uploaded CSV /
  JSON files, with no URL import, external content sources, crawlers, adapters,
  remote image fetching, automatic sync, recommendations, AI assistants, cloud
  sync, or multi-user support.

## v0.1.0 - 2026-07-08

### Added

- Completed the Phase 1 local single-user MVP.
- Added session-based login protection with `APP_PASSWORD` and `SECRET_KEY`.
- Added Chinese / English UI switching with session persistence.
- Added local item CRUD, tag management, creator management, item state
  tracking, search, and simple stats.
- Added CSV / JSON import with preview and confirmation flow.
- Added JSON backup export, readable CSV export, JSON backup preview, and
  append / merge JSON restore.
- Added configurable backup upload size limit through `MAX_BACKUP_UPLOAD_MB`.
- Added Dockerfile, Docker Compose deployment, SQLite persistence under
  `./data`, and N100 / LAN deployment documentation.
- Added GitHub Actions CI and basic automated test coverage.

### Changed

- Clarified Phase 1 local-only boundaries in README, TASKS, and REVIEW.
- Unified page feedback for success, error, and info messages.
- Improved import, backup, restore, and form operation user feedback.

### Fixed

- Added clear page-level feedback for login failure, import preview failure,
  and backup preview failure.
- Confirmed invalid backup restore paths do not damage existing database contents.

### Security

- Kept passwords and session signing secrets in environment variables.
- Kept `.env` ignored by git and documented that it must not be committed.
- Kept all main pages and APIs behind login protection.
- Documented that direct public internet exposure is not recommended.

### Known limitations

- Only one local user is supported.
- The app is intended for LAN / local deployment.
- Direct public internet exposure is not recommended.
- Backup restore is append / merge based, not an overwrite restore.
- There are no external content sources, crawlers, recommendation systems, or
  AI assistants.
- The current FastAPI / Starlette TestClient warning does not affect
  functionality; revisit it after the dependency path stabilizes.
