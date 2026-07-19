# Repository-derived Video Metadata Profile v1

## Profile status

This is a Provider-neutral research profile derived from four fixed public
repository snapshots. It is `draft / reference only / not approved` and does
not activate a Provider. The production registry remains
`EndpointRegistry(())`; application version is `1.1.0`, Schema is `4`, and the
backup format is `nsfwtrack.backup.v2`.

## Fixed evidence inputs

| Source role | Repository | Commit | Accepted concepts |
|---|---|---|---|
| local state and merge protection | `lmixture/JavdBviewed` | `8c9245726906ece8d49f553542874980512d4504` | user state, manual fields, soft delete, sync facts |
| metadata vocabulary and aggregation | `Yuukiy/JavSP` | `c4cfe61188234dd24c75b53b42b054327fef3e58` | identifiers, titles, summary, people, organizations, tags, rating, assets, priority merge |
| manifest/versioning reference | `EWEDLCM/FnDepot` | `9a2449eaf012c352bca2ed4381e005a37f67d757` | versioned JSON, stable keys, required/optional, explicit overrides, backward compatibility |
| operation taxonomy reference | `venera-app/venera` | `a0eba914f4c2a84ac1bc925adec2baabe920b9be` | source identity/version, search/detail/category, pagination, optional asset-like operations |

The upstream licenses, maintenance facts and non-adopted behavior are recorded
in the evidence ledger. No implementation is copied.

## Normalized contract

The profile maps to the existing immutable contracts:

- `VideoIdentifier`: Provider-scoped opaque external identity plus optional
  catalog number;
- `VideoPerson` and `VideoOrganization`: bounded display values and scoped
  identity with an explicit role;
- `VideoSeries`, `VideoTag`, and `VideoRating`: source-scoped, bounded and
  scale-aware values;
- `VideoAsset`: opaque asset ID and declared media facts, never a fetch
  authorization or persisted arbitrary locator;
- `VideoMetadataProvenance`: source identity, operation, observed/source time,
  available field and canonical-value digest;
- `VideoSearchResult`, `VideoDetail`, and `VideoSearchPage`: immutable
  operation-specific result shapes;
- `LocalVideoMetadata` and `VideoMetadataMergePlan`: local/user state and a
  deterministic zero-write merge plan kept separate from remote candidates.

## Merge and local-state policy

Source results are parsed independently, then ordered by an explicit immutable
priority. Non-empty values fill missing fields; absence never means deletion.
Alternative assets remain bounded candidates. Local ratings, notes, favorites,
lists, manually edited fields, soft deletion and sync facts remain authoritative.
Hard identity or scale conflicts stop for review. No merge plan writes a
database, file, media record or Registry entry.

## Manifest and Versioning Profile

FnDepot evidence supports a bounded parser/admission split:

1. Parse exact bytes into a versioned JSON envelope with bounded depth, size and
   field counts.
2. Validate the stable key, required fields, optional fields, version and
   explicit override precedence.
3. Reject duplicate keys, incomplete entries, unsupported versions and
   contradictory identity before creating a candidate.
4. Admit only a complete, code-owned typed record; admission does not execute a
   manifest, scan directories, resolve locators or grant network/download
   authority.
5. Preserve explicit backward compatibility as a parser rule, never as silent
   field loss.

This is a design rule for local metadata/catalog parsing, not an invitation to
load or run FnDepot content.

## Operation profile

Only these operation slots are retained for a future explicit Approval:

| Operation | Result | Write | Follow-up | Status |
|---|---|---|---|---|
| `search` | bounded `VideoSearchPage` | none | none | candidate future |
| `detail` | one `VideoDetail` | none | none | candidate future |
| `asset_list` | bounded `VideoAsset` tuple | none | none | optional candidate future |

Category/discovery, auth, remote writes, content loading, playback, download,
background synchronization and dynamic plugin execution are denied. Pagination
may use a bounded page number or opaque next token; a token is data, not a host,
path or permission.

## Readiness and blockers

All four repositories are reference-only and cannot be the first Production
Provider. A real activation still requires a user-named Provider, lawful access
and terms basis, exact fixed network facts, typed code-owned adapter, redacted
static fixtures, production Approval Artifact, and N4D-C/D-A validation. No
upstream URL, selector, login, cookie, response, download, JavaScript runtime or
remote source is part of this profile.
