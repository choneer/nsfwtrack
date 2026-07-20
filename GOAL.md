# Phase 5-R1 — v1.2.0 Integration Freeze Audit

## Outcome

Phase 5-R1 completed the static integration freeze at base
`e5be8388561306fb3711574e6302d24752721941`.

```text
Gate = PASS — no R2 corrective required
Application = 1.1.0
Schema = 4
Backup = nsfwtrack.backup.v2 (v1 restore compatible)
Production Registry = EndpointRegistry(())
Production Search Packages = ()
Production Search Providers = ()
N5C = complete/frozen
N6/N7 = not implemented
Hermes = not called
Tag/Release = not created
N100 = not deployed
```

R1 added no product capability and changed no production behavior. The only
production-file edit is the `app/routers/source_search.py` module docstring,
which now accurately describes Search, Detail, signed Preview, and explicit
Confirm. Documentation was synchronized and a small static integration-freeze
test was added.

## Audit evidence

- `HEAD` and `origin/main` both began at
  `e5be8388561306fb3711574e6302d24752721941`.
- Annotated tag object `07643bf6a7b36cb488c80c0ac694b6bc733e61e3`
  still peels to v1.1.0 commit
  `c1ff2760f8ee8ca988493aa04e8b4affbc4b4b9d`.
- The documented 21-commit Phase 5 chain is exact and linear, with no merge or
  unexpected product-code commit.
- N1 outbound boundaries, N2 Schema/Backup behavior, N4 Approval/Package/
  Artifact gates, metadata contracts, N5 Search/UI, signed Plan/Token,
  transactional Apply, and Session-bound Web invariants all passed review.
- GET remains operation/DB/material/apply-free. Confirm remains POST-only,
  performs zero Provider/catalog work, and attempts B1 Apply at most once.
- Production imports no tests-only fixture and activates no Provider, host,
  endpoint, credential, cookie, playback, download, sync, background task,
  recommendation, or AI capability.
- Findings were four documentation-level notes; all were disposed within R1.
  `REVIEW.md` contains the evidence, impact, disposition, and R2 decision.

## Verification

```text
R1 focused                 5 passed
N5 targeted              232 passed
Full pytest             1393 passed
pip check                  passed
git diff --check           passed
Docker production smoke    passed
```

The isolated production Docker smoke verified non-root UID/GID 10001,
read-only root filesystem, all capabilities dropped, no-new-privileges,
temporary `/tmp`, writable isolated `/app/data`, required `/login` security
headers, Schema 4, and SQLite/media-index persistence across container
recreation. It mounted a temporary directory outside the repository and did
not access the existing `data/` directory.

The resulting single normal fast-forward commit is validated by the repository
Actions jobs `test` and `Docker production smoke`; their run ID and final status
are external post-push evidence reported in the handoff, so this tracked file
is not amended after validation.

## Release state

R2 corrective is not required. Application version remains `1.1.0`. Phase
5-R3 owns the `1.2.0` version update, RC freeze, and the one Phase 5 Hermes
acceptance only after that candidate is fully frozen. Phase 5-R4 formal release
has not been published and still requires separate authorization. N100 remains
unauthorized.
