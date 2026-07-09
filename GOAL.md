# GOAL.md

# 当前目标：Phase 2-D2 标签 / 创作者 / 合集清理与合并

请先读取 `RULE.md`，再执行本文件。  
本轮所有开发必须遵守 `RULE.md`。

---

## 一、目标

新增本地元数据清理能力：

- 重复标签检测与合并
- 重复创作者检测与合并
- 重复合集检测与合并

本轮只做本地手动合并，不做 AI、不做自动批量合并、不做外部查询。

---

## 二、建议新增内容

建议新增：

```text
app/services/metadata_cleanup.py
app/templates/cleanup.html
app/templates/cleanup_compare.html
tests/test_metadata_cleanup.py

建议新增页面：

/cleanup
/cleanup/compare

/cleanup/compare 支持：

type=tag
type=creator
type=collection
primary_id
duplicate_id
三、重复检测规则

检测范围：

tags
creators
collections

支持两种规则：

exact_name
name 去除首尾空格后完全相同
normalized_name
Unicode NFKC
去除首尾空格
casefold
连续空白折叠为单个空格

检测只生成候选，不修改数据库，不自动合并。

四、清理候选页

/cleanup 页面展示：

重复标签候选
重复创作者候选
重复合集候选
匹配类型
匹配 key
对象名称
关联条目数量
对比 / 合并入口
空状态

页面需要登录，只读，不自动修改数据。

五、对比页

/cleanup/compare 页面展示：

类型：tag / creator / collection
primary 对象
duplicate 对象
名称
关联条目数量
关联条目预览
合并危险提示
合并前备份提示
合并按钮

要求：

非法 type 不 500
primary 不存在不 500
duplicate 不存在不 500
primary_id == duplicate_id 时拒绝
合并必须 POST
合并必须 confirm
不允许 GET 合并
六、合并策略
标签合并
保留 primary tag
删除 duplicate tag
duplicate 关联条目转移到 primary
已有关联不重复创建
不删除任何条目
创作者合并
保留 primary creator
删除 duplicate creator
duplicate 关联条目转移到 primary
已有关联不重复创建
不删除任何条目
合集合并
保留 primary collection
删除 duplicate collection
duplicate 内条目转移到 primary
已有关联不重复创建
不删除任何条目

合集 description 处理：

primary description 为空，duplicate 非空：复制 duplicate
双方都有且不同：默认保留 primary
用户明确选择时，才允许用 duplicate 覆盖
七、结果摘要

合并完成后显示：

合并类型
primary 名称
duplicate 名称
转移关联数量
跳过重复关联数量
duplicate 是否删除
collection description 如何处理

不要只显示“合并成功”。

八、导航入口

新增清理入口：

登录后导航显示“数据清理”
标签页可进入清理页
创作者页可进入清理页
合集页可进入清理页

不要破坏移动端导航。

九、i18n

新增中文 / English 文案，至少覆盖：

数据清理
元数据清理
重复标签
重复创作者
重复合集
名称完全匹配
名称归一化匹配
没有重复元数据
对比元数据
保留对象
将被删除的对象
合并标签
合并创作者
合并合集
合并前请备份
合并后重复对象会被删除
转移关联
跳过重复关联
合并成功
合并失败
非法清理类型
不能合并同一对象
description 冲突
十、测试

至少覆盖：

未登录访问 /cleanup 跳转登录
清理页可正常渲染
无重复候选空状态
标签 exact / normalized 检测
创作者 exact / normalized 检测
合集 exact / normalized 检测
对比页正常渲染
非法 type 不 500
primary / duplicate 不存在不 500
primary_id == duplicate_id 拒绝
合并必须 POST
标签合并转移关联并删除 duplicate
创作者合并转移关联并删除 duplicate
合集合并转移关联并删除 duplicate
合并不会删除条目
重复关系不会重复创建
合集 description 冲突默认保留 primary
用户选择后可覆盖 description
i18n 仍通过
旧功能全量回归通过
十一、文档

更新：

README.md
TASKS.md
REVIEW.md
CHANGELOG.md

CHANGELOG 写入 Unreleased，不要修改已发布版本段。

十二、完成后汇报

完成后按以下格式汇报：

修改文件
新增文件
是否新增依赖
是否修改数据库结构
测试结果
Docker 验收结果
提交 hash
清理检测规则
标签 / 创作者 / 合集合并策略
是否确认不会删除条目
是否确认不会自动合并
i18n 是否通过
是否已提交推送
下一步建议
