# Egress diagnostics (branch `nsfwtrack_grok`)

## Scope

- **Page:** `/egress` (session auth required)
- **APIs:** `GET /api/egress/status`, `GET /api/egress/probe-quality`
- **Package:** `app/egress/` (stdlib urllib only — independent of Provider `outbound_http` allowlists)

## What it does

1. **Multi-source MyIP** (OpenClash-style): concurrent probes to api.ip.sb, ipify, ip-api, myip.ipip.net, upaiyun; consensus IP + agreement count.
2. **Proxy path**: same probes through `NSFW_HTTP_PROXY` / standard proxy env / selected pool entry.
3. **Proxy pool**: load `data/proxy-pool.json` (or `NSFW_PROXY_POOL_CONFIG`), probe exit IP + geo/risk, optional quality grade (sub2api-style fixed public targets).
4. **JavDB hint**: flag if proxy consensus country is JP/KR (blocked by JavDB). Does **not** enable production JavDB hosts.

## Config

```bash
cp examples/proxy-pool.example.json data/proxy-pool.json
# edit proxy URL(s); file is gitignored
export NSFW_HTTP_PROXY=http://127.0.0.1:6123   # optional override
```

`data/proxy-pool.json` is gitignored. Never commit credentials in proxy URLs.

## Display

UI reuses NSFWTrack light theme (`base.html` cards, metrics, tables) with:

- consensus IP cards + agreement bar
- JavDB geo banner (ok / blocked / unknown)
- pool table with risk pills and quality grades
- collapsible raw JSON for debugging

## Not in scope

- Provider login / CookieCloud / VIP bypass
- Expanding `PRODUCTION_ENDPOINT_REGISTRY`
- SOCKS proxies without a local HTTP relay (use Clash HTTP port)

## Attribution / upstream ideas

- OpenClash multi-source MyIP check pattern
- sub2api-style proxy quality targets
- Geo: api.ip.sb / ip-api.com (public endpoints for local diagnostics only)
