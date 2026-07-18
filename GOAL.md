# 当前目标：Phase 5-N2 — Schema 4 来源追踪与 Backup v2

## 1. 阶段目标

为 v1.2.0 建立向后兼容的来源身份存储和备份恢复基础。

本阶段实现：

1. Schema `3 → 4` 连续迁移
2. 扩展 `item_sources` 来源追踪字段
3. provider / external ID 唯一身份约束
4. `nsfwtrack.backup.v2`
5. 继续恢复 `nsfwtrack.backup.v1`
6. 来源身份冲突预览与事务化恢复
7. 稳定版 v1.1.0 对 Schema 4 的安全拒绝
8. 完整迁移、备份和 Docker 回归

本阶段不实现真实 provider、外部网络请求、搜索 UI、手动入库 UI 或自动
同步。

Phase 5-N2 完成后进行 GitHub Actions 和云端 diff 复核，不调用 Hermes。

## 2. 授权基线

- 仓库：`/home/nsfwtrack`
- 分支：`main`
- HEAD / `origin/main`：

  `6e7f57b54ffc54cb150c971ebf4edaa53632dc8f`

- 当前正式版本：`v1.1.0`
- 当前应用版本：`1.1.0`
- 当前 Schema：`3`
- 目标开发 Schema：`4`
- 目标发布版本：`v1.2.0`
- N100：未部署

开始前工作区只能是：

    M GOAL.md
    ?? data/

staged 必须为空。

## 3. 必须读取

完整读取：

- `RULE.md`
- `GOAL.md`
- `PLAN.md`
- `TASKS.md`
- `REVIEW.md`
- `README.md`
- `CHANGELOG.md`
- `PERFORMANCE.md`

重点审计：

- `app/models.py`
- `app/services/schema_version.py`
- `app/services/migrations.py`
- Schema upgrade 页面和路由
- `app/services/exporter.py`
- `app/services/backup.py`
- `app/services/backup_validator.py`
- `app/services/sources.py`
- backup 页面和模板
- i18n
- migration / backup / restore / release-security 测试
- Docker 与 CI

不得进入、读取、枚举、复制或修改既有 `data/`。

## 4. 编码前状态矩阵

编码前先在测试或实施说明中固定以下矩阵。

### 4.1 Schema 矩阵

| 数据库状态 | 当前应用行为 |
|---|---|
| 空数据库 | 直接创建完整 Schema 4 |
| Schema 1 | preview/apply 连续执行 1→2→3→4 |
| Schema 2 | preview/apply 连续执行 2→3→4 |
| Schema 3 | preview/apply 执行 3→4 |
| Schema 4 | 正常启动，无需迁移 |
| Schema 5+ | 拒绝启动，application_outdated |
| 结构缺失或版本未知 | 失败关闭，不写入 |
| 迁移任一步骤失败 | 整个事务回滚到原 Schema |

### 4.2 Backup 矩阵

| 输入 | 结果 |
|---|---|
| 合法 backup v1 | 按四个新字段为 null 恢复 |
| 合法 backup v2 | 恢复来源追踪字段 |
| 未知 backup schema | 拒绝 |
| payload 内重复 normalized URL | validation error |
| payload 内重复 provider/external ID | validation error |
| 与本地完全相同的来源映射 | reuse / skip |
| normalized URL 指向不同 Item | hard conflict，零写入 |
| provider/external ID 指向不同 Item | hard conflict，零写入 |
| 同一身份但 URL 或来源事实不一致 | hard conflict，零写入 |
| 无效 provider key、external ID、时间或 hash | validation error |
| restore 中途异常 | 整体事务回滚 |
| preview | 零数据库写入、零网络 |
| apply | 零网络 |

任何不可逆写入后都必须根据真实事务结果重新分类，异常不等于零变化。

## 5. Schema 4 数据模型

更新 `ItemSource`，保留全部现有字段：

- `id`
- `item_id`
- `url`
- `normalized_url`
- `title`
- `created_at`

新增 nullable 字段：

```text
provider_key
external_id
last_checked_at
metadata_hash
```

建议数据库类型：

```text
provider_key     VARCHAR(64)  NULL
external_id      VARCHAR(512) NULL
last_checked_at  DATETIME     NULL
metadata_hash    VARCHAR(96)  NULL
```

要求：

- Schema 3 迁移后的历史行四个字段全部为 null；
- 现有 `normalized_url` 全局唯一约束保持；
- 不删除、重命名或重建现有业务数据；
- 不新增 provider 表；
- 不把媒体索引作为来源数据；
- 不修改 Item、Creator、Tag、状态、合集或媒体模型。

### 5.1 Provider identity

来源身份由以下组合表示：

```text
(provider_key, external_id)
```

要求：

- 两者都为非空时必须唯一；
- 创建 SQLite partial unique index；
- 只有两列均非 null 的行进入唯一索引；
- provider key 为小写代码标识：

  ```text
  [a-z][a-z0-9_-]{0,63}
  ```

- external ID 是 provider 内部 opaque、区分大小写的稳定标识；
- external ID 不做整数转换、不做 casefold；
- legacy URL 来源允许两列都为 null；
- 应用服务不得创建只有其中一列非 null 的新记录。

不得静默把现有 URL 猜测为 provider 身份。

### 5.2 metadata_hash

本阶段固定存储格式：

```text
v1:sha256:<64 个小写十六进制字符>
```

要求：

- nullable；
- 不保存原始 provider response；
- 不保存凭据、Header、Cookie 或未映射 payload；
- N2 只实现存储和备份校验，不计算真实 provider 元数据 hash；
- 真实生成逻辑留给 Phase 5-N6。

### 5.3 last_checked_at

要求：

- nullable；
- 只接受合法 ISO-8601 时间；
- 应用层统一为 timezone-aware datetime；
- N2 不主动更新该字段；
- 备份恢复只能恢复经过校验的值。

## 6. Schema 3 → 4 迁移

在现有 migration registry 中增加唯一连续步骤，例如：

```text
from_version = 3
to_version   = 4
name         = extend_item_sources_provider_metadata
```

### 6.1 Preview

必须只读，并说明：

- 将新增四个 nullable 字段；
- 将创建 provider/external ID partial unique index；
- 现有来源行保持不变；
- 不请求网络；
- 建议升级前备份数据库；
- Schema 4 数据库不能直接交给 v1.1.0。

### 6.2 Precheck

至少验证：

- 当前真实版本为 Schema 3；
- `item_sources` 存在；
- 原有必需字段完整；
- 四个新字段尚不存在；
- 目标索引尚不存在；
- `normalized_url` 唯一性仍存在；
- 无异常结构或未知表替换。

### 6.3 Apply

要求：

- 使用现有 `BEGIN IMMEDIATE` 事务；
- 使用明确的 SQLite DDL；
- 新增字段均允许 null；
- 创建命名稳定的 partial unique index；
- 不扫描网络或媒体；
- 不修改任何现有来源行的字段值；
- 不重新创建或复制整个 `item_sources` 表，除非 SQLite 能力确实无法安全完成；
- 若必须重建表，先停止并报告，不得自行扩大范围。

### 6.4 Postcheck

至少验证：

- 四个字段存在；
- 类型和 nullable 状态符合设计；
- 原有字段、外键和 normalized URL 唯一约束仍存在；
- partial unique index 存在、列顺序正确、unique=true；
- partial predicate 确实要求两列均非 null；
- 所有迁移前历史行四个新字段均为 null；
- Schema migration 版本记录为 4。

只检查索引列名而不检查 partial predicate 不足以通过。

## 7. Fresh Schema 4

空数据库初始化必须直接创建 Schema 4，包括：

- 完整新 ItemSource 字段；
- partial unique index；
- 现有媒体索引表和 singleton；
- SchemaMigration baseline 版本 4。

同时确认：

- fresh Schema 4 与 Schema 3→4 后结构等价；
- `Base.metadata.create_all()` 不负责改造旧数据库；
- 旧数据库只能通过 migration registry 升级。

## 8. 旧版本拒绝

使用隔离临时目录验证：

1. 当前代码创建或迁移一个 Schema 4 数据库；
2. 使用稳定 tag `v1.1.0` 的代码或镜像尝试启动；
3. 预期稳定版拒绝启动，并报告数据库版本高于应用版本；
4. 不允许稳定版写入、降级或改变 Schema 4 数据库。

不得使用既有 `data/`，不得修改 `v1.1.0` tag。

## 9. Backup schema

将现有常量拆分为明确版本：

```python
BACKUP_SCHEMA_V1 = "nsfwtrack.backup.v1"
BACKUP_SCHEMA_V2 = "nsfwtrack.backup.v2"
CURRENT_BACKUP_SCHEMA = BACKUP_SCHEMA_V2
SUPPORTED_BACKUP_SCHEMAS = {
    BACKUP_SCHEMA_V1,
    BACKUP_SCHEMA_V2,
}
```

新导出始终使用：

```text
nsfwtrack.backup.v2
```

恢复继续接受 v1 和 v2。

不得让旧版应用静默忽略 v2 provider metadata，因此不承诺 v2 可恢复到
v1.1.0。

## 10. Backup v2 导出

`item_sources` 每行新增：

```text
provider_key
external_id
last_checked_at
metadata_hash
```

要求：

- 保留现有字段；
- datetime 使用现有稳定 ISO 格式；
- null 保持 JSON null；
- provider/external ID 不转换；
- 不导出 provider 原始响应；
- 不导出搜索临时结果；
- 不导出 outbound 错误或日志；
- 不导出媒体索引；
- 不因导出发起网络请求。

CSV 导出格式本阶段保持不变，除非现有测试要求同步；不得擅自增加新的
CSV 网络来源格式。

## 11. Backup v1 兼容

恢复 v1 时：

- 缺少四个新字段视为 null；
- 保持原有来源 URL、标题和 Item 映射；
- 不猜测 provider；
- 不请求 URL；
- 不生成 metadata hash；
- preview 和 restore 结果必须明确标记输入 schema 为 v1。

现有合法 v1 fixture 必须继续通过。

## 12. Backup v2 校验

每个 v2 `item_sources` 行必须验证：

- `item_id`；
- `url`；
- `normalized_url`；
- `provider_key`；
- `external_id`；
- `last_checked_at`；
- `metadata_hash`。

规则：

- URL 仍通过现有 `normalize_source_url()`；
- normalized URL 必须与重新计算值完全一致；
- provider_key / external_id 必须同时为空或同时非空；
- provider_key 必须符合固定格式；
- external_id 非空、无控制字符、长度不超过 512；
- last_checked_at 必须为合法 timezone-aware ISO datetime；
- metadata_hash 必须符合固定版本格式；
- provider metadata 为 null 时，last_checked_at 和 metadata_hash 是否允许保留，
  必须在编码前明确。推荐要求 provider 身份为空时后二者也必须为空；
- 不要求 provider 当前已注册，因为备份恢复必须能保存暂时不可用的来源记录；
- 不发起网络验证。

## 13. Payload 内重复检查

在接触数据库前检测：

- 重复 backup Item ID；
- 重复 normalized URL；
- 重复非空 `(provider_key, external_id)`；
- 同一来源身份出现不同 URL；
- 同一 URL 出现不同来源身份；
- 半空 provider identity；
- 不一致 metadata。

发现这些问题时：

- preview 返回稳定 validation error；
- apply 禁止执行；
- 不部分恢复其他行；
- 不静默选择任意一行。

## 14. 本地冲突语义

在将 backup Item ID 映射到实际本地 Item 后分类。

### 14.1 Exact reuse

同时满足以下事实才允许 reuse / skip：

- normalized URL 相同；
- 实际目标 Item 相同；
- provider key 相同；
- external ID 相同；
- 不存在相互矛盾的来源事实。

允许 title、last_checked_at 或 metadata_hash 根据既定恢复规则保持本地值，
不得在“reuse”名义下静默覆盖。

### 14.2 Hard conflict

以下任一情况阻止整个恢复：

- normalized URL 已属于另一个实际 Item；
- provider/external ID 已属于另一个实际 Item；
- 同一 provider/external ID 对应不同 normalized URL；
- 同一 normalized URL 对应不同非空 provider/external ID；
- legacy 本地行与 v2 provider 行需要 enrichment，但用户尚未明确批准；
- 无法确定来源身份是否一致。

本阶段 backup restore 不做 legacy enrichment。

### 14.3 Create

只有当：

- normalized URL 不存在；
- provider/external ID 不存在；
- 目标 Item 映射明确；
- 所有字段校验通过；

才允许创建新 ItemSource。

## 15. Preview 结果

扩展 preview 结果，至少包含：

```text
input_schema
item_sources
item_sources_to_create
item_sources_to_reuse
item_sources_conflicts
item_sources_errors
```

必要时增加：

```text
provider_sources
legacy_sources
```

要求：

- 冲突必须有稳定、无敏感信息的分类；
- 不返回完整异常堆栈；
- 不泄露不必要的本地数据；
- preview 零写入；
- preview 不更新 `last_checked_at`；
- preview 不创建锁文件；
- preview 零网络。

若存在 hard conflict，必须明确标记当前恢复不可执行。

## 16. Restore apply

要求：

- 继续使用单一数据库事务；
- apply 前重新执行全部关键校验；
- 不信任旧 preview；
- 恢复过程中不访问网络；
- create/reuse/conflict 分类必须在事务内重新确认；
- hard conflict 导致整次恢复零提交；
- 任意 IntegrityError 或其他异常整体回滚；
- 不删除现有条目或来源；
- 不覆盖不同 Item 的来源；
- 不自动 enrichment legacy 行；
- 成功后按现有规则使派生媒体索引失效；
- 结果摘要报告 create、reuse、skip 和 error 数量。

异常后必须使用独立 Session 或连接确认事务真实结果；不能仅根据异常类型
断言零变化。

## 17. Existing UI 与 i18n

允许更新现有：

- Schema upgrade 页面；
- Backup preview 页面；
- Backup restore 结果；
- 对应中英文文案。

要求：

- 不增加外部来源搜索页面；
- 不增加 provider 配置页面；
- 不增加网络入口；
- 中英文 key 对称；
- GET 页面零写入；
- backup 上传和 preview 仍然零网络；
- Schema upgrade 仍需登录、备份确认和显式 POST apply。

## 18. 安全边界

N2 全阶段必须保证：

- 不调用 `OutboundHttpClient.fetch_json()`；
- 不注册生产 provider；
- 不修改 `PRODUCTION_ENDPOINT_REGISTRY`；
- 不请求真实 DNS；
- 不请求互联网；
- 不读取代理环境；
- 不请求 backup 中的 URL；
- 不下载远程图片；
- 不保存 Cookie、Token 或凭据；
- 不自动同步；
- 不调用 Hermes。

建议增加测试，令网络调用在 migration、backup preview 和 restore 中直接失败，
证明这些流程零网络。

## 19. 允许修改

允许按实际需要修改：

- `app/models.py`
- `app/services/schema_version.py`
- `app/services/migrations.py`
- `app/services/exporter.py`
- `app/services/backup.py`
- `app/services/backup_validator.py`
- `app/services/sources.py`
- 现有 Schema upgrade 路由和模板
- 现有 Backup 路由和模板
- i18n
- 对应测试
- `GOAL.md`
- `README.md`
- `PLAN.md`
- `TASKS.md`
- `REVIEW.md`
- `CHANGELOG.md`

不得修改：

- `app/services/outbound_http.py`，除非为无行为变化的 import/test 兼容修正；
- Adapter contracts 或 registry；
- 外部搜索路由；
- 真实 provider；
- Dockerfile、Compose 或 CI；
- 应用版本；
- tag 或 Release。

不得增加新的第三方依赖。

## 20. 测试

### 20.1 Targeted

至少覆盖：

```text
Schema 3→4
Schema 1→2→3→4
Schema 2→3→4
fresh Schema 4
重复 apply
未来 Schema 拒绝
迁移 preview 零写入
迁移任一步骤失败整体回滚
partial unique index 实际约束
partial predicate 精确检查
legacy 行新字段全 null
```

Backup：

```text
v2 export
v1 restore
v2 restore
unknown schema reject
payload duplicate URL
payload duplicate provider/external ID
half-null identity
invalid provider key
invalid external ID
invalid datetime
invalid metadata hash
exact local reuse
URL different-item conflict
identity different-item conflict
identity/URL disagreement
preview zero-write
apply transaction rollback
media index invalidation
no outbound call
```

### 20.2 Related regression

至少运行：

- migrations
- schema upgrade routes
- backup
- backup validator
- exporter
- sources
- release security
- i18n
- media index invalidation
- application startup

### 20.3 Full suite

本阶段涉及 Schema 和备份核心，必须运行本地全量 pytest。

执行并报告：

```bash
.venv/bin/python -m pytest
.venv/bin/python -m pip check
git diff --check
```

## 21. Docker 验证

全部使用隔离临时目录或 volume。

至少验证：

### 生命周期 A：fresh Schema 4

- build 成功；
- healthy；
- `/login` 为 200；
- Schema 为 4；
- 应用版本仍为 1.1.0；
- 重建容器后数据持续存在；
- 安全属性保持。

### 生命周期 B：真实 Schema 3 → 4

- 使用隔离 Schema 3 数据库；
- 执行真实 preview；
- preview 后数据库字节和逻辑状态不变；
- 执行 apply；
- Schema 成为 4；
- legacy source 四个新字段均为 null；
- 重建容器后保持 Schema 4。

### Backup

- 在隔离实例导出 v2；
- 恢复合法 v1；
- 恢复合法 v2；
- 冲突恢复零提交；
- 整个流程无外部网络。

### Stable rejection

- 使用稳定 v1.1.0 代码或镜像打开 Schema 4 副本；
- 必须安全拒绝；
- 数据库不得变化。

清理所有临时容器、网络、volume、镜像 tag、数据库和测试目录。

## 22. 提交

确认：

- 应用版本仍为 `1.1.0`；
- Schema 为 `4`；
- 新导出为 backup v2；
- v1 backup 仍可恢复；
- 无真实 provider；
- 无网络入口；
- 未调用 Hermes；
- 未接触既有 `data/`。

创建且只创建一笔提交：

```text
Add Schema 4 source tracking and backup v2
```

推送 `main`，等待：

- `test`
- `Docker production smoke`

均成功。

不得创建第二笔提交。

## 23. 最终报告

报告：

- 开始 SHA
- 最终提交 SHA
- 修改文件
- Schema 4 字段和索引
- 迁移 preview / apply / rollback
- fresh 与连续迁移结果
- stable v1.1.0 拒绝结果
- backup v2 格式
- v1 restore 兼容
- 冲突矩阵
- preview 和 restore 结果计数
- targeted / related / full pytest 数量
- pip check
- Docker 生命周期结果
- Actions run 和两个 job
- 应用版本仍为 `1.1.0`
- Schema 为 `4`
- 生产 registry 仍为空
- 未访问真实网络
- 未实现真实 provider或搜索 UI
- 未调用或编写 Hermes 验收
- 未创建 tag、Release
- 未部署 N100
- 最终工作区仅 `?? data/`
- 既有 `data/` 未接触

完成后停止，等待云端 diff 复核。