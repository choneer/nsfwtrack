# NSFWTrack — 项目进度与开发规划

> NSFWTrack 是本地单用户媒体记录器 / 收藏管理器。  
> 当前开发边界：本地管理、本地数据维护、手动确认操作、SQLite、FastAPI、Jinja2、轻量原生 JavaScript、Docker Compose。
> Phase 3-A1 允许保存用户提供的 URL；Phase 3-A2 允许校验和保存用户上传的本地栅格图片；Phase 3-A3 允许基于本地文件名生成并手动确认媒体关联候选；Phase 3-A4 允许从未匹配本地图片手动确认创建条目；Phase 3-A5 允许对完整本地媒体扫描结果进行只读检索与分页；Phase 3-A6 允许在数据健康页只读审计本地媒体完整性；Phase 3-B1 允许按完整 SHA-256 只读定位重复媒体；Phase 3-B2 允许按重复组只读浏览路径与引用；Phase 3-B3 允许用户明确选择 keeper 后，在重扫、确认和引用安全迁移后删除同组冗余文件；Phase 3-B4 允许只读隔离和审计内部清理锚点与恢复文件；Phase 3-B5 允许用户逐项预览并手动确认将合法锚点恢复为普通媒体；Phase 3-B6 允许用户逐项确认永久删除合法且零引用的锚点残留；Phase 3-C1 允许用户逐项替换或清除 Data Health 报告的无效封面 / 头像引用；Phase 3-C2 允许用户逐项确认删除 Data Health 报告的精确 `.upload-*.tmp` 零引用残留；Phase 3-C3 允许用户只读定位媒体扫描逐项跳过路径和稳定原因；Phase 3-C4 允许用户逐项预览并确认删除仍损坏且零引用的普通媒体；Phase 3-C5 允许只读诊断不可用媒体根目录，并在真实 missing 状态下手动安全初始化；Phase 4-A1 允许登录用户通过现有安全扫描结果只读查看单个普通媒体的文件事实、引用和重复组；Phase 4-A2 允许用户预览并确认同目录安全修改普通媒体 basename，同时迁移全部封面 / 头像引用。仍禁止请求外部网页、远程图片、爬虫、站点 adapter、自动同步、识别、推荐、AI、多用户或云同步。

---

## 一、当前总体状态

当前应用版本与开发阶段：

```text
v1.0.6 / Phase 4-A2 ordinary media safe rename in Unreleased
```

当前最新稳定版本为 `v1.0.6`，发布范围为 Phase 3-B1 与 B2。

当前发布引用：

```text
annotated tag object: d4d5c31cd5b2fed9a90ad69742d54b4c9dbed0b4
peeled commit: 961a3d0cc169e82b261d83207b0ec802007e292b
Release: https://github.com/choneer/nsfwtrack/releases/tag/v1.0.6
```

当前项目状态：

```text
基础可用：已完成
本地管理闭环：已完成
数据导入 / 备份闭环：已完成
合集体系：已完成
重复条目清理：已完成
元数据清理：已完成
使用效率增强：已完成
数据健康检查：F1 / F2 / F3 已发布，F4 提示行为与 K2 专项验收均已完成
设置中心：G1 基础设置中心、G6 危险操作偏好已发布
维护与迁移：Phase 2-H 已完成并随 v0.9.0 发布
稳定性收尾：Phase 2-I1 基线、I2 查询优化、I3 错误处理、I4 发布冻结审查已随 v1.0.0 发布
完成度审计：Phase 2-K1 / K2 已随 v1.0.1 发布；代码开发与 WSL 验收已完成
维护与 CI：Phase 2-L1 至 L6 已随 v1.0.2 发布；L7 已随 v1.0.3 发布；L8 固定非 root 容器用户已随 v1.0.4 发布
产品功能重启：Phase 3-A1 至 A6 已随 v1.0.5 发布；Phase 3-B1 / B2 已随 v1.0.6 发布；Phase 3-B3 / B4 / B5 / B6 / C1 / C2 / C3 / C4 / C5 与 D1 最终集成审查均已完成并位于 Unreleased；Phase 4-A1 / A2 已完成
```

当前完成度估算：

```text
核心业务能力：已完成
代码发布状态：v1.0.6 已正式发布，tag 与正式 GitHub Release 均已验证
当前开发状态：Phase 4-A2 commit 结果歧义修复、本地验收、推送与 Actions 均完成；main 保持应用版本 1.0.6 与 Schema 2
WSL 验收：已完成
N100 部署：尚未开始，等待用户明确授权
```

---

## 二、角色分工

- 用户：需求确认、范围审批、最终发布确认
- 开发者：编码实现、测试、Docker 验收、提交推送
- 审查者：范围、安全、结果与发布前复核

---

## 三、长期开发规则

长期规则以 `RULE.md` 为准。

每个阶段的当前目标以 `GOAL.md` 为准。

原则：

- `RULE.md` 负责长期边界
- `GOAL.md` 负责当前阶段目标
- `CHANGELOG.md` 记录版本变化
- `TASKS.md` 记录任务状态
- `REVIEW.md` 记录审查重点
- `PLAN.md` 记录总体路线和进度

---

## 四、已发布版本

### v0.1.0 — Phase 1 MVP

目标：完成项目底座。

已完成：

- FastAPI 项目结构
- SQLite / SQLAlchemy 数据模型
- Jinja2 页面与轻量原生 JavaScript 交互
- 单用户登录保护
- 条目 CRUD
- 标签管理
- 创作者管理
- 状态 / 评分 / 短评
- 本地搜索
- 基础统计
- CSV / JSON 导入
- Docker Compose
- 基础测试
- README / TASKS / REVIEW / CHANGELOG

---

### v0.2.0 — Phase 2-A 本地管理增强

目标：增强日常条目管理能力。

已完成：

- Phase 2-A1：高级筛选 / 排序 / 分页
- Phase 2-A2：批量编辑
- Phase 2-A3：条目详情页增强
- Phase 2-A4：导入增强

能力：

- 多条件筛选
- 列表排序
- 分页控制
- 当前页批量编辑
- 状态 / 标签 / 评分批量处理
- 条目详情页快速维护
- CSV / JSON 模板
- 导入预览
- 导入错误摘要

---

### v0.3.0 — Phase 2-B UI 与统计增强

目标：提升界面可用性和本地统计能力。

已完成：

- Phase 2-B1：响应式 UI / 移动端打磨
- Phase 2-B2：统计面板增强

能力：

- 移动端布局优化
- 导航与表格适配
- 状态分布统计
- 评分分布统计
- 标签排行
- 创作者排行
- 最近活动
- 数据完整度统计

---

### v0.4.0 — Phase 2-C 合集 / 清单体系

目标：新增合集 / 清单管理能力，并纳入备份导入闭环。

已完成：

- Phase 2-C1：本地合集 / 清单管理
- Phase 2-C2：合集备份 / 导入 / 导出支持

能力：

- 创建合集
- 编辑合集
- 删除合集
- 合集详情页
- 条目加入 / 移出合集
- 批量加入 / 移出合集
- 按合集筛选
- 合集统计
- JSON 备份合集
- JSON 恢复合集
- CSV 导出 / 导入合集
- 旧备份兼容

---

### v0.5.0 — Phase 2-D 数据清理与手动合并

目标：补齐本地数据质量维护能力。

已完成：

- Phase 2-D1：重复条目检测与手动合并
- Phase 2-D2：标签 / 创作者 / 合集清理与合并

能力：

- 重复条目候选检测
- 条目对比页
- 条目手动合并
- 标签重复检测
- 创作者重复检测
- 合集重复检测
- 标签手动合并
- 创作者手动合并
- 合集手动合并
- 合并时 primary 保留
- 合并时 duplicate 删除
- 关联关系转移
- 重复关联跳过
- 合集 description 冲突处理
- 合并前危险提示
- 合并前备份提示
- 合并结果摘要

安全边界：

- 不自动合并
- 不使用 AI 判断语义
- 不请求外部信息
- 不引入外部内容源
- 不删除条目
- 合并必须登录
- 合并必须 POST
- 合并必须手动确认

---

### v0.6.0 — Phase 2-E 使用效率增强

目标：减少重复操作，提高日常使用效率。

已完成：

- Phase 2-E1：保存筛选视图 / 常用视图
- Phase 2-E2：最近访问 / 最近编辑
- Phase 2-E3：快捷操作入口 / 工作台增强

能力：

- 条目列表保存当前筛选视图
- 已保存视图应用 / 更新 / 删除
- saved views JSON 备份 / 恢复兼容
- 条目详情访问记录
- 用户主动编辑记录
- 最近活动页面
- item_activity JSON 备份 / 恢复兼容
- 首页 / 工作台快捷入口
- 条目列表页快捷入口
- 快捷入口只做导航

安全边界：

- 不自动执行危险操作
- 不绕过登录
- 不绕过 POST
- 不绕过 confirm
- 不做 AI 推荐
- 不做智能分析
- 不做外部内容源
- 不做云同步
- 不做多用户共享

---

### v0.7.0 — Phase 2-F 数据健康与校验

目标：补齐本地数据健康检查、写入前校验和低风险维护能力。

已完成：

- Phase 2-F1：数据健康检查 / 本地数据自检
- Phase 2-F2：备份文件校验 / 恢复 dry-run / 导入 dry-run 增强
- Phase 2-F3：数据健康手动修复 / 低风险维护操作

能力：

- 只读数据健康检查页
- 条目基础数据检查
- 孤立关系检查
- 重复关系检查
- saved views 参数检查
- item_activity 检查
- JSON 备份文件校验
- 备份恢复 dry-run 报告
- 导入 dry-run 报告增强
- 低风险手动修复
- 孤立 / 重复关系清理
- 孤立 activity 清理
- 负数 activity 计数修正
- saved views 危险或未知参数清理

安全边界：

- 手动修复不删除 items / tags / creators / collections
- 所有修复必须登录
- 所有修复必须 POST
- 所有修复必须 confirm
- 不自动修复
- 不做一键修复全部
- 不做 AI 判断
- 不做外部内容源
- 不做云同步
- 不做多用户功能

---

### v0.8.0 — Phase 2-G 设置与安全确认

目标：提供本地基础偏好设置，并统一危险操作的安全提示与确认流程。

已完成：

- Phase 2-G1：基础设置中心
- Phase 2-G6：危险操作偏好与确认流程统一

能力：

- 默认语言、分页数量、排序字段、排序方向和首页入口
- 显式 URL 参数和 saved views 优先于默认设置
- standard / strict 危险操作确认模式
- strict 模式服务端精确验证 `CONFIRM`
- 删除、合并、备份恢复、活动清空、健康修复和设置重置统一确认
- 安全提示不可完全关闭
- 摘要 / 详细结果展示偏好
- `app_settings` JSON 备份、校验和恢复兼容
- 旧备份缺少新设置时使用安全默认值

安全边界：

- 不绕过登录、POST、浏览器确认、服务端确认或 rollback
- 结果详情设置不改变业务逻辑、数据范围或事务
- 不做一键全部删除、合并或修复
- 不做多用户、云同步、外部账号、插件或 AI 推荐
- 不做外部内容源

---

### v0.9.0 — Phase 2-H 数据库版本与迁移框架

目标：为本地 SQLite 数据库提供可审查的版本预检和显式升级框架。

已完成：

- Phase 2-H1：数据库版本记录与升级预检
- Phase 2-H2：显式迁移框架与升级 dry-run

能力：

- 内部 `schema_migrations` 版本记录
- 新数据库基线登记和旧数据库安全预检
- 高版本数据库安全拒绝启动
- 低版本数据库只提示升级，不自动迁移
- 代码内迁移注册表和连续路径解析
- 只读升级 dry-run
- 登录、POST、浏览器确认、服务端确认和备份确认
- 迁移步骤、检查和版本记录同事务提交或整链回滚

安全边界：

- 启动时只做兼容性预检，不自动执行迁移
- 升级必须由用户显式触发，升级前建议先做 JSON 备份
- `CURRENT_SCHEMA_VERSION` 保持 `1`
- 生产迁移注册表保持为空，不虚构 `1 -> 2` 生产迁移
- 不支持 Alembic、自动降级、任意 SQL 或用户指定目标版本
- `schema_migrations` 不进入 JSON 备份或恢复

---

### v1.0.0 — Phase 2-I 稳定性与发布冻结

目标：完成本地单用户稳定版的性能、安全、兼容性和发布审查。

已完成：

- Phase 2-I1：100 / 1,000 / 10,000 条隔离性能基线
- Phase 2-I2：按需关系加载、分页收敛和查询优化
- Phase 2-I3：统一安全错误响应、request ID 和脱敏请求日志
- Phase 2-I4：登录、Session、同源写请求、输入输出、rollback 和数据库兼容性总审查

发布边界：

- `CURRENT_SCHEMA_VERSION` 保持 `1`
- 生产迁移注册表保持为空
- 不新增索引、表、字段、依赖或生产迁移
- 不包含外部内容源、URL 导入、爬虫、推荐、AI、云同步或多用户系统

---

### v1.0.1 — Phase 2-K 审计与边界收口

目标：归档 K1 开发完成度审计和 K2 投入使用前边界收口。

已完成：

- Phase 2-K1：实现、文档、入口、测试缺口和 F4 安全提示审计
- Phase 2-K2：本地素材路径契约与登录保护
- 全部批量写入、状态清除和关系解除的浏览器 / 服务端确认
- `.env.example` 精确占位凭据启动拒绝
- F4 双语、备份链接、确认策略和健康空状态专项测试
- 首次安装、v0.9/v1.0 升级、备份和回滚清单

发布边界：

- `CURRENT_SCHEMA_VERSION` 保持 `1`
- 生产迁移注册表保持为空
- 不新增业务功能、依赖、表、字段、索引或生产迁移
- 不修改 v1.0.0 或更早 tag / Release

---

### v1.0.2 — Phase 2-L 维护与 CI 稳定性

目标：发布 L1 至 L6 的依赖兼容、安全响应头和 Docker / CI 稳定性收口。

已完成：

- TestClient 兼容依赖与直接依赖版本基线，CI 增加 `pip check`
- 最小兼容浏览器安全响应头及 500 响应覆盖
- 独立生产 Docker smoke、最小只读权限与同 ref 过时运行取消
- Python 标准库镜像健康检查，CI 先等待 `healthy` 再验证 HTTP / 安全头

发布边界：

- `CURRENT_SCHEMA_VERSION` 保持 `1`，生产迁移注册表保持为空
- 不新增业务功能、接口、数据库变化、Schema、迁移或外部集成
- 不修改 v1.0.1 或更早 tag / Release

---

### v1.0.3 — Phase 2-L7 Docker 运行时安全基线

目标：发布生产与 CI Docker 运行时最小权限收口及配套权限准备说明。

已完成：

- 只读根文件系统、`cap_drop: ALL` 与 `no-new-privileges`
- `/tmp` 64 MiB tmpfs，并保留 `/app/data` 持久化写入
- CI 同步验证实际 capabilities、挂载和可写边界
- rootful Docker 在启动前准备数据目录权限，存量安装先停机并完成可验证备份

发布边界：

- `CURRENT_SCHEMA_VERSION` 保持 `1`，生产迁移注册表保持为空
- 不新增业务功能、依赖、数据库变化、迁移或容器用户切换
- 不修改 v1.0.2 或更早 tag / Release

---

### v1.0.4 — Phase 2-L8 固定非 root 容器用户

目标：发布固定 UID/GID 运行身份及安全的数据目录所有权迁移流程。

已完成：

- `nsfwtrack` UID/GID 固定为 `10001:10001`，应用与 HEALTHCHECK 均通过 Dockerfile `USER` 运行
- L7 只读根、零 capabilities、禁止提权、tmpfs 与最小写入边界保持不变
- CI 与 WSL 验证身份、HTTP / 安全头和 SQLite 重建持久化，Schema 保持 1
- v1.0.3 及更早部署在升级前停机、完成可验证备份，并将 data 迁移为 `10001:10001` / 0700

发布边界：

- 不修改业务逻辑、依赖、数据库、Schema、迁移、容器 UID/GID 或安全配置
- 不修改 v1.0.3 或更早 tag / Release，不部署到 N100

---

## 五、K1 审计后的项目状态

### Phase 2-K2：投入使用前边界收口

状态：已完成。

目标：只修复 K1 已确认的使用前边界和测试缺口。

必须完成：

- 收紧 `cover_path` / `avatar_path` 为真实可用的本地路径契约，禁止浏览器外部拉图
- 为所有批量写入补齐浏览器与服务端确认
- 为状态清除和关系解除建立一致的低风险 / 危险确认规则
- 拒绝 `.env.example` 中的已知密码和 Secret 占位值
- 补齐 F4 双语备份提示、确认模式和无问题空状态专项测试
- 增加首次安装、旧版本升级、备份和回滚的单一操作清单
- 运行全量测试和隔离 Docker 验收

优先级：

```text
高
```

---

### Phase 2-K3：目标部署验收（未开始，非当前开发任务）

说明：这是可选的目标主机操作验收清单，**不是**当前开发任务。
代码开发与 WSL 验收已完成至稳定版 `v1.0.5`。N100 / 目标主机部署尚未开始，
必须等待用户明确授权后才能执行。

授权后可参考的操作项：

- 在仓库外配置唯一强密码和随机 Secret
- 在目标 N100 / LAN 环境验证 build、启动、持久化、重启、登录和停止
- 使用真实浏览器完成桌面 / 移动端、JavaScript confirm 和访问记录 smoke
- 导出新 JSON 备份，先校验，再恢复到全新隔离实例并核对核心数量
- 确认只在受控局域网访问，不直接暴露公网
- 记录最终无 P0 / P1 阻断结论

当前状态：

```text
未开始 / 等待用户明确授权
```

---

### 已完成能力（不再列为剩余阶段）

#### 设置中心（v0.8.0 已发布）

目标：让常用偏好可配置。

计划：

- Phase 2-G1：基础设置中心（已完成：设置页、默认语言、默认每页数量、默认排序方式、默认首页入口）
- Phase 2-G6：危险操作偏好与确认流程统一（已完成：strict `CONFIRM`、备份提醒、结果详情和统一安全提示）

优先级：

```text
中
```

---

#### 维护与迁移（v0.9.0 已发布）

目标：提高长期升级稳定性。

发布范围：

- Phase 2-H1：数据库版本记录、旧库基线和启动结构预检（已发布）
- Phase 2-H2：显式 migration 框架、升级前备份确认、只读 dry-run 和失败整链回滚（已发布）
- Phase 2-H 发布范围已完成；当前没有虚构的 `1 -> 2` 生产迁移

优先级：

```text
中高
```

---

#### 性能与稳定性收尾

目标：为大量数据场景做收尾优化。

计划：

- Phase 2-I1：性能基线与数据库查询审查（已完成，随 v1.0.0 发布）
- Phase 2-I2：查询优化与分页收敛（已完成，随 v1.0.0 发布；未新增索引或迁移）
- Phase 2-I3：异常处理、日志与错误页面统一（已完成，随 v1.0.0 发布）
- Phase 2-I4：安全、兼容性与 v1.0.0 发布前总审查（已完成，随 v1.0.0 发布）
- 后续性能索引或大文件处理必须另行审批，且不阻塞当前本地单用户发布边界

优先级：

```text
中
```

---

## 六、历史路线归档

### v0.6.0 — Phase 2-E 使用效率增强（已完成）

已包含：

- E1：保存筛选视图 / 常用视图
- E2：最近访问 / 最近编辑
- E3：快捷操作入口 / 工作台增强

目标完成度：

```text
约 82% ~ 85%
```

---

### v0.7.0 — Phase 2-F 数据健康检查（已发布 F1 / F2 / F3）

已包含：

- 数据健康检查页（F1 已完成）
- 备份文件校验 / 恢复 dry-run / 导入 dry-run 增强（F2 已完成）
- 数据健康手动修复 / 低风险维护操作（F3 已完成）

K1 审计结论：

- F4 提示行为已存在，不再新增产品阶段；只在 K2 补齐专项验收

目标完成度：

```text
约 87% ~ 90%
```

---

### v0.8.0 — Phase 2-G 设置中心（已发布）

已包含：

- G1：基础设置中心
- 设置页
- 默认语言
- 默认排序
- 默认分页
- 默认首页视图
- JSON 备份 / 恢复兼容本地设置
- G6：危险操作偏好与确认流程统一

目标完成度：

```text
约 90% ~ 93%
```

---

### v0.9.0 — Phase 2-H 维护与迁移（已发布）

已包含：

- H1：数据库版本记录、旧库基线和启动升级预检
- H2：显式 migration 框架、连续路径解析和只读升级 dry-run
- 显式升级确认、升级前备份确认和事务失败整链回滚
- 启动时不自动迁移
- 当前 schema 版本保持 `1`，生产迁移注册表为空

目标完成度：

```text
约 93% ~ 95%
```

---

### v1.0.0 — 稳定版（已发布）

已包含：

- 性能审查
- 数据安全审查
- 全量测试审查
- Docker 验收审查
- 文档整理
- 发布说明整理
- 旧版本升级说明

目标状态：

```text
本地单用户管理系统稳定版
```

---

### v1.0.1 — 审计与边界收口（已发布）

已包含：

- K1 开发完成度审计
- K2 本地素材、确认流程和示例凭据边界收口
- F4 专项安全提示测试
- 安装、升级、备份和回滚清单

目标状态：

```text
稳定版补丁发布；代码开发与 WSL 验收已完成；N100 部署等待用户明确授权
```

---

### v1.0.2 — 维护与 CI 稳定性（已发布）

已包含：

- L1 / L2 测试兼容性、直接依赖版本基线和 `pip check`
- L3 最小浏览器安全响应头
- L4 / L5 / L6 Docker smoke、CI 最小权限 / concurrency 和镜像健康检查

目标状态：

```text
稳定维护版本；代码开发与 WSL 验收已完成；N100 部署等待用户明确授权
```

---

### v1.0.3 — Docker 运行时安全基线（已发布）

已包含：

- L7 只读根文件系统、全部 capabilities 移除和 `no-new-privileges`
- `/tmp` tmpfs、`/app/data` 持久化写入与 CI 实际边界检查
- rootful Docker 启动前数据目录权限准备及存量备份提醒

目标状态：

```text
稳定维护版本；代码开发与 WSL 验收已完成；N100 部署等待用户明确授权
```

---

### v1.0.4 — 固定非 root 容器用户（已发布）

已完成：

- 生产镜像创建固定 `nsfwtrack` UID/GID `10001:10001`，应用与健康检查通过 Dockerfile `USER` 以该身份运行
- CI 数据目录归 `10001:10001` 所有，并验证身份、L7 安全边界、写入边界和安全响应头
- CI 与 WSL 均验证 SQLite 创建后停止并重建容器仍持久化，Schema 保持 1
- README 记录首次安装和 v1.0.3 存量目录的停机、可验证备份、0700 权限迁移流程

边界：

- 不使用 root 启动脚本、sudo/gosu 容器入口、自动 `chown` 或 `chmod 777`
- 不修改业务代码、依赖、数据库、Schema、迁移、版本或旧 tag / Release
- 不部署到 N100

---

### Phase 3-A1 — 来源链接与本地书签导入（已随 v1.0.5 发布）

已完成：

- `item_sources` 支持一个条目多个来源，保存原 URL、规范化 URL、可选标题和创建时间
- 详情页查看 / 添加 / 确认删除来源；纯文本支持一行一 URL 和 `标题<TAB>URL`
- 使用 Python 标准库只解析用户上传的本地浏览器书签 HTML
- 批量导入先只读预览新增、重复、无效和冲突，再确认事务写入并在失败时回滚
- 多个已有条目的标题仅大小写不同或完全相同时明确标记目标歧义，预览与写入均不任意关联
- 全局规范化 URL 唯一约束，HTTP/HTTPS allowlist，无标题时生成本地可读占位标题
- JSON 备份/恢复与 CSV/JSON 条目导入导出同步来源，旧文件缺少来源表/字段仍兼容
- 真实显式 Schema 1 → 2 `create_item_sources` 迁移；旧条目和既有表不修改

网络与范围边界：

- 只保存用户提供的 URL，不请求 URL，不抓取远程标题、元数据或图片
- 不实现爬虫、adapter、自动同步、推荐、AI 或多用户能力
- 不修改 v1.0.4 tag / Release，不部署到 N100

---

### Phase 3-A2 — 本地媒体库（已随 v1.0.5 发布）

已完成：

- 安全扫描 `data/media`，跳过符号链接、非普通文件和不支持格式，并展示引用状态
- WebUI 单图 / 多图上传，限制每批 20 张和每张 10 MB，校验扩展名、MIME 与真实文件结构
- 使用 SHA-256 内容寻址和去重，上传文件保存在现有 `data/media/library`
- 上传先写同目录随机临时文件并 flush / fsync 后原子发布；批次失败回滚本批次全部临时文件和新文件
- 使用既有 `cover_path` / `avatar_path` 设置、替换和清除封面 / 头像，清除关联不删除文件
- 缺失、损坏、伪装或非法图片安全降级为空状态和 404，不导致页面 500

范围边界：

- 不新增表，不修改 Schema 2、迁移、依赖、版本或旧 tag / Release
- 不请求外部 URL，不获取远程图片，不做识别、推荐、AI 或物理删除媒体
- 保持 fixed non-root、只读根、零 capability、no-new-privileges 与现有 data 挂载

---

### Phase 3-A3 — 本地媒体候选配对（已随 v1.0.5 发布）

已完成：

- 对有效且未使用的本地媒体、无封面条目和无头像创作者生成只读候选，不在 GET 或扫描时自动写入
- 使用 NFKC / casefold 精确名称与仅保留字母数字的规范化名称匹配，并支持 `cover` / `avatar` 分隔后缀限定目标类型
- 显示目标类型、匹配依据和置信等级；一媒体多目标或一目标多媒体均标记冲突并禁止应用
- 单项与当前 20 行候选页批量操作均需登录、POST、浏览器确认和服务端确认，strict 模式精确验证 `CONFIRM`
- 写入前重新扫描并拒绝陈旧、冲突、跨页、不可用或已有关系目标；批量选择在一个事务内提交或回滚
- 只填写既有 `cover_path` / `avatar_path`，不覆盖现有关系，不下载、识别、移动、重命名、覆盖或删除媒体文件

范围边界：

- 不新增表，不修改 Schema 2、迁移、依赖、应用版本、旧 tag / Release 或 Docker 安全配置
- 不请求外部网络，不做 AI、图像识别、模糊相似度、自动关联、推荐或媒体物理操作
- 不部署到 N100

---

### Phase 3-A4 — 未匹配媒体快速建档（已随 v1.0.5 发布）

已完成：

- 从有效、未使用且没有 A3 配对的本地图片生成只读新条目候选；头像约定文件明确排除
- 文件名移除图片扩展名和封面约定后缀后生成默认标题，确认前可逐项编辑
- 默认标题显示无效、已有精确同名、已有规范化同名和候选间规范化同名冲突，允许编辑解决
- 单项和当前 20 行候选页批量确认均登录保护、仅 POST、浏览器与服务端确认，strict 精确验证 `CONFIRM`
- 提交时重新扫描、限制当前页、复核本地文件，并以最终标题重新检查已有与本批次冲突
- 任一陈旧、伪造、占用、标题、文件或数据库失败均拒绝整批并 rollback；成功时创建条目并设置既有路径为 `cover_path`
- 媒体文件字节和路径保持不变，不创建、下载、识别、移动、重命名、覆盖或删除文件

范围边界：

- 不新增表，不修改 Schema 2、迁移、依赖、应用版本、旧 tag / Release 或 Docker 安全配置
- 不请求外部网络，不做 AI、图像识别、自动建档、推荐或媒体物理操作
- 不部署到 N100

---

### Phase 3-A5 — 媒体库检索与分页（已随 v1.0.5 发布）

已完成：

- 对完整媒体扫描结果按文件名 / 相对路径做 NFKC 大小写无关本地搜索
- 支持全部、可用、损坏 / 不可用、已使用、未使用状态筛选；使用状态来自现有封面 / 头像引用
- 支持文件名升降序和文件大小升降序，使用文件名 / 路径稳定打破并列
- 媒体卡片固定每页 20 条，非法、负数、非数字和越界页码安全回退或夹取
- `media_page`、`match_page`、`create_page` 与规范化后的 `media_q` / `media_status` / `media_sort` 在三套分页和返回媒体库的表单间保留
- 空扫描与筛选空结果分别显示；非法搜索、状态和排序参数安全回退，GET 零写入
- A3/A4 继续接收完整原始扫描，候选生成和确认逻辑未改变

范围边界：

- 不修改媒体文件或关联，不新增写操作，不请求外部网络，不使用 AI / 图像识别
- 不新增表，不修改 Schema 2、迁移、依赖、应用版本、旧 tag / Release 或 Docker 安全配置
- 不部署到 N100

---

### Phase 3-A6 — 本地媒体完整性审计（已随 v1.0.5 发布）

已完成：

- `/data-health` 增加 media 分类，审计条目封面和创作者头像的本地引用
- 将非法路径、路径越界、符号链接、缺失、损坏及不可用媒体根报告为问题
- 将 `.upload-*.tmp` 残留、不同路径 SHA-256 重复内容及扫描跳过项报告为警告
- 缺失根目录仅在存在有效本地引用时报告；正常未使用媒体不视为问题
- 使用既有全局 200 条明细限制，完整分类和问题总数不被截断
- 页面 GET、扫描和报告零写入；media 问题不提供任何修复、删除或引用清除入口
- 异常根目录安全降级，不请求外部 URL，不影响 A3/A4/A5 逻辑

范围边界：

- 不修改媒体文件或数据库引用，不增加 media fix type
- 不新增表，不修改 Schema 2、迁移、依赖、应用版本、旧 tag / Release 或 Docker 配置
- 不请求外部网络，不部署到 N100

---

### v1.0.5 — Phase 3-A1 至 A6（已正式发布）

发布范围：

- A1 来源链接、本地文本 / 书签导入和真实 Schema 1 → 2 显式迁移
- A2 本地媒体库、安全上传、SHA-256 去重和封面 / 头像关联
- A3 确定性媒体候选与手动确认关联
- A4 未匹配本地媒体手动确认建档
- A5 媒体搜索、筛选、排序和分页
- A6 `/data-health` 只读媒体完整性审计
- 来源同名歧义拒绝与媒体同目录临时文件、fsync、原子发布、竞态复核和批次回滚修复

发布结果与边界：

- 应用元数据统一为 1.0.5，CHANGELOG 冻结到 `2026-07-13` 并保留空 Unreleased
- 不修改功能、Schema 2、既有 1 → 2 迁移、依赖或 Docker 配置
- annotated tag object 为 `6a4def572e100198a446ad56353400138c573f66`
- peeled commit 为 `3c4fee62891ff2826f0b8bc97b33bf3a4d08aa73`
- 正式 Release 为 `https://github.com/choneer/nsfwtrack/releases/tag/v1.0.5`
- 不部署到 N100

---

### Phase 3-B1 — 重复媒体定位（已随 v1.0.6 发布）

已完成：

- 仅将不同路径下、可用且具有相同完整合法 SHA-256 的媒体构成重复组
- 媒体库汇总重复组数、涉及文件数，以及每组保留一份时可节省的字节数
- `media_status=duplicate` 只显示重复组成员；损坏、空 / 非法哈希和单文件不进入
- `media_q` 保留文件名与路径搜索，并支持大小写无关的完整 SHA-256 或前缀搜索
- 重复媒体卡片显示稳定的组内数量和其他媒体路径，原有四种排序与 20 条分页保持
- 三套页码及查询状态在分页、上传、关联、A3 配对与 A4 建档返回流程中继续保留
- GET 前后数据库、封面 / 头像引用、媒体字节及 A3/A4 候选保持不变
- 中英文、README / PLAN / TASKS / REVIEW / CHANGELOG / GOAL 与专项测试同步

范围边界：

- 只读定位，不删除、移动、重命名、覆盖媒体或自动迁移任何引用
- 不修改 A3/A4 候选逻辑，不新增表，不修改 Schema 2、迁移、依赖、版本或 Docker
- 不请求外部网络，不使用 AI / 图像识别，不创建 tag / Release，不部署到 N100

---

### Phase 3-B2 — 重复媒体组视图（已随 v1.0.6 发布）

已完成：

- 新增登录保护的只读 `/media-library/duplicates`，每个真实重复 SHA-256 只显示一组
- B1 与 B2 共用完整合法 SHA-256、不同路径去重和稳定成员排序服务
- 每组展示完整 SHA-256、成员数、单文件大小、总占用和可节省空间
- 每个成员展示媒体路径、可用状态、条目封面引用和创作者头像引用
- 支持文件名、路径和 SHA-256 前缀搜索，以及成员数 / 可节省空间 / SHA 双向稳定排序
- 每页固定 20 组，非法超长搜索、排序和页码安全回退或夹取
- 每组提供完整 SHA 与 `media_status=duplicate` 的 B1 精确筛选链接
- GET 前后数据库、引用、媒体字节及 A3/A4 候选不变；页面无业务 POST

范围边界：

- 不删除、移动、重命名或覆盖媒体，不迁移引用，不建议自动保留项
- 不改变 B1、A3/A4 行为，不新增表，不修改 Schema 2、迁移、依赖、版本或 Docker
- 不请求外部网络，不使用 AI / 图像识别，不创建 tag / Release，不部署到 N100

---

### v1.0.6 — Phase 3-B1 与 B2（已正式发布）

发布范围：

- B1 完整 SHA-256 重复媒体定位、统计、duplicate 筛选、SHA 搜索和同组路径
- B2 登录保护的只读重复组页、组指标、成员引用、搜索排序分页和 B1 精确链接
- B1 / B2 共用同一有效媒体完整 SHA-256 分组边界

发布边界：

- 只读展示，不删除、移动、重命名、覆盖或自动选择媒体
- 不清除或迁移封面 / 头像引用，不改变 A3/A4 候选逻辑
- 不修改 Schema 2、真实 1 → 2 迁移、依赖或 Docker/CI 安全配置
- 不请求外部网络，不使用 AI / 图像识别，不部署到 N100
- annotated tag object 为 `d4d5c31cd5b2fed9a90ad69742d54b4c9dbed0b4`
- peeled commit 为 `961a3d0cc169e82b261d83207b0ec802007e292b`
- 正式 Release 为 `https://github.com/choneer/nsfwtrack/releases/tag/v1.0.6`

发布验收：

- 全量 441 passed，`pip check` 无依赖冲突
- 隔离 Docker 双生命周期均 healthy、`/login` 200、应用版本 1.0.6、Schema 2
- 容器重建前后 SQLite 文件校验和不变，fixed non-root 与只读根保持
- 临时容器、镜像、凭据和数据已清理

---

### Phase 3-B3 — 重复媒体手动整理（Unreleased）

目标：

- 在 B2 重复组页要求用户明确选择唯一 keeper，不预选、不评分、不推荐
- 使用共享 B1/B2 完整合法 SHA-256 分组边界生成只读 GET 预览
- 预览逐路径列出条目封面、创作者头像迁移、待删除文件和预计释放空间
- POST 复用 standard / strict 危险确认并在提交时重新扫描完整组
- 删除前创建同文件系统已验证安全锚点，并在完整删除窗口让组内引用指向锚点
- 删除结束后将引用提交到仍有效的 keeper、无覆盖恢复的原路径或唯一恢复路径
- 删除失败时保留安全副本、报告路径与原因，并允许重新预览后重试

拒绝边界：

- 组成员扩张或缩减、哈希变化、缺失、损坏、符号链接、路径越界和伪造路径全部拒绝
- keeper 在首删前、删除中途或末次删除期间缺失 / 替换时，始终由锚点保留一份有效同哈希内容
- 原路径缺失时只做无覆盖恢复；路径被占用时不覆盖外部文件，改用唯一验证恢复路径
- 成功、异常和删除失败重试均清理临时锚点；无法清理时保留安全副本并明确报告
- 不删除 keeper，不处理其他重复组，不自动批量整理
- 不改变 A3/A4 候选逻辑，不请求网络，不使用 AI / 图像识别
- 不修改版本 1.0.6、Schema 2、迁移、依赖或 Docker/CI 配置
- 不创建 tag / Release，不部署到 N100

---

### Phase 3-B4 — 媒体清理恢复中心（Unreleased）

目标：

- 新增登录保护、只读的 `/media-library/recovery`
- 仅按大小写敏感 basename 前缀识别 `.cleanup-anchor-*` 与 `recovered-*`
- 展示路径、实际字节、完整 SHA、合法性及条目封面 / 创作者头像引用
- 区分已引用、未引用、损坏安全锚点和正常恢复文件
- 支持路径 / SHA 搜索、状态筛选、稳定排序和每页 20 条
- 在 data-health 报告锚点残留、损坏和引用状态

隔离边界：

- 默认媒体扫描静默排除内部锚点，只有恢复中心与 data-health 使用显式内部扫描
- 锚点不进入普通媒体库、B1/B2、上传去重或 A3/A4 候选
- `recovered-*` 保持正常媒体身份，继续参与普通筛选、重复组和候选流程
- 目录前缀和仅在名称中包含关键字的普通文件不误判，非锚点候选 ID 不变
- 恢复中心与 data-health GET 零写入；B5 / B6 写操作仅通过各自独立预览和确认 POST，不提供移动、改名或自动修复
- 不改变 B1/B2 分组语义和 B3 整理流程，不请求网络，不使用 AI / 图像识别
- 不修改版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag 或 Release

---

### Phase 3-B5 — 安全锚点手动恢复（Unreleased）

目标：

- 在恢复中心为每个合法 cleanup anchor 提供独立、零写入 GET 预览
- 展示完整 SHA、路径、device、inode、size、mtime、ctime、全部引用和后果
- POST 复用 standard / strict 危险确认，并重新扫描核对完整身份快照
- 无覆盖发布唯一 `recovered-*`，完成文件与目录 fsync
- 单事务迁移全部封面 / 头像引用，再在零引用复核后身份删除原锚点

安全边界：

- 每次只恢复一个明确选择的合法锚点，不批量恢复、不直接丢弃内容
- 损坏、符号链接、错误扩展、缺失、陈旧、伪造、变化、普通与 `recovered-*` 请求全部拒绝
- 数据库失败整笔回滚，并身份清理本次新建恢复文件；原锚点不删除
- 原锚点删除失败时不回退已安全提交的引用，引用保持在合法同 SHA 恢复文件并报告残留
- 普通交互式封面 / 头像写入不能新建内部锚点引用；既有引用、备份恢复和 B3 内部流程保持兼容
- 不改变 B1/B2/A3/A4、版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 或 N100 状态

---

### Phase 3-B6 — 无引用安全锚点手动清理（Unreleased）

目标：

- 仅为合法且零引用 cleanup anchor 提供单项永久删除预览
- GET 展示路径、完整 SHA、MIME、size、device、inode、mtime、ctime 和不可撤销后果
- POST 复用 standard / strict 确认，并重扫核对完整身份快照
- 使用 SQLite `BEGIN IMMEDIATE` 锁内复核封面和头像引用均为零
- 最终身份验证后只删除目标并 fsync 目录

安全边界：

- 已引用、损坏、符号链接、错误扩展、普通、`recovered-*`、缺失、陈旧、伪造和变化请求全部拒绝
- 引用竞态在写锁内拒绝，不删除文件，不迁移、清除或修改任何数据库引用
- 删除失败保留目标并明确报告；unlink 已完成但目录同步失败时准确报告已移除警告
- 不创建恢复文件，不批量或自动清理，不操作任何其他锚点或普通媒体
- 不改变 B3/B4/B5、B1/B2/A3/A4、备份、Data Health fix、版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 或 N100 状态

---

### Phase 3-C1 — 断裂媒体引用手动修复（Unreleased）

目标：

- 从 Data Health 为缺失、损坏、符号链接、非法 / 越界路径和损坏锚点引用提供登录保护的单项预览
- GET 展示对象、原引用、问题类型、对象快照与后果并保持数据库和文件零写入
- 只允许用户手动选择一个现有合法媒体替换，或明确清除当前单个引用
- 替代媒体按路径 / SHA 搜索、稳定路径排序并固定每页 20 条
- POST 复用 standard / strict 确认，在写锁内重验后条件更新一个 `cover_path` 或 `avatar_path`

安全边界：

- 候选必须是完整验证通过的普通媒体；`recovered-*` 可用，cleanup anchor 永远禁止作为新引用
- 提交时重验对象快照、原引用、当前问题及替代媒体 SHA / size / device / inode / mtime / ctime
- 对象、引用、问题或文件变化，健康对象、陈旧和伪造请求全部拒绝
- 替换身份在条件更新后再次验证；DB / commit 失败整笔回滚
- 不自动推荐、自动清除、批量修复或处理其他健康问题
- 不修改、删除、移动或重命名任何文件，不请求网络，不使用 AI / 图像识别
- 不改变 B3-B6、媒体库、备份 / 导入、版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 或 N100 状态

---

### Phase 3-C2 — 上传残留文件手动清理（Unreleased）

目标：

- 从 Data Health 为 `media_upload_residue` 提供登录保护的单项删除预览
- GET 展示相对路径、size、device、inode、mtime、ctime、当前引用与不可撤销后果
- GET 保持数据库和文件零写入，且不读取、解析、恢复或复制临时文件内容
- POST 复用 standard / strict 确认，只处理用户明确选择的一个目标
- 在 SQLite `BEGIN IMMEDIATE` 写锁内复核封面和头像引用均为零
- 最终完整身份验证后按目录 fd unlink 目标并 fsync 所在目录

安全边界：

- 仅接受 basename 大小写精确匹配 `.upload-*.tmp` 的普通非符号链接文件
- 空中段、近似名称、目录、符号链接、非法 / 越界路径、缺失、陈旧、伪造和同路径替换全部拒绝
- 已引用目标只显示 C1 修复指引，不提供删除表单；引用新增竞态在写锁内拒绝
- 不迁移、清除或修改任何数据库引用，不创建 `recovered-*`，不触碰其他文件
- unlink 失败时文件和数据库不变；unlink 成功但目录 fsync 失败时明确报告已删除警告
- 不自动或批量清理，不请求网络，不使用 AI / 图像识别
- 不改变 C1、B3-B6、上传、Data Health、备份 / 导入、版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 或 N100 状态

---

### Phase 3-C3 — 媒体扫描跳过项定位中心（Unreleased）

目标：

- 为普通媒体扫描增加确定性、去重且稳定排序的逐项 skip 记录
- 区分 `symlink`、`unsupported_extension`、`special_file`、`directory_unreadable` 和 `entry_error`
- 展示安全相对路径、扩展名及可安全取得的 size / device / inode / mtime / ctime
- 新增登录保护的只读 `/media-library/skipped` 页面
- 支持路径搜索、类型筛选、稳定路径 / 类型排序和固定每页 20 条
- Data Health 两个原扫描跳过汇总告警链接到对应筛选结果

安全边界：

- 目录通过 fd 和 `O_DIRECTORY|O_NOFOLLOW` 遍历；符号链接只做 lstat，目录替换竞态也不进入目标
- 媒体候选保存根目录、逐级父目录与文件的 dev / inode / size / mtime / ctime；读取时从根 fd 逐段重开并复核
- 最终文件只通过父目录 fd 与 `O_NOFOLLOW` 打开；读取后再次验证全部 fd 与当前路径映射，通过后才解析和哈希
- 父目录替换成 symlink、文件替换或身份漂移统一安全记录为 `entry_error`，不读取外部替换内容且不进入媒体列表
- 不打开、读取、解析、验证或哈希任何被跳过文件内容
- 单个目录 / 条目错误生成稳定原因并继续扫描其他兄弟项
- 只显示媒体根下安全转义的相对路径，不保留绝对路径、原始 OSError 或敏感信息
- `skipped_symlinks` 等于 symlink 明细数；`skipped_unsupported` 等于其他四类明细总数
- 页面无 POST、删除、移动、改名、恢复、关联、自动处理或网络请求
- 不改变 A3-A6、B1-B6、C1-C2、普通媒体、cleanup anchor、`recovered-*`、上传残留、备份 / 导入、版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 或 N100 状态

验收证据：

- C3 专项已扩展到 `10 passed`，新增子目录 fd 打开后父路径 symlink 替换及同 inode 身份漂移的零读取 / 零哈希覆盖
- A3-A6、B1-B6、C1-C2、媒体库、上传、Data Health、备份与导入组合回归 `263 passed`
- 全量 `540 passed`，`pip check` 无依赖冲突
- 隔离 Docker image build 通过，Compose healthy，`/login` 200，未登录跳过项页 303，down 清理完成
- 功能提交 `c591ca4` 已推送 main，Actions run `29321642902` 的 test / Docker production smoke 均通过
- 父路径竞态修复提交 `c27676f` 已推送 main，Actions run `29332762558` 的 test / Docker production smoke 均通过

---

### Phase 3-C4 — 损坏媒体文件手动清理（Unreleased）

目标：

- Data Health 和媒体库为允许扩展名、普通非符号链接的损坏媒体提供单项预览入口
- GET 展示安全路径、原始 SHA、size、device、inode、mtime、ctime、引用与永久删除后果，保持零写入
- 已引用目标只显示 C1 修复指引，不显示删除表单
- POST 复用 standard / strict 确认，并重验原始 SHA、损坏状态和完整身份
- `BEGIN IMMEDIATE` 内重新确认封面与头像引用均为零，再按目录 fd unlink 并 fsync

安全边界：

- 只处理 Data Health 当前报告的单个损坏普通媒体；`recovered-*` 仍按普通媒体处理
- 有效媒体、cleanup anchor、上传残留、symlink、unsupported / special / entry-error 跳过项均排除
- 内容读取复用 C3 已验证 FD 链，不通过可重解析的 `Path.stat/read_bytes` 打开目标
- 父路径 / 同路径 / symlink 替换、SHA 或任一身份字段变化、文件变为有效图片均在 unlink 前拒绝
- 写锁内新增引用时拒绝；不迁移、清除或改写任何引用
- unlink 失败保留目标；unlink 成功但目录 fsync 失败时准确报告已删除警告
- 不创建恢复副本，不触碰其他媒体，不自动、批量或定时清理
- 不改变版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 或 N100 状态

验收证据：

- C4 专项 `17 passed`，覆盖双入口、零写入、排除项、standard / strict、完整身份与 SHA、父路径 / symlink / 有效图片替换、引用竞态及锁 / 查询 / unlink / fsync 失败
- B3-B6、C1-C3、媒体库、上传、恢复、Data Health、备份与导入组合回归 `280 passed`
- 全量 `557 passed`，`pip check` 无依赖冲突
- Docker image build 通过，Compose healthy，`/login` 200，down 后容器与网络清理完成
- 功能提交 `1e686f3` 已推送 main，Actions run `29336790587` 的 test / Docker production smoke 均通过

---

### Phase 3-C5 — 媒体根目录诊断与安全初始化（Unreleased）

目标：

- 为 `media_root_unavailable` 增加登录保护的只读诊断入口
- 仅展示逻辑 `/media/`、安全状态、父 / 根身份、封面 / 头像引用数和处理后果
- 仅真实 missing 且父链安全时提供手动初始化
- POST 复用 standard / strict 确认，从工作目录 FD 安全打开父链并原子创建最后一级目录
- 创建后 fsync 新目录与父目录，根问题消失，断裂引用继续由 C1 处理

安全边界：

- GET 不写数据库或文件系统，不展示绝对路径、原始异常、UID 或敏感挂载信息
- 父链逐段使用 `O_DIRECTORY|O_NOFOLLOW`，重验完整身份和当前名称映射
- symlink、not_directory、unreadable、scan_failed、ready、危险配置和父目录缺失均无初始化表单
- 目标抢占、symlink 竞态、父目录替换、身份变化、伪造快照和 mkdir 失败均拒绝
- 只调用一次 `mkdir(dir_fd=...)` 创建配置末级，不递归创建、覆盖、移动、chmod 或 chown
- 不修改引用，不创建、恢复、复制或下载媒体文件；不自动或批量处理
- 不改变版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 或 N100 状态

当前验证：

- C5 专项 `16 passed`，覆盖零写入、状态隔离、standard / strict、父链 / 目标竞态、mkdir 期间父路径替换及 fsync 失败
- C1-C4、上传、扫描、Data Health、恢复、备份校验与导入组合回归 `240 passed`
- 全量 `573 passed`，`pip check` 无依赖冲突
- Docker image build、Compose healthy、`/login` 200 与 down 清理通过
- 独立非 root / read-only 容器在 named volume 内完成 missing 初始化；容器重建后空目录保持，诊断返回 root available 且不再提供初始化表单，临时资源已清理
- 功能提交 `9a3a546` 已推送 main，Actions run `29343264820` 的 test / Docker production smoke 均通过
- C4 指定组合回归文档已从 281 更正为 280

---

### Phase 3-D1 — Unreleased 集成总审查与开发冻结

目标：

- 对 B3-B6 与 C1-C5 的路由、服务、模板、导航和状态闭环做最终审查
- 为每类 Data Health finding 核对直接入口、安全拒绝或明确只读说明
- 核对 GET 零写入以及写操作登录、确认、事务、身份、引用和失败报告
- 验证备份、导入、Schema 2、设置、i18n、Docker 与 CI 无回归

确认修复：

- Data Health 根目录、未扫描引用和上传残留不再独立按可替换路径遍历，统一使用 `O_NOFOLLOW` 目录 fd 或 C3 已验证扫描记录
- `media_duplicate_content` 现在按完整 SHA-256 直接进入唯一 B2 重复组
- 认证媒体响应在验证 fd 链内读取并直接返回受限字节，不再验证路径后由 `FileResponse` 二次打开
- B3-B6 的验证、锚点创建、恢复发布和身份删除保留根 / 父目录 fd 身份并复核当前映射
- create 最终返回的新锚点与 publish 最终返回前的刷新锚点 / 目标均绑定原 root、逻辑父路径和逐级目录类型 / dev / inode 身份链，并再次复核当前映射
- C2 保留上传残留父目录链身份，在 unlink 前复核父链和最终文件映射
- 父目录改名并替换为外部 symlink，或替换为含同 inode 硬链接的普通外部目录等注入竞态均安全拒绝，不读写或删除外部目录项

当前验证：

- 19 个 B3-C5/Data Health 相关路由全部包含登录依赖
- 110 个注册路由与 142 个模板字面量链接静态核对，缺失目标为 0
- 最终 create / publish 精确竞态 `2 passed`；B3-B6/C1/C2/C4、媒体响应与 Data Health 核心回归 `177 passed`
- B3-C5、媒体响应、备份、导入、Schema 2、迁移、设置与 i18n 组合回归 `365 passed`
- 全量 `584 passed`，`pip check` 无依赖冲突
- Docker image build、隔离 Compose healthy、`/login` 与五个认证媒体/Data Health 页面 HTTP 200，资源已清理
- 完整矩阵和结论见 `PHASE3_COMPLETION_AUDIT.md`；最终父链修复提交 `db0048d` 的 Actions run `29386547600` 两个 job 均成功
- 保持应用版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、旧 tag / Release 与 N100 状态不变

---

### Phase 4-A1 — 本地媒体单文件详情页

目标与实现：

- 新增登录保护的 `/media-library/detail` 普通媒体只读详情页，不新增 POST 或写操作
- 只接受规范化 `/media/` 路径和普通扫描中的精确记录，拒绝外部 / 转义 / missing / symlink / 特殊文件 / cleanup anchor
- 文件事实直接复用现有逐级目录 FD、文件 FD、内容哈希和当前映射复验结果，不通过目标 `Path.stat` / `Path.read_bytes` 二次打开
- 展示逻辑路径、文件名、扩展名、MIME、size、完整 SHA、有效 / 损坏、recovered、引用与重复状态
- 精确查询并链接全部 item cover / creator avatar 引用；按完整 SHA 展示组内数量、单文件 / 总占用 / 可释放空间和准确重复组入口
- 损坏媒体只链接现有 C4 预览，损坏引用只链接现有 C1 单项修复
- 媒体库、重复组和恢复中心 recovered 普通媒体入口保留各自规范化筛选、排序与分页返回状态

当前验证：

- A1 专项 `17 passed`；媒体、恢复、C1/C4、Data Health、备份、页面、响应式与 i18n 组合回归 `252 passed`
- GET SQL 写语句为 0；目标 / 其他媒体、根 / 父目录身份和目录项前后不变
- 父目录替换竞态只读取原 FD 内容后 404，不读取外部目标；目标 `Path.stat` / `Path.read_bytes` 禁用回归通过
- 全量 `601 passed in 91.96s`，`pip check` 无冲突
- Docker image build、隔离 Compose healthy；`/login` 200、匿名详情 303、认证详情 / 媒体库 200，临时资源已清理
- 实现提交 `c8cfb99` 已推送；Actions run `29389862206` 的 `test` 与 `Docker production smoke` 均为 success
- 保持版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 与 N100 不变

---

### Phase 4-A2 — 普通媒体安全重命名

目标与实现：

- A1 详情页为有效普通 / recovered 媒体提供同目录 basename 输入和零写入 GET 预览
- 目标必须保留原扩展名与大小写，并拒绝路径段、控制字符、百分号、首尾空白、保留前缀、过长和未变化名称
- 排除 anchor、上传残留、damaged、missing、skip、symlink、目录 / FIFO；任何目标对象、同 inode hardlink 或已有目标引用均阻止执行
- 预览展示两条逻辑路径、MIME、完整 SHA、mode / size / device / inode / mtime / ctime、全部引用和后果
- confirmed POST 复用 standard / strict `CONFIRM`，在 `BEGIN IMMEDIATE` 内重验完整源身份、目标不存在且零引用和全部源引用 ID
- 保持已验证父目录 / 源 FD，通过 `os.link(..., follow_symlinks=False)` no-overwrite 创建并持有目标 FD
- 精确迁移全部 cover / avatar 引用并复核 rowcount、源零引用、目标引用集合与源 / 目标 / 父链身份后提交
- 提交前失败 rollback 并按 held-FD inode 清理自建目标；`db.commit()` 抛错后先由独立 Session 重查两条路径的全部引用，仅确认未提交时清理 target
- commit 已实际落盘时保留 target / source 并报告 `committed_source_retained`；混合、无引用歧义或查询失败保留双路径并报告 `commit_outcome_unknown`
- 源删除失败时有效目标和引用保持，按实际状态报告源 / 双路径；成功携带来源状态返回新详情

当前验证：

- A2 专项 `43 passed`，覆盖有 / 无引用、recovered、strict、全身份 / 引用伪造、目标抢占、同 inode link、源 / 目标 / 普通目录 / symlink 替换、commit / unlink / fsync 失败
- SHA、内容、inode 和完整 SHA 重复组保持；目标 `Path.stat` / `Path.read_bytes` 禁用回归通过
- local-media、B3、B5、C1/C2/C4、A1 与 i18n 回归 `144 passed`；媒体 / Data Health / 备份 / 页面 / 响应式 / i18n 组合 `309 passed in 56.52s`
- 全量 `644 passed in 119.82s`，`pip check` 无冲突
- Docker image build、隔离 Compose healthy；user `10001:10001`、read-only root、`cap_drop: ALL`、`no-new-privileges` 保持，`/login` 200、匿名 rename 303、API login / 认证媒体库 200，临时资源已清理
- 实现提交 `b32e848` 已推送；Actions run `29396021693` 的 `test` 与 `Docker production smoke` 均成功
- commit 歧义修复后 A2 / i18n 专项 `50 passed`、核心媒体链 `193 passed in 27.83s`、广泛组合 `315 passed in 46.38s`、全量 `650 passed in 106.83s`，pip check 与隔离 Docker / HTTP 通过；修复提交 `09be556` 与 Actions run `29399210087` 两个 job 均成功
- 保持版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、tag、Release 与 N100 不变

---

## 七、有限执行顺序

当前顺序：

```text
1. Phase 2-L1 测试依赖兼容性收口（httpx2）已完成
2. Phase 2-L2 直接依赖版本基线已完成
3. Phase 2-L3 浏览器安全响应头基线已完成
4. Phase 2-L4 CI Docker 冒烟验收已完成
5. Phase 2-L5 CI 最小权限与重复运行控制已完成
6. Phase 2-L6 Docker 健康状态与就绪验收已完成
7. Phase 2-L7 Docker 运行时安全基线已完成
8. Phase 2-L8 固定非 root 容器用户已随 v1.0.4 发布
9. Phase 3-A1 至 A6 已随 v1.0.5 发布
10. 来源同名歧义与媒体原子上传修复已随 v1.0.5 发布
11. Phase 3-B1 / B2 已随 v1.0.6 正式发布
12. 当前稳定版与应用版本均为 v1.0.6；Schema 为 2
13. Phase 3-B3 重复媒体手动整理已完成并位于 Unreleased
14. Phase 3-B4 媒体清理恢复中心已完成并位于 Unreleased
15. Phase 3-B5 安全锚点手动恢复已完成并位于 Unreleased
16. Phase 3-B6 无引用安全锚点手动清理已完成并位于 Unreleased
17. Phase 3-C1 断裂媒体引用手动修复已完成并位于 Unreleased
18. Phase 3-C2 上传残留文件手动清理已完成并位于 Unreleased
19. Phase 3-C3 媒体扫描跳过项定位中心已完成并位于 Unreleased
20. Phase 3-C4 损坏媒体文件手动清理已完成并位于 Unreleased
21. Phase 3-C5 媒体根目录诊断与安全初始化已完成并位于 Unreleased
22. Phase 3-D1 最终父链修复、本地全套验收与 Actions 完成，Unreleased 开发范围已冻结
23. Phase 4-A1 普通媒体单文件详情页实现、本地验收与 Actions 已完成
24. Phase 4-A2 普通媒体安全重命名实现、本地验收、推送与 Actions 已完成
25. N100 / 目标主机部署未开始，等待用户明确授权
26. 其余仅按实际问题做可选维护
```

已完成依据：

- Phase 2-F1 已完成只读 `/data-health` 页面和基础健康报告
- Phase 2-F2 已完成备份文件校验、恢复 dry-run 和导入 dry-run 报告
- Phase 2-F3 已完成低风险手动修复，修复范围限定在关系表和辅助记录
- Phase 2-G1 已完成本地基础设置中心，覆盖默认语言、分页、排序和首页入口
- Phase 2-G6 已完成 strict `CONFIRM`、备份提醒、结果详情和危险操作提示统一
- Phase 2-H 已随 v0.9.0 完成发布，启动预检、显式升级、备份确认和失败回滚边界已经建立
- Phase 2 结束时 schema 为 1 且生产迁移注册表为空；Phase 3-A1 现已增加唯一真实的 1 → 2 来源表迁移
- Phase 2-I1 已使用 100 / 1,000 / 10,000 条隔离数据完成列表、工作台、统计、维护页和文件 dry-run 基线
- I1 已确认列表与 cleanup 查询放大、合集详情 N+1、元数据 / 候选页无分页和统计重复扫描，未直接修复
- Phase 2-I2 已完成按需关系加载、metadata / candidate 分页、合集双分页、settings 复用、stats 聚合和 data-health 明细上限
- I2 在 10,000 条基线中将 items / cleanup / collection detail / stats 查询数分别从 258 / 249 / 165 / 28 降至 11 / 4 / 9 / 11
- Phase 2-I3 已统一页面 / API 错误、request_id 和脱敏请求日志，并保持高风险事务与确认边界
- I3 静态审查收紧外部 request_id 为 UUID / UUID hex，未匹配路由日志固定为 `/[unmatched]`
- Phase 2-I4 已完成登录与 session、同源写请求、服务端确认、输入输出、rollback、五类数据库和兼容性总审查
- I4 三档性能矩阵保持 I2 查询上限且无 N+1 回归，没有为剩余扫描新增索引或虚构迁移
- Phase 2-I 已随 v1.0.0 发布；任何后续索引仍需单独审批真实迁移
- Phase 2-K1 已确认没有真实 TODO、占位路由或失效入口，并将当时剩余工作限定为 K2 / K3
- Phase 2-K2 已关闭本地素材、批量 / 清除 / 解除确认、示例凭据、F4 专项测试和运维清单缺口
- K2 全量测试 347 passed，隔离 Docker build / up / `/login` 200 / 登录后本地媒体 200 / down 通过并已清理
- Phase 2-L4 已增加独立 Docker 生产冒烟 job、失败日志和始终执行的资源清理，并保留 pytest / pip check
- Phase 2-L5 已将 CI 权限限定为 `contents: read`，同一 workflow / ref 的过时运行由 concurrency 自动取消
- Phase 2-L6 已用 Python 标准库为生产镜像增加 `/login` 健康检查；CI 在执行原有 HTTP / 安全头检查前等待容器 `healthy`
- Phase 2-L7 已为生产与 CI Compose 增加只读根文件系统、`cap_drop: ALL`、`no-new-privileges` 和 `/tmp` tmpfs，并保留 `/app/data` 写入
- Phase 2-L8 已将应用与健康检查切换为固定 UID/GID `10001:10001`，并验证安全边界和 SQLite 重建持久化
- Phase 3-A1 已完成来源 CRUD、本地文本 / 书签预览导入、备份兼容和显式 Schema 1 → 2 升级
- Phase 3-A1 来源导入已补齐同名条目歧义保护，混合批次只写入可唯一确定目标的正常记录
- Phase 3-A2 已完成安全扫描、多图上传、SHA-256 去重、封面 / 头像关联和损坏文件降级
- Phase 3-A2 上传落盘已补齐临时文件、fsync、原子发布、竞态复核和批次失败清理
- Phase 3-A3 已完成确定性文件名候选、双向歧义冲突、单项 / 当前页事务确认及不覆盖保护
- Phase 3-A3 专项覆盖预览零写入、伪造冲突、strict 确认、跨页拒绝、陈旧目标和提交时条件更新，全量 407 passed
- Phase 3-A4 已完成未匹配图片建档、可编辑标题、现有 / 批次冲突拒绝、当前页事务写入和媒体不变保护
- Phase 3-A4 专项覆盖后缀过滤、预览零写入、标题编辑、strict 确认、冲突 / 跨页 / 陈旧 / 伪造拒绝和数据库失败整批回滚，全量 416 passed
- Phase 3-A5 已完成路径搜索、状态筛选、稳定排序、20 条媒体分页、三套页码状态保留和非法参数零写入回退
- Phase 3-A5 专项覆盖 Unicode 路径搜索、五种状态、四种排序、页码夹取、三套分页 URL、空结果、重定向状态和 A3/A4 候选不变，全量 424 passed
- Phase 3-A6 已完成封面 / 头像断裂引用、不可用媒体根、上传残留、SHA-256 重复内容和扫描跳过项的只读审计
- Phase 3-A6 专项覆盖正常未使用媒体、五类引用异常、三类根目录异常、告警汇总、200 条明细上限、GET 零写入和媒体修复拒绝，全量 433 passed
- Phase 3-B1 已完成完整 SHA-256 稳定分组、三项重复统计、duplicate 筛选、SHA 前缀搜索和同组路径展示
- Phase 3-B1 专项覆盖无效 / 单独媒体排除、排序分页状态、GET 零写入及 A3/A4 候选不变，全量 435 passed
- Phase 3-B2 已完成共享分组服务、组指标与引用、三类双向排序、20 组分页和 B1 精确链接
- Phase 3-B2 专项覆盖登录 / 405、边界复用、六种排序、非法参数、分页状态、GET 零写入及双语，全量 441 passed
- v1.0.6 已正式发布且范围仅为 B1 / B2；旧 tag / Release 未移动
- v1.0.6 发布前全量 441 passed、pip check 和隔离 Docker 双生命周期已通过
- Phase 3-B3 已完成显式 keeper、零写入预览、提交重扫、引用先迁移和安全删除实现
- Phase 3-B3 专项覆盖 strict 确认、陈旧 / 伪造 / 越界 / 文件异常拒绝、提交失败零删除及删除失败安全重试
- Phase 3-B3 keeper 竞态修复后全量 459 passed、pip check 与隔离 Docker 双生命周期已通过，SQLite 重建校验和不变且临时资源已清理
- Phase 3-B4 专项 16 passed、完整媒体链 120 passed、全量 474 passed 且 pip check 无冲突
- Phase 3-B4 隔离 Docker 双生命周期均 healthy，登录 / 恢复中心 / 普通媒体 / data-health 200，SQLite 校验和不变且资源已清理
- Phase 3-B5 已完成零写入预览、完整身份重验、无覆盖恢复发布、事务引用迁移、数据库失败补偿和锚点残留报告
- Phase 3-B5 专项覆盖 standard / strict、已引用 / 未引用、损坏 / 符号链接 / 错误扩展 / stale / forged / recovered 拒绝、目标碰撞、文件 / 目录 fsync、DB 回滚清理、删除失败和普通入口隔离
- Phase 3-B5 专项 12 passed、全量 486 passed 且 pip check 无冲突；隔离 Docker 双生命周期 healthy，登录 / 认证 / 恢复中心 / 单项预览 200，SQLite 校验和不变且临时资源已清理
- Phase 3-B5 功能提交 `9e19509` 已推送 main，Actions run `29306074275` 的 test / Docker production smoke 均通过
- Phase 3-B6 已完成零写入预览、完整身份重验、`BEGIN IMMEDIATE` 零引用复核、身份删除、目录 fsync 和失败状态报告
- Phase 3-B6 专项 15 passed，竞态注入、unlink / fsync / 写锁 / 引用查询失败和 B3-B5 完整媒体链回归 156 passed
- Phase 3-B6 全量 501 passed 且 pip check 无冲突；最终工作树隔离 Docker 双生命周期 healthy，登录 / 认证 / 恢复中心 / 删除预览 / 确认删除 200，SQLite 校验和不变且临时资源已清理
- Phase 3-B6 功能提交 `b70e18e` 已推送 main，Actions run `29309167659` 的 test / Docker production smoke 均通过
- Phase 3-C1 已完成 Data Health 单项入口、零写入预览、替代媒体路径 / SHA 搜索与 20 条分页、显式替换 / 清除和条件更新
- Phase 3-C1 提交在 `BEGIN IMMEDIATE` 内重验对象、原引用、问题与替代文件完整身份；陈旧 / 伪造 / cleanup anchor 请求拒绝，DB 失败整笔回滚且不操作文件
- Phase 3-C1 专项 7 passed、B3-B6 / 媒体库 / Data Health / 备份 / 导入组合回归 232 passed、全量 508 passed 且 pip check 无冲突
- Phase 3-C1 隔离 Docker 双生命周期 healthy，登录 / 认证 / Data Health / 预览 / 替换 / 清除 200，引用持久化、媒体 SHA 和 SQLite 重建校验和验收通过
- Phase 3-C1 功能提交 `05adaf7` 已推送 main，Actions run `29314452641` 的 test / Docker production smoke 均通过
- Phase 3-C2 已完成 Data Health 单项入口、零写入且不读内容的完整身份预览、已引用 C1 指引、`BEGIN IMMEDIATE` 零引用复核、身份删除和目录 fsync
- Phase 3-C2 专项覆盖精确 / 近似名称、目录 / 符号链接 / FIFO、非法 / 缺失 / 陈旧 / 伪造 / 同路径替换、standard / strict、引用与身份竞态、写锁 / 查询 / unlink / fsync 失败
- Phase 3-C2 专项 22 passed、C1 / B3-B6 / 上传 / Data Health / 备份 / 导入组合回归 253 passed、全量 530 passed 且 pip check 无冲突
- Phase 3-C2 Docker image build 通过，Compose healthy、`/login` 200，并已完整 down 清理
- Phase 3-C2 功能提交 `ab373b3` 已推送 main，Actions run `29317914417` 的 test / Docker production smoke 均通过
- Phase 3-C4 已完成损坏普通媒体 finding、媒体库 / Data Health 双入口、零写入完整身份预览、C1 引用指引、锁内零引用重验、身份删除和目录 fsync
- Phase 3-C4 专项 17 passed、媒体链与数据回归 280 passed、全量 557 passed 且 pip check 无冲突；Docker build、healthy Compose、`/login` 200 与 down 清理通过
- Phase 3-C4 功能提交 `1e686f3` 已推送 main，Actions run `29336790587` 的 test / Docker production smoke 均通过
- Phase 3-D1 已完成 B3-C5 finding / 导航 / 身份 / 引用 / GET / POST / 失败状态总审查，完整证据见 `PHASE3_COMPLETION_AUDIT.md`
- Phase 3-D1 修复 Data Health 路径重走、重复 finding 缺少直接入口、B3-B6 共享验证媒体父路径重解析及 C2 父链身份丢失四类真实问题
- Phase 3-D1 最终父链精确竞态 2 passed、核心回归 177 passed、组合回归 365 passed、全量 584 passed，pip check 与隔离 Docker healthy / HTTP 验收通过；修复提交 `db0048d` 的 Actions run `29386547600` 两个 job 均成功，已重新记录最终冻结
- Phase 4-A1 已完成安全只读详情聚合、全部引用与完整 SHA 重复组展示、三类来源状态返回、C1/C4 复用及外部路径 / symlink / 特殊文件 / anchor / 竞态拒绝；专项 17 passed、媒体链组合 252 passed、全量 601 passed、pip check 与隔离 Docker / HTTP 通过；提交 `c8cfb99` 与 Actions run `29389862206` 两个 job 均成功
- Phase 4-A2 已完成同目录 basename 预览、完整身份 / 引用快照、写锁重验、verified-parent-FD no-overwrite hardlink、事务引用迁移与 commit 后身份删除；commit 歧义修复改为独立 Session 复核后才决定清理或保留双路径，修复后专项 50 passed、广泛组合 315 passed、全量 650 passed、pip check 与隔离 Docker / HTTP 通过；修复提交 `09be556` 与 Actions run `29399210087` 两个 job 均成功
- 当前发布准备与本地验收完成后仍需单独发布指令；N100 部署须等待用户明确授权

---

## 八、长期禁止项

除非用户明确重新审批，否则禁止实现：

- 请求或抓取外部内容源
- 爬虫
- 站点 adapter
- 远程图片拉取
- 自动同步
- 多源搜索
- 随机探索
- 推荐系统
- AI 语义判断
- 云同步
- 多用户系统
- 复杂权限系统
- 前端框架重构
- 未审批的新依赖

明确允许：保存用户提供的来源 URL、解析用户上传的本地书签 HTML、
解析用户提供的纯文本 URL 清单。允许项不得发起外部 HTTP 请求或扩展为
远程元数据 / 图片获取、站点适配或自动化采集。

---

## 九、开发阶段完成标准

每个阶段完成前必须确认：

- 功能在 GOAL.md 范围内
- 未触碰 RULE.md 禁止项
- 测试通过
- Docker build 通过
- Docker compose 能启动
- `/login` GET 返回 200
- i18n key 对称
- README 更新
- TASKS 更新
- REVIEW 更新
- CHANGELOG 写入 Unreleased
- 工作区干净
- 已提交并推送，除非用户要求暂停

---

## 十、发布标准

发布版本前必须确认：

- 当前阶段已通过审查
- 完整测试通过
- Docker 验收通过
- CHANGELOG 从 Unreleased 整理到新版本段
- README 当前版本号更新
- TASKS / REVIEW 同步更新
- 不修改旧 tag
- 创建 annotated tag
- 推送 main 和 tag
- 创建 GitHub Release
- Release 内容与 CHANGELOG 一致
