# Phase 3 Completion Audit / Phase 3 完成度审计

## Audit Scope

This audit freezes the current Unreleased Phase 3-B3 through C5 work on top of
the published `v1.0.6` baseline. It reviews the integrated routes, services,
templates, navigation, data-health findings, file identities, database
references, failure reporting, and compatibility boundaries.

The audit does not change application version `1.0.6`, Schema `2`, the real
Schema `1 -> 2` migration, dependencies, Docker/CI configuration, tags,
Releases, or N100 deployment state.

## Reviewed Workflows

| Phase | Workflow | Read entry | Confirmed write | Closed state |
| --- | --- | --- | --- | --- |
| B3 | Duplicate media cleanup | Duplicate groups and organize preview | Explicit keeper cleanup | Redundant paths disappear; references end on a verified keeper, restored path, recovery path, or accurately reported retained anchor |
| B4 | Cleanup recovery center | Recovery center | None | Read-only classification of referenced, unreferenced, damaged anchors and recovered media |
| B5 | Safety-anchor restore | Single-anchor restore preview | Publish `recovered-*`, migrate references, then remove anchor when safe | References resolve to verified ordinary media; retained anchor remains visible when final removal fails |
| B6 | Unreferenced-anchor delete | Single-anchor delete preview | Delete one still-valid zero-reference anchor | Anchor disappears from recovery center and Data Health |
| C1 | Broken-reference repair | Single cover/avatar repair preview | Explicit replacement or clear | Repaired object finding disappears; unrelated findings and every media file remain unchanged |
| C2 | Upload-residue cleanup | Single residue delete preview | Delete one exact zero-reference `.upload-*.tmp` | Selected residue finding disappears; references and other files remain unchanged |
| C3 | Scan-skip location | Skip list | None | Read-only stable location and reason; no automatic remediation |
| C4 | Damaged-media cleanup | Data Health or media-library preview | Delete one still-damaged zero-reference file | Selected damaged-file finding disappears; referenced files remain C1-only |
| C5 | Media-root diagnostic | Root diagnostic | Missing-only final-directory initialization | Root finding disappears after safe initialization; broken references remain visible for C1 |

## Data Health Finding Matrix

| Finding | Entry or explanation | Rejection boundary | State after handling |
| --- | --- | --- | --- |
| `media_reference_invalid_path` / `media_reference_path_escape` | C1 single-reference preview | Invalid object, stale reference, forged replacement, or healthy state rejects | Replaced/cleared object finding disappears |
| `media_reference_missing` / `media_reference_symlink` / `media_reference_damaged` | C1 single-reference preview | Replacement must be current validated ordinary local media; cleanup anchors reject | Finding disappears only for the explicitly changed reference |
| `media_cleanup_anchor_referenced` | Recovery center and B5 restore | B6 has no delete form while referenced | B5 moves references to verified `recovered-*`; retained failures stay visible |
| `media_cleanup_anchor_unreferenced` | Recovery center; B5 restore or B6 delete | Stale, damaged, symlinked, wrong-type, or newly referenced targets reject | Restore produces ordinary recovered media; delete removes the anchor finding |
| `media_cleanup_anchor_damaged` | Recovery center explanation | B5/B6 reject because content is not a valid anchor | Finding intentionally remains for manual filesystem inspection |
| `media_upload_residue` | C2 preview | Exact case-sensitive `.upload-*.tmp`, regular non-symlink, unchanged identity, and zero locked references required | Successful delete removes only this finding |
| `media_damaged_file` | C4 preview from Data Health and media library | Still damaged, unchanged full identity/SHA, and zero locked references required | Successful delete removes only this finding |
| `media_duplicate_content` | Exact full-SHA link to B2 duplicate group, then B3 manual cleanup | No default keeper; stale membership or identity rejects | Group shrinks or disappears according to remaining valid paths |
| `media_scan_skipped_symlinks` / `media_scan_skipped_unsupported` | C3 skip list with matching filter | Read-only; no delete, move, parse, hash, or automatic fix | Finding follows the next safe scan result |
| `media_root_unavailable` | C5 diagnostic | Initialization exists only for a genuine missing final directory with verified parents | Safe initialization removes root finding; C1 findings remain until explicitly repaired |

Every media finding therefore has either a direct bounded workflow, a precise
read-only location/explanation, or an intentional fail-closed state. The D1
audit added the previously missing exact full-SHA entry for
`media_duplicate_content`.

## Authentication And Write Boundaries

- Static route introspection found 19 B3-C5/Data Health/recovery/skip routes;
  all 19 include `require_page_auth`.
- All previews, diagnostics, lists, grouping pages, and skip pages are GET-only
  and have regression coverage proving database and relevant filesystem state
  remain unchanged.
- Every mutation uses POST plus the shared browser/server confirmation policy;
  strict mode requires exact `CONFIRM`.
- Reference-sensitive C1, C2, B6, and C4 writes recheck state under SQLite
  transaction/write-lock boundaries. B3 and B5 preserve a verified valid copy
  while references move between safe paths.
- Stale snapshots, identity drift, symlinks, parent replacement, new
  references, write-lock/query/commit failures, unlink failures, and fsync
  warnings have explicit fail-closed or accurately reported post-unlink paths.
- No GET creates, deletes, restores, renames, links, initializes, or rewrites a
  database record or media path.

## File Identity And Namespace Invariants

The final invariant is not just "the inode still matches." Validation retains
the configured root plus every parent directory identity, opens each component
through `O_DIRECTORY|O_NOFOLLOW`, opens the final entry through its verified
parent fd, and rechecks the current mapping before content use or unlink.

- B3 safety-anchor creation and B3/B5 publication use the verified parent fd;
  no temporary or recovered file is created through a re-resolved path.
- B3/B5/B6 validated media reads and deletes retain the parent fd chain and
  reject parent replacement before parsing, hashing, linking, or unlinking.
- C2 retains the residue parent chain, never reads residue content, and rejects
  a replaced parent/current mapping before unlink.
- C3/C4 continue to use their complete traversal candidate snapshots and
  verified fd chains.
- C5 continues to create only the configured missing final directory through a
  verified parent fd.

## Confirmed D1 Findings And Fixes

1. Data Health independently re-walked upload-residue paths and used a
   path-based root `scandir`. A queued directory/root replacement could cross
   the intended local-media namespace during a read-only audit. Residues now
   come only from C3's verified skip records, and root/reference checks use
   `O_NOFOLLOW` directory fds with identity checks.
2. `media_duplicate_content` had an explanation but no per-finding action.
   Each finding now links by its complete SHA-256 to the one matching B2 group.
3. Authenticated media responses validated one path and then let
   `FileResponse` reopen it. A parent replacement between those steps could
   serve an external same-name image. The response now reads and validates the
   bounded media bytes inside the retained fd chain and returns those bytes
   directly; a changed mapping returns 404 without reading the replacement.
4. Shared `ValidatedLocalMediaFile` operations used a verified final inode but
   reopened parent paths for safety-anchor creation, publication, and deletion.
   A parent symlink race with an external hard link could target an external
   directory entry. Validation records now retain parent identities, and all
   B3-B6 reads/links/unlinks use and recheck the verified fd chain.
5. C2 observed a residue and later reopened its parent chain without retaining
   the original parent identities. It now retains and revalidates the complete
   parent mapping before the identity-bound unlink.
6. A final create/publish validation could accept the expected inode through an
   ordinary replacement parent populated with hard links without proving that
   the returned records retained the original parent chain. Created anchors,
   refreshed anchors, and published targets now require the same root, logical
   parent parts, and stable directory type/device/inode chain as the initiating
   record, followed by a fresh current-mapping check. File ctime is deliberately
   not compared across hard-link creation.

Regression tests inject parent rename/symlink races after fd reads and exact
post-create/post-link races before final validation. The latter replace the
parent with an ordinary external directory populated with same-inode hard
links. The original selected inode, moved directory, unrelated media, database
references, and external entries remain intact on every rejected path.

## Static And Compatibility Audit

- No genuine TODO, FIXME, HACK, XXX, `NotImplementedError`, placeholder route,
  or HTTP 501 implementation remains in application/test code.
- Template audit: 110 registered routes, 142 literal `href`/`action` references,
  and 0 missing literal targets.
- The apparent `pass` matches are exception classes, bounded cleanup catches,
  or expected compatibility classes; none is an unfinished implementation.
- Chinese/English translation dictionaries remain symmetric and template
  translation tests pass.
- The combined 365-test regression covers B3-C5, media library, media serving,
  upload, recovery, Data Health, backup export/validation/restore, import,
  Schema 2, migrations, settings, danger confirmation, and i18n.
- Backup payloads still exclude media bytes and internal `schema_migrations`;
  no backup/import format, table, field, index, schema version, migration, or
  dependency changed in D1.

## Verification

- Exact final create/publish parent-chain races: `2 passed`.
- B3-B6/C1/C2/C4, authenticated media response, and Data Health core
  regression: `177 passed in 28.65s`.
- Combined integration/compatibility regression: `365 passed in 55.41s`.
- Full suite: `584 passed in 115.46s` on Python 3.12.13.
- `pip check`: `No broken requirements found.`
- Production image: build passed.
- Isolated Compose: container reached `healthy`, user `10001:10001`, read-only
  root, `cap_drop: ALL`, and `no-new-privileges` remained active.
- HTTP smoke: `/login`, authenticated `/data-health`, `/media-library`,
  `/media-library/duplicates`, `/media-library/recovery`, and
  `/media-library/skipped` all returned HTTP 200.
- Compose container/network and isolated temporary data were removed.
- Historical GitHub Actions run
  [`29350252749`](https://github.com/choneer/nsfwtrack/actions/runs/29350252749)
  completed successfully for both `test` and `Docker production smoke` on D1
  audit commit `d22d9d7`; the final parent-chain repair still requires a new run.

## Conclusion

The local release blocker is closed: final create/publish results are bound to
the initiating root/parent identity chain, the exact ordinary-directory
hard-link races reject success, and all local acceptance gates pass. The final
completion/freeze conclusion remains temporarily withdrawn only until the repair
is pushed and its new GitHub Actions `test` and `Docker production smoke` jobs
both succeed.

Release preparation remains a separate user-approved task. This audit creates
no tag, GitHub Release, version change, or N100 deployment.
