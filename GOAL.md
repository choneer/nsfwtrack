# GOAL.md

# 当前目标：Phase 2-G1 基础设置中心

请先读取 `RULE.md`、`PLAN.md`，再执行本文件。
长期边界以 `RULE.md` 为准。

---

## 一、目标

新增本地基础设置中心，让用户配置常用默认行为。

本轮实现：

- 设置页 `/settings`
- 默认语言
- 默认每页数量
- 默认排序字段
- 默认排序方向
- 默认首页入口
- 设置保存 / 更新
- 设置恢复默认值，可选

本轮不做：

- 多用户设置
- 复杂权限
- 云同步
- 外部账号
- 主题市场
- 插件系统
- AI 推荐
- 外部内容源

---

## 二、数据库

本轮允许新增一个本地表：

- `app_settings`

建议字段：

- `id`
- `key`
- `value`
- `created_at`
- `updated_at`

要求：

- `key` 唯一
- 只允许白名单 setting key
- 不修改已有表字段
- 不新增依赖
- 旧数据库通过 `create_all` 兼容
- JSON 备份 / 恢复应兼容 `app_settings`
- 旧备份没有 `app_settings` 时不能失败

---

## 三、允许的设置项

只允许这些 key：

- `default_language`
- `default_page_size`
- `default_sort`
- `default_sort_dir`
- `default_home`

建议取值：

```text
default_language: zh / en
default_page_size: 10 / 20 / 50 / 100
default_sort: updated_at / created_at / title / rating
default_sort_dir: asc / desc
default_home: workbench / items / stats / activity
```

要求：

- 非法 key 拒绝
- 非法 value 拒绝
- 不允许用户传任意 key 写入数据库
- 不允许保存外部 URL
- 不允许保存脚本内容

---

## 四、页面与路由

建议新增或增强：

- `GET /settings`
- `POST /settings`
- `POST /settings/reset`，可选

要求：

- 必须登录
- 保存设置必须 POST
- reset 必须 POST + confirm
- GET `/settings` 只读
- 非法值不 500
- 保存后显示结果提示
- 设置页移动端可用
- 不破坏语言切换
- 不破坏登录 / 登出

---

## 五、设置生效范围

要求：

- 默认每页数量用于条目列表页没有 `page_size` 参数时
- 默认排序字段 / 方向用于条目列表页没有排序参数时
- 默认语言只在用户没有显式选择语言时生效
- 默认首页入口用于首页工作台展示或入口高亮
- 显式 URL 参数优先级高于默认设置
- 不影响 saved views 中已保存的参数

---

## 六、安全边界

必须遵守：

- 不执行任意 SQL
- 不保存未知设置项
- 不保存外部 URL
- 不请求外部网络
- 不引入第三方依赖
- 不修改核心业务数据
- 不自动创建条目 / 标签 / 创作者 / 合集
- 不影响已发布 tag

---

## 七、测试要求

至少覆盖：

- 未登录访问 `/settings` 跳转登录
- 登录后设置页正常渲染
- 可以保存合法设置
- 非法 key 被拒绝
- 非法 value 被拒绝
- 设置保存后能读取
- 默认 page_size 生效
- 默认 sort / sort_dir 生效
- 显式 URL 参数优先于默认设置
- 默认语言不破坏现有语言切换
- reset 设置可恢复默认值，如实现 reset
- 旧备份无 `app_settings` 不失败
- 新备份包含 `app_settings` 可恢复
- i18n key 覆盖测试通过
- 旧功能全量回归通过

---

## 八、文档更新

完成后更新：

- README.md
- TASKS.md
- REVIEW.md
- CHANGELOG.md
- PLAN.md，如需要

要求：

- 写入 Phase 2-G1
- 说明设置中心只保存本地偏好
- 说明不涉及多用户 / 云同步
- CHANGELOG 只写 Unreleased
- 不修改旧 tag
- 不创建 GitHub Release

---

## 九、验收与汇报

运行 `RULE.md` 中的验收命令。

完成后汇报：

1. 修改 / 新增文件
2. 是否新增表 / 字段 / 依赖
3. `app_settings` 如何设计
4. 支持哪些 setting key
5. 如何校验 key / value
6. 设置如何生效
7. 备份 / 恢复如何兼容
8. 测试结果
9. Docker 结果
10. 文档更新
11. 提交 hash
12. 下一步建议
