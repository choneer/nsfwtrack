# GOAL.md

# 当前目标：Phase 2-H2 显式迁移框架与升级 dry-run

请先读取 `RULE.md`、`PLAN.md`。
长期边界以 `RULE.md` 为准。

---

## 一、目标

建立轻量、显式、可测试的数据库迁移框架：

- 迁移注册表
- 迁移路径解析
- 升级 dry-run
- 用户显式触发升级
- 失败回滚
- 升级状态页面

本轮不为测试而虚构生产迁移，不强行提升 `CURRENT_SCHEMA_VERSION`，不修改现有业务表。

---

## 二、迁移框架

建议新增：

- `app/services/migrations.py`
- `app/templates/schema_upgrade.html`
- `tests/test_migrations.py`

每个迁移步骤至少包含：

- `from_version`
- `to_version`
- `name`
- `preview`
- `apply`
- 源版本前置检查
- 目标版本完成检查

要求：

- 迁移只能由代码注册
- 不接受用户 SQL、表名或版本号
- 路径必须连续，不能重复、跳级或循环
- 先读取数据库版本，再解析迁移路径
- 不能要求旧数据库提前符合最新结构
- 完成迁移后再校验目标结构

---

## 三、页面与路由

建议新增：

- `GET /schema-upgrade`
- `POST /schema-upgrade/preview`
- `POST /schema-upgrade/apply`

要求：

- 需要登录
- GET 只读
- preview 只读，不写数据库
- apply 必须 POST
- apply 必须 browser confirm
- 复用现有危险操作服务端确认
- strict 模式仍要求精确 `CONFIRM`
- 必须确认已知晓升级前备份要求
- 不提供降级、跳过检查或手动改版本功能

---

## 四、升级行为

状态处理：

- 当前版本：显示无需升级
- 低版本且有完整路径：允许 preview 和显式升级
- 低版本但无路径：拒绝升级并说明缺失路径
- 高版本：继续拒绝启动或升级
- 结构无法确认：拒绝升级

apply 要求：

- 整条迁移链尽量在同一事务中完成
- 迁移步骤和版本记录必须原子提交
- 任一步失败时 rollback
- post-check 失败时 rollback
- 失败后不得留下错误版本记录或半迁移状态
- 启动时不得自动执行迁移

---

## 五、dry-run

dry-run 展示：

- 当前版本与目标版本
- 迁移步骤和顺序
- 每步预计结构变化
- 前置检查结果
- warning / error
- 是否可升级
- 升级前备份提示

dry-run 不得：

- 修改表结构
- 修改业务数据
- 写入版本记录
- 自动触发 apply

---

## 六、备份与安全

要求：

- `schema_migrations` 继续与 JSON 备份隔离
- 旧备份不能覆盖 schema 版本
- 升级入口不得执行任意 SQL
- 不新增自动迁移或自动降级
- 不修改已发布 tag
- 不创建 GitHub Release

---

## 七、测试

至少覆盖：

- 注册表拒绝重复、断层、倒序和循环路径
- 当前版本无需升级
- 低版本可解析连续路径
- 无完整路径时拒绝
- 高版本拒绝
- preview 不写数据库
- GET 不执行迁移
- 未登录不能升级
- standard / strict 确认仍有效
- 缺少备份确认时拒绝
- 两步迁移中第二步失败时全部 rollback
- post-check 失败时 rollback
- 失败后版本记录不变化
- 用户不能提交任意 SQL、表名或版本号
- `schema_migrations` 不进入备份
- i18n 与全量回归测试通过

测试可以使用临时数据库和测试专用迁移注册表。
不要为了测试增加无意义的生产迁移或提升当前 schema 版本。

---

## 八、文档与验收

更新：

- README.md
- TASKS.md
- REVIEW.md
- CHANGELOG.md
- PLAN.md

要求：

- CHANGELOG 只写 `Unreleased`
- 说明启动时不会自动迁移
- 说明升级必须显式确认并建议先备份
- 运行 `RULE.md` 中的测试和 Docker 验收
- 通过后提交并推送到 `origin/main`

完成后汇报：

1. 修改 / 新增文件
2. 迁移注册表与路径解析方式
3. preview 如何保证只读
4. apply 如何确认和执行
5. rollback 与版本记录如何保证原子性
6. 如何避免迁移前要求最新结构
7. 当前 schema 版本是否变化
8. 测试与 Docker 结果
9. 提交 hash
