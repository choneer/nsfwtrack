# GOAL.md

# 当前目标：Phase 2-D2 标签 / 创作者 / 合集清理与合并

请先读取 `RULE.md`，再执行本文件。  
本轮所有开发必须遵守 `RULE.md`。

`RULE.md` 是长期通用规则，本文档只描述当前阶段目标。

---

## 一、目标

新增本地元数据清理能力：

- 重复标签检测与合并
- 重复创作者检测与合并
- 重复合集检测与合并

本轮只做本地手动合并。

本轮不做：

- AI 同义词识别
- 自动批量合并
- 一键全部合并
- 外部信息查询
- 推荐系统
- 外部内容源
- URL 导入
- 爬虫
- adapter
- 云同步
- 多用户系统

---

## 二、建议新增内容

建议新增文件：

- `app/services/metadata_cleanup.py`
- `app/templates/cleanup.html`
- `app/templates/cleanup_compare.html`
- `tests/test_metadata_cleanup.py`

建议新增页面：

- `/cleanup`
- `/cleanup/compare`

`/cleanup/compare` 支持参数：

- `type=tag`
- `type=creator`
- `type=collection`
- `primary_id`
- `duplicate_id`

本轮不要新增数据库表，不要修改已有数据库字段，不要新增依赖。

---

## 三、重复检测规则

检测范围：

- tags
- creators
- collections

支持两种规则：

### 1. exact_name

规则：

- `name` 去除首尾空格后完全相同

要求：

- 不修改数据库中的原始名称
- 只用于生成候选
- 不自动合并

### 2. normalized_name

归一化规则：

- Unicode NFKC
- 去除首尾空格
- casefold
- 连续空白折叠为单个空格

要求：

- 归一化只用于检测候选
- 不修改数据库中的原始名称
- 不请求外部网络
- 不做 AI 判断
- 不做模糊相似度算法
- 不新增依赖

检测结果必须标明匹配类型：

- `exact_name`
- `normalized_name`

---

## 四、清理候选页

`/cleanup` 页面展示：

- 重复标签候选
- 重复创作者候选
- 重复合集候选
- 匹配类型
- 匹配 key
- 对象名称
- 关联条目数量
- 对比 / 合并入口
- 空状态

要求：

- 需要登录
- 页面只读
- 不自动修改数据
- 没有候选时显示空状态
- 长名称不能撑破布局
- 移动端可用
- 中文 / English 文案覆盖

---

## 五、元数据对比页

`/cleanup/compare` 页面展示：

- 类型：tag / creator / collection
- primary 对象
- duplicate 对象
- 名称
- 关联条目数量
- 关联条目预览
- 合并危险提示
- 合并前备份提示
- 合并按钮

合集类型还需要展示：

- primary description
- duplicate description
- description 冲突提示
- 是否使用 duplicate description 覆盖 primary description 的选项

要求：

- 需要登录
- 非法 type 不 500
- primary 不存在不 500
- duplicate 不存在不 500
- `primary_id == duplicate_id` 时拒绝
- 页面必须清楚说明 duplicate 会被删除
- 合并必须由用户手动提交
- 不允许自动合并
- 不允许批量自动合并

---

## 六、标签合并策略

定义：

- primary tag：保留标签
- duplicate tag：被合并后删除的标签

合并后：

- primary tag 保留
- duplicate tag 删除
- duplicate tag 关联的所有条目转移到 primary tag
- 已有关联不重复创建
- 不删除任何条目
- 不影响其他标签

要求：

- 合并必须 POST
- 合并需要登录
- 合并前必须有浏览器 confirm
- 合并过程尽量事务安全
- primary 不存在时失败
- duplicate 不存在时失败
- primary 和 duplicate 相同时失败
- 合并结果摘要显示转移了多少条关联、跳过了多少重复关联、是否删除 duplicate
- 合并失败时 rollback
- 不允许无确认合并

---

## 七、创作者合并策略

定义：

- primary creator：保留创作者
- duplicate creator：被合并后删除的创作者

合并后：

- primary creator 保留
- duplicate creator 删除
- duplicate creator 关联的所有条目转移到 primary creator
- 已有关联不重复创建
- 不删除任何条目
- 不影响其他创作者

要求与标签合并一致。

---

## 八、合集合并策略

定义：

- primary collection：保留合集
- duplicate collection：被合并后删除的合集

合并后：

- primary collection 保留
- duplicate collection 删除
- duplicate collection 内的所有条目转移到 primary collection
- 已有关联不重复创建
- 不删除任何条目
- 不删除任何标签
- 不删除任何创作者

description 处理规则：

1. primary description 为空，duplicate description 非空：
   - 自动复制 duplicate description 到 primary

2. primary description 非空，duplicate description 也非空且不同：
   - 默认保留 primary
   - 页面提示存在冲突
   - 用户明确选择时，才允许用 duplicate description 覆盖 primary

要求：

- 不要无提示覆盖 primary description
- 合并结果摘要说明 description 如何处理
- 删除 duplicate collection 不得删除条目

---

## 九、合并前确认与安全提示

合并是危险操作，必须有确认。

要求：

- 合并按钮必须有浏览器 confirm
- 页面必须显示危险提示
- 提示说明 duplicate 会被删除
- 提示说明关联条目会转移到 primary
- 提示建议合并前先做 JSON 备份
- 合并操作必须是 POST
- 合并操作需要登录
- 不能通过 GET 执行合并
- 不能自动执行合并
- 不能批量无确认合并

---

## 十、合并结果摘要

合并完成后显示结果摘要。

至少包含：

- 合并类型：标签 / 创作者 / 合集
- 保留对象名称
- 被删除对象名称
- 转移了多少条关联
- 跳过了多少条重复关联
- description 是否复制 / 覆盖 / 保留，仅合集
- duplicate 是否已删除
- 是否建议重新查看清理页

要求：

- 使用 flash message 或结果页
- 不要只显示“合并成功”
- 合并失败时显示清楚错误
- 不要展示完整异常堆栈
- 中文 / English 文案覆盖

---

## 十一、入口与导航

新增元数据清理入口。

要求：

- 登录后导航中有清理入口
- 可以从标签页进入清理页
- 可以从创作者页进入清理页
- 可以从合集页进入清理页
- 移动端导航不应明显挤压
- 不破坏语言切换
- 不破坏登录 / 登出
- 项目名 NSFWTrack 不要翻译

---

## 十二、备份与数据安全提醒

本轮不要求修改备份格式，但必须提醒用户：

- 合并前建议先做 JSON 备份

要求：

- 对比页显示备份建议
- README 说明合并前建议备份
- 不自动创建备份
- 不实现云备份
- 不实现定时备份

---

## 十三、i18n 文案

新增中文 / English 文案，至少覆盖：

- 数据清理
- 元数据清理
- 重复标签
- 重复创作者
- 重复合集
- 重复名称
- 名称完全匹配
- 名称归一化匹配
- 没有重复元数据
- 对比元数据
- 保留对象
- 将被删除的对象
- 合并标签
- 合并创作者
- 合并合集
- 确认合并
- 合并前请备份
- 合并后重复对象会被删除
- 转移关联
- 跳过重复关联
- 合并成功
- 合并失败
- 合并结果
- 非法清理类型
- 非法对象
- 不能合并同一对象
- description 冲突
- 保留主 description
- 使用重复合集 description
- 已删除重复对象

要求：

- zh 和 en 的 key 集合保持一致
- 不要翻译 API 字段名
- 不要翻译 NSFWTrack
- 不要破坏已有翻译测试

---

## 十四、测试要求

请新增或更新测试，至少覆盖：

1. 未登录访问 `/cleanup` 跳转登录
2. 登录后清理页可以正常渲染
3. 没有重复候选时显示空状态
4. 重复标签 exact_name 能检测出来
5. 重复标签 normalized_name 能检测出来
6. 重复创作者 exact_name 能检测出来
7. 重复创作者 normalized_name 能检测出来
8. 重复合集 exact_name 能检测出来
9. 重复合集 normalized_name 能检测出来
10. 唯一对象不会出现在重复候选中
11. 对比页可以正常渲染
12. type 非法时失败但不 500
13. primary_id 不存在时失败但不 500
14. duplicate_id 不存在时失败但不 500
15. primary_id == duplicate_id 时失败
16. 合并操作必须登录
17. 合并必须通过 POST
18. 标签合并能转移 item_tags
19. 标签合并不会重复创建关联
20. 标签合并后 duplicate tag 被删除
21. 创作者合并能转移 item_creators
22. 创作者合并不会重复创建关联
23. 创作者合并后 duplicate creator 被删除
24. 合集合并能转移 item_collections
25. 合集合并不会重复创建关联
26. 合集合并后 duplicate collection 被删除
27. 合集合并不会删除条目
28. 合集 description 冲突默认保留 primary
29. 用户选择覆盖 description 时可以使用 duplicate description
30. 合并结果摘要包含转移数量和跳过数量
31. 中文文案正常
32. English 文案正常
33. i18n key 覆盖测试仍通过
34. 现有重复条目合并 / 合集 / 备份 / 导入 / 筛选 / 批量编辑 / 详情页 / 统计 / 登录测试仍通过

测试注意：

- 不要写依赖 CSS 像素的脆弱测试
- 必须测试合并不会删除条目
- 必须测试 duplicate 元数据对象会被删除
- 必须测试关系不会重复创建
- 必须测试 primary_id == duplicate_id
- 必须测试旧功能回归

---

## 十五、文档更新

完成后更新：

- README.md
- TASKS.md
- REVIEW.md
- CHANGELOG.md

要求：

- README 增加 Phase 2-D2 标签 / 创作者 / 合集清理与合并说明
- README 说明合并前建议先备份
- README 说明第一版只做手动确认合并
- README 说明不会自动批量合并
- TASKS.md 增加并标记本轮完成项
- REVIEW.md 增加元数据清理 / 合并审查项
- CHANGELOG.md 写入 Unreleased
- 不要写入 v0.1.0 / v0.2.0 / v0.3.0 / v0.4.0 已发布版本段
- 不要修改已发布 tag
- 不要创建 GitHub Release

---

## 十六、验收命令

完成后运行 `RULE.md` 中的验收命令。

要求：

- 所有测试通过
- Docker build 通过
- Docker Compose 能启动
- `/login` GET 返回 200
- 启动后正常 down
- 不要因为本轮改动破坏 CI

---

## 十七、完成后汇报格式

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
15. 元数据重复检测规则如何实现
16. 清理候选页如何实现
17. 元数据对比页如何实现
18. 标签合并如何实现
19. 创作者合并如何实现
20. 合集合并如何实现
21. 关系转移如何避免重复
22. 合集 description 冲突如何处理
23. 合并前确认如何实现
24. 合并结果摘要包含什么
25. 是否确认 duplicate 标签 / 创作者 / 合集会被删除
26. 是否确认不会删除条目
27. i18n 是否仍通过
28. README / TASKS / REVIEW / CHANGELOG 更新了什么
29. 是否已提交并推送
30. 下一步建议