# NSFWTrack Phase 2-K1 Development Completion Audit

Audit date: `2026-07-11`

Audit baseline: `v1.0.0` / commit `0d0de73`

Release status: K1 and K2 are published in `v1.0.1`.

The original K1 review was a read-only product-completion audit. The K2 closure
addendum below records the bounded fixes it requested; neither stage changes
dependencies, database structure, schema version, migrations, tags, or
releases.

## Executive Conclusion

The core local single-user workflow is implemented and broadly covered by the
current test suite. The repository contains no genuine TODO / FIXME marker,
stub route, 501 response, `NotImplementedError`, or dead navigation entry.

Phase 2-K2 has now closed every P0 / P1 use-before finding from this audit.
Code development and WSL acceptance are complete for `v1.0.1`:

1. **Phase 2-K2: use-before boundary closure (complete)** — closed local
   media-path, confirmation, secret-preflight, and focused regression gaps.
2. **Phase 2-K3: target-host / N100 deployment (not started)** — optional
   operator run only after explicit user authorization. It is not a current
   development task.

No additional product feature phase is required. Optional maintenance remains
outside the stable release scope unless separately approved.

## Phase 2-K2 Closure - 2026-07-11

- Added one local-only `/media/...` contract backed by `data/media`, protected
  by login and reused by API, page, backup validation / preview / restore, and
  rendering boundaries. External and ambiguous paths are rejected; legacy
  invalid covers are not rendered.
- Added browser and server confirmation to every current-page bulk write,
  state clear, and item relationship detach. Missing confirmation and wrong
  strict text fail before writes; exact `CONFIRM` succeeds in strict mode.
- Added startup rejection for the two exact `.env.example` credential
  placeholders without value disclosure.
- Closed focused F4 coverage for complete bilingual warnings, backup links,
  `dangerous_only`, `always`, strict confirmation, and clean reports.
- Added the single install / v0.9-v1.0 upgrade / rollback checklist requested by
  K1-03.
- Full pytest passed: 347 tests. Isolated Docker build, startup, stable
  `/login` 200, authenticated mounted-media 200, shutdown, and cleanup passed.
- No dependency, database structure, schema version, production migration,
  or external request was added by K2. The completed K1 / K2 work is published
  as the `v1.0.1` patch release. No current P0 / P1 completion finding remains.
  Code development and WSL acceptance are complete. N100 / target-host
  deployment has not started and waits for explicit user authorization.

## Evidence Collected

- Read `RULE.md`, `GOAL.md`, `PLAN.md`, `TASKS.md`, `README.md`, and
  `REVIEW.md` before inspecting implementation.
- Searched tracked source, templates, tests, scripts, CI, and documentation for
  TODO, FIXME, XXX, TBD, placeholders, empty branches, 501 responses, and
  unimplemented exceptions.
- Enumerated 95 application routes. Existing security regression coverage
  asserts that every non-public route declares an authentication dependency.
- Compared static template links, forms, and fragment targets with the route
  and page inventory; no dead application entry was found.
- Counted 31 test files, 275 declared test functions, and 309 collected tests.
- Reran the focused data-health / confirmation suite: 44 tests passed.
- Reran the complete suite after documentation changes: 309 tests passed with
  the existing TestClient deprecation warning only.
- Built and started an isolated Docker Compose project with a fresh `/tmp`
  data directory; `/login` returned HTTP 200, then the project and data were
  removed.
- Confirmed `CURRENT_SCHEMA_VERSION = 1` and an empty production migration
  registry.

## Placeholder And Dead-Code Review

### No Placeholder Blocker Found

The `pass` statements found by the scan are intentional:

- Pydantic create schemas inherit their complete field definitions.
- SQLAlchemy's declarative `Base` has no implementation body by design.
- Typed exception/result subclasses use their parent behavior.
- One nested rollback guard deliberately ignores a secondary rollback failure.

Template `placeholder=` attributes are normal form hints. The only `#...`
quick-action links target existing `saved-views`, `workbench`, `recent-views`,
or `recent-edits` elements.

### Low-Priority Cleanup Only

- `LoginRequest` and `CreatorUpdate` are currently unused by routes.
- `data_health.fix_backup_warning_title` and
  `data_health.fix_backup_warning_body` are translated but superseded by the
  shared danger notice.

These do not create a broken user flow. Remove or document them only during a
future maintenance pass; do not create a feature stage for them.

## Documented Capability Review

### Implemented And Evidenced

- Local authentication, Session cookies, Same-Origin enforcement, safe local
  redirects, generic errors, request IDs, and redacted request logging.
- Item, tag, creator, collection, state, search, filter, sorting, pagination,
  saved-view, activity, statistics, duplicate, and cleanup workflows.
- Local CSV / JSON import, JSON backup validation, preview, append/merge
  restore, old-backup compatibility, and rollback behavior.
- Data-health read-only reporting and allowlisted low-risk manual fixes.
- Settings, strict confirmation, schema preflight, migration dry-run, explicit
  migration apply contract, and full-chain rollback tests.
- Bilingual key symmetry and structure-level responsive checks.
- I2 query-count ceilings and the isolated 100 / 1,000 / 10,000 performance
  matrix recorded in `PERFORMANCE.md`.

### Documentation Mismatches

1. **HTMX is named as an implemented stack component, but no `hx-*` behavior
   exists.** The current frontend is Jinja2 plus small vanilla JavaScript.
   This is not a missing user capability and must not be "fixed" by adding a
   frontend dependency. Current planning text should describe the actual
   implementation.
2. **The plan says old-version upgrade instructions are included, but README
   provides scattered backup and Docker commands rather than one explicit
   upgrade/rollback checklist.** K2 should add a bounded operator runbook.
3. **`cover_path` is presented as a local cover path, but there is no local
   static asset route or upload contract.** This is a real implementation
   boundary issue described below.

## Findings Requiring Completion Before Real Data

### K1-01: Cover Paths Can Trigger External Browser Requests (Closed In K2)

Priority: **P0 / use-before blocker**

K2 status: **Closed.** The sole accepted prefix is authenticated `/media/...`
backed by `data/media`; all specified input, restore, and rendering boundaries
share the local validator.

Evidence:

- `ItemBase.cover_path` and `ItemUpdate.cover_path` only trim text and impose a
  length limit (`app/schemas.py`).
- Item list, detail, and collection-detail templates place the stored value
  directly in `<img src>`.
- The application mounts no app-owned local media directory (`app/main.py`).
- Isolated runtime proof accepted both `https://audit.invalid/pixel.png` and
  `/local-covers/audit.png`; the external value appeared in rendered HTML and
  the local route returned 404.
- No test covers remote, protocol-relative, data-URI, or invalid local cover
  values.

Impact:

- An imported or manually entered external URL makes the user's browser issue
  a remote request, contradicting the documented local-only / no remote image
  boundary.
- The advertised local path does not render under the current Docker setup.

K2 acceptance:

- Choose one deliberately small local-only contract: either serve only an
  app-owned mounted local media prefix, or stop rendering/exposing cover paths
  until such a contract exists.
- Reject external schemes, protocol-relative paths, data URLs, traversal, and
  ambiguous separators at API, page, and backup-restore boundaries.
- Apply the same stored-path policy to `avatar_path`, even though avatars are
  not currently rendered.
- Add API/page/restore/rendering regression tests. Do not fetch or proxy remote
  media and do not add URL import.

### K1-02: Confirmation Coverage Does Not Match RULE.md (Closed In K2)

Priority: **P0 / use-before blocker**

K2 status: **Closed.** Every bulk write, state clear, and relationship detach
now requires browser and server confirmation and honors strict `CONFIRM`.

Evidence:

- `RULE.md` forbids unconfirmed bulk modifications and requires confirmation
  for deletion.
- `/items/bulk` validates server confirmation only when
  `bulk_action == "delete"`; status, rating, add/remove tag, and add/remove
  collection actions write immediately.
- The bulk test helper adds `confirm=1` only for delete, so current tests encode
  the missing confirmation behavior.
- Item state clearing and item-tag / creator / collection detachment forms use
  POST but have no browser confirmation marker or server confirmation.
- Removing an item from a collection has the same gap.

Impact:

- A single accidental click can clear state/review data, detach relationships,
  or modify every selected item without the confirmation boundary required by
  the project rules.

K2 acceptance:

- Require explicit browser and server confirmation for every bulk write.
- Require confirmation for state clearing and review each relationship-removal
  form under one documented low-risk/destructive taxonomy.
- Preserve strict `CONFIRM` for operations classified as dangerous.
- Add missing-confirm, wrong-strict-text, exact-confirm, no-partial-write, and
  bilingual prompt tests without widening operation scope.

### K1-03: Shipped Placeholder Secrets Are Accepted (Closed In K2)

Priority: **P1 / mandatory deployment gate**

K2 status: **Closed.** Exact shipped placeholders fail startup without value
disclosure, with empty, valid, malformed upload, and cookie settings covered.

Evidence:

- `.env.example` contains known placeholder values.
- `_read_required_env` rejects only empty values, so copied placeholders start
  successfully.
- README tells operators to choose strong values, but no startup regression
  protects against accidentally deploying the shipped examples.

K2 acceptance:

- Fail closed for the exact shipped placeholder password and secret, with a
  safe error that does not echo either value.
- Add configuration tests for empty, placeholder, valid, and malformed upload
  / cookie settings.
- Add one concise first-install and v0.9/v1.0 upgrade/rollback checklist.

## F4 Safety-Prompt Review

Status: **Complete, including focused K2 acceptance coverage.**

Evidence:

- `/data-health` is read-only and links directly to JSON backup.
- Fix controls appear only for detected, allowlisted issue types.
- The shared danger notice states the affected object, consequence, deleted
  records, recoverability, current mode, and backup recommendation.
- The page explicitly states that core items, tags, creators, and collections
  are not deleted and that only one fix runs at a time.
- Fix requests require login, POST, `confirm=1`, and strict `CONFIRM` when
  configured; rollback and core-entity preservation are tested.
- The focused health / fix / danger suite passes 44 tests.

K2 test closure:

- Assert the complete F4 warning copy and backup link in both languages.
- Assert that `dangerous_only` still shows the backup recommendation for a
  health fix and that `always` does not weaken any confirmation.
- Assert no fix controls render for a clean report.

F4 does not require another product feature or a new database operation.

## Other Test Gaps

### Must Close In K2

- Local media-path validation across API, page, restore, and templates.
- Confirmation behavior for non-delete bulk writes and clear/detach actions.
- Exact `.env.example` placeholder rejection.
- Focused F4 warning visibility and policy tests.

### Optional After Explicit Authorization (K3 / N100)

Not a current development task. N100 deployment has not started.

- A real browser run of JavaScript confirmation and the detail-page view POST;
  TestClient does not execute JavaScript.
- Desktop and mobile viewport smoke checks; existing responsive tests assert
  HTML/CSS structure rather than rendered geometry.
- Export, validate, restore into a fresh isolated deployment, then compare core
  entity and relation counts.
- Target N100/LAN startup, persistence, restart, login, and shutdown.

### Optional Later

- Pin or constrain dependencies for reproducible future rebuilds.
- Phase 2-L1 resolved the TestClient deprecation warning with `httpx2==2.5.0`
  in development / CI dependencies.
- Add Docker health checks or CI Docker smoke only if operational experience
  shows a need.
- Add indexes only after new measurements justify a real schema migration.

## Out Of Scope

Do not turn completion work into any of the following:

- External cover lookup, remote image proxying, URL import, content sources,
  crawlers, adapters, or automatic synchronization.
- Recommendations, AI analysis, semantic matching, or automatic merging.
- Cloud backup/sync, multi-user accounts, complex permissions, or public-host
  hardening that implies direct internet exposure.
- A frontend framework migration or HTMX rewrite solely to match old wording.
- Invented schema versions, migrations, indexes, or tables.

## Current Status After v1.0.1

### Phase 2-K2: Use-Before Boundary Closure

Status: **Complete.** Published in `v1.0.1`.

Scope was limited to K1-01, K1-02, K1-03, focused F4 tests, and the matching
README / REVIEW / CHANGELOG updates. It did not add product features,
dependencies, schema changes, external requests beyond the published patch.

Exit gate (met):

- All K2 acceptance bullets pass.
- Full pytest and isolated Docker / WSL acceptance pass.
- No current P0/P1 completion finding remains.

### Phase 2-K3: Target Deployment Acceptance

Status: **Not started. Not a current development task.**

N100 / target-host deployment waits for explicit user authorization. Until
then, do not treat the following as open engineering work.

If later authorized, the operator checklist is:

- Unique deployment secrets are configured outside git.
- Target-host Docker, persistence, restart, LAN login, and browser smoke pass.
- A fresh JSON backup is exported, validated, restored into an isolated empty
  instance, and count-compared before real data is entrusted to the system.
- The final audit records no remaining use-before blocker.

Everything else in this document is optional maintenance or explicitly outside
the project boundary.
