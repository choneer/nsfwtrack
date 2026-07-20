# Phase 5-R3 — Application 1.2.0 / Release Candidate Freeze

## Outcome

Phase 5-R3 completed the release-candidate freeze from base
`04ca2d87ae93b85affbe3eeb4c7558b2d6fdf674`.

```text
Local gate = RC READY — pending cloud review
Application = 1.2.0 release candidate
Latest stable release = v1.1.0
Schema = 4
Backup = nsfwtrack.backup.v2
Backup v1 restore = supported
Production Registry = EndpointRegistry(())
Production Search Packages = ()
Production Search Providers = ()
N5C = complete/frozen
N6/N7 = not implemented
R1 = PASS
R2 = skipped
Hermes = not called
R4 = not released
N100 = not deployed
```

R3 adds no feature and activates no Provider. The only production-code change
is the FastAPI version literal in `app/main.py`, from `1.1.0` to `1.2.0`.
Current-version test expectations, release-candidate documentation, and a small
R3 invariant test were synchronized. Historical v1.1.0 release and compatibility
evidence remains unchanged.

## Version-reference inventory

Current candidate references updated to `1.2.0`:

- `app/main.py` FastAPI metadata.
- Executable current-version assertions in the five existing Phase 5 tests.
- The explicitly user-authorized expected literal in
  `tests/test_release_security.py`.
- README, PLAN, TASKS, REVIEW, CHANGELOG, Provider contract, roadmap, and the new
  R3 candidate test.

References retained as v1.1.0:

- latest stable Release, annotated tag object, peeled commit, and Phase 4 release
  evidence;
- historical Phase 5 checkpoint versions, tests, and Actions evidence;
- stable v1.1.0 Schema 4 rejection and Backup compatibility documentation;
- the formal CHANGELOG `[1.1.0]` section.

No global replacement was used. No other runtime application-version definition
exists under `app/`.

## Candidate scope

Included: controlled outbound/adapter foundation; Schema 4 ItemSource identity,
check, and hash fields; Backup v2 export and v1/v2 restore; Approval/Package/
Artifact gates; provider-neutral metadata; authenticated Search/Detail;
deterministic Apply Plan; purpose-bound HMAC Token; Session-bound Preview/
Confirm; transactional local Apply with `BEGIN IMMEDIATE`, stale/replay/field
ownership/rollback/post-check/independent final-state proof; synthetic-only
tests; and an empty production state.

Excluded: real Provider activation, Provider authentication/Vault/Cookie,
remote images, playback, asset resolve, N6 download, N7 update/sync/
recommendation, background jobs, cloud sync, AI, multi-user, published images,
Tag/Release, and N100 deployment.

## Verification

```text
Application version check       1.2.0
R1 + R3 focused                 9 passed
N5 targeted                   236 passed
All Phase 5                   513 passed
Full pytest                  1397 passed
pip check                       passed
git diff --check                passed
Docker production smoke         passed
```

The isolated Docker double-lifecycle smoke verified Application `1.2.0`, fresh
Schema 4, `/login` health and security headers, UID/GID 10001, read-only root,
all capabilities dropped, no-new-privileges, `/tmp` tmpfs, isolated writable
`/app/data`, and SQLite/media-index persistence after container recreation.
Temporary containers, image, credentials, and `/tmp/nsfwtrack-r3-smoke.*` data
were cleaned up. The repository `data/` directory was not mounted or accessed.

The resulting single normal fast-forward candidate commit is validated by the
repository Actions jobs `test` and `Docker production smoke`; the run ID and
final result are external post-push evidence reported in the handoff, so the
candidate is not amended after validation.

## Release state

R3 remains a release candidate, not a formal release. No v1.2.0 tag or Release
exists from this phase. Hermes has not been called. After cloud review succeeds,
the next separately authorized action is the single Phase 5 Hermes acceptance
against the exact candidate SHA. R4 formal release and N100 deployment remain
pending and unauthorized.
