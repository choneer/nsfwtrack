# Video Metadata Provider Approval Draft

> Status: **draft / not approved**
>
> Every value below is a placeholder. This document contains no approved
> Provider, real host, endpoint, credential, or response fixture. Filling it in
> later does not activate a Provider; a separate explicit user approval and
> machine-checkable production Approval are still required.

## 1. Identity and product fit

Required record keys in the future typed Approval:

```text
provider_key
display_name
content_scope
product_fit
lawful_access_basis
terms_basis
attribution_policy
metadata_host
asset_host
search_operation
detail_operation
asset_list_operation
response_fixture
rate_limit
content_type
response_limit
field_mapping
error_mapping
```

- `provider_key`: `<required-provider-key>`
- `display_name`: `<required-display-name>`
- `content_scope`: `<required-content-scope>`
- `product_fit`: `<required-nsfw-core-fit>`
- `lawful_access_basis`: `<required-lawful-access-basis>`
- `terms_basis`: `<required-terms-or-api-basis>`
- `attribution_policy`: `<required-attribution-policy>`
- Explicit exclusions: `<required-explicit-exclusions>`

Approval state:

- [ ] Provider identity approved
- [ ] Product and lawful-use basis approved
- [ ] Attribution/retention obligations approved
- [ ] Final production scope approved

## 2. Fixed hosts

Wildcards, suffix rules, response-discovered hosts, user-entered hosts, and
unreviewed redirects are invalid.

| Purpose | Host ID | Exact hostname | Port | Auth allowed | Approved |
|---|---|---|---|---|---|
| `metadata_host` | `<metadata-host-id>` | `<exact-metadata-hostname>` | `<required-port>` | `<required-auth-policy>` | `[ ]` |
| `asset_host` | `<asset-host-id>` | `<exact-asset-hostname>` | `<required-port>` | `<required-auth-policy>` | `[ ]` |

Additional fixed hosts: `<none-or-explicit-placeholder-rows>`

## 3. Operations

### `search_operation`

- Path template: `<fixed-search-path-template>`
- Method and encoding: `<fixed-method-and-encoding>`
- Typed input mapping: `<query-page-page-size-mapping>`
- Authentication: `<required-auth-mode-or-none>`
- Content-Type: `<approved-content-type>`
- Response limit: `<approved-byte-limit>`
- Page-size/rate limit: `<approved-page-and-rate-limit>`
- Response fixture: `<reviewed-search-fixture-reference>`
- Approved: `[ ]`

### `detail_operation`

- Path template: `<fixed-detail-path-template>`
- Method and encoding: `<fixed-method-and-encoding>`
- Typed input mapping: `<external-id-mapping>`
- Authentication: `<required-auth-mode-or-none>`
- Content-Type: `<approved-content-type>`
- Response limit: `<approved-byte-limit>`
- Rate limit: `<approved-rate-limit>`
- Response fixture: `<reviewed-detail-fixture-reference>`
- Approved: `[ ]`

### `asset_list_operation`

- Requested: `<yes-or-no-after-review>`
- Path template: `<fixed-asset-list-path-or-not-applicable>`
- Method and encoding: `<fixed-method-and-encoding-or-not-applicable>`
- Typed input mapping: `<external-id-mapping-or-not-applicable>`
- Authentication: `<required-auth-mode-or-none>`
- Content-Type: `<approved-content-type-or-not-applicable>`
- Response limit: `<approved-byte-limit-or-not-applicable>`
- Rate limit: `<approved-rate-limit-or-not-applicable>`
- Response fixture: `<reviewed-asset-fixture-reference-or-not-applicable>`
- Approved: `[ ]`

`discover`, `asset_resolve`, authentication operations, playback, and download
are not requested by this draft and remain denied.

## 4. Field mapping

| Provider-neutral field | Reviewed payload location/type | Required | Merge/provenance rule | Approved |
|---|---|---:|---|---|
| `external_id` | `<required>` | `<required>` | `<required>` | `[ ]` |
| `catalog_number` | `<required>` | `<required>` | `<required>` | `[ ]` |
| `title` / `alternate_titles` | `<required>` | `<required>` | `<required>` | `[ ]` |
| `summary` | `<required>` | `<required>` | `<required>` | `[ ]` |
| `release_date` / `duration_seconds` | `<required>` | `<required>` | `<required>` | `[ ]` |
| `performers` / `director` | `<required>` | `<required>` | `<required>` | `[ ]` |
| `studio` / `publisher` / `series` | `<required>` | `<required>` | `<required>` | `[ ]` |
| `tags` | `<required>` | `<required>` | `<raw-and-normalized-rule>` | `[ ]` |
| `rating` | `<required>` | `<required>` | `<scale-rule>` | `[ ]` |
| `canonical_url` | `<required>` | `<required>` | `<attribution-only-rule>` | `[ ]` |
| `cover` / `preview_images` / `preview_video` | `<required>` | `<required>` | `<opaque-asset-rule>` | `[ ]` |
| `source_updated_at` / `available_fields` | `<required>` | `<required>` | `<required>` | `[ ]` |

## 5. Error and fixture gate

- `error_mapping`: `<required-complete-stable-error-mapping>`
- `response_fixture`: `<required-redacted-static-fixture-set>`
- Malformed/duplicate-key/non-finite fixture: `<required>`
- Oversized/content-type fixture: `<required>`
- 401/403/404/429/5xx fixture: `<required>`
- Timeout/cancel/unknown fixture: `<required>`
- Fixture provenance and redistribution basis: `<required>`
- Fixture contains no credential or live locator: `<required-confirmation>`

Final decision:

- [ ] Every required placeholder has been replaced with reviewed facts
- [ ] Typed production Approval passes the local Validator
- [ ] User explicitly authorizes the exact N4D implementation scope

Until all boxes are checked in a later authorized phase, activation status is
`not_approved` and the Production Provider Registry must remain unchanged.

## 6. N4D-A typed policy placeholders

These fields are required by the current Approval contract but remain entirely
unfilled in this draft:

- `fixed_non_secret_headers`: `<placeholder-only; no real header names or values>`
- `fixed_header_case_order_rule`: `<case-insensitive name, case-sensitive value, order-independent>`
- `fixed_header_forbidden_name_rule`: `<placeholder for complete deny list>`
- `fixed_header_auth_value_rule`: `<Bearer/Basic/Token/ApiKey forms denied>`
- `connect_timeout_seconds`: `<3.0 only for current shared client>`
- `total_timeout_seconds`: `<10.0 only for current shared client>`
- `error_mapping_profile`: `<shared_outbound_v1 only>`
- `raw_payload_retention`: `<discard for production>`
- `test_fixture_raw_payload_retention`: `<test_fixture_only only with test_fixture scope>`

This draft still contains no real Provider, Host, Endpoint, Header, credential,
raw payload, or Fixture. Fixed headers are not an authentication channel, and
the policy placeholders do not authorize any network or Registry action.
