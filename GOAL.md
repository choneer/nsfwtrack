# GOAL.md

# 当前目标：Phase 2-F1 数据健康检查 / 本地数据自检

请先读取 `RULE.md`、`PLAN.md`，再执行本文件。
`RULE.md` 是长期通用规则，本文档只描述本轮开发目标。
如果 `RULE.md` 与本文档冲突，以 `RULE.md` 的安全边界为准。

---

## 一、目标

新增本地数据健康检查能力，帮助用户发现数据库中的潜在问题。

本轮只做只读检查和报告展示。

本轮实现：

- 数据健康检查页
- 条目数据基础检查
- 标签 / 创作者 / 合集关系检查
- saved views 检查
- item activity 检查
- 备份前安全提示
- 健康报告摘要
- 问题明细列表

本轮不做：

- 自动修复
- 一键修复
- 自动删除数据
- 自动合并
- AI 判断
- 外部信息查询
- 外部内容源
- URL 导入
- 爬虫
- adapter
- 云同步
- 多用户系统

---

## 二、数据库变更

本轮不允许新增数据库表。
不允许修改已有数据库字段。
不允许新增依赖。

本轮只读取现有数据：

- items
- tags
- creators
- collections
- item_tags
- item_creators
- item_collections
- saved_views
- item_activity

---

## 三、检查范围

新增数据健康检查服务。

建议新增：

- `app/services/data_health.py`
- `app/templates/data_health.html`
- `tests/test_data_health.py`

建议新增页面：

- `GET /data-health`

`/data-health` 要求：

- 需要登录
- 页面只读
- 不修改数据库
- 不删除任何数据
- 不自动修复
- 不请求外部网络
- 没有问题时显示健康状态
- 有问题时显示摘要和明细

---

## 四、检查项目

至少检查以下问题：

### 1. 条目基础检查

检查：

- 空标题条目
- rating 超出允许范围
- status 不在允许状态中
- 创建时间 / 更新时间缺失或异常
- extra JSON 异常，若项目中存在该字段

要求：

- 只报告问题
- 不修改条目
- 不删除条目

---

### 2. 关系完整性检查

检查：

- item_tags 中 item 不存在
- item_tags 中 tag 不存在
- item_creators 中 item 不存在
- item_creators 中 creator 不存在
- item_collections 中 item 不存在
- item_collections 中 collection 不存在

要求：

- 只报告孤立关系
- 不删除关系
- 不删除条目
- 不删除标签 / 创作者 / 合集

---

### 3. 重复关系检查

检查：

- 同一个 item 重复关联同一个 tag
- 同一个 item 重复关联同一个 creator
- 同一个 item 重复关联同一个 collection

要求：

- 只报告重复关系
- 不自动去重
- 不自动删除

---

### 4. saved views 检查

检查：

- saved view 名称为空
- saved view query_string 为空或异常
- query_string 包含未知参数
- query_string 包含 page / next / redirect / 外部 URL 等不应保存的参数

要求：

- 只报告问题
- 不自动修改 saved view
- 不删除 saved view

---

### 5. item activity 检查

检查：

- item_activity 指向不存在的 item
- view_count / edit_count 为负数
- last_viewed_at / last_edited_at 异常

要求：

- 只报告问题
- 不自动清理 activity

---

## 五、健康报告展示

`/data-health` 页面展示：

- 总体状态：健康 / 有警告 / 有问题
- 问题总数
- 按类型分组的问题数量
- 问题明细
- 影响对象类型
- 影响对象 id
- 简短说明
- 建议用户先做 JSON 备份
- 后续修复入口占位说明，可选

要求：

- 不展示完整异常堆栈
- 长文本不能撑破布局
- 移动端可用
- 中文 / English 文案覆盖

---

## 六、安全边界

必须遵守：

- 本轮所有检查只读
- GET /data-health 不能写数据库
- 不允许自动修复
- 不允许自动删除
- 不允许自动合并
- 不允许自动导入
- 不允许执行任意 SQL
- 不允许请求外部网络
- 不允许读取站外 URL
- 不允许引入第三方统计或分析

---

## 七、入口与导航

新增数据健康检查入口：

- 登录后导航中增加数据健康入口，或放入工作台快捷入口
- README 中说明入口位置
- REVIEW 中增加审查项

要求：

- 不破坏现有导航
- 不破坏语言切换
- 不破坏登录 / 登出
- 不影响 saved views / activity / cleanup / duplicates

---

## 八、i18n 文案

新增中文 / English 文案，至少覆盖：

- 数据健康
- 数据健康检查
- 健康
- 有警告
- 有问题
- 问题总数
- 问题明细
- 条目问题
- 关系问题
- 重复关系
- saved views 问题
- activity 问题
- 孤立关系
- 空标题
- 无效评分
- 无效状态
- 未知参数
- 建议先备份
- 本页只读
- 暂无数据问题
- 返回工作台

要求：

- zh 和 en 的 key 集合保持一致
- 不翻译 API 字段名
- 不翻译 NSFWTrack
- 不破坏已有 i18n 测试

---

## 九、测试要求

请新增或更新测试，至少覆盖：

1. 未登录访问 `/data-health` 跳转登录
2. 登录后 `/data-health` 可以正常渲染
3. 健康数据时显示无问题状态
4. 空标题条目能被报告
5. 无效 rating 能被报告
6. 无效 status 能被报告
7. 孤立 item_tags 能被报告
8. 孤立 item_creators 能被报告
9. 孤立 item_collections 能被报告
10. 重复 item_tags 能被报告
11. 重复 item_creators 能被报告
12. 重复 item_collections 能被报告
13. saved view 未知参数能被报告
14. saved view 中 page / next / redirect 能被报告
15. item_activity 指向不存在 item 能被报告
16. view_count / edit_count 为负数能被报告
17. `/data-health` 不修改数据库
18. `/data-health` 不删除任何业务数据
19. 中文文案正常
20. English 文案正常
21. i18n key 覆盖测试仍通过
22. 现有 saved views / activity / cleanup / duplicates / backup / import / filters / bulk edit / login 测试仍通过

测试注意：

- 不写依赖 CSS 像素的脆弱测试
- 必须测试只读
- 必须测试不会删除业务数据
- 必须测试旧功能回归

---

## 十、文档更新

完成后更新：

- README.md
- TASKS.md
- REVIEW.md
- CHANGELOG.md
- PLAN.md，如需要

要求：

- README 增加数据健康检查说明
- README 说明本轮只读，不会自动修复
- README 说明发现问题后建议先做 JSON 备份
- TASKS.md 增加并标记 Phase 2-F1 完成项
- REVIEW.md 增加数据健康检查审查项
- CHANGELOG.md 写入 Unreleased
- 不写入 v0.1.0 到 v0.6.0 已发布版本段
- 不修改已发布 tag
- 不创建 GitHub Release

---

## 十一、验收要求

完成后运行 `RULE.md` 中的验收命令。

要求：

- 所有测试通过
- Docker build 通过
- Docker Compose 能启动
- `/login` GET 返回 200
- 启动后正常 down
- 不因为本轮改动破坏 CI

---

## 十二、完成后汇报格式

完成后按以下格式汇报：

1. 修改文件
2. 新增文件
3. 是否新增环境变量
4. 是否修改数据库结构
5. 是否新增数据库表
6. 是否新增依赖
7. 是否新增业务功能
8. 测试结果
9. 实际测试命令
10. Docker build 是否通过
11. Docker compose 是否能启动
12. `/login` GET 状态码
13. 当前 git diff 概要
14. 是否触碰 REVIEW.md 的超范围项
15. 数据健康检查服务如何实现
16. 条目基础检查如何实现
17. 关系完整性检查如何实现
18. 重复关系检查如何实现
19. saved views 检查如何实现
20. item activity 检查如何实现
21. `/data-health` 页面如何实现
22. 如何保证只读不修改数据库
23. 如何保证不删除业务数据
24. i18n 是否仍通过
25. README / TASKS / REVIEW / CHANGELOG / PLAN 更新了什么
26. 是否已提交并推送
27. 下一步建议
