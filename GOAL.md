# GOAL.md

# 当前目标：Phase 2-I3 异常处理、日志与错误页面统一

请先读取 `RULE.md`、`PLAN.md`。
长期边界以 `RULE.md` 为准。

---

## 一、目标

统一页面和 API 的异常处理：

- 400 / 403 / 404 / 405 / 409 / 422 / 500
- 安全错误页面
- JSON 错误响应
- 请求标识 `request_id`
- 本地日志格式
- 未捕获异常安全回退

本轮不修改数据库结构，不新增依赖。

---

## 二、错误响应

页面请求：

- 返回对应状态码
- 使用统一错误模板
- 显示简短、可理解的提示
- 提供返回首页或上一安全页面的入口

JSON/API 请求：

- 保持 JSON 响应
- 至少包含：
  - `error`
  - `message`
  - `request_id`
- 不破坏现有 API 字段和状态码

要求：

- 404 不得变成 500
- 405 保留正确的 `Allow` 信息
- 422 不破坏 FastAPI 校验行为
- 预期业务错误不得被错误记录为系统崩溃

---

## 三、安全边界

用户响应中不得出现：

- Python traceback
- SQL 语句或参数
- 数据库路径
- 服务器绝对路径
- 环境变量
- Cookie / Session
- Authorization header
- Token 或凭据
- 上传文件内容
- 内部异常细节

500 页面只显示通用提示和 `request_id`。

---

## 四、请求标识与日志

为每个请求生成或接受安全的 `request_id`。

建议：

- 响应头返回 `X-Request-ID`
- 日志包含：
  - request_id
  - method
  - path
  - status
  - duration
  - exception type，仅异常时

要求：

- 不信任过长或非法的外部 request id
- 不记录敏感请求头、Cookie、表单密码或文件内容
- 不接入外部日志、遥测或第三方监控
- 不把普通 404 大量记录为严重错误

---

## 五、高风险流程

重点统一以下流程的错误提示：

- 备份校验与恢复
- 导入与 dry-run
- 条目及元数据合并
- 数据健康修复
- 设置保存与重置
- Schema 预检与显式升级

要求：

- 保留原有 rollback
- 保留登录、POST、confirm 和 strict `CONFIRM`
- 不改变操作范围或业务结果
- 错误发生后不得留下半写入状态

---

## 六、建议实现

可新增：

- `app/errors.py`
- `app/request_context.py`
- `app/templates/error.html`
- `tests/test_error_handling.py`

可以复用现有页面、flash 和日志结构，避免重复实现。

---

## 七、测试

至少覆盖：

- 页面 404 返回统一 HTML 和 404
- JSON 404 返回 JSON
- 405 状态和 Allow 信息正确
- 422 保持正常校验响应
- 模拟未捕获异常返回安全 500
- 500 响应不泄露 traceback、SQL、路径或凭据
- 每个响应包含有效 `X-Request-ID`
- 非法外部 request id 被替换
- 日志包含 request_id 和状态码
- 日志不包含 Cookie、Authorization、密码或上传内容
- 预期业务错误不变成 500
- 高风险操作失败仍 rollback
- i18n 和全量回归测试通过

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
- 不修改旧 tag
- 不创建 Release
- 运行全量测试和 Docker 验收
- 通过后提交并推送到 `origin/main`

完成后汇报：

1. 修改 / 新增文件
2. 错误处理架构
3. HTML 与 JSON 如何区分
4. request_id 如何生成和校验
5. 日志记录及脱敏方式
6. 500 如何防止信息泄露
7. 高风险操作错误边界
8. 测试与 Docker 结果
9. 提交 hash
