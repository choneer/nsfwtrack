# Phase 5-N5C-B2 — Session-Bound Preview / Confirm UI（完成）

## 完成结果

Phase 5-N5C-B2 已完成。N5C 现已形成：

```text
Search → Detail → signed Preview → explicit Confirm → local Apply
```

- 新增 `app/provider_apply/web.py`，只负责 Session-bound Web key material。
- 已认证 Detail Preview 按需创建或修复 64 lowercase-hex Session nonce；Confirm
  只读取既有 nonce，绝不隐式创建。
- Session generation 与 app generation 使用 constant-time exact comparison；
  cross-session、logout/relogin、generation rotation 后旧 Token 均失效。
- `SECRET_KEY`、generation 与 nonce 通过两个独立 HMAC-SHA256 domain 分别派生
  exact 32-byte secret 与 bounded opaque context；secret/context/nonce/generation
  不进入模板可见内容、URL、flash、日志、错误、数据库或 app/module cache。
- POST `/source-search/detail` 保持 Provider detail exactly once，search/asset_list 为 0；
  N5C-A Plan builder 只执行 bounded SELECT，数据库零写入。
- 有变化时签发固定 600 秒 Token；Token 只在 autocomplete-off hidden input，响应为
  `Cache-Control: no-store` / `Pragma: no-cache`。
- no-op 不签 Token、不显示确认表单、不创建 nonce。
- Preview 显示 create/update、安全字段 current/proposed、will-write/keep-local、
  duplicate-title warning/link、10-minute expiry、Confirm 不重调 Provider 与 stale 提示；
  不显示 canonical/source URL、external ID、metadata hash 或 key material。
- 新增认证 POST `/source-search/apply`，精确要求 `confirmation=apply`；不读取 Provider
  catalog，不调用任何 Provider operation，每请求最多调用 N5C-B1 apply 一次。
- 成功使用 303 Item PRG 与稳定中英文 success/info flash；普通失败返回 source search。
- `commit_state_unknown` 不自动重试，303 到 `/items`，明确要求先检查本地条目并禁止
  直接重复提交。Token 不进入 Location、flash 或日志。
- GET `/source-search` 继续保持 Provider operation 0、DB call 0、nonce/Token/apply 0，
  production empty state 不变。

## 验证证据

```text
focused B2: 36 passed
specified N4D/N5A/N5B/N5C regression: 323 passed
full suite: 1388 passed
```

提交前还需执行并记录：

```text
.venv/bin/python -m pip check
git diff --check
git status --short
```

固定不变量：

```text
Application = 1.1.0
Schema = 4
Backup = nsfwtrack.backup.v2
Production Registry = EndpointRegistry(())
Production Search Packages = ()
Production Search Providers = ()
```

未接入真实 Provider、Host、Endpoint 或 fixture；未实现认证/Vault、远程图片、播放、
下载、自动 Apply、后台任务、同步、Schema/Migration/Backup format/依赖、Docker/Compose/CI
变化。未调用 Hermes，未创建 Tag/Release，未部署 N100，既有 `data/` 未接触。

最终发布门禁仍为：创建并普通 fast-forward 推送唯一提交
`Add session-bound provider apply UI`，等待 GitHub Actions `test` 与
`Docker production smoke` 均成功后报告。
