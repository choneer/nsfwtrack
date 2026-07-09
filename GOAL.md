# GOAL.md

# NSFWTrack 当前开发目标

本轮开发目标：  
进入 Phase 2-C2，在保持项目本地单用户边界不变的前提下，补齐合集 / 清单数据在备份、恢复、导出和导入流程中的支持。

Phase 2-C1 已新增本地合集功能：

- `collections`
- `item_collections`

但当前备份 / 导入流程尚未完整覆盖合集数据。
本轮重点是修复这个数据安全缺口。

本轮重点：

- JSON 备份导出包含合集数据
- JSON 备份导出包含条目-合集关联数据
- JSON 备份预览显示合集数量和关联数量
- JSON 备份恢复支持合集和合集关联
- 旧备份文件仍可恢复
- CSV 导出包含合集字段
- CSV / JSON 导入支持 collections 字段
- 导入预览显示即将创建 / 关联的合集数量
- 导入结果摘要显示合集相关数量
- 中英文文案覆盖
- 测试和文档更新

本轮不做外部内容源，不做 URL 导入，不做爬虫，不做推荐系统，不做 AI 助手。

---

## 一、必须遵守的项目边界

NSFWTrack 是项目名称。

Phase 2-C2 的目标是：

> 让合集 / 清单数据进入本地备份、恢复、导出和导入闭环，避免用户备份恢复后丢失合集关系。

本轮允许实现：

- JSON 备份导出 collections
- JSON 备份导出 item_collections
- JSON 备份预览显示合集数据
- JSON 备份恢复 collections
- JSON 备份恢复 item_collections
- CSV 导出增加合集字段
- CSV 导入支持 collections 字段
- JSON 导入支持 collections 字段
- 导入预览显示合集相关统计
- 导入结果摘要显示合集相关统计
- README / TASKS / REVIEW / CHANGELOG 文档更新
- 相关测试

本轮允许修改：

- 备份 / 恢复 service
- 导入 service
- CSV / JSON 模板下载逻辑
- 导入页面模板
- 备份页面模板
- 统计或文档中相关说明
- i18n 文案
- 相关测试

本轮禁止实现：

- 外部内容源
- URL 导入
- 爬虫
- adapter
- 远程图片拉取
- 自动同步
- 多源搜索
- 随机探索接口
- 推荐系统
- AI 助手
- AI 分析
- 自动生成合集
- 智能推荐合集
- 云端同步
- 云端备份
- 定时任务
- 多用户系统
- 复杂权限系统
- 新增数据库表
- 修改已有数据库字段
- 删除已有数据库字段
- 新增依赖
- Alembic
- React / Vue / Svelte
- 前端构建流程
- 修改 v0.1.0 tag
- 修改 v0.2.0 tag
- 修改 v0.3.0 tag
- 创建新的 GitHub Release

如果发现上述超范围内容，不要实现，直接跳过并说明原因。

---

## 二、本轮任务 1：确认现有备份 / 导入结构

开始实现前，请先检查当前项目中已有的：

- JSON 备份导出结构
- JSON 备份恢复逻辑
- JSON 备份预览逻辑
- CSV 导出结构
- CSV 导入结构
- JSON 导入结构
- 导入预览逻辑
- 导入结果摘要结构

要求：

1. 不要破坏旧备份格式。
2. 不要让旧 JSON 备份恢复失败。
3. 新增字段应尽量向后兼容。
4. 旧备份中没有 `collections` 时，应按空合集处理。
5. 旧备份中没有 `item_collections` 时，应按无合集关联处理。
6. 旧 CSV 文件中没有合集字段时，导入仍应正常。
7. 旧 JSON 导入文件中没有合集字段时，导入仍应正常。

---

## 三、本轮任务 2：JSON 备份导出支持合集数据

请增强 JSON 备份导出。

导出的 JSON 备份应包含：

1. collections
2. item_collections

建议结构可以是以下任一方式，但必须清晰、可恢复：

### 方案 A：独立 collections + item_collections

```json
{
  "collections": [
    {
      "id": 1,
      "name": "Example collection",
      "description": "Example description",
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "item_collections": [
    {
      "item_id": 1,
      "collection_id": 1
    }
  ]
}
```

### 方案 B：collections 内嵌 item 引用

```json
{
  "collections": [
    {
      "name": "Example collection",
      "description": "Example description",
      "items": ["Example item title"]
    }
  ]
}
```

要求：

- 优先选择更适合当前项目已有备份结构的方案。
- 备份中可以包含原始 id，但恢复时不要盲目信任目标数据库中的 id 一定相同。
- 恢复时应建立安全映射。
- 合集名称必须保留。
- 合集描述必须保留。
- 条目-合集关联必须可恢复。
- 不要导出任何外部数据源信息。
- 不要请求外部网络。
- 不要改变已有条目 / 标签 / 创作者 / 状态备份能力。

---

## 四、本轮任务 3：JSON 备份预览支持合集数据

请增强备份预览。

预览至少显示：

1. 备份中的合集数量
2. 备份中的条目-合集关联数量
3. 即将创建的合集数量
4. 即将跳过或合并的合集数量
5. 可恢复的合集关联数量
6. 无法恢复的合集关联数量

无法恢复的合集关联包括：

- 关联的条目不存在
- 关联的合集不存在
- 备份引用格式无效
- 数据不完整

要求：

- 预览不写入数据库。
- 预览旧备份文件不应报错。
- 预览没有 collections 的备份时，应显示 0 或合理空状态。
- 错误提示应可读。
- 不要显示完整异常堆栈。
- 中文 / English 文案覆盖。

---

## 五、本轮任务 4：JSON 备份恢复支持合集数据

请增强 JSON 备份恢复。

恢复要求：

1. 可以恢复 collections。
2. 可以恢复 item_collections。
3. 旧备份没有合集数据时仍可恢复。
4. 合集名称为空时跳过并记录错误。
5. 重复合集名称时按现有策略合并或跳过，但不要创建重复合集。
6. 恢复合集关联时，不应重复创建关联。
7. 关联目标条目不存在时，应跳过该关联并记录错误。
8. 关联目标合集不存在时，应跳过该关联并记录错误。
9. 恢复过程不能因为单条坏数据导致整体 500。
10. 恢复结果摘要应包含合集相关数量。
11. 删除合集不会删除条目的规则不能被破坏。
12. 不实现覆盖式恢复。
13. 不删除用户现有数据。
14. 尽量使用事务。
15. 失败时不要留下明显半写入脏数据。

恢复结果摘要至少包含：

- 恢复 / 创建合集数量
- 跳过合集数量
- 创建条目-合集关联数量
- 跳过条目-合集关联数量
- 合集相关错误数量

---

## 六、本轮任务 5：CSV 导出支持合集字段

请增强 CSV 导出。

CSV 导出应增加一个字段：

```text
collections
```

字段规则：

- 一个条目属于多个合集时，使用分号分隔。
- 没有关联合集时为空。
- CSV 表头不要翻译。
- 不要破坏已有 CSV 字段。
- 旧测试中依赖原字段时，应更新测试以包含新字段。
- 中文 / English 页面文案可说明该字段用途。

示例：

```csv
title,summary,status,rating,note,tags,creators,collections,extra
Example item,Example summary,planned,4,Example note,tag1;tag2,creator1,collection1;collection2,"{""source"":""manual""}"
```

---

## 七、本轮任务 6：CSV 导入支持 collections 字段

请增强 CSV 导入。

CSV 导入应支持字段：

```text
collections
```

规则：

1. 多个合集使用分号分隔。
2. 合集名称 trim。
3. 空合集名称忽略。
4. 不存在的合集可以自动创建。
5. 已存在的合集直接关联。
6. 重复合集名称不要重复创建。
7. 同一条目重复关联同一合集时不要重复创建关系。
8. collections 字段可选。
9. 旧 CSV 没有 collections 字段时仍可导入。
10. 预览时显示即将创建的合集数量。
11. 预览时显示即将创建的条目-合集关联数量。
12. 导入结果摘要显示合集创建 / 关联数量。
13. 无效 collections 格式不应导致 500。

注意：

- 这里允许“从导入文件中创建合集”，因为这是用户本地上传的导入数据，不是外部源。
- 不允许 URL 导入。
- 不允许外部数据源。
- 不允许自动从网络补全合集信息。

---

## 八、本轮任务 7：JSON 导入支持 collections 字段

请增强 JSON 导入。

单个 item 建议支持：

```json
{
  "title": "Example item",
  "summary": "Example summary",
  "status": "planned",
  "rating": 4,
  "note": "Example note",
  "tags": ["example"],
  "creators": ["Example creator"],
  "collections": ["Example collection"],
  "extra": {
    "source": "manual"
  }
}
```

规则：

1. `collections` 可选。
2. `collections` 必须是数组；如果不是数组，应作为错误行处理。
3. 数组元素应为字符串。
4. 空字符串忽略。
5. 不存在的合集可以自动创建。
6. 已存在合集直接关联。
7. 重复合集不要重复创建。
8. 重复关联不要重复创建。
9. 预览时显示合集相关统计。
10. 确认导入时写入合集和关联。
11. 旧 JSON 导入文件没有 collections 字段时仍可导入。
12. 不允许 URL 导入。
13. 不允许外部数据源。

---

## 九、本轮任务 8：导入模板更新

请更新 CSV / JSON 导入模板。

CSV 模板字段应包含：

```text
title,summary,status,rating,note,tags,creators,collections,extra
```

JSON 模板 item 示例应包含：

```json
"collections": ["Example collection"]
```

要求：

- 模板下载需要登录。
- 模板不包含外部 URL。
- 模板不包含真实敏感信息。
- 字段名不要翻译。
- 页面说明支持中文 / English。

---

## 十、本轮任务 9：导入预览增强

请增强导入预览。

预览新增显示：

1. 即将创建的合集数量
2. 即将关联的合集关系数量
3. collections 字段错误数量
4. 前 5 条预览数据中显示合集信息
5. 错误行中显示 collections 相关错误

要求：

- 预览不写入数据库。
- 预览 CSV / JSON 都支持。
- 旧文件没有 collections 字段时不报错。
- collections 字段错误不应导致 500。
- 部分错误行时仍只导入有效行。
- 全部错误时禁止确认导入。
- 中文 / English 文案覆盖。

---

## 十、本轮任务 10：导入结果摘要增强

请增强导入完成后的结果摘要。

新增统计：

1. 创建合集数量
2. 关联合集数量
3. 跳过合集数量
4. collections 字段错误数量

要求：

- 不要只显示“导入成功”。
- 没有合集数据时显示 0 或不显示混乱内容。
- 有错误时提示查看错误行。
- 中文 / English 文案覆盖。
- 不破坏已有 tag / creator / state / item 统计。

---

## 十一、本轮任务 11：备份页面文案更新

请更新备份页面说明。

要求明确说明：

1. JSON 备份包含条目数据。
2. JSON 备份包含标签和创作者数据。
3. JSON 备份包含状态 / 评分 / 短评数据。
4. JSON 备份包含合集数据。
5. JSON 备份包含条目-合集关联。
6. CSV 导出包含 collections 字段。
7. JSON 恢复会合并合集，不会覆盖删除现有数据。
8. 删除合集不会删除条目。
9. 备份 / 恢复只处理本地数据。
10. 不包含外部数据源。

---

## 十二、本轮任务 12：i18n 文案更新

请补充中文 / English 文案。

至少覆盖：

- 备份包含合集
- 合集备份
- 合集恢复
- 合集关联
- 条目-合集关联
- 恢复合集数量
- 跳过合集数量
- 恢复合集关联数量
- 跳过合集关联数量
- 创建合集数量
- 关联合集数量
- collections 字段
- collections 字段说明
- collections 字段错误
- collections 必须是数组
- collections 只能包含字符串
- CSV collections 字段
- JSON collections 字段
- 即将创建的合集
- 即将关联的合集
- 无法恢复的合集关联
- 旧备份兼容
- 旧导入文件兼容
- 备份恢复不会删除条目
- 本地合集数据

要求：

- `zh` 和 `en` 的 key 集合保持一致。
- 不要把 API / CSV / JSON 字段名翻译掉。
- 不要把 NSFWTrack 翻译掉。
- 不要破坏已有翻译测试。

---

## 十三、本轮任务 13：测试

请新增或更新测试，至少覆盖：

1. JSON 备份导出包含 collections。
2. JSON 备份导出包含 item_collections。
3. JSON 备份预览显示合集数量。
4. JSON 备份预览显示合集关联数量。
5. 旧 JSON 备份没有 collections 时仍可预览。
6. 旧 JSON 备份没有 collections 时仍可恢复。
7. JSON 备份恢复可以创建合集。
8. JSON 备份恢复可以恢复条目-合集关联。
9. JSON 备份恢复重复合集不会重复创建。
10. JSON 备份恢复重复关联不会重复创建。
11. JSON 备份恢复坏关联时跳过并记录错误。
12. CSV 导出包含 collections 字段。
13. CSV 导出条目所属多个合集时使用分号分隔。
14. CSV 导入支持 collections 字段。
15. CSV 导入可自动创建合集。
16. CSV 导入可关联已有合集。
17. CSV 导入重复合集不会重复创建。
18. CSV 导入旧文件没有 collections 字段仍可导入。
19. JSON 导入支持 collections 字段。
20. JSON 导入可自动创建合集。
21. JSON 导入可关联已有合集。
22. JSON 导入 collections 不是数组时进入错误行。
23. JSON 导入 collections 元素不是字符串时进入错误行。
24. 导入预览不写入合集数据。
25. 导入结果摘要包含合集创建 / 关联数量。
26. CSV 模板包含 collections 字段。
27. JSON 模板包含 collections 示例。
28. 备份页面文案说明包含合集数据。
29. 中文文案正常。
30. English 文案正常。
31. i18n key 覆盖测试仍通过。
32. 现有合集 / 筛选 / 批量编辑 / 详情页 / 导入 / 备份 / 统计 / 登录测试仍通过。

测试注意：

- 不要写依赖 CSS 像素的脆弱测试。
- 重点覆盖数据安全和向后兼容。
- 旧备份兼容必须覆盖。
- 预览不写库必须覆盖。
- 重复合集和重复关联必须覆盖。
- 恢复不能删除现有条目必须覆盖。

---

## 十四、文档更新

完成后请同步更新：

1. `README.md`
2. `TASKS.md`
3. `REVIEW.md`
4. `CHANGELOG.md`

要求：

- README 增加 Phase 2-C2 备份 / 导入支持合集数据说明。
- README 说明 JSON 备份包含合集和条目-合集关联。
- README 说明 CSV 导出 / 导入支持 collections 字段。
- README 说明旧备份和旧导入文件仍兼容。
- TASKS.md 增加并标记本轮完成项。
- REVIEW.md 增加合集备份 / 导入审查项。
- CHANGELOG.md 在 `Unreleased` 小节记录本轮改动。
- 不要把本轮内容写进 `v0.1.0` / `v0.2.0` / `v0.3.0` 已发布内容中。
- 不要修改已发布的 tag。
- 不要创建新的 release。

---

## 十五、验收命令

完成后运行：

```bash
.venv/bin/python -m pytest
docker compose build
docker compose up -d
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8000/login"
docker compose down
```

如果当前环境没有 `.venv/bin/python`，可以使用实际可用的 Python，但输出中需要说明实际命令。

要求：

1. 所有测试通过。
2. Docker build 成功。
3. Docker Compose 能启动。
4. `/login` GET 返回 200。
5. 启动后正常 down。
6. 不要因为本轮改动破坏 CI。

---

## 十六、Phase 2-C2 自查

完成后请自查：

1. 是否补齐 JSON 备份 collections。
2. 是否补齐 JSON 备份 item_collections。
3. 是否补齐 JSON 备份恢复 collections。
4. 是否补齐 JSON 备份恢复 item_collections。
5. 是否旧备份仍兼容。
6. 是否旧 CSV / JSON 导入仍兼容。
7. 是否 CSV 导出包含 collections。
8. 是否 CSV 导入支持 collections。
9. 是否 JSON 导入支持 collections。
10. 是否导入预览不写入合集数据。
11. 是否重复合集不会重复创建。
12. 是否重复合集关联不会重复创建。
13. 是否坏关联会跳过并记录错误。
14. 是否恢复不会删除现有条目。
15. 是否没有外部内容源。
16. 是否没有 URL 导入。
17. 是否没有爬虫。
18. 是否没有 adapter。
19. 是否没有远程图片拉取。
20. 是否没有自动同步。
21. 是否没有推荐系统。
22. 是否没有 AI 助手。
23. 是否没有云同步。
24. 是否没有新增数据库表。
25. 是否没有修改已有数据库字段。
26. 是否没有新增依赖。
27. 是否没有引入前端框架。
28. 是否中文 / English 切换仍正常。
29. 是否合集 / 筛选 / 批量编辑 / 详情页 / 导入 / 备份 / 统计等旧功能仍正常。
30. 是否没有修改 v0.1.0 tag。
31. 是否没有修改 v0.2.0 tag。
32. 是否没有修改 v0.3.0 tag。
33. 是否没有创建新的 GitHub Release。

---

## 十七、输出要求

完成后请输出：

1. 修改了哪些文件。
2. 新增了哪些文件。
3. 是否新增环境变量。
4. 是否修改数据库结构。
5. 是否新增数据库表。
6. 是否新增依赖。
7. 是否新增业务功能。
8. 测试是否通过。
9. 实际使用的测试命令。
10. Docker build 是否通过。
11. Docker compose 是否能启动。
12. `/login` GET 状态码。
13. 当前 git diff 概要。
14. 是否触碰 `REVIEW.md` 的超范围项。
15. JSON 备份如何包含合集数据。
16. JSON 备份如何包含条目-合集关联。
17. JSON 备份预览如何显示合集数据。
18. JSON 备份恢复如何恢复合集。
19. JSON 备份恢复如何恢复条目-合集关联。
20. 旧备份如何保持兼容。
21. CSV 导出如何包含 collections 字段。
22. CSV 导入如何支持 collections 字段。
23. JSON 导入如何支持 collections 字段。
24. 导入预览如何显示合集相关统计。
25. 导入结果摘要如何显示合集相关统计。
26. 备份页面文案更新了什么。
27. 重复合集如何避免。
28. 重复关联如何避免。
29. 坏关联如何处理。
30. 是否确认恢复不会删除条目。
31. i18n 是否仍通过。
32. README / TASKS / REVIEW / CHANGELOG 更新了什么。
33. 是否建议提交。
34. 下一步建议。
