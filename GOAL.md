# Phase 5-R4 — Release v1.2.0

## Outcome

Phase 5-R4 completed the formal v1.2.0 release workflow from frozen candidate
`1f0b6000cdb417685ecde79b7ab808a47fa63708`.

```text
Application = 1.2.0
Latest stable = v1.2.0
Schema = 4
Backup = nsfwtrack.backup.v2
Backup v1/v2 restore = supported
R1 = PASS
R2 = skipped
R3 = frozen
Hermes = PASS
R4 = released
N5C = complete/frozen
N6/N7 = not implemented
Production Registry = EndpointRegistry(())
Production Search Packages = ()
Production Search Providers = ()
N100 = not deployed
```

R4 added no feature and changed no production code, Application metadata,
Schema, Migration, Backup implementation, dependency, Docker, Compose, or CI.
It did not call Hermes again, publish an image, activate a Provider, or deploy
N100.

## Release preparation

- Pre-release gates proved that no local/remote `v1.2.0` tag or GitHub Release
  existed before work began.
- The dedicated GitHub token file had mode `600`; the token was read only inside
  controlled subprocesses and was not printed, copied, or written to the repo.
- The entire existing `Unreleased` body was archived unchanged under
  `[1.2.0] - 2026-07-20`; a new empty `Unreleased` remains at the top.
- `[1.1.0]` and all earlier release sections, stable tag evidence, compatibility
  notes, historical Actions, test counts, and candidate audit records remain.
- README, PLAN, TASKS, REVIEW, Provider contract, and roadmap now record the
  formal v1.2.0 release while keeping production catalogs empty and N6/N7
  unimplemented.
- Fixed R1/R3 documentation-state tests were updated without weakening version,
  Schema, Backup, catalog, or route assertions. The dynamic additional-test list
  was empty. A focused R4 formal-release invariant test was added.

## Verification

```text
Runtime invariants                   passed
Focused R1/R3/R4/security          36 passed
All Phase 5                       518 passed
Full pytest                      1402 passed
pip check                           passed
git diff --check                    passed
Production Docker smoke             passed
```

The isolated Docker double-lifecycle smoke verified Application `1.2.0`, fresh
Schema 4, `/login` health and security headers, UID/GID 10001, read-only root,
CapDrop ALL and `CapEff=0`, no-new-privileges, `/tmp` tmpfs, isolated writable
`/app/data`, and SQLite/media-index persistence after container recreation.
Temporary containers, image, credentials, and `/tmp/nsfwtrack-r4-smoke.*` data
were cleaned up. The repository `data/` directory was not mounted or accessed.

## Publication chain

The single normal fast-forward release commit is validated by its main-push
Actions jobs `test` and `Docker production smoke`. Only after both succeed is
annotated tag `v1.2.0` created at that release commit and pushed. The tag-push
Actions must also both succeed before the non-draft, non-prerelease GitHub
Release `NSFWTrack v1.2.0` is created from the frozen CHANGELOG section.

Release commit SHA, annotated tag object SHA, peeled commit, both Actions run
IDs, and the verified Release URL/status are external post-commit evidence in
the final handoff. The validated release commit is not amended and no corrective
commit is created.

## Security and scope

Included: controlled outbound/adapter foundation, Schema 4 source identity,
Backup v2/v1 restore, Approval/Package/Artifact gates, provider-neutral
metadata, authenticated Search/Detail, deterministic Apply Plan, purpose-bound
HMAC Token, Session-bound Preview/Confirm, and transactional local Apply with
Token-first, `BEGIN IMMEDIATE`, stale/replay/field ownership/rollback/post-check/
independent final-state proof.

Excluded: real Provider activation, Provider auth/Vault/Cookie, remote image,
playback, asset resolve, N6 download, N7 update/sync/recommendation, background
jobs, cloud sync, AI, multi-user, image publication, and N100 deployment.
