# GOAL.md

# 当前目标：Phase 2-I2 查询优化与分页收敛

请先读取 `RULE.md`、`PLAN.md`、`PERFORMANCE.md`。
长期边界以 `RULE.md` 为准，I1 基线以 `PERFORMANCE.md` 为准。

---

## 一、目标

针对 I1 已确认的问题优化现有查询：

- 降低 items 页查询放大
- 降低 metadata cleanup 查询放大
- 消除 collection detail 的 N+1
- 限制无界列表和明细加载
- 减少重复 settings 查询
- 优化 stats 和 data-health 的重复扫描

本轮只修改查询、加载策略和分页逻辑。

---

## 二、禁止项

本轮不得：

- 新增索引
- 修改表或字段
- 提升 schema 版本
- 编写生产迁移
- 新增依赖
- 引入缓存、后台任务或外部服务
- 修改默认 schema 2 数据卷

如果确认必须新增索引才能继续，停止实现并在报告中说明，不要自行修改 schema。

---

## 三、优先优化范围

### P0

#### Items 列表

- 避免为当前页之外的条目加载关系
- 避免重复加载 tag / creator / collection / state
- 保持现有筛选、排序、分页、saved views 和批量编辑行为
- 不允许为降低查询数而改变返回结果

#### Metadata cleanup

- 避免一次性加载全部关系对象
- 候选页只获取展示所需字段和计数
- 对比页按需加载具体对象
- 不改变重复检测和合并逻辑

### P1

#### Collection detail

- 消除逐条查询 collection 的 N+1
- 合集条目保持分页或明确上限
- 可选条目列表必须分页、搜索或限制数量
- 不改变合集成员关系

#### Metadata 页面和 duplicates

- tags / creators / collections 列表增加合理分页
- duplicates 候选避免无界展示
- 保持现有筛选、合并和确认逻辑

### P2

- 合并同一请求中的重复 settings 查询
- 减少 stats 对相同表的重复扫描
- data-health 明细设置安全上限，并显示截断提示
- 不隐藏问题总数，只限制页面明细数量

---

## 四、兼容要求

必须保持：

- URL 参数兼容
- saved views 兼容
- 中英文兼容
- 现有排序结果
- 现有分页语义
- 登录、POST、confirm 和 rollback
- 备份、导入、清理及合并行为
- API / CSV / JSON 字段不变

---

## 五、性能验收

优化后重新运行 I1 的三档基线：

- 100 items
- 1,000 items
- 10,000 items

重点比较：

- items / filtered_items
- cleanup
- collection_detail
- tags / creators / collections
- duplicates
- stats
- data-health
- settings 查询次数

要求：

- collection detail 不再出现逐条 N+1
- items 与 cleanup 查询数明显低于 I1
- 查询数不能随当前页条目数线性增加
- workbench / activity / saved views 等原本有界路径不能退化
- 不使用固定毫秒数作为测试阈值
- 将新旧结果写入 `PERFORMANCE.md`

---

## 六、测试

至少覆盖：

- items 结果与优化前一致
- items 分页只加载当前页所需数据
- collection detail 无 N+1
- 合集可选条目有分页或上限
- cleanup 候选结果保持一致
- metadata 列表分页正常
- duplicates 不再无界加载
- data-health 总数准确且明细可截断
- settings 不在同一请求中重复查询
- saved views、筛选、排序、批量编辑不回归
- 全量测试和性能审计通过

---

## 七、文档与验收

更新：

- `PERFORMANCE.md`
- `README.md`
- `TASKS.md`
- `REVIEW.md`
- `CHANGELOG.md`
- `PLAN.md`

要求：

- CHANGELOG 只写 `Unreleased`
- 不修改旧 tag
- 不创建 Release
- 使用隔离数据库和数据卷
- 运行全量测试与 Docker 验收
- 提交并推送到 `origin/main`

---

## 八、完成后汇报

1. 修改 / 新增文件
2. 各 P0 / P1 / P2 问题如何处理
3. collection detail N+1 如何消除
4. 哪些页面新增分页或上限
5. 优化前后查询数对比
6. 是否改变返回结果或业务逻辑
7. 是否需要新增索引或迁移
8. 测试与 Docker 结果
9. `PERFORMANCE.md` 更新
10. 提交 hash
