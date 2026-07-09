# Codex 开发任务清单 — MVP

按顺序执行，每完成一项打个 [x]。

## 前置准备

- WSL Ubuntu 22.04
- `python3.12 -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements-dev.txt`
- VS Code + Codex 插件

## Day 1: 骨架 + 数据库 + 基础 API

- [x] **T1.1** 初始化 FastAPI 项目结构
  - `app/main.py`：FastAPI 入口
  - `app/config.py`：读取环境变量（DATABASE_URL、APP_PASSWORD、SECRET_KEY）
  - `app/database.py`：SQLite + SQLAlchemy 初始化
- [x] **T1.2** 设计 SQLAlchemy 模型
  - `app/models.py`：6 张表 → items、creators、tags、item_tags、item_creators、user_item_states
  - 含外键、级联删除、唯一约束
- [x] **T1.3** 实现 items CRUD API
  - `routers/items.py`：GET/POST/PUT/DELETE
  - 分页列表，按创建时间倒序
  - extra 字段存 JSON

## Day 2: 标签 + 创作者

- [x] **T2.1** 标签管理 API
  - `routers/tags.py`：GET/POST/PUT/DELETE
- [x] **T2.2** 创作者管理 API
  - `routers/creators.py`：GET/POST/GET{id}/DELETE

## Day 3: 登录 + 状态 + 搜索 + 统计

- [x] **T3.1** 单用户登录保护
  - `app/auth.py`：密码从 `APP_PASSWORD` 环境变量读取，禁止默认空密码
  - `routers/auth.py`：POST /api/auth/login、POST /api/auth/logout
  - Session cookie 认证（`starlette.middleware.sessions`）
  - 所有页面和 API 默认需登录
  - 日志不得输出密码、cookie、token
  - `.env.example` 提供模板，`.env` 在 gitignore
- [x] **T3.2** 状态标记 API
  - `POST /api/items/{id}/state`：设置 status/rating/review
  - `GET /api/items/{id}/state`：查状态
  - `DELETE /api/items/{id}/state`：取消
- [x] **T3.3** 搜索 API
  - `routers/search.py`：标题模糊搜索 + 标签过滤 + 状态过滤 + 分页
- [x] **T3.4** 统计 API
  - `routers/stats.py`：总数/各状态统计/时间线

## Day 4: 前端页面

- [x] **T4.1** 基础模板 + 登录页
  - `templates/base.html`：导航栏 + 通用布局
  - `templates/login.html`：密码登录表单
- [x] **T4.2** 首页
  - 最近添加 + 快捷操作入口
- [x] **T4.3** 条目列表 + 详情页
  - 列表：卡片布局（封面、标题、标签、状态标记）
  - 详情：信息 + 标记按钮 + 标签 + 创作者
  - 新增/编辑表单
- [x] **T4.4** 标签管理页 + 创作者管理页
- [x] **T4.5** 统计页面
- [x] **T4.6** 中文 / English 语言切换
  - `app/i18n.py`：中英翻译字典，默认中文
  - `/set-language?lang=zh|en`：切换语言
  - Session 保存语言偏好，刷新后不丢失
  - 所有 Jinja2 页面展示文本接入 `t("...")`

## Day 5: 导入 + 部署 + 测试

- [x] **T5.1** CSV/JSON 导入
  - `services/importer.py`：解析 CSV，自动创建不存在的标签和创作者
  - `templates/import.html`：上传 + 预览 + 确认
- [x] **T5.2** Dockerfile + docker-compose.yml
  - 多阶段构建
  - `data/` 目录持久化
  - `.env` 映射
- [x] **T5.3** 基础测试
  - `tests/test_database.py`：建表 + 模型
  - `tests/test_items.py`：CRUD
  - `tests/test_states.py`：标记
  - `tests/test_search.py`：搜索
- [x] **T5.4** 整体验收 + 修复

## 本地备份与恢复

- [x] **B1** 本地 JSON 导出
  - `GET /api/backup/export/json`
  - 导出 items、tags、creators、item_tags、item_creators、user_item_states
- [x] **B2** 本地 CSV 导出
  - `GET /api/backup/export/csv`
  - 导出 items 可读字段、标签、创作者和状态
- [x] **B3** 本地 JSON 备份恢复
  - `POST /api/backup/restore/json`
  - 只接受本项目导出的 JSON 文件，事务性追加 / 合并
- [x] **B4** 备份页面与 i18n
  - `/backup`
  - 导航入口、JSON/CSV 导出按钮、JSON 备份上传入口
- [x] **B5** 备份恢复测试
  - 未登录保护、JSON/CSV 导出、结构校验、合法恢复、非法恢复不破坏数据、中英文页面
- [x] **B6** 备份恢复体验增强
  - `MAX_BACKUP_UPLOAD_MB` 默认 5MB，可配置
  - `POST /api/backup/preview/json`：只预览校验，不写入数据库
  - `/backup` 页面明确合并恢复、非覆盖恢复、本地文件限制
  - 备份错误提示支持中文 / English
  - 覆盖缺文件、非 JSON、超限、非法 JSON、schema 不匹配、缺字段、恢复异常测试

## 本轮清理

- [x] 删除 `data/ehtag_version`
- [x] 删除 `docs/legacy/`
- [x] 确认当前代码不依赖 `docs/legacy/`
- [x] 确认未引入外部 HTTP 请求、爬虫、adapter、远程图片拉取、第三方 cookie/token 管理、自动同步、多源搜索或随机探索接口

## Phase 1 收尾体验修复

- [x] 增加轻量 session flash message，支持 success / error / info 与中英文文案
- [x] 登录、退出、条目、标签、创作者、状态等页面表单操作提供明确反馈
- [x] CSV / JSON 导入预览和确认失败路径提供页面错误提示
- [x] 备份预览 / 恢复成功失败提示复用统一样式，保留本地合并恢复边界
- [x] README 补充本地开发、Docker Compose、N100 局域网部署、`.env`、数据持久化、安全和测试说明
- [x] 确认 TestClient warning 来源，暂不引入不稳定依赖或大范围测试重写
- [x] 补充登录失败、导入失败和备份预览失败页面测试

## v0.1.0 发布前整理

- [x] README 标注 `v0.1.0 / Phase 1 MVP`，列出已包含功能与本地 MVP 边界
- [x] CHANGELOG 增加 `v0.1.0` 小节，包含 Added / Changed / Fixed / Security / Known limitations
- [x] 确认 FastAPI 应用版本号为 `0.1.0`
- [x] 确认 GitHub Actions CI 使用 `requirements-dev.txt` 并运行 `python -m pytest`
- [x] 保持 tag / GitHub Release 仅为发布准备，本轮不自动创建

## 发布前文档与 CI 格式修复

- [x] README / CHANGELOG / TASKS / REVIEW 保持正常 Markdown 标题、列表、段落和代码块
- [x] `.github/workflows/ci.yml` 保持正常多行 YAML 缩进
- [x] 未修改 `app/` 业务代码，未新增业务功能，未创建 tag 或 GitHub Release

## Phase 2-A1 高级筛选与列表页增强

- [x] 新增本地条目查询整理服务，统一处理筛选、排序、分页和非法参数回退
- [x] 列表页支持关键词、状态、单标签、单创作者、最低评分和创建 / 更新时间范围筛选
- [x] 列表页支持最新创建、最早创建、最近更新、最早更新、标题 A-Z、标题 Z-A、评分高到低、评分低到高排序
- [x] 列表页支持 `10` / `20` / `50` / `100` 分页大小，默认 `20`
- [x] 筛选、排序、分页大小和页码使用 query string，刷新和复制链接后保留状态
- [x] 列表页展示当前筛选条件、当前排序、清空筛选入口和无匹配结果空状态
- [x] 新增高级筛选、排序、分页相关中文 / English 文案，并保持 i18n key 覆盖一致
- [x] 补充列表页登录保护、筛选、排序、分页、非法参数、表单状态、空状态和中英文页面测试
- [x] 更新 README / TASKS / REVIEW / CHANGELOG，记录 Phase 2-A1 未发布改动
- [x] 确认本轮未接入外部内容源、爬虫、adapter、远程图片拉取、自动同步、多源搜索、推荐系统或 AI 助手

## Phase 2-A2 批量编辑

- [x] 列表页支持当前页条目多选、全选当前页和取消选择
- [x] 新增本地批量操作服务，统一处理条目 ID 校验、事务提交、处理数和跳过数
- [x] 支持批量修改状态，非法状态安全拒绝
- [x] 支持批量添加一个已有标签，不自动创建不存在标签
- [x] 支持批量移除一个已有标签，条目没有该标签时安全跳过
- [x] 支持批量设置 1-5 评分，非法评分安全拒绝
- [x] 支持批量删除选中条目，并通过现有级联关系清理标签、创作者和状态关联
- [x] 批量删除使用浏览器确认，并在页面显示危险操作与不可撤销提示
- [x] 批量操作后通过安全 `next` 返回列表页，尽量保留筛选、排序、分页和分页大小参数
- [x] 新增批量操作成功 / 失败中文与 English flash 文案
- [x] 补充批量操作登录保护、无选择、非法输入、标签、评分、删除清理、保留参数和中英文文案测试
- [x] 更新 README / TASKS / REVIEW / CHANGELOG，记录 Phase 2-A2 未发布改动
- [x] 确认本轮未接入外部内容源、爬虫、adapter、远程图片拉取、自动同步、多源搜索、推荐系统或 AI 助手

## Phase 2-A3 详情页增强

- [x] 详情页按基本信息、状态信息、标签信息、创作者信息和操作区域分区展示
- [x] 详情页展示标题、描述、创建时间、更新时间、`extra JSON`、当前状态、评分和短评
- [x] 详情页支持快速保存状态、评分和短评，缺少 `UserItemState` 时安全创建
- [x] 非法状态和非法评分会通过 flash error 安全拒绝，不触发 500
- [x] 详情页支持添加一个已有标签，不自动创建不存在标签
- [x] 详情页支持移除一个当前关联标签，不存在标签安全失败
- [x] 详情页支持关联一个已有创作者，不自动创建不存在创作者
- [x] 详情页支持解除一个当前关联创作者，不存在创作者安全失败
- [x] 重复标签 / 创作者关联不会重复创建关联行
- [x] 从列表进入详情时带安全 `next`，返回列表保留筛选、排序、页码和分页大小参数
- [x] 不安全 `next` 会回退到站内路径，不允许外部 URL 或协议相对 URL
- [x] 新增详情页中英文文案和成功 / 失败 flash 文案，并保持 i18n key 覆盖一致
- [x] 补充详情页登录保护、渲染、状态 / 评分 / 短评、标签、创作者、`next` 和中英文文案测试
- [x] 更新 README / TASKS / REVIEW / CHANGELOG，记录 Phase 2-A3 未发布改动
- [x] 确认本轮未接入外部内容源、爬虫、adapter、远程图片拉取、自动同步、多源搜索、推荐系统或 AI 助手

## Phase 2-A4 导入增强

- [x] 导入页面提供 CSV 模板下载入口，模板包含表头和本地示例数据
- [x] 导入页面提供 JSON 模板下载入口，模板使用 `items` 数组和本地示例数据
- [x] 导入页面补充字段说明，覆盖 CSV / JSON 支持字段、必填字段、可选字段、内部状态值、评分规则和本地上传边界
- [x] CSV 上传预览阶段支持一次性字段映射，可映射到 `title`、`summary`、`status`、`rating`、`note`、`tags`、`creators`、`extra` 或忽略该列
- [x] CSV 字段映射校验缺少 `title`、重复映射和无效映射，不触发 500
- [x] CSV / JSON 预览展示总行数、可导入数量、错误数量、即将创建标签数量、即将创建创作者数量、前 5 条预览数据和错误行
- [x] 错误行展示行号、错误原因、原始标题或简要内容
- [x] 预览不写入数据库；确认导入时只写入有效行，全部错误时禁止确认
- [x] 导入结果摘要展示成功导入、跳过、创建标签、创建创作者、标签关联、创作者关联、状态记录和错误数量
- [x] 整理 `app/services/importer.py`，统一模板、解析、预览、字段映射、错误行和结果摘要结构
- [x] 新增导入增强中文 / English 文案，并保持 i18n key 覆盖一致
- [x] 补充模板下载、字段映射、错误路径、预览不写库、部分错误行、结果摘要和中英文页面测试
- [x] 更新 README / TASKS / REVIEW / CHANGELOG，记录 Phase 2-A4 未发布改动
- [x] 确认本轮未接入外部内容源、URL 导入、爬虫、adapter、远程图片拉取、自动同步、推荐系统、AI 助手、云同步、多用户系统或大型前端框架

## v0.2.0 发布准备

- [x] 确认 `main` 已包含 Phase 2-A1 高级筛选 / 排序 / 分页
- [x] 确认 `main` 已包含 Phase 2-A2 批量编辑
- [x] 确认 `main` 已包含 Phase 2-A3 详情页增强
- [x] 确认 `main` 已包含 Phase 2-A4 导入增强
- [x] 将 CHANGELOG 的 `Unreleased` 内容整理为 `v0.2.0` 发布段
- [x] 更新 README 当前版本状态与 Phase 2 发布说明
- [x] 保持 `v0.1.0` tag 不变
- [x] 本轮仅做 release 文档准备，不新增业务功能、不进入 Phase 3

## Phase 2-B1 移动端 / 响应式 UI 打磨

- [x] 全站基础布局补充响应式 CSS，控制主内容边距、卡片、网格、表单、按钮、标签和 flash message 在窄屏下的展示
- [x] 顶部导航支持移动端换行分组，保持 NSFWTrack、语言切换和登录 / 登出入口可见
- [x] 条目列表页筛选区、批量编辑区、条目卡片、多选 checkbox 和分页区域完成移动端布局优化
- [x] 详情页基本信息、状态信息、标签、创作者、快速编辑和操作区在移动端纵向排列并保留删除确认
- [x] 导入页面模板下载、字段说明、CSV 字段映射、预览、错误行和结果摘要区域使用可换行布局与局部表格滚动
- [x] 条目、标签、创作者等表单页面在移动端保持输入框、textarea、select 和按钮布局清晰
- [x] 备份页面保持导出、预览和恢复表单移动端可点击；统计、标签和创作者表格使用局部横向滚动
- [x] 长标题、长标签、长创作者名称和 `extra JSON` 不应撑破页面，必要内容在局部区域滚动或断行
- [x] 新增响应式 HTML 结构测试，覆盖首页、列表、详情、导入、备份、统计、标签和创作者页面
- [x] 更新 README / TASKS / REVIEW / CHANGELOG，记录 Phase 2-B1 未发布改动
- [x] 确认本轮未新增业务功能、依赖、数据库结构、外部内容源、URL 导入、爬虫、adapter、推荐系统、AI 助手、云同步或多用户系统

## Phase 2-B2 统计面板增强

- [x] 新增本地统计 service，集中生成总览、状态分布、评分分布、标签排行、创作者排行、最近活动和数据完整性结构
- [x] 统计页总览卡片展示总条目数、总标签数、总创作者数、有状态记录、有评分、平均评分、最近 7 天新增和最近 30 天新增
- [x] 状态分布覆盖 `wish`、`watching`、`watched`、`like`、`dislike`、`ignore`，显示数量和比例
- [x] 评分分布覆盖 1-5 分数量、比例、平均评分、最高评分和最低评分
- [x] 标签使用排行展示本地关联数量最多的前 10 个标签及占比
- [x] 创作者关联排行展示本地关联数量最多的前 10 个创作者及占比
- [x] 最近活动展示最近 7 / 30 天新增与更新数量，并以纯 HTML / CSS 展示 7 天趋势
- [x] 数据完整性概览展示没有标签、没有创作者、没有状态记录、没有评分和没有描述的条目数量
- [x] 空数据场景显示稳定空状态，比例计算不除零
- [x] 新增统计增强中文 / English 文案，并保持 i18n key 覆盖一致
- [x] 补充统计页登录保护、空数据、总览数量、分布、排行、近期活动、完整性和中英文页面测试
- [x] 更新 README / TASKS / REVIEW / CHANGELOG，记录 Phase 2-B2 未发布改动
- [x] 确认本轮未接入外部内容源、URL 导入、爬虫、adapter、推荐系统、AI 分析、图表库、新依赖、数据库结构变更、云同步或多用户系统

## v0.3.0 发布准备

- [x] 确认 `main` 已包含 Phase 2-B1 移动端 / 响应式 UI 打磨
- [x] 确认 `main` 已包含 Phase 2-B2 统计面板增强
- [x] 将 CHANGELOG 的 `Unreleased` 内容整理为 `v0.3.0` 发布段
- [x] 更新 README 当前版本状态与 Phase 2-B 发布说明
- [x] 保持 `v0.1.0` 和 `v0.2.0` tag 不变
- [x] 本轮仅做 release 文档准备，不新增业务功能、不进入 Phase 3

## Phase 2-C1 合集 / 清单管理

- [x] 新增本地 SQLite 合集模型 `collections`，包含名称、可选描述、创建时间和更新时间
- [x] 新增本地 SQLite 关联模型 `item_collections`，支持条目与合集多对多关系
- [x] 合集名称去除首尾空格，空名称和重复名称有友好错误提示
- [x] 删除合集只删除合集与关联关系，不删除任何条目
- [x] 新增 `/collections` 合集列表页，显示名称、描述、条目数量、创建时间、更新时间、详情、编辑和删除入口
- [x] 新增合集创建、编辑、删除页面流程，所有页面和提交都要求登录
- [x] 新增合集详情页，展示合集信息、合集内条目、空状态和添加 / 移出条目能力
- [x] 条目详情页展示所属合集，并支持加入一个已有合集或移出当前关联合集
- [x] 条目列表页支持按合集筛选，并和关键词、标签、创作者、状态、排序、分页共同保留 query string
- [x] 批量编辑支持将当前页选中条目加入一个已有合集，或从一个已有合集移出
- [x] 批量合集操作只处理当前页选中条目，不实现跨页全选或持久化选择状态
- [x] 统计页增加总合集数、有合集条目数、无合集条目数和合集排行
- [x] 新增合集相关中文 / English 文案，并保持 i18n key 覆盖一致
- [x] 补充合集 CRUD、关联管理、筛选、批量操作、统计、i18n 和新表创建测试
- [x] 更新 README / TASKS / REVIEW / CHANGELOG，记录 Phase 2-C1 未发布改动
- [x] 确认本轮未接入外部内容源、URL 导入、爬虫、adapter、推荐系统、AI 助手、云同步、多用户系统、前端构建流程或新依赖
- [x] 确认本轮未修改 `v0.1.0`、`v0.2.0` 或 `v0.3.0` tag，未创建 GitHub Release

## Phase 2-C2 备份 / 导入支持合集数据

- [x] JSON 备份导出包含 `collections` 和 `item_collections`
- [x] JSON 备份预览显示合集数量、条目-合集关联数量、即将创建 / 合并合集数量、可恢复 / 不可恢复关联数量和合集错误数量
- [x] JSON 恢复支持合并合集，并保留旧备份缺少合集表时的兼容性
- [x] JSON 恢复支持恢复条目-合集关联，重复关联不会重复创建
- [x] JSON 恢复遇到空合集名称、坏关联、缺失条目或缺失合集时跳过并记录合集错误
- [x] JSON 恢复采用追加 / 合并策略，不删除现有条目，不覆盖清空数据库
- [x] CSV 导出增加 `collections` 字段，多合集用分号分隔
- [x] CSV 导入支持可选 `collections` 字段，自动创建或关联本地合集
- [x] JSON 导入支持可选 `collections` 字符串数组，非数组或非字符串元素进入错误行
- [x] CSV / JSON 旧导入文件缺少 `collections` 字段时仍可正常导入
- [x] CSV / JSON 导入预览显示即将创建合集、即将关联合集和 collections 字段错误数量，且预览不写库
- [x] 导入结果摘要显示创建合集、关联合集、跳过合集和 collections 字段错误数量
- [x] CSV / JSON 导入模板加入 `collections` 示例字段
- [x] 备份页面说明 JSON 备份包含合集和条目-合集关联，CSV 导出包含 `collections` 字段，恢复不会删除条目
- [x] 新增备份 / 导入合集相关中文 / English 文案，并保持 i18n key 覆盖一致
- [x] 补充备份、恢复、导出、导入、预览、模板、兼容性和坏关联测试
- [x] 更新 README / TASKS / REVIEW / CHANGELOG，记录 Phase 2-C2 未发布改动
- [x] 确认本轮未新增数据库表、未修改已有数据库字段、未新增依赖、未引入外部内容源 / URL 导入 / 爬虫 / adapter / 推荐系统 / AI 助手 / 云同步 / 多用户系统
- [x] 确认本轮未修改 `v0.1.0`、`v0.2.0` 或 `v0.3.0` tag，未创建 GitHub Release

## v0.4.0 发布准备

- [x] 确认 `main` 已包含 Phase 2-C1 合集 / 清单管理
- [x] 确认 `main` 已包含 Phase 2-C2 备份 / 导入支持合集数据
- [x] 将 CHANGELOG 的 `Unreleased` 内容整理为 `v0.4.0` 发布段
- [x] 更新 README 当前版本状态与 Phase 2-C 发布说明
- [x] 保持 `v0.1.0`、`v0.2.0` 和 `v0.3.0` tag 不变
- [x] 本轮仅做 release 文档准备，不新增业务功能、不改数据库结构、不新增依赖、不进入 Phase 3

## Phase 2-D1 重复条目检测与手动合并

- [x] 新增本地重复检测 service，基于本地 SQLite 条目生成候选组
- [x] 支持标题完全匹配检测，忽略首尾空格，不修改原始标题
- [x] 支持标题归一化匹配检测，使用 Unicode NFKC、首尾 trim、casefold 和连续空白折叠
- [x] 检测结果标明 `exact_title` 或 `normalized_title`
- [x] 新增 `/duplicates` 候选列表页，要求登录且只读展示
- [x] 候选列表展示匹配类型、匹配 key、候选数量、标题、状态、评分、标签数量、创作者数量和合集数量
- [x] 候选列表提供对比入口，空结果显示稳定空状态
- [x] 新增 `/duplicates/compare` 条目对比页，要求登录并校验非法 ID、缺失条目和相同条目
- [x] 对比页展示保留条目和重复条目的标题、简介、状态、评分、短评、标签、创作者、合集、`extra JSON`、创建时间和更新时间
- [x] 对比页明确 primary 为保留条目、duplicate 为合并后删除条目
- [x] 合并仅支持手动 POST 提交，不支持 GET 合并、自动合并或批量自动合并
- [x] 合并前显示危险提示、备份建议和浏览器二次确认
- [x] 合并保留 primary item，并在成功后删除 duplicate item
- [x] 合并转移标签、创作者和合集关系，不重复创建关系
- [x] 合并不会删除标签、创作者或合集记录本身
- [x] primary 缺少状态、评分、短评或简介而 duplicate 有值时安全复制
- [x] 状态、评分、短评和简介冲突默认保留 primary，用户可显式选择 duplicate 覆盖
- [x] 空值不会默认覆盖 primary，非法状态和非法评分不会写入
- [x] `extra JSON` 缺失时复制，双方都有值时浅合并非冲突键，冲突键默认保留 primary
- [x] 非法 `extra` 内容不会触发 500，合并结果保持有效 JSON
- [x] 合并结果 flash 摘要展示关系转移数量、字段处理结果、`extra` 新增键数量、冲突保留数量和 duplicate 删除状态
- [x] 导航、条目列表页和条目详情页加入重复检测入口
- [x] 新增重复检测 / 合并相关中文 / English 文案，并保持 i18n key 覆盖一致
- [x] 补充重复检测登录保护、空状态、候选检测、对比校验、POST-only 合并、关系转移、冲突处理、`extra` 合并、状态复制、删除 duplicate 和中英文文案测试
- [x] 更新 README / TASKS / REVIEW / CHANGELOG，记录 Phase 2-D1 未发布改动
- [x] 确认本轮未新增数据库表、未修改已有数据库字段、未新增依赖
- [x] 确认本轮未接入外部内容源、URL 导入、爬虫、adapter、AI 去重、图片相似度、自动批量合并、推荐系统、云同步或多用户系统
- [x] 确认本轮未修改 `v0.1.0`、`v0.2.0`、`v0.3.0` 或 `v0.4.0` tag，未创建 GitHub Release

## Phase 2-D2 标签 / 创作者 / 合集清理与合并

- [x] 新增本地元数据清理 service，基于本地 SQLite tags、creators、collections 生成候选组
- [x] 支持名称完全匹配检测，忽略首尾空格，不修改数据库原始名称
- [x] 支持名称归一化匹配检测，使用 Unicode NFKC、首尾 trim、casefold 和连续空白折叠
- [x] 检测结果标明 `exact_name` 或 `normalized_name`
- [x] 新增 `/cleanup` 候选列表页，要求登录且只读展示
- [x] 候选列表展示元数据类型、匹配类型、匹配 key、对象名称、关联条目数量和对比入口
- [x] 候选列表覆盖重复标签、重复创作者、重复合集和稳定空状态
- [x] 新增 `/cleanup/compare` 元数据对比页，要求登录并校验非法 type、非法对象和相同对象
- [x] 对比页展示 primary 保留对象、duplicate 将删除对象、名称、关联条目数量、关联条目预览和危险提示
- [x] 合集对比页展示 primary / duplicate description、description 冲突提示和使用 duplicate description 覆盖选项
- [x] 合并仅支持手动 POST 提交，不支持 GET 合并、自动合并、一键全部合并或批量自动合并
- [x] 合并前显示危险提示、备份建议和浏览器二次确认
- [x] 标签合并保留 primary tag，转移 duplicate tag 的 item_tags，跳过重复关联并删除 duplicate tag
- [x] 创作者合并保留 primary creator，转移 duplicate creator 的 item_creators，跳过重复关联并删除 duplicate creator
- [x] 合集合并保留 primary collection，转移 duplicate collection 的 item_collections，跳过重复关联并删除 duplicate collection
- [x] 合集合并不会删除任何条目、标签或创作者
- [x] primary description 为空且 duplicate description 非空时自动复制
- [x] description 冲突默认保留 primary，只有用户显式选择时才覆盖
- [x] 合并结果 flash 摘要展示合并类型、保留对象、删除对象、转移关联数、跳过重复关联数、description 处理、duplicate 删除状态和重新查看清理页建议
- [x] 登录后导航、标签页、创作者页和合集页加入元数据清理入口
- [x] 新增元数据清理 / 合并相关中文 / English 文案，并保持 i18n key 覆盖一致
- [x] 补充元数据清理登录保护、空状态、候选检测、对比校验、POST-only 合并、关系转移、重复关系跳过、删除 duplicate、保留条目、description 冲突和中英文文案测试
- [x] 更新 README / TASKS / REVIEW / CHANGELOG，记录 Phase 2-D2 未发布改动
- [x] 确认本轮未新增数据库表、未修改已有数据库字段、未新增依赖
- [x] 确认本轮未接入外部内容源、URL 导入、爬虫、adapter、AI 同义词识别、自动批量合并、推荐系统、云同步或多用户系统
- [x] 确认本轮未修改 `v0.1.0`、`v0.2.0`、`v0.3.0` 或 `v0.4.0` tag，未创建 GitHub Release

## v0.5.0 发布准备

- [x] 确认 `main` 已包含 Phase 2-D1 重复条目检测与手动合并
- [x] 确认 `main` 已包含 Phase 2-D2 标签 / 创作者 / 合集清理与手动合并
- [x] 将 CHANGELOG 的 `Unreleased` 中 Phase 2-D1 / D2 内容整理为 `v0.5.0` 发布段
- [x] 更新 README 当前版本状态与 Phase 2-D 数据清理发布说明
- [x] 保持 `v0.1.0`、`v0.2.0`、`v0.3.0` 和 `v0.4.0` tag 不变
- [x] 本轮仅做 release 文档准备，不新增业务功能、不改数据库结构、不新增依赖、不进入 Phase 3

## Phase 2-E1 保存筛选视图 / 常用视图

- [x] 新增本地 SQLite `saved_views` 表，包含 `id`、`name`、`query_string`、`created_at` 和 `updated_at`
- [x] 通过现有 `create_all` 机制兼容旧数据库启动，不修改已有表字段，不删除已有表
- [x] 条目列表页新增常用视图面板，可输入名称保存当前筛选 / 排序 / page_size 参数
- [x] 支持应用保存视图，使用 GET 重定向回 `/items`，不修改数据库
- [x] 支持更新保存视图为当前筛选条件，更新操作要求登录和 POST
- [x] 支持删除保存视图，删除操作要求登录、POST 和浏览器确认
- [x] 视图名称去除首尾空格，空名称、重复名称和过长名称有中英文友好提示
- [x] 保存 query string 时只保留条目列表已有白名单参数，忽略未知参数和站外跳转参数
- [x] 保存 query string 时不保存 `page` 页码，避免应用视图后跳到过期分页
- [x] 保存 query string 使用稳定参数顺序，便于测试和比较
- [x] JSON 备份导出 / 预览 / 恢复支持 `saved_views`，旧备份缺少该表时仍兼容
- [x] 新增保存视图中文 / English 文案，并保持 i18n key 覆盖一致
- [x] 补充保存视图登录保护、创建、校验、重复名称、参数过滤、应用、非法 ID、更新、POST-only 删除、删除后不存在、页面展示、中英文文案和备份兼容测试
- [x] 更新 README / TASKS / REVIEW / CHANGELOG，记录 Phase 2-E1 未发布改动
- [x] 确认本轮未接入 AI 推荐、智能分类、外部内容源、URL 导入、爬虫、adapter、云同步、多用户共享视图或复杂权限
- [x] 确认本轮未修改已发布 tag，未创建 GitHub Release，未新增依赖，未修改已有数据库字段

## Phase 2-E2 最近访问 / 最近编辑

- [x] 新增本地 SQLite `item_activity` 表，包含 `id`、`item_id`、`last_viewed_at`、`view_count`、`last_edited_at`、`edit_count`、`created_at` 和 `updated_at`
- [x] `item_activity.item_id` 指向本地条目，并通过唯一约束保证每个 item 最多一条 activity 记录
- [x] 通过现有 `create_all` 机制兼容旧数据库启动，不修改已有表字段，不删除已有表
- [x] 登录用户访问条目详情页时记录 `last_viewed_at` 和累加 `view_count`
- [x] 未登录访问、列表页曝光和不存在条目不会写入 activity
- [x] 访问记录失败时使用安全记录逻辑，不应导致详情页 500
- [x] 条目基础信息编辑成功后记录 `last_edited_at` 和累加 `edit_count`
- [x] 状态、评分和短评更新成功后记录最近编辑
- [x] 标签添加 / 移除成功后记录最近编辑
- [x] 创作者添加 / 移除成功后记录最近编辑
- [x] 合集加入 / 移出成功后记录最近编辑，覆盖条目详情页和合集详情页入口
- [x] 当前页批量编辑成功后仅为实际处理到的条目记录最近编辑，不做跨页扩展
- [x] 新增 `/activity` 最近活动页面，要求登录，只读展示最近访问和最近编辑
- [x] 首页显示最近访问和最近编辑入口，条目列表页提供最近访问 / 最近编辑快捷入口
- [x] 条目详情页显示该条目的访问次数、编辑次数、最后访问时间和最后编辑时间
- [x] 新增 `POST /activity/clear`，要求登录、POST 和浏览器确认
- [x] 清空最近活动只删除 `item_activity` 记录，不删除条目、标签、创作者、合集或 saved views
- [x] JSON 备份导出 / 预览 / 恢复支持 `item_activity`，旧备份缺少该表时仍兼容
- [x] JSON 恢复跳过缺失条目的 activity 行并记录错误，不因为坏 activity 数据触发 500
- [x] 不记录 IP、User-Agent、设备指纹、外部来源或站外 URL
- [x] 新增最近活动中文 / English 文案，并保持 i18n key 覆盖一致
- [x] 补充最近活动登录保护、空状态、访问记录、重复访问、未登录不写入、不存在条目不写入、编辑记录、重复编辑、状态 / 评分 / 标签 / 创作者 / 合集 / 批量编辑记录、排序、清空安全、i18n 和备份兼容测试
- [x] 更新 README / TASKS / REVIEW / CHANGELOG，记录 Phase 2-E2 未发布改动
- [x] 确认本轮未接入 AI 推荐、智能分析、自动分类、外部内容源、URL 导入、爬虫、adapter、云同步、多用户活动流、第三方统计或用户画像
- [x] 确认本轮未修改已发布 tag，未创建 GitHub Release，未新增依赖，未修改已有数据库字段

## Phase 2-E3 快捷操作入口 / 工作台增强

- [x] 首页 / 工作台新增快捷操作区，集中入口覆盖新增条目、条目列表、保存视图、最近活动、统计、合集、重复条目、元数据清理、导入和备份
- [x] 首页新增已保存视图轻量卡片，复用本地 `saved_views` 数据并通过只读 GET 入口进入对应列表视图
- [x] 首页保留最近访问和最近编辑区，并提供跳转到 `/activity` 对应区域的入口
- [x] 条目列表页新增快捷操作区，覆盖新增条目、保存当前视图、已保存视图、最近活动、重复条目检测、元数据清理、导入和备份
- [x] 条目列表页 `saved_views` 面板增加稳定锚点，快捷入口只跳转到现有表单和列表区域
- [x] 快捷入口均为导航链接，不直接执行删除、批量删除、合并、清空 activity 或恢复备份等危险操作
- [x] 保持登录保护、POST-only 修改、浏览器确认提示、筛选、排序、分页、saved views 和批量编辑行为不变
- [x] 使用现有 Jinja2 模板和 CSS 增加响应式 quick action grid，移动端自动单列显示
- [x] 新增工作台 / 快捷操作相关中文 / English 文案，并保持 i18n key 覆盖一致
- [x] 补充首页登录保护、快捷入口存在、快捷区不含 POST / confirm、空 saved views / activity 不 500、首页 saved views / 最近活动入口、条目列表页快捷入口、筛选和 saved views 保留、中英文文案测试
- [x] 更新 README / TASKS / REVIEW / CHANGELOG，记录 Phase 2-E3 未发布改动
- [x] 确认本轮未新增数据库表、未修改已有数据库字段、未新增依赖
- [x] 确认本轮未接入 AI 推荐、智能分析、自动分类、外部内容源、URL 导入、爬虫、adapter、云同步、多用户共享、第三方统计或活动趋势图表
- [x] 确认本轮未修改已发布 tag，未创建 GitHub Release
