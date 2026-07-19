# Provider Operation Capability Matrix v1

## Status vocabulary

- `observed`: the fixed source documentation or type contract names the
  operation; it is not an NSFWTrack implementation.
- `reference only`: useful for contract design, with no activation authority.
- `candidate future`: can be considered only after a new explicit Approval.
- `denied current`: outside the current production profile or explicitly
  prohibited by the phase boundary.
- `not applicable`: no meaningful evidence or authority for this direction.

## Matrix

| Operation | JavdBviewed | JavSP | FnDepot | Venera | NSFWTrack B0 disposition |
|---|---|---|---|---|---|
| `search` | reference only | reference only | not applicable | observed | candidate future |
| `detail` | reference only | reference only | not applicable | observed | candidate future |
| `asset_list` | reference only | reference only | not applicable | reference only | candidate future |
| `discover/category` | not applicable | not applicable | not applicable | observed | denied current; no automatic discovery |
| `auth` | not applicable | not applicable | not applicable | not applicable | denied current |
| `favorites/write` | not applicable | not applicable | not applicable | not applicable | denied current; no remote mutation |
| `content load` | not applicable | not applicable | not applicable | not applicable | denied current |
| `playback` | not applicable | not applicable | not applicable | not applicable | denied current |
| `download` | not applicable | not applicable | not applicable | not applicable | denied current |
| `background sync` | reference only | not applicable | not applicable | not applicable | denied current; explicit user action only |
| `dynamic plugin execution` | not applicable | not applicable | not applicable | not applicable | denied current; code-owned typed binding only |

The source columns are evidence classifications, not permissions. Operations
outside each repository's allowed B0 extraction boundary are `not applicable`
rather than extracted. Venera's runtime model is rejected, and FnDepot's
manifest cannot execute or grant download authority.

## Current production profile

The only operation names that may appear in a future, separately approved
Production Profile are:

```text
search
detail
asset_list (optional)
```

The profile is still unactivated. It has no host, endpoint, method, response
fixture, credential, adapter, or Registry entry. The current registry value is
exactly `EndpointRegistry(())`.

## Operation invariants

- Each operation is separate; search never chains to detail or assets.
- Inputs and authority are code-owned typed values, not user URLs, source
  responses, manifest locators, or dynamically loaded code.
- Search/detail/asset results are immutable, bounded and provenance-aware.
- Operations do not write the database or filesystem and do not download media.
- Pagination is bounded and explicit: page numbers or opaque next tokens are
  data, never authority.
- Any future operation needs a complete Approval, static redacted fixtures,
  exact response and limit policy, and the existing N4D-C/D-A gates.
