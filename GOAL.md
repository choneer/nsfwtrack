# GOAL.md

# 当前目标：Phase 2-F3 数据健康手动修复 / 低风险维护操作

请先读取 `RULE.md`、`PLAN.md`，再执行本文件。
本轮目标只描述当前阶段，长期边界以 `RULE.md` 为准。

---

## 一、目标

基于 Phase 2-F1 的数据健康检查结果，新增低风险手动修复能力。

本轮只允许修复：

- 孤立关系：`item_tags` / `item_creators` / `item_collections`
- 重复关系：`item_tags` / `item_creators` / `item_collections`
- 孤立 `item_activity`
- 负数 `view_count` / `edit_count`
- `saved_views.query_string` 中的危险或未知参数

本轮严禁：

- 删除 `items`
- 删除 `tags`
- 删除 `creators`
- 删除 `collections`
- 自动修复
- 一键修复全部
- 自动合并
- AI 判断
- 外部查询
- 外部内容源
- URL 导入
- 爬虫
- 云同步
- 多用户系统

核心原则：

```text
只能修关系和辅助记录，不能删除核心业务实体。
```

---

## 二、数据库要求

本轮不新增表，不改字段，不新增依赖。

允许修改：

- `item_tags`
- `item_creators`
- `item_collections`
- `item_activity`
- `saved_views.query_string`

不允许修改：

- `items`
- `tags`
- `creators`
- `collections`

---

## 三、建议实现

建议新增：

- `app/services/data_health_fixes.py`
- `tests/test_data_health_fixes.py`

建议增强：

- `GET /data-health`
- `POST /data-health/fix`

要求：

- `GET /data-health` 继续只读
- 修复必须登录
- 修复必须 POST
- 修复必须有 confirm
- 修复前提示先做 JSON 备份
- 每次只允许修复一种 `fix_type`
- 不允许 `fix_all`
- 不允许用户传表名或 SQL
- 服务端必须用白名单分派修复逻辑
- 修复失败必须 rollback
- 修复完成显示结果摘要

---

## 四、允许的 fix_type

只允许：

- `orphan_item_tags`
- `orphan_item_creators`
- `orphan_item_collections`
- `duplicate_item_tags`
- `duplicate_item_creators`
- `duplicate_item_collections`
- `orphan_item_activity`
- `negative_activity_counts`
- `saved_view_blocked_params`

其他 `fix_type` 必须拒绝，但不能 500。

---

## 五、页面要求

`/data-health` 页面增加低风险修复入口。

要求：

- 只在对应问题存在时显示修复按钮
- 修复按钮必须有 confirm
- 页面说明不会删除条目 / 标签 / 创作者 / 合集
- 页面说明修复前建议备份
- 修复后显示删除 / 修正 / 跳过数量
- 不展示完整异常堆栈
- 中文 / English 文案覆盖

---

## 六、测试要求

至少覆盖：

- 未登录不能修复
- GET 不能修复
- 非法 `fix_type` 不 500
- `fix_all` 被拒绝
- 孤立关系可清理
- 重复关系可清理
- 孤立 activity 可删除
- 负数 activity 计数可修正为 0
- saved views 危险参数可清理
- 不删除任何 item / tag / creator / collection
- 修复失败 rollback
- i18n 仍通过
- 旧功能全量回归通过

---

## 七、文档更新

完成后更新：

- README.md
- TASKS.md
- REVIEW.md
- CHANGELOG.md
- PLAN.md，如需要

要求：

- 写入 Phase 2-F3
- 说明只做低风险手动修复
- 说明不会删除核心业务实体
- 说明修复前建议备份
- CHANGELOG 只写 Unreleased
- 不修改旧 tag
- 不创建 GitHub Release

---

## 八、验收

运行 `RULE.md` 中的验收命令。

要求：

- pytest 全部通过
- Docker build 通过
- Docker compose up 通过
- `/login` 返回 200
- compose down 正常
- 提交并推送到 `origin/main`

---

## 九、完成后汇报

按以下格式汇报：

1. 修改 / 新增文件
2. 是否新增表 / 字段 / 依赖
3. 支持哪些 `fix_type`
4. 如何保证不删除核心业务实体
5. 如何保证没有一键修复全部
6. 如何保证 POST / confirm / 登录
7. rollback 如何处理
8. 测试结果
9. Docker 结果
10. 文档更新
11. 提交 hash
12. 下一步建议
