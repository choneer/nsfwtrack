# Repository-derived Provider Evidence Ledger v1

## Status and boundary

This ledger is a static, repository-derived evidence record for Phase 5-N4D-D-B0.
It is not a Provider approval, an executable manifest, or a source of network
authority. The four snapshots below are pinned to the exact commits supplied by
the user. No repository was cloned or vendored, and no source code, fixture,
image, response, credential, content-site address, selector, or download locator
is reproduced here.

The current production registry remains `EndpointRegistry(())`. All four
repositories are reference-only and are not directly activatable Production
Providers.

## Fixed evidence table

| Repository | Default branch | Reviewed commit | Repository status at review | License / terms | Evidence role |
|---|---|---|---|---|---|
| `lmixture/JavdBviewed` | `main` | `8c9245726906ece8d49f553542874980512d4504` | Not marked archived; active maintenance is not inferred | `AGPL-3.0-only` in `LICENSE` and package metadata | local video state, user ownership, sync contract |
| `Yuukiy/JavSP` | `master` | `c4cfe61188234dd24c75b53b42b054327fef3e58` | Not marked archived; fixed snapshot is the reviewed boundary | `GPL-3.0-only`; README also states Anti-996/additional terms | metadata vocabulary and deterministic source aggregation |
| `EWEDLCM/FnDepot` | `main` | `9a2449eaf012c352bca2ed4381e005a37f67d757` | Not marked archived; update workflow is described but does not grant activation | No root `LICENSE` found at the fixed revision; legal review remains open | versioned catalog/manifest and admission concepts |
| `venera-app/venera` | `master` | `a0eba914f4c2a84ac1bc925adec2baabe920b9be` | Archived; README states that the project is no longer maintained | `GPL-3.0` in `LICENSE` | operation taxonomy and pagination vocabulary only |

"Not marked archived" is a bounded observation, not a claim that a project is
maintained, safe, or suitable for production. License conclusions apply only to
the reviewed snapshot and do not authorize code reuse.

## JavdBviewed

Reviewed evidence:

- `apps/extension/src/types/index.ts:11-45` defines actor aliases, timestamps,
  deletion and sync-related facts, including manual-edit and blacklist state.
- `apps/extension/src/types/index.ts:118-130` separates local/JavDB list
  identity and counts from timestamps.
- `apps/extension/src/types/index.ts:145-188` models viewed/browsed/want and
  untracked state, deletion, release date, rating, notes, manual fields,
  duration, series, categories, user fields, favorites and list membership.
- `apps/extension/src/features/webdavSync/domain/types.ts:22-90` defines client
  profile, known device/source, last-sync facts, versioned upload index and
  data-version/count metadata.
- `apps/extension/src/features/webdavSync/application/dataMerge.ts:14-53,212-337`
  describes cloud/local/custom/smart merge summaries and field-level policy:
  local priority, manual protection, preserved local creation time, de-duplicated
  tags, status ordering, and fallback for missing fields.
- `apps/extension/src/features/webdavSync/application/importSanitizer.ts:9-50`
  preserves current-device metadata and merges known-device records.

Adopted as contract evidence: local state is separate from source metadata;
manual fields and user notes are authoritative; soft deletion and sync facts are
explicit; merge behavior is deterministic and field-aware.

Not adopted: browser-page parsing, selectors, account/login behavior, WebDAV
transport, media search, download, preview, userscript behavior, or AGPL code.
The repository is not an official NSFWTrack Provider and cannot activate one.

## JavSP

Reviewed evidence:

- `javsp/datatype.py:16-54` exposes source-scoped fields for catalog number,
  plot, covers, genres and IDs, score, title, serial, performers, director,
  duration, producer, publisher, release date, preview images and preview video.
- `javsp/datatype.py:99-119` maps stable metadata concepts to NFO/template
  fields such as number, title, actor, score, censor, series, director,
  producer, publisher, date, label and genre.
- `javsp/__main__.py:116-158` selects configured sources and removes failed
  sources before aggregation.
- `javsp/__main__.py:161-258` preserves source order as priority, fills only
  missing scalar fields, retains existing values when an incoming source is
  missing a field, accumulates cover candidates, and fails aggregation when a
  required key is unavailable.
- Root `LICENSE` is GPL-3.0. The README additionally states Anti-996 and other
  use terms; any reuse would require a separate legal review.

Adopted as contract evidence: source-scoped result, provenance/priority,
first-nonempty scalar selection, retained alternatives, missing-is-not-delete,
and an explicit required-field gate.

Not adopted: crawler modules, source-specific networking, cookies/proxies,
browser launch, fixture copying, media download, naming, or scraper code. JavSP
is a multi-source scraper reference, not a directly activatable Provider.

## FnDepot

Reviewed evidence:

- `README.md`, sections "Repository Standards" and "Directory Structure",
  require a versioned index and a stable application key that corresponds to an
  application entry; the document describes compatibility with an older
  single-architecture form.
- `README.md`, section "Metadata", describes required versus optional fields,
  architecture-specific overrides, fallback behavior, and an explicit priority
  of architecture-specific values over common values.
- `fndepot.json` is a JSON object with top-level `schema_version`, `source_info`
  and `apps` maps. Each app is keyed by a stable name; releases are version
  maps, and packages are architecture maps with declared size and checksum
  facts. The manifest also contains locator-shaped fields, which are excluded
  from this profile.
- The README describes push-based source updates and backward-compatible
  parsing. That operational description is reference material only.

Adopted as contract evidence: a bounded versioned JSON parser can inspect a
manifest first, validate stable keys and required fields, apply explicit
override precedence, and admit only complete entries. "Parser first, admission
later" and "incomplete entry is not activated" are NSFWTrack safety rules
derived from this structure, not permission to execute a manifest.

Not adopted: download or installation locators, automatic path construction,
package execution, directory scanning, auto-discovery, or any manifest-driven
side effect. FnDepot is an application source, not a video-content Provider.
The missing root license is a production-readiness blocker.

## Venera

Reviewed evidence:

- `README.md` explicitly states that the project is no longer maintained.
- `doc/comic_source.md`, "Write basic information", separates source `name`,
  stable `key`, `version`, minimum app version and update metadata.
- The same document defines separate explore/category/search operations,
  list/detail result shapes, and both page-number and opaque next-token forms.
- Its "Comic Details" section separates loading one detail record, optional
  thumbnails, and chapter image listing. These are taxonomy references only.
- `LICENSE` is GPL-3.0 and the repository is archived at the fixed revision.

Adopted as contract evidence: explicit source identity/version, operation
separation, bounded pagination, optional capabilities, and list/detail
separation.

Not adopted: JavaScript source execution, remote source loading, account/login,
cookies, WebView, content loading, image locators, playback, or download. The
current NSFWTrack production profile is Python/code-owned and has no Venera
activation.

## Cross-repository conclusion

The evidence supports a Provider-neutral metadata and operation contract only.
It does not supply a lawful production Provider, fixed network facts, response
fixtures, or an approval artifact. A future Provider must be separately named,
legally reviewed, statically approved, bound to code-owned operations, and pass
the existing N4D-C/D-A gates. Until then, every repository above remains
`reference only`, with no production registry entry.
