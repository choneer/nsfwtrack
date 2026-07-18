# Comic Provider Approval Draft

> Status: **draft / not approved**
>
> Every value is a placeholder. This document names no real Provider, host,
> endpoint, credential, cookie, fixture payload, or approved capability. It
> cannot install code or activate the Production Provider Registry.

## 1. Provider identity and use basis

- Provider Approval ID: `<required-approval-id>`
- Code-owned `provider_key`: `<required-provider-key>`
- Display name: `<required-display-name>`
- Content scope and NSFW-core fit: `<required-scope-and-fit>`
- Lawful access basis: `<required-lawful-access-basis>`
- Terms/API/use-policy basis: `<required-terms-basis>`
- Attribution policy: `<required-attribution-policy>`
- Retention/deletion obligations: `<required-policy>`
- Explicit exclusions: `<required-exclusions>`

Approval state:

- [ ] Identity and product fit approved
- [ ] Lawful/terms/attribution basis approved
- [ ] Fixed Python adapter approach approved
- [ ] Final production scope approved

## 2. Exact hosts

| Purpose | Host ID | Exact hostname | Port | Credential scope | Approved |
|---|---|---|---|---|---|
| Metadata Host | `<required>` | `<required>` | `<required>` | `<required>` | `[ ]` |
| Asset Host | `<required>` | `<required>` | `<required>` | `<required>` | `[ ]` |
| Auth Host | `<required-or-none>` | `<required-or-none>` | `<required>` | `<field-names-only-or-none>` | `[ ]` |
| Redirect Host | `<required-or-none>` | `<required-or-none>` | `<required>` | `<required>` | `[ ]` |

Wildcards, suffix matching, source-script hosts, response-discovered hosts, and
user-entered hosts are invalid.

## 3. Operations

| Operation | Fixed path | Method/encoding | Typed input | Pagination | Response/limit | Auth | Approved |
|---|---|---|---|---|---|---|---|
| Search | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `[ ]` |
| Category List | `<required-or-not-applicable>` | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `[ ]` |
| Category Items | `<required-or-not-applicable>` | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `[ ]` |
| Detail | `<required>` | `<required>` | `<required>` | `<none>` | `<required>` | `<required>` | `[ ]` |
| Chapter List | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `[ ]` |
| Page List | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `[ ]` |
| Asset List | `<required-or-not-applicable>` | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `[ ]` |

Optional discover, auth, favorite, comment, rating, and download operations are
`<not-requested-unless-separately-reviewed>` and remain denied by default.

## 4. Identity and field mapping

- Comic identity rule: `<provider-key-plus-opaque-external-id-rule>`
- Chapter identity rule: `<provider-comic-plus-opaque-chapter-id-rule>`
- Page identity rule: `<provider-comic-chapter-plus-opaque-page-id-rule>`
- Asset identity/locator separation: `<required-rule>`
- Chapter grouping and stable order: `<required-rule>`
- Page order and duplicate rejection: `<required-rule>`

| DTO/field group | Reviewed payload location/type | Bounds/normalization | Approved |
|---|---|---|---|
| Search identity/title/summary/cover | `<required>` | `<required>` | `[ ]` |
| Detail titles/summary/status/language | `<required>` | `<required>` | `[ ]` |
| Creators/categories/tags | `<required>` | `<raw-and-normalized-rule>` | `[ ]` |
| Chapter groups/IDs/titles/order/time | `<required>` | `<required>` | `[ ]` |
| Page IDs/order/dimensions | `<required>` | `<required>` | `[ ]` |
| Asset IDs/MIME/size/hash/expiry | `<required>` | `<required>` | `[ ]` |
| Provenance/source updated time | `<required>` | `<required>` | `[ ]` |

## 5. Authentication and cookie lifecycle

- Login mode: `<required-mode-or-none>`
- Fixed login/test/logout operations: `<required-or-none>`
- Credential field names, never values: `<required-or-none>`
- Cookie names/domain/path/secure/expiry policy, never values: `<required-or-none>`
- Secret Vault requirement: `<required-or-none>`
- Expired/invalid/revoked/unknown handling: `<required>`
- Automatic relogin/retry: `<must-be-denied-unless-separately-approved>`
- Browser cookie extraction: `<must-be-denied>`

## 6. Reading, cache, and download policy

- Page Asset Host and locator policy: `<required>`
- Relative-reference/redirect policy: `<required>`
- Per-page response and media limits: `<required>`
- Reader prefetch bound: `<required-or-none>`
- Cache policy and location: `<required-or-none>`
- Local reading-progress policy: `<required-local-only-policy>`
- Remote/local favorite separation: `<required>`
- Whole-chapter automatic download: `<must-be-denied>`
- Explicit download policy: `<not-applicable-unless-separately-approved>`

## 7. Errors and fixtures

- Error mapping: `<required-complete-stable-error-mapping>`
- Search/detail/category fixtures: `<required-redacted-static-fixtures>`
- Chapter/page/asset fixtures: `<required-redacted-static-fixtures>`
- Duplicate/malformed/oversized fixtures: `<required>`
- 401/403/404/429/5xx fixtures: `<required>`
- Expired/cancelled/unknown fixtures: `<required>`
- Fixture provenance/redistribution basis: `<required>`
- No credential/live locator in fixtures: `<required-confirmation>`
- No JavaScript execution or remote Source install: `<required-confirmation>`

Final decisions:

- [ ] Every requested capability, host, operation, mapping, limit, and fixture is approved
- [ ] Every unrequested capability remains explicitly denied
- [ ] Typed production Approval passes the local Validator
- [ ] User explicitly authorizes the exact N4G implementation scope

Until all applicable boxes are checked in a later authorized phase, activation
status is `not_approved`.
