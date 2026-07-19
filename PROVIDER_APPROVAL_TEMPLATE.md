# Provider Approval Template

> Complete every required field with user-supplied facts. Do not infer, search
> for, recommend, or substitute a Provider, host, endpoint, authentication mode,
> or download source. Unchecked or incomplete sections are not approved.

## Machine-checkable gate

Phase 5-N4B adds a frozen, typed, Provider-neutral `ProviderApproval` model and
pure local validation against code-owned `ProviderCapabilities` and
`ProviderEndpoint` objects. Completing this human template does not construct,
register, enable, or contact a Provider. Before any real N4 activation, every
approved fact must be represented explicitly in the typed production-scope
Approval and pass all capability, operation, host, method, encoding, auth,
cookie, response, redirect, Asset Host, rate, and limit comparisons.

Fixture approvals use only reserved `.invalid` hosts and are explicitly
test-only; they can never pass the production activation gate. Approval objects
contain policy facts only, never token, password, cookie, client-secret, or
other credential values. Missing or mismatched facts remain blockers, and no
Approval is loaded from a URL, environment substitution, include, template, or
Python import.

Phase 5-N4D-D-A adds a separate immutable Artifact handoff. Completing this
template still does not create an Artifact automatically: a future authorized
phase must encode every approved typed fact into exact
`nsfwtrack.provider-approval` version `1` canonical JSON, attach its local
SHA-256 integrity digest, and select only an opaque code-owned Adapter binding
ID. The Artifact cannot carry a callable, module/class path, environment value,
credential, raw response or remote trust statement.

Phase 5-N4D-D-B0 repository evidence is contract reference only. JavSP,
JavdBviewed, FnDepot and Venera do not fill any placeholder in this template and
cannot be named as an approved Provider by inference. A future approval may use
the field/provenance/merge vocabulary and the `search`/`detail`/optional
`asset_list` operation profile, but must still supply every Provider-specific
fact below directly and explicitly.

## 1. Approval record

- Approval identifier: `<required>`
- Approval date: `<required>`
- Approved target phase: `<required>`
- Approving user: `<required>`
- Provider display name: `<required>`
- Code-owned Provider key: `<required>`
- Requested implementation scope: `<required>`
- Explicit exclusions: `<required>`

## 2. Product fit and authority

- NSFW-first core relevance: `<required>`
- Intended content scope: `<required>`
- Out-of-scope content: `<required>`
- User's lawful access basis: `<required>`
- Terms/API/use-policy basis: `<required>`
- Access-control boundaries: `<required>`
- Attribution requirement: `<required>`
- Attribution text/fields: `<required or not-applicable with reason>`
- Attribution display location: `<required or not-applicable with reason>`
- Retention/deletion obligations: `<required>`
- Regional/account/age/subscription constraints: `<required>`

User decision:

- [ ] Provider identity and NSFW-core relevance approved
- [ ] Legal/terms/access basis approved
- [ ] Attribution and retention obligations approved

## 3. Capability manifest

### 3.1 Metadata

- [ ] `search` requested
- [ ] `detail` requested
- Approved metadata limitations: `<required>`

### 3.2 Auth

- [ ] Authentication capability requested
- Approved auth operations: `<required or not-applicable>`

### 3.3 Discovery

- [ ] `discover` requested
- Discovery bounds and trigger: `<required or not-applicable>`
- Maximum candidates per request: `<required or not-applicable>`

### 3.4 Asset

- [ ] `asset_list` requested
- [ ] `asset_resolve` requested
- Approved asset kinds: `<required or not-applicable>`

### 3.5 Download

- [ ] `download` requested
- Approved download kinds: `<required or not-applicable>`
- Maximum selected files per request: `<required or not-applicable>`
- Maximum aggregate bytes per request: `<required or not-applicable>`

- Capability combinations and denied implications: `<required>`
- Operations explicitly not approved: `<required>`

User decision:

- [ ] Every requested capability is individually approved
- [ ] Every non-requested capability remains denied

## 4. Exact host allowlists

List every host separately. Wildcards, suffix rules, user-entered hosts, and
response-discovered hosts are not valid entries.

### 4.1 Metadata hosts

| Host ID | Exact lowercase ASCII hostname | Port | Purpose | Authentication allowed | User approved |
|---|---|---|---|---|---|
| `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `[ ]` |

Additional metadata host rows: `<add explicit rows or state none>`

### 4.2 Authentication hosts

| Host ID | Exact lowercase ASCII hostname | Port | Purpose | Credential fields allowed | User approved |
|---|---|---|---|---|---|
| `<required or not-applicable>` | `<required or not-applicable>` | `<required or not-applicable>` | `<required or not-applicable>` | `<required or not-applicable>` | `[ ]` |

Additional authentication host rows: `<add explicit rows or state none>`

### 4.3 Asset hosts

| Host ID | Exact lowercase ASCII hostname | Port | Asset kinds | Authentication allowed | User approved |
|---|---|---|---|---|---|
| `<required or not-applicable>` | `<required or not-applicable>` | `<required or not-applicable>` | `<required or not-applicable>` | `<required or not-applicable>` | `[ ]` |

Additional asset host rows: `<add explicit rows or state none>`

### 4.4 Host policy

- DNS answer policy: `<required>`
- Numeric-IP pinning requirement: `<required>`
- TLS hostname/SNI/Host requirement: `<required>`
- TCP and TLS peer verification: `<required>`
- Redirect host expansion: `<required>`
- Cross-host credential forwarding: `<required>`

User decision:

- [ ] Every metadata host approved exactly
- [ ] Every authentication host approved exactly or explicitly not applicable
- [ ] Every asset host approved exactly or explicitly not applicable
- [ ] No wildcard or response-discovered host approved

## 5. Fixed operation and endpoint registry

Create one row for every operation. Do not combine search, detail, discovery,
asset listing, asset resolution, authentication, and download into one row.

| Operation ID | Capability layer | Host ID | Fixed path template | Method | Request encoding | Auth requirement | Response kind | User approved |
|---|---|---|---|---|---|---|---|---|
| `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `<required>` | `[ ]` |

For each operation, complete a separate block:

### Operation: `<required>`

- Fixed host reference: `<required>`
- Fixed path template: `<required>`
- Path parameters and validation: `<required or none>`
- Query parameters and validation: `<required or none>`
- HTTP method: `<required>`
- Request encoding: `<required or none>`
- Typed request fields: `<required or none>`
- Fixed non-secret headers: `<required or none>`
- Fixed header names are non-sensitive, printable, static, and exact-approved:
  `<required or none>`
- Fixed header name case/order comparison and duplicate rejection: `<required>`
- Forbidden/credential-like header rejection: `<required>`
- Fixed header value authentication-form rejection: `<required>`
- Credential injection field/location: `<required or none>`
- Approved cookie names/scopes: `<required or none>`
- Response kind: `<required>`
- Allowed response content types: `<required>`
- Top-level response shape: `<required or not-applicable>`
- Maximum response bytes: `<required>`
- Connect deadline: `<required; current shared value is 3.0 seconds>`
- Total deadline: `<required; current shared value is 10.0 seconds>`
- Typed timeout policy exact-match result: `<required>`
- Provider concurrency limit: `<required>`
- Per-operation rate limit: `<required>`
- Pagination model and maximum: `<required or not-applicable>`
- Redirect allowed: `<required>`
- Redirect maximum hops: `<required or zero>`
- Exact redirect host/path rules: `<required or none>`
- Authentication retained across redirect: `<required or no>`
- Stable status/error mapping: `<required; current profile is shared_outbound_v1>`
- Error mapping profile: `<required; exact typed profile>`
- Raw payload retention: `<required; production must be discard>`
- Test-fixture-only raw retention scope: `<required or not-applicable>`
- User approval: `[ ]`

Additional operation blocks: `<add one complete block per operation>`

## 6. Authentication approval

Select only approved modes:

- [ ] `none`
- [ ] `api_token`
- [ ] `oauth`
- [ ] `username_password`
- [ ] `session_cookie`

- Public operations: `<required>`
- Protected operations and scopes: `<required or none>`
- Credential fields: `<required or none>`
- Credential acquisition flow: `<required or none>`
- Authentication test flow: `<required or none>`
- Expiry detection: `<required or none>`
- Refresh flow and retry bound: `<required or none>`
- Logout flow: `<required or none>`
- Remote revocation flow: `<required or none>`
- Local removal outcome rules: `<required or none>`
- Long-term password retention required: `<required>`
- Long-term password retention reason: `<required or not-applicable>`
- Token placement: `<required or not-applicable>`
- Token scopes: `<required or not-applicable>`
- Authorization host reference: `<required or not-applicable>`
- Token host reference: `<required or not-applicable>`
- Callback rule: `<required or not-applicable>`
- OAuth state rule: `<required or not-applicable>`
- PKCE rule: `<required or not-applicable>`
- Session cookie names: `<required or not-applicable>`
- Cookie Domain: `<required or not-applicable>`
- Cookie Path: `<required or not-applicable>`
- Cookie Secure/SameSite requirements: `<required or not-applicable>`
- Cookie expiry behavior: `<required or not-applicable>`
- 401/403 behavior: `<required>`
- Unknown auth outcome behavior: `<required>`
- Secret replacement and rollback behavior: `<required>`

User decision:

- [ ] Authentication mode and every credential field approved
- [ ] Secret lifecycle, expiry, refresh, logout, and revocation approved
- [ ] Any long-term password retention separately approved or denied

## 7. Secret Vault implications

- Provider Secret Vault required: `<required>`
- Required envelope fields: `<required or not-applicable>`
- Required auth-mode binding: `<required or not-applicable>`
- Required key rotation behavior: `<required or not-applicable>`
- Required new encryption dependency: `<required>`
- Dependency name/version/rationale: `<required or not-applicable>`
- Failure behavior when key is unavailable: `<required>`
- Backup inclusion: `<required>`
- Configuration export inclusion: `<required>`
- Migration from any prior secret format: `<required or not-applicable>`

User decision:

- [ ] Secret Vault requirements approved
- [ ] Dependency implication approved or explicitly denied
- [ ] Ordinary backup/configuration exclusion approved

## 8. Search mapping

- Query input fields: `<required or not-applicable>`
- Query length/character rules: `<required or not-applicable>`
- Pagination request mapping: `<required or not-applicable>`
- Result external ID mapping: `<required or not-applicable>`
- Canonical URL mapping/validation: `<required or not-applicable>`
- Title mapping: `<required or not-applicable>`
- Creator mapping: `<required or not-applicable>`
- Tag mapping: `<required or not-applicable>`
- Date mapping: `<required or not-applicable>`
- Summary mapping: `<required or not-applicable>`
- Content-type mapping: `<required or not-applicable>`
- Provider-updated timestamp mapping: `<required or not-applicable>`
- Missing/null field semantics: `<required or not-applicable>`
- Maximum returned results: `<required or not-applicable>`
- Attribution mapping: `<required or not-applicable>`
- Raw response persistence: `<required>`

User decision:

- [ ] Search input, pagination, limits, and every output mapping approved

## 9. Detail mapping

- External ID request mapping: `<required or not-applicable>`
- Canonical URL mapping/validation: `<required or not-applicable>`
- Title mapping: `<required or not-applicable>`
- Creator mapping: `<required or not-applicable>`
- Tag mapping: `<required or not-applicable>`
- Date mapping: `<required or not-applicable>`
- Summary mapping: `<required or not-applicable>`
- Content-type mapping: `<required or not-applicable>`
- Provider-updated timestamp mapping: `<required or not-applicable>`
- Missing/null field semantics: `<required or not-applicable>`
- Asset-summary mapping: `<required or not-applicable>`
- Attribution mapping: `<required or not-applicable>`
- Raw response persistence: `<required>`

User decision:

- [ ] Detail input and every output mapping approved

## 10. Discovery approval

- Discovery enabled: `<required>`
- User trigger: `<required or not-applicable>`
- Input fields: `<required or not-applicable>`
- Candidate source and bounds: `<required or not-applicable>`
- Maximum pages/results: `<required or not-applicable>`
- Local preference upload: `<required>`
- Automatic import: `<required>`
- Automatic download: `<required>`
- Link traversal/recursion: `<required>`

User decision:

- [ ] Discovery approved with exact bounds or explicitly denied

## 11. Asset listing and resolution

- Asset listing enabled: `<required>`
- Asset resolution enabled: `<required>`
- Asset ID mapping: `<required or not-applicable>`
- Asset ID stability/expiry: `<required or not-applicable>`
- Approved asset kinds: `<required or not-applicable>`
- Display-name mapping: `<required or not-applicable>`
- MIME mapping: `<required or not-applicable>`
- Size mapping: `<required or not-applicable>`
- Checksum algorithm/value mapping: `<required or not-applicable>`
- Authentication requirement by asset kind: `<required or not-applicable>`
- Download eligibility mapping: `<required or not-applicable>`
- Maximum assets per item: `<required or not-applicable>`
- Locator lifetime: `<required or not-applicable>`
- Locator path grammar: `<required or not-applicable>`
- Locator query grammar: `<required or not-applicable>`
- Locator binding fields: `<required or not-applicable>`
- Locator persistence: `<required>`
- Locator UI/log exposure: `<required>`
- Re-resolution behavior: `<required or not-applicable>`

User decision:

- [ ] Asset list mapping approved or explicitly denied
- [ ] Dynamic locator rules approved or explicitly denied

## 12. Download approval

- Download enabled: `<required>`
- User confirmation text/gesture: `<required or not-applicable>`
- Single-download limit: `<required or not-applicable>`
- Small-batch file-count limit: `<required or not-applicable>`
- Small-batch aggregate-byte limit: `<required or not-applicable>`
- Global hard byte limit: `<required or not-applicable>`
- Provider byte limit: `<required or not-applicable>`
- Operation byte limit: `<required or not-applicable>`
- Per-asset byte limit: `<required or not-applicable>`
- Allowed Content-Types: `<required or not-applicable>`
- Required magic/signature checks: `<required or not-applicable>`
- Provider checksum algorithm: `<required or not-applicable>`
- Local SHA-256 requirement: `<required or not-applicable>`
- Content-Length treatment: `<required or not-applicable>`
- Range supported: `<required or not-applicable>`
- Range required: `<required or not-applicable>`
- Truncated/overlong stream behavior: `<required or not-applicable>`
- Redirect rules: `<required or not-applicable>`
- Download authentication/cookie forwarding: `<required or not-applicable>`
- Remote filename treatment: `<required or not-applicable>`
- Local naming strategy: `<required or not-applicable>`
- Temporary isolation location/policy: `<required or not-applicable>`
- No-overwrite publication rule: `<required or not-applicable>`
- Local relationship target: `<required or not-applicable>`
- Source/provenance relationship: `<required or not-applicable>`
- Existing-file/deduplication behavior: `<required or not-applicable>`
- Cancellation behavior before/after publication: `<required or not-applicable>`
- Cleanup-failure recovery entry: `<required or not-applicable>`
- Commit-error independent review: `<required or not-applicable>`
- Outcome-unknown behavior: `<required or not-applicable>`
- Media-index coordination: `<required or not-applicable>`
- Automatic retry: `<required>`
- Hidden/background execution: `<required>`

User decision:

- [ ] Download kinds, limits, MIME/magic/hash rules approved or explicitly denied
- [ ] Naming, provenance, relationship, cancellation, cleanup, and outcome rules approved
- [ ] Range and redirect behavior approved or explicitly denied

## 13. Stable errors and logging

- Provider status-to-error mapping: `<required>`
- Authentication error mapping: `<required or not-applicable>`
- Asset error mapping: `<required or not-applicable>`
- Download error mapping: `<required or not-applicable>`
- Rate-limit representation: `<required>`
- Unknown-outcome representation: `<required>`
- User-visible redaction rules: `<required>`
- Log allowlisted fields: `<required>`
- Log forbidden fields: `<required>`
- Provider raw-response handling: `<required>`

User decision:

- [ ] Stable error and redaction contract approved

## 14. Deterministic fixtures and fault matrix

### 14.1 Fixtures

- Fixture provenance: `<required>`
- Fixture licensing/terms: `<required>`
- Secret/identifier sanitization: `<required>`
- Static search fixtures: `<required or not-applicable>`
- Static detail fixtures: `<required or not-applicable>`
- Static discovery fixtures: `<required or not-applicable>`
- Static asset fixtures: `<required or not-applicable>`
- Static auth fixtures: `<required or not-applicable>`
- Static file-byte fixtures: `<required or not-applicable>`
- Fake DNS/transport/clock plan: `<required>`
- Confirmation that tests use no real network: `[ ]`

### 14.2 Required fault cases

- [ ] Authentication success
- [ ] Authentication failure
- [ ] Authentication expiry
- [ ] Authentication revocation
- [ ] Authentication outcome unknown
- [ ] 401
- [ ] 403
- [ ] 404
- [ ] 429
- [ ] 5xx
- [ ] Malformed payload
- [ ] Duplicate/ambiguous payload fields
- [ ] Oversized response
- [ ] Timeout
- [ ] Cancellation
- [ ] Unsafe or mixed DNS result
- [ ] TLS/peer mismatch
- [ ] Disallowed asset host
- [ ] Invalid/expired locator
- [ ] Redirect denial and approved redirect bound
- [ ] Oversized file
- [ ] Truncated/overlong stream
- [ ] Content-Type mismatch
- [ ] Magic/signature mismatch
- [ ] Provider hash mismatch
- [ ] Temporary-file failure
- [ ] No-overwrite conflict
- [ ] Parent/object replacement
- [ ] Publication failure
- [ ] Database relationship failure
- [ ] Commit raised after commit
- [ ] Cleanup failure
- [ ] Outcome unknown
- [ ] One media-index coordination per request
- [ ] Log and public-error redaction

- Additional Provider-specific fault cases: `<required or none>`

User decision:

- [ ] Fixture set and complete fault matrix approved

## 15. Dependency, Schema, and backup implications

- New direct dependency required: `<required>`
- Dependency details and alternatives: `<required or not-applicable>`
- Schema change required: `<required>`
- Schema change details and rollback: `<required or not-applicable>`
- Migration required: `<required>`
- Migration details: `<required or not-applicable>`
- Backup format change required: `<required>`
- Backup behavior details: `<required or not-applicable>`
- Secret Vault excluded from ordinary backup: `<required>`
- Application version implication: `<required>`
- Separate authorization required before implementation: `<required>`

User decision:

- [ ] Dependency implications approved or explicitly denied
- [ ] Schema/migration implications approved or explicitly denied
- [ ] Backup implications approved or explicitly denied

## 16. Provider Approval Artifact v1 handoff

- Artifact ID: `<required opaque identifier>`
- Artifact format: `nsfwtrack.provider-approval`
- Artifact version: `1`
- Artifact creation time (UTC): `<required>`
- Review revision: `<required opaque identifier>`
- Approval/Capabilities/Endpoint/Evidence parity reviewed: `<required>`
- Fixture digest catalog reviewed: `<required>`
- Canonical bytes reproduced independently: `<required>`
- SHA-256 attestation verified: `<required>`
- Attestation understood as integrity-only, not signature/trust: `<required>`
- Opaque code-owned Adapter binding ID: `<required>`
- Binding metadata parity reviewed: `<required>`
- Artifact contains no callable/module/class/path/URL/credential/raw response:
  `<required>`
- N4D-D-A offline loader result: `<required>`

User decision:

- [ ] I approve the exact canonical Artifact bytes and SHA-256 integrity value.
- [ ] I understand the Artifact does not itself authorize network access or trust.
- [ ] I approve the exact code-owned binding ID and no dynamic import mechanism.
- [ ] I authorize a separate N4D-D-B implementation only for these reviewed facts.

## 17. Final explicit approval

- Completed sections reviewed: `<required>`
- Remaining blanks: `<required; must be none>`
- Remaining ambiguities: `<required; must be none>`
- Provider facts supplied by user rather than inferred/searched: `<required>`
- Exact approved N4 implementation boundary: `<required>`
- Capabilities deferred to later phases: `<required>`
- Additional prohibitions: `<required or none>`

Final decisions:

- [ ] I explicitly approve this Provider identity and its NSFWTrack core use.
- [ ] I explicitly approve every listed metadata, auth, and asset host.
- [ ] I explicitly approve every listed endpoint, method, encoding, response
      kind, content type, size/rate limit, and redirect rule.
- [ ] I explicitly approve the selected authentication mode and secret lifecycle.
- [ ] I explicitly approve the search/detail mappings and any discovery,
      asset-list, asset-resolve, and download capabilities marked above.
- [ ] I explicitly approve the dynamic locator, file limit, MIME, magic, hash,
      Range, naming, provenance, publication, relationship, and outcome rules.
- [ ] I explicitly approve the deterministic fixtures and full fault matrix.
- [ ] I explicitly approve or deny every dependency, Schema, migration, and
      backup implication.
- [ ] I understand that unchecked, blank, ambiguous, or unlisted capabilities,
      hosts, endpoints, auth modes, and download sources remain denied.
- [ ] I authorize N4 implementation only within the completed scope above.

- Final approval statement: `<required explicit user statement>`
- Final approval date: `<required>`
- Approving user: `<required>`

Until every required field is complete and the final decisions are checked,
implementation MUST NOT begin and no host, endpoint, auth mode, download source,
dependency, or Schema behavior may be inferred or substituted.
