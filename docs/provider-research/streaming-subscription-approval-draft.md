# Subscription and Streaming Provider Approval Draft

> Status: **draft / not approved**
>
> All values are placeholders. No real subscription host, Provider host,
> endpoint, credential, manifest, or approved candidate appears here. Catalog
> source Approval and runtime Streaming Provider Approval are separate gates.

## 1. Subscription catalog source

- Catalog approval ID: `<required-catalog-approval-id>`
- Subscription Host ID: `<required-subscription-host-id>`
- Exact subscription hostname: `<required-exact-hostname>`
- Port: `<required-port>`
- Fixed Path: `<required-fixed-path>`
- Method: `<required-fixed-method>`
- Authentication mode: `<required-mode-or-none>`
- Content-Type: `<required-content-type>`
- Maximum compressed response: `<required-byte-limit>`
- Maximum actual response: `<required-byte-limit>`
- Deadline/rate limit: `<required-deadline-and-rate-limit>`
- Lawful access/terms basis: `<required-use-basis>`
- Attribution/retention policy: `<required-policy>`
- Refresh trigger: `<must-be-explicit-authenticated-post>`
- Approved: `[ ]`

## 2. Subscription JSON schema

- Envelope/version: `<required-reviewed-envelope-and-version>`
- Top-level type: `<required-reviewed-type>`
- Unknown-key policy: `<required-policy>`
- Duplicate-key/item policy: `<required-policy>`
- Revision identity policy: `<required-policy>`

| Input key | Exact type | Required | Bounds/normalization | Approved |
|---|---|---:|---|---|
| `id` | `<required>` | `<required>` | `<required>` | `[ ]` |
| `name` | `<required>` | `<required>` | `<required>` | `[ ]` |
| `baseUrl` | `<required>` | `<required>` | `<candidate-only-no-access-rule>` | `[ ]` |
| `group` | `<required>` | `<required>` | `<ordinary-and-premium-display-rule>` | `[ ]` |
| `enabled` | `<required>` | `<required>` | `<recommendation-only-rule>` | `[ ]` |
| `priority` | `<required>` | `<required>` | `<bounded-display-order-rule>` | `[ ]` |

- Reviewed static fixture: `<required-redacted-fixture-reference>`
- Fixture redistribution basis: `<required>`
- Candidate addresses remain uncontacted: `<required-confirmation>`

## 3. Candidate under review

- Candidate Provider ID: `<required-candidate-id>`
- Candidate display name: `<required-display-name>`
- Subscription revision: `<required-revision-id>`
- Group: `<required-group>`
- Source-enabled fact: `<required-boolean>`
- Source priority: `<required-integer>`
- Candidate Approval state: `<must-start-unreviewed-or-drafted>`
- Candidate base URL fact: `<required-candidate-value-not-authority>`
- Approved for production activation: `[ ]`

The ordinary/`premium` group does not approve authentication, subscription
entitlement, playback, or download.

## 4. Runtime Provider identity and hosts

- Runtime `provider_key`: `<required-provider-key>`
- Content scope/product fit: `<required>`
- Lawful access/terms basis: `<required>`
- Attribution policy: `<required>`

| Purpose | Host ID | Exact hostname | Port | Credential scope | Approved |
|---|---|---|---|---|---|
| Metadata Host | `<required>` | `<required>` | `<required>` | `<required>` | `[ ]` |
| Asset Host | `<required-or-not-applicable>` | `<required-or-not-applicable>` | `<required>` | `<required>` | `[ ]` |
| Playback Host | `<required-or-not-applicable>` | `<required-or-not-applicable>` | `<required>` | `<required>` | `[ ]` |
| Redirect Host | `<required-or-none>` | `<required-or-none>` | `<required>` | `<required>` | `[ ]` |
| Auth Host | `<required-or-none>` | `<required-or-none>` | `<required>` | `<required-fields-not-values>` | `[ ]` |

No wildcard, suffix, response-discovered, or candidate-derived host is valid.

## 5. Operations and playback policy

| Operation | Fixed path | Method/encoding | Typed inputs | Response type | Limit | Auth | Approved |
|---|---|---|---|---|---|---|---|
| `search` | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `[ ]` |
| `detail` | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `[ ]` |
| `playback_list` | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `[ ]` |
| `playback_resolve` | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `[ ]` |

- Authentication requirements/lifecycle: `<required>`
- Cookie names and lifecycle, never values: `<required-or-none>`
- Playback manifest type: `<required-reviewed-type>`
- Relative-reference/query inheritance rule: `<required-reviewed-rule>`
- Manifest/variant/segment bounds: `<required>`
- Maximum media size: `<required-or-not-applicable>`
- Redirect policy: `<required-exact-policy>`
- Expiry/cancellation policy: `<required>`
- Download requested: `<must-be-no-unless-separately-approved>`

## 6. Mapping, errors, and evidence

- Metadata field mapping: `<required-complete-mapping>`
- Playback group/source/variant/manifest mapping: `<required-complete-mapping>`
- Error mapping: `<required-complete-stable-error-mapping>`
- Search/detail/playback fixtures: `<required-static-redacted-fixtures>`
- 401/403/404/429/5xx fixtures: `<required>`
- Invalid/oversized/expired/cancelled/unknown fixtures: `<required>`
- No live locator/credential in fixtures: `<required-confirmation>`
- No userscript execution or access-control bypass: `<required-confirmation>`

Final decisions:

- [ ] Catalog source is separately approved
- [ ] Candidate is explicitly selected for a production Approval review
- [ ] Runtime Provider identity, every host, operation, auth rule, and limit is approved
- [ ] Typed production Approval passes the local Validator
- [ ] User explicitly authorizes N4E and/or N4F implementation scope

Until a later phase checks every applicable box, both catalog activation and
runtime Provider activation remain `not_approved`.
