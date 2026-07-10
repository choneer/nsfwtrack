# GOAL.md

# 当前目标：Phase 2-G6 危险操作偏好与确认流程统一

请先读取 `RULE.md`、`PLAN.md`，再执行本文件。
长期边界以 `RULE.md` 为准。

---

## 一、目标

统一危险操作的提示与确认流程，并允许用户提高确认强度。

覆盖：

- 删除条目及批量删除
- 删除标签 / 创作者 / 合集
- 条目与元数据合并
- 清空最近活动
- 恢复备份
- 数据健康手动修复
- 设置恢复默认值

设置只能增强确认，不能关闭确认。

---

## 二、设置项

复用现有 `app_settings` 表，不新增表、不改字段、不新增依赖。

新增白名单 key：

- `danger_confirmation_mode`
  - `standard`
  - `strict`
- `backup_reminder_mode`
  - `always`
  - `dangerous_only`
- `danger_result_detail`
  - `summary`
  - `detailed`

要求：

- 不允许 `off`、`disabled`、`never`
- 不允许未知 key / value
- 不允许外部 URL 或脚本内容
- 旧设置与旧备份继续兼容

---

## 三、确认模式

### standard

保留现有安全流程：

- 必须登录
- 必须 POST
- 浏览器 confirm
- 现有服务端确认字段

### strict

在 standard 基础上，危险操作还必须提交固定确认文本：

- `CONFIRM`

要求：

- 服务端必须验证，不能只靠前端
- 缺少或错误确认文本时拒绝操作
- 不得因为设置异常降级为无确认
- 设置读取失败时安全回退到 `standard`

---

## 四、统一安全提示

危险操作页面统一展示：

- 操作对象
- 操作后果
- 是否会删除数据
- 是否可恢复
- JSON 备份建议
- 当前确认模式

`backup_reminder_mode` 只能控制：

- 所有危险操作都显示备份提示
- 仅适合备份的危险操作显示提示

不能完全关闭安全提示。

---

## 五、结果摘要

`danger_result_detail` 只控制结果展示：

- `summary`：显示成功 / 失败和影响数量
- `detailed`：额外显示对象、转移、删除、跳过和冲突处理

不能改变业务逻辑或安全校验。

---

## 六、安全要求

必须保证：

- GET 不执行危险操作
- 设置不能绕过登录、POST、confirm 或服务端确认
- 不新增一键全部删除 / 合并 / 修复
- 不改变现有操作的数据范围
- 不删除额外业务数据
- 失败时保持原有 rollback
- 非法设置安全回退
- 不修改已发布 tag

---

## 七、测试

至少覆盖：

- 合法设置可保存
- 非法 key / value 被拒绝
- 不允许关闭确认
- standard 模式保留现有流程
- strict 模式缺少 `CONFIRM` 时拒绝
- strict 模式错误文本时拒绝
- strict 模式正确文本时执行
- GET 不能执行危险操作
- 设置异常时安全回退
- backup reminder 不能完全关闭
- 结果详情设置不改变业务数据
- 旧备份无新设置时兼容
- 新备份可恢复新设置
- i18n 通过
- 全量回归测试通过

---

## 八、文档与验收

更新：

- README.md
- TASKS.md
- REVIEW.md
- CHANGELOG.md
- PLAN.md，如需要

要求：

- CHANGELOG 只写 `Unreleased`
- 不创建 tag 或 GitHub Release
- 运行 `RULE.md` 中的测试和 Docker 验收
- 验收通过后提交并推送到 `origin/main`

---

## 九、完成后汇报

1. 修改 / 新增文件
2. 新增了哪些 setting key
3. standard / strict 如何实现
4. 哪些危险操作已统一
5. 如何防止关闭或绕过确认
6. 备份提示如何处理
7. 结果详情设置如何处理
8. 备份兼容情况
9. 测试与 Docker 结果
10. 提交 hash
