# GOAL.md

# 当前目标：Phase 2-F2 备份文件校验 / 导入 dry-run 增强

请先读取 `RULE.md`、`PLAN.md`，再执行本文件。
`RULE.md` 是长期通用规则，本文档只描述本轮开发目标。
如果 `RULE.md` 与本文档冲突，以 `RULE.md` 的安全边界为准。

---

## 一、目标

增强本地数据写入前的安全检查能力。

本轮实现：

- JSON 备份文件校验
- 备份恢复 dry-run
- 导入 dry-run 增强
- 校验报告摘要
- 校验问题明细
- 写入前备份提示

本轮只做校验和 dry-run 报告。
本轮不真正恢复备份，不真正导入数据，不修改数据库。

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

本轮只允许：

- 读取上传的本地 JSON / CSV 文件
- 解析文件内容
- 校验结构
- 生成 dry-run 报告
- 不写入数据库

---

## 三、备份文件校验

增强 JSON 备份文件校验能力。

建议新增或增强：

- `app/services/backup_validator.py`
- `tests/test_backup_validator.py`

建议页面入口：

- 复用 `/backup`
- 或新增只读校验入口，例如 `POST /backup/validate`

校验内容至少包括：

- JSON 是否可解析
- 是否为对象结构
- 是否包含受支持的表数据
- 是否包含未知顶层字段
- `items` 结构是否合理
- `tags` 结构是否合理
- `creators` 结构是否合理
- `collections` 结构是否合理
- `saved_views` 结构是否合理
- `item_activity` 结构是否合理
- 关系表数据是否能映射到条目 / 标签 / 创作者 / 合集
- 是否存在重复关系
- 是否存在缺失必填字段
- 是否存在明显非法字段值

要求：

- 校验不写数据库
- 校验不删除任何数据
- 校验失败不展示完整异常堆栈
- 旧版本备份缺少新表时不应被视为致命错误
- 未知字段应作为 warning，而不是直接崩溃
- 文件过大时要有清楚错误或限制提示

---

## 四、备份恢复 dry-run

新增或增强恢复前 dry-run 报告。

dry-run 应展示：

- 预计读取多少条 items
- 预计读取多少 tags
- 预计读取多少 creators
- 预计读取多少 collections
- 预计读取多少 saved views
- 预计读取多少 item_activity
- 预计读取多少关系
- 预计跳过多少无效数据
- 预计有哪些 warning
- 是否建议先做当前数据库 JSON 备份

要求：

- dry-run 不执行恢复
- dry-run 不写入数据库
- dry-run 不修改当前数据
- dry-run 不删除当前数据
- dry-run 不自动创建标签 / 创作者 / 合集
- dry-run 不改变 saved views / activity
- dry-run 只是报告

---

## 五、导入 dry-run 增强

项目已有导入预览能力，本轮只增强安全检查和报告。

增强内容：

- 更清楚地区分 error / warning / info
- 报告将要导入的条目数量
- 报告将要跳过的行数
- 报告缺失字段
- 报告未知字段
- 报告无效 rating / status
- 报告标签 / 创作者字段异常
- 报告重复标题候选，可选
- 明确提示 dry-run 不会写入数据库

要求：

- 不破坏现有 CSV / JSON 导入流程
- 不改变已有导入字段语义
- 不请求外部网络
- 不读取站外 URL
- 不自动修复导入文件
- 不自动创建额外数据，除非用户走现有正式导入流程

---

## 六、报告展示

校验 / dry-run 报告至少包含：

- 总体状态：可继续 / 有警告 / 不建议继续
- error 数量
- warning 数量
- info 数量
- 影响的数据类型
- 影响行号或对象 id
- 简短说明
- 建议操作
- 写入前备份提示

要求：

- 长文本不能撑破布局
- 移动端可用
- 不展示完整异常堆栈
- 中文 / English 文案覆盖

---

## 七、安全边界

必须遵守：

- 本轮所有校验和 dry-run 都只读
- 不允许写数据库
- 不允许删除任何数据
- 不允许自动修复
- 不允许自动导入
- 不允许自动恢复备份
- 不允许自动合并
- 不允许请求外部网络
- 不允许读取站外 URL
- 不允许执行任意 SQL
- 不允许引入第三方分析

---

## 八、i18n 文案

新增中文 / English 文案，至少覆盖：

- 备份校验
- 校验备份文件
- 恢复 dry-run
- 导入 dry-run
- 校验报告
- 可继续
- 有警告
- 不建议继续
- 错误
- 警告
- 信息
- 未知字段
- 缺失字段
- 无效数据
- 文件过大
- JSON 解析失败
- dry-run 不会写入数据库
- 建议先备份当前数据库
- 返回备份页
- 返回导入页

要求：

- zh 和 en 的 key 集合保持一致
- 不翻译 API 字段名
- 不翻译 NSFWTrack
- 不破坏已有 i18n 测试

---

## 九、测试要求

请新增或更新测试，至少覆盖：

1. 未登录访问备份校验入口跳转登录
2. 登录后可以提交 JSON 备份校验
3. 非 JSON 文件或非法 JSON 能显示错误
4. 空 JSON / 非对象 JSON 能显示错误
5. 旧版本备份缺少 saved_views / item_activity 不失败
6. 未知顶层字段显示 warning
7. 缺失必填字段能报告
8. 无效 rating / status 能报告
9. 孤立关系能报告
10. 重复关系能报告
11. saved_views 异常参数能报告
12. item_activity 缺失 item 能报告
13. dry-run 不写入数据库
14. dry-run 不删除任何业务数据
15. 导入 dry-run 能报告行数 / 错误 / 警告
16. 导入 dry-run 不破坏现有正式导入流程
17. 中文文案正常
18. English 文案正常
19. i18n key 覆盖测试仍通过
20. 现有 data-health / saved views / activity / cleanup / backup / import / filters / login 测试仍通过

测试注意：

- 必须测试只读
- 必须测试旧备份兼容
- 必须测试不会删除业务数据
- 不写依赖 CSS 像素的脆弱测试

---

## 十、文档更新

完成后更新：

- README.md
- TASKS.md
- REVIEW.md
- CHANGELOG.md
- PLAN.md，如需要

要求：

- README 增加备份校验 / dry-run 说明
- README 说明 dry-run 不会写入数据库
- README 说明正式恢复 / 导入前建议先备份
- TASKS.md 增加并标记 Phase 2-F2 完成项
- REVIEW.md 增加备份校验 / dry-run 审查项
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
15. 备份文件校验如何实现
16. 备份恢复 dry-run 如何实现
17. 导入 dry-run 增强如何实现
18. 校验报告如何展示
19. 如何保证只读不写数据库
20. 如何保证不删除业务数据
21. 旧备份兼容如何处理
22. i18n 是否仍通过
23. README / TASKS / REVIEW / CHANGELOG / PLAN 更新了什么
24. 是否已提交并推送
25. 下一步建议
