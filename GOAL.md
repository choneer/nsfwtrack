# GOAL.md

# 当前目标：Phase 2-I4 安全、兼容性与 v1.0.0 发布前总审查

请先读取：

- `RULE.md`
- `PLAN.md`
- `REVIEW.md`
- `PERFORMANCE.md`
- `CHANGELOG.md`

本阶段为发布前冻结审查，不新增产品功能。

---

## 一、目标

全面检查当前 `main` 是否满足 `v1.0.0` 发布条件：

- 安全边界
- 数据完整性
- Schema 与迁移兼容性
- 页面和功能兼容性
- 错误处理与日志脱敏
- 性能回归
- 文档一致性
- Docker 与数据库场景回归

允许修复已确认的发布阻塞问题，但不得借机扩展功能。

---

## 二、禁止项

本轮不得：

- 新增产品功能
- 新增外部内容源、爬虫、推荐或 AI 功能
- 修改数据库表、字段或索引
- 提升 `CURRENT_SCHEMA_VERSION`
- 新增生产迁移
- 新增第三方依赖
- 修改旧 tag 或 Release
- 创建 `v1.0.0` tag 或 Release
- 使用或修改默认 schema 2 数据卷

如确认必须修改数据库结构、迁移协议或重大权限边界，停止对应实现并报告，不要自行扩大范围。

---

## 三、安全审查

### 1. 登录与 Session

检查：

- 未登录用户不能访问受保护页面和操作
- 登录成功后重新生成 Session，避免会话固定
- 登出后旧 Session 失效
- Cookie 至少设置 `HttpOnly`
- `SameSite` 设置合理
- HTTPS 环境可安全启用 `Secure`
- 不在 URL、日志或错误响应中暴露 Session
- 登录跳转不存在开放重定向

### 2. 状态修改请求

逐项检查所有：

- POST
- PUT
- PATCH
- DELETE

要求：

- 必须登录
- 不允许使用 GET 修改数据
- 保留浏览器确认和服务端确认
- strict 模式继续要求精确 `CONFIRM`
- 检查 CSRF / Same-Origin 防护是否完整
- 不能只依赖前端 JavaScript confirm 作为安全措施

如当前缺少有效的 CSRF 或同源防护，应视为发布阻塞问题，并使用现有架构实现最小安全修复，不新增依赖。

### 3. 输入与输出

检查：

- HTML 默认转义
- 搜索、标题、名称、短评等内容不能造成 XSS
- URL 参数不能造成开放重定向
- 上传大小限制有效
- 非 JSON、损坏 JSON、超大文件和非法字段安全失败
- 文件名、异常值和上传正文不进入日志
- 404、422、500 不泄露内部信息

---

## 四、数据完整性审查

重点验证：

- 条目、标签、创作者、合集删除
- 批量编辑和批量删除
- 条目合并
- 元数据合并
- 数据健康修复
- 设置保存和重置
- 导入预览与确认
- 备份校验与恢复
- Schema preview 与显式迁移框架

要求：

- 失败时完整 rollback
- 不留下部分写入
- preview / dry-run 保持只读
- 确认对象在提交前重新读取，避免使用过期状态
- 合并和删除不会产生孤立关系
- 外键和唯一约束错误转换为安全业务错误
- 重复提交不会造成不可预测状态

---

## 五、Schema 与数据库兼容性

使用隔离副本验证：

### 场景 A：全新数据库

- 自动创建 Schema 1
- 正常记录 baseline
- 可登录并使用核心功能

### 场景 B：旧版无版本记录的兼容数据库

- baseline 检测正确
- 不修改业务数据
- 行数和关键关系保持不变

### 场景 C：合法 Schema 1 数据库

- 正常启动
- 不重复写入 migration 记录
- 备份、导入、设置和查询正常

### 场景 D：低于应用要求的数据库

- 正确进入升级提示
- 不提前执行最新结构查询
- preview 保持只读

### 场景 E：高于应用版本的 Schema 2 数据库副本

- 明确拒绝启动或访问业务功能
- 不自动降级
- 不修改任何表或版本记录

不得使用真实默认 schema 2 数据卷，只能使用复制出的隔离测试副本。

---

## 六、兼容性回归

检查中英文环境下：

- 登录和登出
- 首页工作台
- 条目 CRUD
- 搜索、筛选、排序和分页
- saved views
- 批量编辑
- 标签、创作者和合集
- duplicates 和 cleanup
- activity
- stats
- data-health
- settings
- backup / restore
- CSV / JSON import / export
- 错误页面

要求：

- URL 参数兼容
- 现有备份格式兼容
- API、CSV、JSON 字段不变
- 空数据场景不报错
- 超过一页的数据不会丢失
- 默认设置与 Session 显式选择优先级正确

---

## 七、错误处理与日志复核

确认：

- 每个响应均有合法 `X-Request-ID`
- 非法外部 ID 被替换
- 未匹配路径记录为 `/[unmatched]`
- 已匹配路径记录路由模板
- 405 保留 `Allow`
- 422 不回显 `input`
- 500 只显示通用提示和 request_id
- 日志不包含 query、Cookie、Authorization、密码、Token、表单、上传正文或异常值
- 普通 404 和业务错误不记录为严重崩溃
- 日志中的 request_id、状态码和响应一致

---

## 八、性能回归

重新运行 100 / 1,000 / 10,000 三档性能矩阵。

确认至少保持：

- items：约 11 次查询
- filtered items：约 11 次
- cleanup：约 4 次
- collection detail：约 9 次
- duplicates：约 7 次
- metadata 列表：约 3 次
- stats：约 11 次
- 无 N+1 回归

不使用固定毫秒数作为失败阈值。

---

## 九、文档审查

检查并统一：

- `README.md`
- `PLAN.md`
- `TASKS.md`
- `REVIEW.md`
- `CHANGELOG.md`
- `.env.example`
- Docker 使用说明
- 备份与恢复说明
- Schema 兼容说明
- 本地单用户安全边界
- 已知限制

要求：

- 不宣称未实现的能力
- 不保留过时测试数量或阶段状态
- `CHANGELOG.md` 仍只更新 `Unreleased`
- 暂不写正式发布日期
- 暂不创建 tag 或 Release

---

## 十、验收

必须执行：

- 安全专项测试
- Schema / migration 专项测试
- backup / import 专项测试
- 全量 pytest
- 三档性能矩阵
- Docker build
- Docker 使用全新隔离数据卷启动
- `/login` 连续返回 200
- HTML / JSON 错误响应抽查
- Docker down 与临时数据清理

不得接触默认 schema 2 数据卷。

---

## 十一、完成标准

完成后报告：

1. 修改文件
2. 安全审查结果
3. CSRF / Same-Origin 结论
4. 登录、Session 和 Cookie 结论
5. 数据完整性与 rollback 结果
6. 五类数据库场景结果
7. 中英文和功能兼容结果
8. 错误处理与日志结果
9. 性能回归结果
10. 文档一致性结果
11. 测试与 Docker 结果
12. 已知非阻塞限制
13. 是否存在发布阻塞问题
14. 是否满足 `v1.0.0` 发布条件
15. 提交 hash

通过后提交并推送到 `origin/main`，但不要创建 tag 或 GitHub Release。