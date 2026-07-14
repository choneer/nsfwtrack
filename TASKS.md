# 开发任务清单 — MVP

按顺序执行，每完成一项打个 [x]。

## 当前状态（v1.0.6 已发布，Phase 3-C3 已完成于 Unreleased）

当前稳定版与最新 Release：`v1.0.6`。Phase 3-B1 / B2 已正式发布，
Phase 3-B3 / B4 / B5 / B6 / C1 / C2 / C3 已完成并位于 Unreleased，应用 Schema 仍为 `2`。

- Annotated tag object：`d4d5c31cd5b2fed9a90ad69742d54b4c9dbed0b4`
- Peeled commit：`961a3d0cc169e82b261d83207b0ec802007e292b`
- Release：`https://github.com/choneer/nsfwtrack/releases/tag/v1.0.6`

N100 / 目标主机部署尚未开始，**不是当前开发任务**，必须等待用户明确授权。
完整证据见 `COMPLETION_AUDIT.md`。历史任务保留在本文后半部分，
不再作为新增开发路线。

### Phase 3-C3 媒体扫描跳过项定位中心（Unreleased）

- [x] 扫描逐项记录安全相对路径、稳定原因、扩展名及可取得的 lstat 身份信息
- [x] 精确区分 symlink、unsupported extension、special file、directory unreadable 和 entry error
- [x] 结果按路径与原因去重并确定性排序，单项错误不打断其他目录或条目
- [x] 目录使用 fd 与 `O_DIRECTORY|O_NOFOLLOW` 遍历，检查后替换成 symlink 的竞态也不跟随
- [x] 媒体候选保存根、逐级父目录和最终文件的 dev / inode / size / mtime / ctime 身份
- [x] 读取从根 fd 逐段 `O_DIRECTORY|O_NOFOLLOW` 重开父目录，最终文件通过 `dir_fd + O_NOFOLLOW` 打开
- [x] 读取后复核全部已开 fd 和当前名称映射，通过后才解析与哈希，不再使用候选 `Path.stat/read_bytes`
- [x] 子目录 fd 打开后父路径替换为外部 symlink、文件替换或身份漂移均安全生成 `entry_error`
- [x] 被跳过文件内容从不打开、读取、解析、验证或哈希，符号链接目标不读取
- [x] 安全转义控制字符与反斜线，不展示绝对宿主机路径、原始 OSError 或敏感信息
- [x] `skipped_symlinks` 与 symlink 明细数一致，`skipped_unsupported` 与其他四类明细总数一致
- [x] 新增登录保护的只读 `/media-library/skipped` 页面，无 POST 或文件 / 数据库写操作
- [x] 页面支持路径搜索、单类 / 原 unsupported 范围筛选、稳定排序和固定 20 条分页
- [x] 页面展示路径、类型、扩展名、size、device、inode、mtime 与 ctime
- [x] Data Health 的 symlink / unsupported 两个汇总告警链接到各自对应筛选结果
- [x] 普通媒体、cleanup anchor、`recovered-*`、上传残留与 invalid image 行为保持兼容
- [x] 不新增删除、移动、改名、恢复、关联、自动处理、网络或 AI 能力
- [x] 同步中文 / English、模板、CHANGELOG Unreleased、README / PLAN / TASKS / REVIEW / GOAL 和专项测试
- [x] 保持版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、旧 tag / Release 和 N100 状态不变
- [x] C3 专项扩展到 `10 passed`，父目录后置替换与同 inode 身份漂移均验证零外部读取、零哈希
- [x] A3-A6、B1-B6、C1-C2、媒体库、上传、Data Health、备份与导入组合回归 `263 passed`
- [x] 全量 `540 passed`、`pip check`、隔离 Docker build / healthy / `/login` 200 / 未登录跳过项页 303 / down 清理通过
- [x] 功能提交 `c591ca4` 已推送 main，Actions run `29321642902` 的 test / Docker production smoke 均通过
- [x] 父路径竞态修复提交 `c27676f` 已推送 main，Actions run `29332762558` 的 test / Docker production smoke 均通过

### Phase 3-C2 上传残留文件手动清理（Unreleased）

- [x] Data Health 仅为 exact basename `.upload-*.tmp` 普通非符号链接残留提供单项入口
- [x] 登录保护 GET 展示 path、size、device、inode、mtime、ctime、引用与后果并保持零写入
- [x] GET 与 POST 均不读取、解析、恢复或复制临时文件内容
- [x] 已引用目标显示 C1 指引且无删除表单，不自动迁移、清除或修改引用
- [x] POST 复用 standard / strict `CONFIRM`，并逐字段重验完整身份快照
- [x] 结束预览读事务后获取 `BEGIN IMMEDIATE`，锁内复核封面 / 头像引用均为零
- [x] 最终身份重验后按目录 fd unlink 单个目标，并 fsync 所在目录
- [x] 拒绝空中段、近似名称、目录、符号链接、非法 / 越界、缺失、陈旧、伪造和同路径替换
- [x] 引用竞态在写锁内拒绝；目标与数据库引用均保持不变
- [x] 锁、引用查询、身份和 unlink 失败均保留目标；fsync 失败明确报告目标已删除
- [x] 成功后 Data Health 不再报告目标，非目标文件和全部数据库记录保持不变
- [x] 不自动或批量清理，不创建恢复文件，不触碰普通媒体、cleanup anchor 或 `recovered-*`
- [x] 同步中文 / English、模板、CHANGELOG Unreleased、README / PLAN / TASKS / REVIEW / GOAL 和专项测试
- [x] C2 专项 `22 passed`，C1 / B3-B6 / 上传 / Data Health / 备份 / 导入组合回归 `253 passed`
- [x] 全量 `530 passed`、pip check、Docker image build、Compose healthy、`/login` 200 与 down 清理通过
- [x] 功能提交 `ab373b3` 已推送 main，Actions run `29317914417` 的 test / Docker production smoke 均通过
- [x] 保持版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、旧 tag / Release 和 N100 状态不变

### Phase 3-C1 断裂媒体引用手动修复（Unreleased）

- [x] Data Health 仅为缺失、损坏、符号链接、非法 / 越界路径和损坏锚点封面 / 头像引用提供单项入口
- [x] 登录保护 GET 展示对象、原引用、问题类型、对象快照和后果，数据库与媒体文件零写入
- [x] 替代候选仅含完整验证通过的普通本地媒体，支持路径 / SHA 搜索、稳定排序和固定 20 条分页
- [x] `recovered-*` 可作为普通替代媒体，cleanup anchor、损坏文件和符号链接始终排除并由服务端拒绝
- [x] 用户必须逐项选择现有媒体替换或明确清除，不自动推荐、不自动清除、不批量修复
- [x] POST 复用 standard / strict `CONFIRM`，并在 `BEGIN IMMEDIATE` 内重验对象、原引用和问题类型
- [x] 替换前后核对完整 SHA、size、device、inode、mtime、ctime，只执行一个带原值条件的字段更新
- [x] 对象、原引用、问题或替代媒体变化，以及陈旧、伪造和健康对象请求均拒绝
- [x] 数据库 / commit 失败整笔回滚；不删除、修改、移动或重命名任何媒体文件
- [x] 成功后 Data Health 不再报告目标问题，非目标对象、其他字段与全部文件保持不变
- [x] 同步中文 / English、模板、CHANGELOG Unreleased、README / PLAN / TASKS / REVIEW / GOAL 和专项测试
- [x] C1 专项 `7 passed`，B3-B6 / 媒体库 / Data Health / 备份 / 导入组合回归 `232 passed`
- [x] 全量 `508 passed`、pip check 与隔离 Docker 双生命周期、真实替换 / 清除及媒体零变化验收通过
- [x] 功能提交 `05adaf7` 已推送 main，Actions run `29314452641` 的 test / Docker production smoke 均通过
- [x] 保持版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、旧 tag / Release 和 N100 状态不变

### Phase 3-B6 无引用安全锚点手动清理（Unreleased）

- [x] 仅为合法且零引用 cleanup anchor 提供登录保护的单项永久删除预览
- [x] GET 展示完整路径、SHA、MIME、size、device、inode、mtime、ctime 和不可撤销后果并保持零写入
- [x] POST 复用 standard / strict `CONFIRM`，提交时重扫并逐字段验证完整身份
- [x] 结束预检读事务后获取 SQLite `BEGIN IMMEDIATE`，锁内复核封面 / 头像引用均为零
- [x] 最终删除前再次验证完整身份和 SHA，按身份 unlink 并 fsync 所在目录
- [x] 拒绝已引用、损坏、符号链接、错误扩展、普通、`recovered-*`、缺失、陈旧、伪造和变化请求
- [x] 引用竞态在写锁复核时拒绝，目标文件不删除且不迁移 / 清除数据库引用
- [x] 删除和锁失败保留文件并明确报告；unlink 后目录同步失败准确报告已删除警告
- [x] 只删除用户确认的单个目标，不创建恢复文件、不批量或自动清理
- [x] Data Health 与恢复中心在成功后自然移除该锚点状态，不新增自动 fix
- [x] 同步中文 / English、模板、CHANGELOG Unreleased 与当前文档
- [x] B6 专项 `15 passed`、媒体链及 B3-B5 回归 `156 passed`
- [x] 全量 `501 passed`、pip check 与隔离 Docker 双生命周期及真实确认删除验收通过并清理
- [x] 功能提交 `b70e18e` 已推送 main，Actions run `29309167659` 的 test / Docker production smoke 均通过
- [x] 保持版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、旧 tag / Release 和 N100 状态不变

### Phase 3-B5 安全锚点手动恢复（Unreleased）

- [x] 为合法 cleanup anchor 增加登录保护、零写入的单项 GET 恢复预览
- [x] 展示完整路径、SHA-256、MIME、大小、device、inode、mtime、ctime、全部引用和操作后果
- [x] POST 复用 standard / strict `CONFIRM`，并重新扫描逐字段验证完整身份
- [x] 无覆盖创建唯一 `recovered-*`，验证同 inode / SHA 并完成文件与目录 fsync
- [x] 单事务迁移全部条目封面和创作者头像引用，事务内复核原锚点零引用
- [x] 提交后锁定复核引用与文件身份，仅在零引用时身份删除原锚点
- [x] 数据库失败回滚引用并身份清理新恢复文件
- [x] 锚点删除失败时引用保持在合法恢复文件，并报告锚点残留与原因
- [x] 拒绝损坏、符号链接、错误扩展、陈旧、伪造、变化、普通或 `recovered-*` 请求
- [x] 普通交互式条目 / 创作者创建、编辑和媒体设置不能新建内部锚点引用
- [x] 不批量恢复、不直接丢弃内容、不操作 `recovered-*`，保持备份、B3 与 B1/B2/A3/A4 边界
- [x] 同步中文 / English、模板、CHANGELOG Unreleased 与当前文档
- [x] B5 专项 `12 passed`、全量 `486 passed`、pip check 与隔离 Docker 双生命周期验收通过并清理
- [x] 功能提交 `9e19509` 已推送 main，Actions run `29306074275` 的 test / Docker production smoke 均通过
- [x] 保持版本 1.0.6、Schema 2、迁移、依赖、Docker/CI、旧 tag / Release 和 N100 状态不变

### Phase 3-B4 媒体清理恢复中心（Unreleased）

- [x] 新增登录保护、只读的 `/media-library/recovery` 恢复中心
- [x] 仅按大小写敏感 basename 前缀精确识别 `.cleanup-anchor-*` 与 `recovered-*`，不使用 contains
- [x] 普通扫描排除内部锚点，恢复扫描可定位合法、损坏、错误扩展和符号链接锚点
- [x] 锚点不进入普通媒体库、B1/B2、上传去重或 A3/A4；非锚点候选 ID 保持不变
- [x] `recovered-*` 保持正常媒体身份，并增加普通媒体筛选、卡片标识和恢复状态
- [x] 恢复中心展示路径、实际大小、完整 SHA（可校验时）、合法性及封面 / 头像引用
- [x] 区分已引用、未引用、损坏锚点和恢复文件，支持路径 / SHA 搜索、稳定排序和 20 条分页
- [x] data-health 增加已引用、未引用和损坏锚点审计，不提供自动修复
- [x] GET 零写入，页面无删除、移动、改名、引用迁移或自动恢复操作
- [x] 同步中文 / English、模板、CHANGELOG Unreleased 与当前文档
- [x] B4 / i18n 专项 `16 passed`、媒体链 `120 passed`、全量 `474 passed` 且 pip check 无冲突
- [x] 隔离 Docker 双生命周期、登录、恢复中心、普通媒体、data-health 与持久化验收通过并清理
- [x] 功能提交 `4d7a061` 已推送 main，Actions run `29251083388` 的 test / Docker production smoke 均通过
- [x] 确认版本 1.0.6、Schema 2、迁移、依赖、Docker/CI 及旧 tag / Release 不变

### Phase 3-B3 重复媒体手动整理（Unreleased）

- [x] 在重复组页提供无默认值的 keeper 单选与只读 GET 预览入口
- [x] 仅接受共享 B1/B2 服务确认的单个完整合法 SHA-256 重复组
- [x] 预览逐路径列出封面 / 头像引用迁移、待删除文件和预计释放空间，保持零写入
- [x] POST 复用 standard / strict `CONFIRM` 危险确认并重新扫描完整组
- [x] 拒绝成员变化、哈希变化、缺失、损坏、符号链接、越界与伪造路径
- [x] 删除前创建同文件系统已验证安全锚点，并在整个删除窗口让封面 / 头像引用指向该合法同哈希文件
- [x] keeper 在首删前、中途或末次删除期间缺失时无覆盖恢复；路径被占用时保留外部文件并迁移到唯一恢复路径
- [x] 数据库失败不删除文件；删除失败保留安全副本并可重试；成功、异常和重试均清理临时锚点
- [x] 不删除 keeper、不处理其他组、不改变 A3/A4 候选逻辑
- [x] 同步中文 / English、模板、CHANGELOG Unreleased 与发布后文档状态
- [x] B3 / i18n 专项 `18 passed`，keeper 竞态修复覆盖首删前、中途与末次删除三种时序
- [x] 完整 `459 passed`、pip check 与隔离 Docker 双生命周期重新通过并清理
- [x] 修复提交 `bba2aa0` 已推送 main，Actions run `29236104263` 的 test / Docker production smoke 均通过
- [x] 功能提交 `79de4e4` 已推送 main，Actions run `29233302653` 的 test / Docker production smoke 均通过
- [x] 未改版本 1.0.6、Schema 2、迁移、依赖、Docker/CI 或旧 tag / Release，未部署 N100

### v1.0.6 正式发布

- [x] 发布范围仅包含 Phase 3-B1 重复媒体定位与 B2 重复媒体组视图
- [x] 应用版本元数据和发布回归断言从 1.0.5 更新为 1.0.6
- [x] 将 B1 / B2 从 Unreleased 冻结为 `[1.0.6] - 2026-07-13`
- [x] CHANGELOG 顶部保留新的空 Unreleased
- [x] 同步 README / PLAN / TASKS / REVIEW / GOAL 发布候选状态
- [x] 保留 B1 / B2 只读、无媒体操作、无引用迁移及 A3/A4 不变边界
- [x] 未修改 Schema 2、迁移、依赖、Docker/CI 安全配置或旧 tag / Release
- [x] 全量 `441 passed`、pip check 与隔离 Docker 双生命周期通过并清理
- [x] 发布准备提交 `c8200da` 已推送 main，Actions run `29230348185` 的 test / Docker production smoke 均通过
- [x] annotated tag `v1.0.6` 与正式 GitHub Release 已创建并验证，未部署 N100

### Phase 3-B2 重复媒体组视图（已随 v1.0.6 发布）

- [x] 新增登录保护的只读 `/media-library/duplicates`，每个真实 SHA-256 只显示一组
- [x] 提取 B1/B2 共用分组服务，完整合法 SHA、不同路径和稳定成员边界保持一致
- [x] 每组展示完整 SHA-256、成员数、单文件大小、总占用和可节省空间
- [x] 每个成员展示路径、可用状态、条目封面和创作者头像引用
- [x] 支持文件名 / 路径 / SHA 搜索及成员数 / 可节省空间 / SHA 双向稳定排序
- [x] 每页固定 20 组，非法搜索、排序和页码安全回退或夹取
- [x] 提供完整 SHA 与 `media_status=duplicate` 的 B1 精确筛选链接
- [x] GET 前后数据库、引用、媒体字节及 A3/A4 候选不变，业务路径无 POST
- [x] 同步中文 / English、README / PLAN / TASKS / REVIEW / CHANGELOG / GOAL 与专项测试
- [x] 全量 `441 passed`，`pip check` 无依赖冲突
- [x] 隔离 Docker build / healthy / `/login` 连续三次 200 / 登录后重复组页 200 / down 通过并清理
- [x] 功能提交 `b4725a9` 已推送，Actions run `29228843856` 的 test / Docker production smoke 均通过
- [x] 未改 B1 行为、Schema 2、迁移、依赖、版本、Docker、旧 tag / Release，未部署 N100

### Phase 3-B1 重复媒体定位（已随 v1.0.6 发布）

- [x] 仅按可用媒体的完整合法 SHA-256 建立稳定重复组，并要求至少两个不同路径
- [x] 汇总重复组数、涉及文件数和每组保留一份时可节省空间
- [x] 新增 `media_status=duplicate`，只显示真实重复组成员
- [x] `media_q` 同时支持文件名、路径、完整 SHA-256 和大小写无关的 SHA 前缀
- [x] 重复卡片显示组内数量和稳定排序的其他媒体路径
- [x] 损坏文件、空 / 非法 SHA 和单独文件不标记为重复
- [x] 保留四种排序、20 条分页、三套页码、筛选及既有表单返回状态
- [x] GET 前后数据库、引用和媒体字节不变，A3/A4 候选 ID 保持一致
- [x] 同步中文 / English、README / PLAN / TASKS / REVIEW / CHANGELOG / GOAL 与专项测试
- [x] 全量 `435 passed`，`pip check` 无依赖冲突
- [x] 隔离 Docker build / healthy / `/login` 连续三次 200 / down 通过并清理
- [x] 功能提交 `a0bc3a5` 已推送，Actions run `29227243480` 的 test / Docker production smoke 均通过
- [x] 未改 Schema 2、迁移、依赖、版本、Docker、旧 tag / Release，未部署 N100

### v1.0.5 正式发布

- [x] 应用版本元数据和发布回归断言从 1.0.4 更新为 1.0.5
- [x] 将 A1 至 A6、来源同名歧义修复和媒体原子上传修复冻结为 `[1.0.5] - 2026-07-13`
- [x] CHANGELOG 顶部保留新的空 Unreleased 段
- [x] README / PLAN / TASKS / REVIEW / GOAL 发布准备状态同步
- [x] 保持功能代码、Schema 2、真实 1 → 2 迁移、依赖和 Docker 配置不变
- [x] 全量 `433 passed`、pip check 与隔离 Docker 双生命周期验收通过并清理
- [x] 发布准备提交推送到 main，Actions test / Docker production smoke 通过
- [x] 创建并推送 annotated `v1.0.5` tag，tag object 与 peeled commit 验证通过
- [x] 创建正式 GitHub Release，标题为 `NSFWTrack v1.0.5`，非 Draft / Pre-release
- [x] README / PLAN / TASKS / REVIEW / GOAL 发布后状态提交 `cce9bcd`，Actions test / Docker smoke 通过

### Phase 3-A6 本地媒体完整性审计（已随 v1.0.5 发布）

- [x] `/data-health` 增加只读 media 分类、完整汇总和统一问题明细
- [x] 条目封面与创作者头像引用覆盖非法值、路径越界、符号链接、缺失和损坏
- [x] 媒体根缺失、符号链接、非目录、不可读或扫描失败均安全报告且页面不 500
- [x] 无引用且尚未初始化的缺失根目录保持健康；正常未使用媒体不算问题
- [x] `.upload-*.tmp` 残留与不同路径 SHA-256 重复内容作为 warning 报告
- [x] 汇总安全扫描跳过的符号链接和不支持文件
- [x] 沿用全局 200 条明细上限，同时保留完整分类与问题计数
- [x] GET 前后数据库引用与媒体文件不变，不请求外部 URL
- [x] media 问题不进入修复白名单，伪造 POST 被拒绝且不清除引用或修改文件
- [x] A3 / A4 / A5 服务保持不变；不改 Schema 2、迁移、依赖、版本或 Release
- [x] 同步中文 / English、README / PLAN / TASKS / REVIEW / CHANGELOG / GOAL 与专项测试
- [x] 全量 `433 passed`、pip check 与隔离 Docker 双生命周期通过，临时资源已清理
- [x] Actions test / Docker production smoke 通过并完成临时资源清理

### Phase 3-A5 媒体库检索与分页（已随 v1.0.5 发布）

- [x] 文件名和相对 `/media/...` 路径支持 NFKC 大小写无关本地搜索，输入限制 200 字符
- [x] 支持全部、可用、损坏 / 不可用、已使用和未使用筛选，使用状态来自现有封面 / 头像引用
- [x] 支持文件名升 / 降序和文件大小升 / 降序，并稳定处理并列项
- [x] 媒体卡片固定每页 20 条，非法、负数、非数字和越界页码安全回退或夹取
- [x] 媒体分页保留筛选、`match_page` 和 `create_page`；A3/A4 分页保留媒体状态和彼此页码
- [x] 上传、手动关联、A3 配对和 A4 建档返回时保留规范化媒体查询状态
- [x] 空扫描与筛选空结果分别显示，中英文筛选、排序、统计和空状态文案对称
- [x] GET 前后数据库与媒体字节不变；非法搜索、状态和排序参数不 500 且回退默认
- [x] A3/A4 继续使用完整原始扫描，专项测试比较候选 ID 前后不变
- [x] 不修改媒体、关联、表、Schema 2、迁移、依赖、版本、旧 tag / Release 或 Docker 配置
- [x] 同步 README / PLAN / TASKS / REVIEW / CHANGELOG / GOAL 与专项测试
- [x] 全量 `424 passed`、pip check 与隔离 Docker 双生命周期通过并清理；Actions 结果随最终提交汇报

### Phase 3-A4 未匹配媒体快速建档（已随 v1.0.5 发布）

- [x] 仅从有效、未使用且没有 A3 配对的本地图片生成只读新条目候选，不自动建档
- [x] 文件名移除扩展名和封面约定后缀生成默认标题，头像约定文件排除
- [x] 标题确认前可编辑，默认无效 / 已有精确同名 / 规范化同名 / 候选间冲突均明确显示
- [x] 提交时以最终标题重新拒绝已有精确同名、已有规范化同名和所选批次规范化同名
- [x] 支持单项与当前 20 行候选页批量确认，不跨页全选
- [x] 所有写操作登录保护、仅 POST、浏览器与服务端确认；strict 模式精确要求 `CONFIRM`
- [x] 提交时重新扫描、复核当前页与每个媒体文件，陈旧、伪造、占用或无效输入均拒绝
- [x] 成功时创建条目并设置既有媒体路径为 `cover_path`；任一失败整批 rollback
- [x] 不创建、下载、识别、移动、重命名、覆盖或删除媒体文件
- [x] 不新增表，不改 Schema 2、迁移、依赖、版本、旧 tag / Release 或 Docker 安全配置
- [x] 中英文、README / PLAN / TASKS / REVIEW / CHANGELOG / GOAL 与专项测试同步
- [x] 全量 `416 passed`、pip check 与隔离 Docker 双生命周期通过并清理；Actions 结果随最终提交汇报

### Phase 3-A3 本地媒体候选配对（已随 v1.0.5 发布）

- [x] 仅对有效未使用媒体、无封面条目和无头像创作者生成只读候选，不自动写入
- [x] 支持 NFKC / casefold 精确名称、仅保留字母数字的规范化名称及 `cover` / `avatar` 约定后缀
- [x] 展示目标类型、匹配依据和高 / 中置信等级，并保持稳定候选 ID 与排序
- [x] 同一媒体命中多个目标或同一目标命中多个媒体时标记冲突，UI 与服务端均禁止应用
- [x] 支持单项和当前 20 行候选页批量确认，不跨页全选
- [x] 写入时重新扫描并拒绝陈旧、跨页、不可用或已有关系目标，批量使用单事务
- [x] 所有写操作登录保护、仅 POST、浏览器和服务端确认；strict 模式精确要求 `CONFIRM`
- [x] 不覆盖已有封面 / 头像，不下载、识别、移动、重命名、覆盖或删除媒体文件
- [x] 不新增表，不改 Schema 2、迁移、依赖、版本、旧 tag / Release 或 Docker 安全配置
- [x] 中英文、README / PLAN / TASKS / REVIEW / CHANGELOG / GOAL 与专项测试同步
- [x] 全量 `407 passed`、pip check 与隔离 Docker 双生命周期通过并清理；Actions 结果随最终提交汇报

### Phase 3-A2 本地媒体库（已随 v1.0.5 发布）

- [x] 扫描 `data/media` 并展示条目封面 / 创作者头像引用状态，不跟随符号链接或越出目录
- [x] 支持单图和多图上传；每批 20 张、每张 10 MB，并校验扩展名、MIME 与文件结构
- [x] 仅接受 AVIF / GIF / JPEG / PNG / WebP，拒绝 SVG、HTML、伪装、损坏和不支持文件
- [x] 使用 SHA-256 内容寻址去重，相同图片不重复保存
- [x] 同目录随机临时文件写完后 flush / fsync 并原子发布；写入、关闭或批次中途失败均回滚且无残留
- [x] 支持设置、替换和确认清除封面 / 头像；清除关联不物理删除文件，strict 模式仍需 `CONFIRM`
- [x] 缺失或损坏媒体安全显示为空状态，文件端点返回 404 而非 500
- [x] 所有写操作登录保护并使用 POST；不请求外部 URL，不做识别、推荐或 AI
- [x] 不新增表，不改 Schema 2、依赖、版本、旧 Release 或 Docker 安全配置
- [x] 中英文、README / PLAN / TASKS / REVIEW / CHANGELOG / GOAL 与测试同步
- [x] 全量 `397 passed`、`pip check` 与隔离 Docker 双生命周期通过并清理；Actions 结果随最终提交汇报

### Phase 3-A1 来源链接与批量书签导入（已随 v1.0.5 发布）

- [x] 修改 RULE，允许保存用户提供 URL、解析本地书签 HTML 与纯文本 URL 清单
- [x] 新增 `item_sources`，支持一个条目多个来源、可选标题、创建时间和全局规范化 URL 唯一约束
- [x] 详情页查看 / 添加来源，删除必须浏览器与服务端确认且不删除条目
- [x] 支持一行一个 URL、`标题<TAB>URL` 与本地浏览器书签 HTML
- [x] 批量导入先只读预览新增 / 重复 / 无效 / 冲突，再确认事务写入；异常整批回滚
- [x] 多个已有同名或仅大小写不同条目明确报告歧义并跳过；正常混合记录仍按事务规则写入
- [x] 无标题生成本地可读 URL 占位标题，不请求远程网页、元数据或图片
- [x] 新增真实显式 Schema 1 → 2 `create_item_sources` 迁移，dry-run 不写库，apply 保留旧数据
- [x] JSON 备份 / 恢复与 CSV/JSON 条目导入导出同步来源，旧文件缺少来源仍兼容
- [x] 中英文 key 对称，来源与迁移专项保持通过，全量 377 passed
- [x] 保持应用版本 1.0.4，不修改旧 tag / Release，不部署 N100
- [x] 同步 README / PLAN / TASKS / REVIEW / CHANGELOG / GOAL

### Phase 2-L8 固定非 root 容器用户

- [x] 镜像创建固定 UID/GID `10001:10001` 的 `nsfwtrack` 用户，并以 Dockerfile `USER` 运行应用和健康检查
- [x] CI 隔离数据目录归 `10001:10001` 所有，验证 `Config.User`、`id -u` 与 `id -g`
- [x] 保持只读根、`cap_drop: ALL`、`CapEff=0`、`NoNewPrivs=1` 与 `/tmp` tmpfs
- [x] 验证 `/app/data`、`/tmp` 可写，`/app`、`/etc`、`/usr/local` 不可写
- [x] 验证 healthy、`/login`、安全头、SQLite 创建、容器重建持久化与 Schema 1
- [x] README 记录首次安装和 v1.0.3 存量数据的停机、可验证备份及 `10001:10001`/`0700` 迁移
- [x] 未使用 `chmod 777`、root 启动脚本、sudo/gosu 容器入口或自动 `chown`
- [x] 全量测试、`pip check`、隔离 Docker 与 Actions 验收通过并清理
- [x] 同步 PLAN / TASKS / CHANGELOG / REVIEW / GOAL，不改版本或创建 Release

### Phase 2-L7 Docker 运行时安全基线

- [x] 生产与 CI Compose 使用只读根文件系统并移除全部 Linux capabilities
- [x] 启用 `no-new-privileges`，为 `/tmp` 提供 64 MiB tmpfs
- [x] 保持 `/app/data` 持久化、镜像健康检查及现有 HTTP / 安全头行为
- [x] CI 验证 `/app/data` 与 `/tmp` 可写，`/app`、`/etc`、`/usr/local` 不可写
- [x] 全量测试、`pip check`、隔离 Docker 与 Actions 验收通过
- [x] 更新 README / PLAN / TASKS / CHANGELOG / GOAL

### Phase 2-L6 Docker 健康状态与就绪验收

- [x] 为生产镜像增加仅使用 Python 标准库访问现有 `/login` 的 `HEALTHCHECK`
- [x] CI 启动容器后等待 `healthy`，再执行原有 `/login` 与安全响应头检查
- [x] 保持失败日志、`always()` 清理、pytest 与 `pip check` 流程
- [x] 全量测试、`pip check` 与隔离 Docker healthy 验收通过
- [x] 更新 README / PLAN / TASKS / CHANGELOG / GOAL

### Phase 2-L5 CI 最小权限与重复运行控制

- [x] 将 workflow 权限明确限制为 `contents: read`
- [x] 按 workflow 与 ref 设置 concurrency，并启用 `cancel-in-progress`
- [x] 保持 test、`pip check`、Docker smoke、失败日志与清理步骤不变
- [x] 精简同步 PLAN / TASKS / CHANGELOG，不改业务代码、依赖、数据库、Schema 或版本

### Phase 2-L4 CI Docker 冒烟验收

- [x] 在 GitHub Actions 增加独立 `docker-smoke` 任务，保留现有 pytest / pip check
- [x] 使用临时随机凭据和隔离数据目录启动生产镜像，不使用示例占位值
- [x] 等待 `/login` 200 并检查基础安全响应头与 `X-Request-ID`
- [x] 失败时输出容器日志；`always` 清理 compose 资源与临时目录
- [x] 本地全量测试与按 CI 设计的隔离 Docker 冒烟通过
- [x] 更新 README / TASKS / REVIEW / CHANGELOG / GOAL / PLAN

### Phase 2-L3 浏览器安全响应头基线

- [x] 增加统一 `SecurityHeadersMiddleware`，覆盖成功 / 重定向 / 错误 / JSON / 媒体响应
- [x] 设置 `X-Content-Type-Options`、`Referrer-Policy`、`X-Frame-Options` 和受限 `Permissions-Policy`
- [x] 不启用 HSTS，不加入会破坏现有表单或内联脚本的激进 CSP
- [x] 保持 `X-Request-ID`、405 `Allow` 与现有登录 / 确认 / 媒体行为
- [x] 专项测试 11 passed；全量 `358 passed`；`pip check` 通过
- [x] 隔离 Docker build / up / `/login` 200 含安全头 / down 清理通过
- [x] 更新 README / TASKS / REVIEW / CHANGELOG / GOAL / PLAN

### Phase 2-L2 直接依赖版本基线

- [x] 在全新 Python 3.12 环境确认当前已验证兼容版本
- [x] 固定 `requirements.txt` 直接运行时依赖版本（不生成完整传递锁）
- [x] 固定 `requirements-dev.txt` 直接测试依赖版本（`httpx2` / `pytest`）
- [x] CI 在安装后增加 `pip check`
- [x] 全新 venv 安装、`pip check`、全量 `347 passed` 无弃用警告
- [x] 隔离 Docker build / up / `/login` 200 / version 1.0.1 / down 清理通过
- [x] 更新 README / TASKS / REVIEW / CHANGELOG / GOAL / PLAN

### Phase 2-L1 测试依赖兼容性收口

- [x] 复现并确认 TestClient / HTTPX 弃用警告来自 Starlette `testclient` 在仅安装 `httpx` 时的兼容分支
- [x] 以最小依赖调整安装 `httpx2==2.5.0`，不使用 warning filter 掩盖
- [x] 仅更新 `requirements-dev.txt`；运行时 `requirements.txt`、业务代码、数据库与 Schema 不变
- [x] 全量测试 `347 passed` 且该弃用警告消失
- [x] 隔离 Docker build / up / `/login` 200 / down 通过并清理
- [x] 更新 README / TASKS / REVIEW / CHANGELOG / GOAL

### Phase 2-K1 开发完成度审计

- [x] 搜索 TODO / FIXME / 占位实现 / 501 / 未完成分支
- [x] 枚举 95 个路由并核对模板入口和页面锚点，无失效入口
- [x] 对照 README / PLAN / TASKS / REVIEW 检查已承诺能力
- [x] 盘点 31 个测试文件、275 个测试函数和 309 个收集测试
- [x] 复核 F4：提示行为已实现，44 项 health / fix / danger 测试通过
- [x] 全量测试 309 passed，隔离 Docker build / up / `/login` 200 / down 通过并已清理
- [x] 确认本轮只输出审计和文档，不修改业务代码、依赖、Schema 或迁移
- [x] 将剩余工作收敛为 K2 和 K3，不新增产品阶段

### Phase 2-K2 投入使用前边界收口

- [x] 定义唯一的本地素材路径契约；禁止 `cover_path` / `avatar_path` 外部 URL、协议相对路径、data URL、路径穿越和歧义分隔符
- [x] 让合法本地封面在 Docker 挂载下真实可读，或在本地素材契约完成前停止暴露 / 渲染该字段
- [x] 在 API、页面表单、备份恢复和模板渲染边界补齐本地素材路径测试
- [x] 为 status / rating / tag / collection 的全部批量写入增加浏览器和服务端确认
- [x] 为状态清除及关系解除建立一致的低风险 / 危险确认规则并补齐 strict 测试
- [x] 拒绝 `.env.example` 的已知 APP_PASSWORD / SECRET_KEY 占位值，错误不得回显凭据
- [x] 补齐 F4 中英文完整提示、备份链接、dangerous_only / always 和无问题空状态测试
- [x] 增加首次安装、v0.9/v1.0 升级、备份和回滚的单一操作清单
- [x] 运行完整 pytest 与隔离 Docker 验收，确认无剩余 P0 / P1 项

### Phase 2-K3 目标部署验收（未开始 / 非当前开发任务）

状态：N100 部署尚未开始；等待用户明确授权后才可执行。
以下仅作授权后的操作参考清单，不计入当前开发任务。

- [ ] （授权后）在仓库外配置唯一强密码和随机 Secret，不使用示例占位值
- [ ] （授权后）在目标 N100 / LAN 主机验证 Docker build、启动、持久化、重启、登录和停止
- [ ] （授权后）使用真实桌面 / 移动端浏览器验证布局、JavaScript confirm 和详情访问记录 POST
- [ ] （授权后）导出当前 JSON 备份并通过校验
- [ ] （授权后）将备份恢复到全新隔离实例，核对核心实体、关系、设置和活动数量
- [ ] （授权后）确认服务仅在受控局域网访问，不直接暴露公网
- [ ] （授权后）记录最终无使用前阻断结论后再导入不可替代的真实数据

### 可延后优化

- [x] 直接运行时 / 测试依赖版本基线已在 Phase 2-L2 固定；完整传递依赖锁文件仍未实施
- [x] TestClient / `httpx` 弃用警告已在 Phase 2-L1 通过 `httpx2` 解决
- [ ] 仅在新性能数据证明必要时审批索引和真实迁移

### 明确不做

- [x] 不实现外部封面查询、远程图片代理、URL 导入、爬虫或 adapter
- [x] 不实现推荐、AI、自动合并、云同步、多用户或复杂权限
- [x] 不为匹配旧文档措辞而引入 HTMX 或前端框架重写
- [x] 不虚构 Schema 版本、生产迁移、索引或新表

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

## v0.6.0 发布准备

- [x] 确认 `main` 已包含 Phase 2-E1 保存筛选视图 / 常用视图
- [x] 确认 `main` 已包含 Phase 2-E2 最近访问 / 最近编辑
- [x] 确认 `main` 已包含 Phase 2-E3 快捷操作入口 / 工作台增强
- [x] 将 CHANGELOG 的 `Unreleased` 中 Phase 2-E1 / E2 / E3 内容整理为 `v0.6.0` 发布段
- [x] 更新 README 当前版本状态与 Phase 2-E 使用效率增强发布说明
- [x] 保持 `v0.1.0`、`v0.2.0`、`v0.3.0`、`v0.4.0` 和 `v0.5.0` tag 不变
- [x] 本轮仅做 release 文档准备，不新增业务功能、不改数据库结构、不新增依赖、不进入 Phase 3

## Phase 2-F1 数据健康检查 / 本地数据自检

- [x] 新增只读数据健康检查 service，集中生成健康报告摘要和问题明细
- [x] 新增 `/data-health` 页面，要求登录并只读展示报告
- [x] 页面展示总体状态、问题总数、警告 / 问题数量、按类型分组数量和问题明细
- [x] 条目基础检查覆盖空标题、无效评分、无效状态、缺失 / 异常时间、更新时间早于创建时间和异常 `extra` JSON
- [x] 关系完整性检查覆盖 `item_tags`、`item_creators`、`item_collections` 指向缺失条目或缺失标签 / 创作者 / 合集
- [x] 重复关系检查覆盖同一条目重复关联同一标签、创作者或合集
- [x] saved views 检查覆盖空名称、空 / 异常 `query_string`、未知参数、`page` / `next` / `redirect` 和外部 URL
- [x] item activity 检查覆盖缺失条目引用、负数 `view_count` / `edit_count` 和异常活动时间
- [x] 登录后顶部导航加入数据健康入口，首页工作台加入数据健康检查入口
- [x] 页面明确建议发现问题后先导出 JSON 备份
- [x] 页面不提供自动修复、一键修复、自动删除、自动合并或 AI 判断入口
- [x] 新增数据健康中文 / English 文案，并保持 i18n key 覆盖一致
- [x] 补充 `/data-health` 登录保护、健康状态、条目问题、孤立关系、重复关系、saved views 问题、activity 问题、只读不修改数据库、不删除业务数据和中英文页面测试
- [x] 更新 README / TASKS / REVIEW / CHANGELOG / PLAN，记录 Phase 2-F1 未发布改动
- [x] 确认本轮未新增数据库表、未修改已有数据库字段、未新增依赖
- [x] 确认本轮未接入外部内容源、URL 导入、爬虫、adapter、AI 判断、自动修复、自动删除、自动合并、云同步或多用户系统
- [x] 确认本轮未修改已发布 tag，未创建 GitHub Release

## Phase 2-F2 备份文件校验 / 导入 dry-run 增强

- [x] 新增 `app/services/backup_validator.py`，生成备份校验和恢复 dry-run 结构化报告
- [x] 备份校验报告区分 `error` / `warning` / `info`，展示总体状态、数量、影响数据类型、行号 / 对象 id、说明和细节
- [x] JSON 备份校验覆盖 schema、tables、未知顶层字段、未知表、必填字段、未知行字段、重复 id、空标题、空名称、无效 `extra` JSON、无效 `status` 和无效 `rating`
- [x] 关系校验覆盖 `item_tags`、`item_creators`、`item_collections` 的缺失条目 / 缺失目标和重复关系
- [x] saved views 校验覆盖空 `query_string`、异常 percent 编码、外部 URL、`page` / `next` / `redirect` 和未知参数
- [x] item activity 校验覆盖缺失条目、重复 activity、负数或无效 `view_count` / `edit_count`
- [x] 旧 JSON 备份缺少 `collections`、`item_collections`、`saved_views` 或 `item_activity` 等可选表时兼容为 info，不作为致命错误
- [x] `/backup` 页面复用本地 JSON 上传入口，显示备份校验 / 恢复 dry-run 报告，不执行恢复
- [x] `/api/backup/preview/json` 成功响应增加 `report` 字段，同时保留非法文件的 400 行为
- [x] 导入预览页面增加 CSV / JSON dry-run 报告，展示可导入行、跳过行、错误、警告、信息和写入前备份提示
- [x] 导入 dry-run 覆盖未知字段、缺失标题、无效 `rating` / `status`、异常 `tags` / `creators`、重复标题候选和当前数据库已有标题
- [x] JSON `tags` / `creators` 字段异常会进入错误行；字符串形式保持兼容解析并给出 warning
- [x] dry-run 和校验均只读，不写 SQLite、不删除业务数据、不自动修复、不自动导入、不自动恢复、不自动合并
- [x] 新增备份校验 / 导入 dry-run 中文 / English 文案，并保持 i18n key 覆盖一致
- [x] 补充备份校验登录保护、异常文件、旧备份兼容、未知字段、缺失字段、非法值、孤立关系、重复关系、saved views、item activity、只读不写库、不删除数据、导入 dry-run 和中英文页面测试
- [x] 更新 README / TASKS / REVIEW / CHANGELOG / PLAN，记录 Phase 2-F2 未发布改动
- [x] 确认本轮未新增数据库表、未修改已有数据库字段、未新增依赖
- [x] 确认本轮未接入外部内容源、URL 导入、爬虫、adapter、AI 判断、自动修复、一键修复、自动删除、自动导入、自动恢复、自动合并、云同步或多用户系统
- [x] 确认本轮未修改已发布 tag，未创建 GitHub Release

## Phase 2-F3 数据健康手动修复 / 低风险维护操作

- [x] 新增 `app/services/data_health_fixes.py`，使用服务端白名单分派低风险修复逻辑
- [x] 新增 `POST /data-health/fix`，要求登录、POST、`confirm=1` 和单一 `fix_type`
- [x] `/data-health` 继续通过 GET 只读生成健康报告，不写数据库、不执行修复
- [x] 页面只在对应问题存在时显示修复按钮，并提供浏览器确认、备份提示和核心实体不删除说明
- [x] 支持清理孤立 `item_tags`、`item_creators`、`item_collections`
- [x] 支持清理重复 `item_tags`、`item_creators`、`item_collections`，兼容旧 schema 中缺少唯一约束的重复关系
- [x] 支持清理孤立 `item_activity`
- [x] 支持将负数 `view_count` / `edit_count` 修正为 `0`
- [x] 支持清理 `saved_views.query_string` 中的 `page` / `next` / `redirect`、未知参数和外部 URL 值
- [x] 修复结果显示删除 / 修正 / 跳过数量摘要
- [x] 修复失败时 rollback，并展示友好错误，不展示完整异常堆栈
- [x] 非法 `fix_type` 和 `fix_all` 会被拒绝且不 500
- [x] 确认不会删除 `items`、`tags`、`creators`、`collections`
- [x] 新增低风险修复中文 / English 文案，并保持 i18n key 覆盖一致
- [x] 补充未登录、GET、非法 `fix_type`、`fix_all`、缺少 confirm、孤立关系、重复关系、孤立 activity、负数计数、saved views 参数、核心实体保留和 rollback 测试
- [x] 更新 README / TASKS / REVIEW / CHANGELOG / PLAN，记录 Phase 2-F3 未发布改动
- [x] 确认本轮未新增数据库表、未修改已有数据库字段、未新增依赖
- [x] 确认本轮未接入外部内容源、URL 导入、爬虫、adapter、AI 判断、自动修复、一键修复全部、自动合并、云同步或多用户系统
- [x] 确认本轮未修改已发布 tag，未创建 GitHub Release

## v0.7.0 发布准备

- [x] 确认 `main` 已包含 Phase 2-F1 数据健康检查 / 本地数据自检
- [x] 确认 `main` 已包含 Phase 2-F2 备份文件校验 / 导入 dry-run 增强
- [x] 确认 `main` 已包含 Phase 2-F3 数据健康手动修复 / 低风险维护操作
- [x] 将 CHANGELOG 的 `Unreleased` 中 Phase 2-F1 / F2 / F3 内容整理为 `v0.7.0` 发布段
- [x] 更新 README 当前版本状态与 Phase 2-F 数据健康维护发布说明
- [x] 保持 `v0.1.0`、`v0.2.0`、`v0.3.0`、`v0.4.0`、`v0.5.0` 和 `v0.6.0` tag 不变
- [x] 本轮仅做 release 文档准备，不新增业务功能、不改数据库结构、不新增依赖、不进入 Phase 3

## Phase 2-G1 基础设置中心

- [x] 新增本地 `app_settings` 表，保存 `key` / `value` / 时间戳，不修改已有表字段
- [x] 支持 `default_language`、`default_page_size`、`default_sort`、`default_sort_dir` 和 `default_home`
- [x] 使用服务端白名单校验 setting key / value，拒绝未知 key、外部 URL、脚本内容和非法值
- [x] 新增 `/settings` 页面，要求登录并只读展示当前设置
- [x] 新增 `POST /settings` 保存设置，保存失败时 rollback 并显示友好 flash
- [x] 新增 `POST /settings/reset` 恢复默认设置，要求 `confirm=1`
- [x] 默认每页数量在 `/items` 没有 `page_size` 参数时生效
- [x] 默认排序字段 / 方向在 `/items` 没有 `sort` 参数时生效
- [x] 显式 URL 参数优先于本地默认设置，saved views 已保存 query string 不受影响
- [x] 默认语言只在 session 没有显式语言选择时生效，不破坏 `/set-language`
- [x] 首页工作台展示当前默认入口并高亮条目列表、统计或最近活动入口
- [x] JSON 备份导出 / 预览 / 校验 / 恢复支持 `app_settings`
- [x] 旧 JSON 备份缺少 `app_settings` 时按空可选表兼容，不失败
- [x] 新增设置中心中文 / English 文案，并保持 i18n key 覆盖一致
- [x] 补充设置页登录保护、合法保存、非法 key/value、默认分页、默认排序、显式 URL 覆盖、语言切换优先级、reset、默认首页高亮和备份兼容测试
- [x] 更新 README / TASKS / REVIEW / CHANGELOG / PLAN，记录 Phase 2-G1 未发布改动
- [x] 确认本轮未新增依赖，未接入外部内容源、URL 导入、爬虫、adapter、AI 推荐、云同步、多用户设置、外部账号或插件系统
- [x] 确认本轮未修改已发布 tag，未创建 GitHub Release

## Phase 2-G6 危险操作偏好与确认流程统一

- [x] 复用现有 `app_settings`，不新增表、不修改已有字段、不新增依赖
- [x] 新增 `danger_confirmation_mode` 白名单：`standard` / `strict`
- [x] 新增 `backup_reminder_mode` 白名单：`always` / `dangerous_only`
- [x] 新增 `danger_result_detail` 白名单：`summary` / `detailed`
- [x] 拒绝 `off` / `disabled` / `never`、未知 key、外部 URL、脚本和任意值
- [x] standard 保留登录、写方法、浏览器 confirm、现有服务端确认和 rollback
- [x] strict 在 standard 基础上由服务端精确验证固定文本 `CONFIRM`
- [x] 非法或不可读确认设置安全回退到 `standard`，不会回退为无确认
- [x] 统一条目 / 当前页批量删除、标签 / 创作者 / 合集删除的确认策略
- [x] 统一条目合并、元数据合并、活动清空和备份恢复的确认策略
- [x] 统一数据健康手动修复和设置恢复默认值的确认策略
- [x] 危险页面显示对象、后果、删除范围、可恢复性、备份建议和当前模式
- [x] 备份提醒只能在 `always` 和 `dangerous_only` 间切换，不能关闭安全提示
- [x] 结果详情只改变摘要 / 详细展示，不改变业务数据、范围或事务
- [x] JSON 备份导出 / 预览 / 校验 / 恢复支持三个 G6 设置
- [x] 旧备份缺少 G6 设置时兼容并使用安全默认值
- [x] 补充 strict 缺失 / 错误 / 正确文本、GET 安全、异常回退和全入口测试
- [x] 保持无一键全部删除 / 合并 / 修复，无自动执行或安全绕过
- [x] 更新 README / TASKS / REVIEW / CHANGELOG / PLAN，仅记录 Unreleased
- [x] 确认未修改已发布 tag，未创建 GitHub Release

## v0.8.0 发布准备

- [x] 确认 `main` 已包含 Phase 2-G1 基础设置中心
- [x] 确认 `main` 已包含 Phase 2-G6 危险操作偏好与确认流程统一
- [x] 再次运行全量测试与 Docker build / compose / `/login` 验收
- [x] 将 CHANGELOG 的 `Unreleased` 中 Phase 2-G1 / G6 内容整理为 `v0.8.0 - 2026-07-10` 发布段
- [x] 将 CHANGELOG 的 `Unreleased` 重置为无未发布变更
- [x] 更新 README / TASKS / REVIEW / PLAN 当前版本与发布状态
- [x] 保持 `v0.1.0` 到 `v0.7.0` 的发布内容与 tag 不变
- [x] 本轮仅做 release 文档准备，不新增业务功能、不改数据库结构、不新增依赖

## Phase 2-H1 数据库版本记录与升级预检

- [x] 新增内部 `schema_migrations` 表，`version` 为唯一主键，并记录 `name` / `applied_at`
- [x] 定义 `CURRENT_SCHEMA_VERSION = 1` 和基线名称，不引入 Alembic 或新依赖
- [x] 新空数据库在同一初始化事务中创建当前结构并登记基线版本
- [x] 旧数据库无版本表时先检查全部必要业务表和列，再登记基线
- [x] 必要表或列缺失时拒绝登记，不用 `create_all` 掩盖异常结构
- [x] 当前数据库版本等于应用版本时正常启动且不重复登记
- [x] 数据库版本低于应用时只报告需要升级，不自动迁移、不改版本号
- [x] 数据库版本高于应用时拒绝启动，并提供兼容性与备份提示
- [x] 空版本表、异常版本结构或不可读状态按无法确认处理
- [x] 初始化失败不留下错误版本记录，不修改业务数据
- [x] 设置页新增登录保护的只读数据库版本状态区域
- [x] 展示应用版本、数据库版本、状态、最近登记时间和升级前备份提示
- [x] 不提供版本编辑、降级、跳过检查或任意版本提交入口
- [x] JSON 备份不导出 `schema_migrations`
- [x] 恢复时忽略伪造的 `schema_migrations` 数据，不覆盖本地版本
- [x] 补充新旧库、高低版本、结构异常、失败回滚、只读页面、备份隔离和 i18n 测试
- [x] 更新 README / TASKS / REVIEW / CHANGELOG / PLAN，仅记录 Unreleased
- [x] 确认未修改现有业务表字段、未新增依赖、未修改已发布 tag、未创建 GitHub Release

## Phase 2-H2 显式迁移框架与升级 dry-run

- [x] 新增代码内 `MigrationStep` 和 `MigrationRegistry`，生产注册表保持为空
- [x] 每步包含源 / 目标版本、名称、preview、apply、pre-check 和 post-check
- [x] 注册表拒绝重复、断层、跳级、倒序、循环、非法版本和无效 callback
- [x] 先读取数据库版本，再从代码注册表解析连续升级路径
- [x] 低版本启动不再提前要求数据库符合最新模型结构
- [x] 当前版本显示无需升级，缺少路径 / 高版本 / 无法确认时拒绝升级
- [x] 新增登录保护的 `GET /schema-upgrade` 只读状态页
- [x] 新增 `POST /schema-upgrade/preview`，不接受 SQL、表名或目标版本
- [x] dry-run 展示版本、步骤顺序、预计变化、warning / error 和 pre-check 状态
- [x] 使用 SQLite `query_only`、只读 authorizer 和 rollback 阻止 preview 数据 / DDL / 版本写入
- [x] 后续步骤 pre-check 在 dry-run 标记 deferred，apply 时按链顺序重新执行
- [x] 新增 `POST /schema-upgrade/apply`，要求登录、POST、浏览器和服务端危险确认
- [x] apply 要求明确确认升级前 JSON 备份，strict 模式精确验证 `CONFIRM`
- [x] apply 在同一事务内重读版本、解析路径、执行步骤、post-check 和写版本记录
- [x] 任一步失败、post-check 失败或版本记录异常时回滚整条迁移链
- [x] 不支持降级、跳过检查、手动版本修改或用户自定义迁移参数
- [x] `schema_migrations` 继续与 JSON 备份导出 / 恢复隔离
- [x] 当前 `CURRENT_SCHEMA_VERSION` 保持 `1`，不添加测试用生产迁移
- [x] 未修改任何现有业务表或字段，未新增依赖、Alembic、tag 或 GitHub Release
- [x] 补充框架、只读、确认、两步回滚、post-check、路由安全和 i18n 测试
- [x] 更新 README / TASKS / REVIEW / CHANGELOG / PLAN，仅记录 Unreleased

## v0.9.0 发布准备

- [x] 确认 `main` 已包含 Phase 2-H1 数据库版本记录与升级预检
- [x] 确认 `main` 已包含 Phase 2-H2 显式迁移框架与升级 dry-run
- [x] 再次运行全量测试与 Docker build / compose / `/login` 验收
- [x] 将 CHANGELOG 的 `Unreleased` 中 Phase 2-H1 / H2 内容整理为 `v0.9.0 - 2026-07-10` 发布段
- [x] 将 CHANGELOG 的 `Unreleased` 重置为无未发布变更
- [x] 更新 README / TASKS / REVIEW / PLAN 当前版本与发布状态
- [x] 明确启动时只做预检、不自动迁移，升级必须显式触发并建议先做 JSON 备份
- [x] 保持 `CURRENT_SCHEMA_VERSION = 1` 和空生产迁移注册表，不虚构 `1 -> 2` 生产迁移
- [x] 保持 `v0.1.0` 到 `v0.8.0` 的发布内容与 tag 不变
- [x] 本轮仅做 release 文档准备，不新增业务功能、不改数据库结构、不新增依赖

## Phase 2-I1 性能基线与数据库查询审查

- [x] 新增可重复执行的 SQLite 性能审查服务和命令行工具
- [x] 审查连接启用 `PRAGMA query_only`，并在成功 / 失败后恢复连接状态
- [x] 拦截写语句，不接受用户 SQL、表名或目标数据库路径
- [x] 使用临时数据库生成 100 / 1,000 / 10,000 条条目和配套关系数据
- [x] 审查列表分页 / 筛选 / 排序、工作台、统计、标签、创作者和合集
- [x] 审查 saved views、activity、duplicates、cleanup 和 data-health
- [x] 审查备份 preview / validation 和 JSON 导入 dry-run
- [x] 记录查询数量、重复 SQL 指纹、耗时、`EXPLAIN QUERY PLAN`、全表扫描和 N+1
- [x] 确认列表结果保持分页，但筛选元数据加载触发批量查询放大
- [x] 确认合集详情存在 N+1，并无界加载全部可选条目
- [x] 确认 cleanup、duplicates 和元数据列表随数据量明显退化
- [x] 确认工作台、activity、备份校验和导入 dry-run 未出现 SQL N+1
- [x] 新增 `PERFORMANCE.md`，区分已验证问题、暂未发现问题和 I2 建议
- [x] 性能测试不依赖固定毫秒阈值，覆盖只读、分页查询上限和 N+1 判定
- [x] 未新增索引、表、字段、依赖、真实迁移、缓存、后台任务或业务优化
- [x] 未使用或修改默认 schema 2 数据卷，临时数据已清理
- [x] 更新 README / TASKS / REVIEW / CHANGELOG / PLAN，仅记录 Unreleased
- [x] 未修改已发布 tag，未创建 GitHub Release

## Phase 2-I2 查询优化与分页收敛

- [x] items 当前页按需加载 tags / creators / collections / state，并阻止无关反向关系递归加载
- [x] filter metadata 保持完整选项和现有筛选语义，不再加载关联 item graph
- [x] cleanup 候选改为 id / name / relation count 标量查询，对比和合并继续按需加载完整对象
- [x] collection detail 消除逐成员 collection N+1，不再重复加载完整合集
- [x] collection members 使用 20 条分页，显示完整成员总数
- [x] available items 使用 20 条分页和本地标题搜索，不改变成员关系
- [x] tags / creators / collections 使用 50 条分页，旧 URL 默认第一页
- [x] duplicates / cleanup 按 20 个 comparison pair 分页，每个候选仍可通过翻页访问
- [x] data-health 孤立关系查询由 6 次合并为 3 次
- [x] data-health 保持完整总数和 fix count，仅限制页面明细为前 200 条
- [x] 同一页面请求复用一次 settings 读取，workbench saved views 在 SQL 中限制为 4 条
- [x] stats 聚合与日桶查询从基线 28 次收敛为 11 次，返回结构和数值测试不变
- [x] activity 只加载页面实际使用的 item 标题，保持 50 + 50 上限
- [x] 性能测试使用查询数和行数上限，不使用固定毫秒阈值
- [x] 重跑 100 / 1,000 / 10,000 隔离性能矩阵并更新 PERFORMANCE.md
- [x] 保持 saved views、筛选、排序、批量编辑、合并、备份、导入、确认和 rollback 行为
- [x] 未新增索引、表、字段、依赖、生产迁移，未提升 schema 版本
- [x] 未使用默认 schema 2 数据卷，未修改旧 tag，未创建 GitHub Release

## Phase 2-I3 异常处理、日志与错误页面统一

- [x] 为 400 / 403 / 404 / 405 / 409 / 422 / 500 统一双语 HTML 错误页面
- [x] `/api/` 和显式 JSON 请求统一返回 `error` / `message` / `request_id`
- [x] 保留兼容 `detail` 字段、原状态码和 405 `Allow` 响应头
- [x] 422 保留 FastAPI 校验 type / loc / msg，不回显提交的 input
- [x] 每个成功、重定向和错误响应都返回 `X-Request-ID`
- [x] 外部 request id 仅接受标准 UUID 或 32 位 UUID hex，其他值自动替换
- [x] 请求日志包含 request_id / method / 安全 route path / status / duration
- [x] 异常日志只记录 exception type，不记录异常值或 traceback
- [x] 禁用包含原始 query string 的重复 Uvicorn access log
- [x] 日志不记录 Authorization、Cookie、query、表单密码或上传内容
- [x] 500 只返回通用提示和 request_id，不泄露 SQL、路径、环境或凭据
- [x] 普通 404 / 业务 4xx 不记录为系统崩溃
- [x] 未捕获异常后的未提交数据库写入由 Session close rollback
- [x] 备份、导入、合并、健康修复、设置和 schema 升级原 rollback 测试通过
- [x] 登录、POST、confirm 和 strict `CONFIRM` 行为保持不变
- [x] 未修改数据库结构、依赖、已发布 tag，未创建 GitHub Release
- [x] `ghp_` / `github_pat_` 凭据外形 request id 不进入响应或日志
- [x] 未匹配路由固定记录 `/[unmatched]`，不记录包含 token 的原始路径
- [x] 已匹配路由继续记录应用拥有的模板路径，不记录具体路径参数

## Phase 2-I4 安全、兼容性与 v1.0.0 发布前总审查

- [x] 枚举全部页面和 API 路由，确认非公开路由均有 session 登录保护
- [x] 审查全部 POST / PUT / DELETE，确认没有 GET 业务数据写操作或 PATCH 写路由
- [x] 将详情页访问活动从 GET 写入迁移到登录且同源保护的 POST
- [x] 为带 Origin / Referer 的不安全请求增加同源校验，并保留无头本地 API 客户端兼容
- [x] 登录清理认证前 session，登出和重启使旧认证 cookie 失效
- [x] Session cookie 保持 HttpOnly / SameSite=Lax，并支持显式启用 Secure
- [x] 所有危险页面操作增加服务端 confirm，strict 模式继续精确验证 CONFIRM
- [x] 收紧 next / 语言跳转，拒绝外部、反斜杠、编码反斜杠和控制字符目标
- [x] 非法或非对象登录 JSON 安全返回 400，不泄露内部异常
- [x] CSV / JSON 导入增加可配置上传上限，超限时解析和写入均不发生
- [x] 验证 Jinja 默认转义、404 / 422 / 500 响应与请求日志脱敏
- [x] 条目、元数据、合集、批量、合并、健康、设置、备份、导入和迁移 rollback 回归通过
- [x] 使用隔离数据库验证全新、旧无版本、合法 Schema 1、低版本和高版本五类场景
- [x] 中英文、URL 参数、备份格式、分页、空数据和设置优先级回归通过
- [x] 重跑 100 / 1,000 / 10,000 隔离性能矩阵，查询上限保持且无 N+1
- [x] 保持 CURRENT_SCHEMA_VERSION=1、空生产迁移注册表和默认 schema 2 数据卷不变
- [x] 未新增产品功能、依赖、索引、表、字段、生产迁移、tag 或 GitHub Release

## v1.0.0 正式发布

- [x] 将 FastAPI 应用版本元数据更新为 `1.0.0`
- [x] 将 Phase 2-I1 / I2 / I3 / I4 从 `Unreleased` 整理为 `## [1.0.0] - 2026-07-11`
- [x] 保留空白 `Unreleased`，未修改 v0.9.0 或更早发布段
- [x] 更新 README / PLAN / TASKS / REVIEW / GOAL 当前版本与发布状态
- [x] 全量测试通过：309 passed
- [x] 使用全新隔离 Docker 数据目录完成 build / up / `/login` 连续 200 / down
- [x] 容器内应用版本为 `1.0.0`，隔离数据库基线仍为 Schema 1
- [x] 保持 `CURRENT_SCHEMA_VERSION = 1` 和空生产迁移注册表
- [x] 未修改业务逻辑、数据库结构、索引、依赖或旧 tag / Release
- [x] 创建发布提交、annotated `v1.0.0` tag 和正式 GitHub Release
- [x] 未使用或修改默认 schema 2 数据卷

## v1.0.1 正式发布

- [x] 确认 `main` 已包含 Phase 2-K1 开发完成度审计和 Phase 2-K2 边界收口
- [x] 将 FastAPI 应用版本元数据更新为 `1.0.1`
- [x] 将 K1 / K2 从 `Unreleased` 整理为 `## [1.0.1] - 2026-07-11`
- [x] 保留空白 `Unreleased`，未修改 v1.0.0 或更早发布段
- [x] 更新 README / PLAN / TASKS / REVIEW / GOAL / COMPLETION_AUDIT 发布状态
- [x] 全量测试通过：347 passed
- [x] 使用全新隔离 Docker 数据目录完成 build / up / `/login` 连续 200 / down
- [x] 容器内应用版本为 `1.0.1`，隔离数据库基线仍为 Schema 1
- [x] 保持 `CURRENT_SCHEMA_VERSION = 1` 和空生产迁移注册表
- [x] 未修改业务逻辑、依赖、数据库结构、Schema、迁移或旧 tag / Release
- [x] 创建发布提交、annotated `v1.0.1` tag 和正式 GitHub Release
- [x] 未使用或修改默认 schema 2 数据卷

## v1.0.2 正式发布

- [x] 确认 `main` 已包含 Phase 2-L1 至 L6
- [x] 将 FastAPI 应用版本元数据和回归断言更新为 `1.0.2`
- [x] 将 L1 至 L6 从 `Unreleased` 整理为 `## [1.0.2] - 2026-07-12`
- [x] 保留空白 `Unreleased`，未修改 v1.0.1 或更早发布段
- [x] 更新 README / PLAN / TASKS / REVIEW / GOAL 发布状态
- [x] 全量测试通过：358 passed；`pip check` 通过
- [x] 使用全新隔离 Docker 数据目录完成 build / healthy / `/login` / version / down
- [x] 容器内应用版本为 `1.0.2`，隔离数据库基线仍为 Schema 1
- [x] 未修改业务逻辑、依赖、数据库、Schema、迁移或旧 tag / Release
- [x] 创建发布提交、annotated `v1.0.2` tag 和正式 GitHub Release
- [x] `main`、tag peeled commit 和 Release target 指向同一发布提交
- [x] 未部署到 N100，临时容器、镜像和数据已清理

## v1.0.3 正式发布

- [x] 确认 `main` 已包含 Phase 2-L7 与 README 数据目录权限准备修复
- [x] 将 FastAPI 应用版本元数据和回归断言更新为 `1.0.3`
- [x] 将 L7 从 `Unreleased` 整理为 `## [1.0.3] - 2026-07-12`，并保留新的空白 `Unreleased`
- [x] 同步 README / PLAN / TASKS / REVIEW / GOAL 发布状态与 rootful Docker 权限说明
- [x] 全量测试通过：358 passed；`pip check` 通过
- [x] 隔离 Docker 验证安全配置、healthy、写入边界、SQLite 持久化、版本与 Schema 1
- [x] 未修改业务逻辑、依赖、数据库、Schema、迁移、容器用户或旧 tag / Release
- [x] 创建发布提交、annotated `v1.0.3` tag 和正式 GitHub Release
- [x] `main`、tag peeled commit 和 Release target 指向同一发布提交
- [x] 未部署到 N100，临时容器、镜像和数据已清理

## v1.0.4 正式发布

- [x] 确认 `main` 已包含 Phase 2-L8 固定非 root 容器用户和数据目录迁移流程
- [x] 将 FastAPI 应用版本元数据和回归断言更新为 `1.0.4`
- [x] 将 L8 从 `Unreleased` 整理为 `## [1.0.4] - 2026-07-12`，并保留新的空白 `Unreleased`
- [x] 同步 README / PLAN / TASKS / REVIEW / GOAL 发布状态和 v1.0.3 及更早升级要求
- [x] 全量测试通过：358 passed；`pip check` 通过
- [x] 隔离 Docker 验证 `10001:10001` 身份、L7/L8 安全边界、HTTP / 安全头和 SQLite 重建持久化 / Schema 1
- [x] 未修改业务逻辑、依赖、数据库、Schema、迁移、容器 UID/GID、安全配置或旧 tag / Release
- [x] 创建发布提交、annotated `v1.0.4` tag 和正式 GitHub Release
- [x] `main`、tag peeled commit 和 Release target 指向同一发布提交
- [x] 未部署到 N100，临时容器、镜像和数据已清理
