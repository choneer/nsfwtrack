# GOAL.md

# NSFWTrack 当前开发目标

本轮开发目标：
在保持 Phase 1 本地 MVP 边界不变的前提下，新增本地数据导出与备份恢复功能。

---

## 一、必须遵守的项目边界

NSFWTrack 是项目名称。

Phase 1 严格限定为：

> 本地单用户内容记录器 / 收藏管理器 MVP。

本轮只允许实现：

* 本地数据 JSON 导出
* 本地数据 CSV 导出
* 本地 JSON 备份恢复
* 备份 / 导出页面
* 相关测试
* README / TASKS / REVIEW 文档更新

本轮禁止实现：

* 外部内容源
* 爬虫
* adapter
* 远程图片拉取
* cookie / token 管理，登录 session 和语言偏好 session 除外
* 自动同步
* 多源搜索
* 随机探索接口
* 推荐系统
* AI 助手

如果开发中发现上述超范围内容，不要实现，直接跳过并说明原因。

---

## 二、本轮新增功能：数据导出

请新增本地数据导出功能。

要求：

1. 支持 JSON 导出。
2. 支持 CSV 导出。
3. 导出内容只来自本地 SQLite 数据库。
4. 不允许请求任何外部地址。
5. 导出接口必须要求登录。
6. 导出数据应包含：

   * items
   * tags
   * creators
   * item_tags
   * item_creators
   * user_item_states
7. JSON 导出应尽量完整，适合作为备份。
8. CSV 导出可以优先导出 items 主表，并包含标签、创作者、状态等可读字段。
9. 导出文件名建议包含日期时间，例如：

   * `nsfwtrack-backup-YYYYMMDD-HHMMSS.json`
   * `nsfwtrack-items-YYYYMMDD-HHMMSS.csv`

---

## 三、本轮新增功能：备份恢复

请新增 JSON 备份恢复功能。

要求：

1. 只支持恢复由本项目导出的 JSON 备份。
2. 恢复入口必须要求登录。
3. 恢复前需要做基本格式校验。
4. 恢复失败时不能破坏现有数据库。
5. 恢复逻辑需要尽量使用事务。
6. 第一版可以采用“追加 / 合并导入”策略，不必实现覆盖整个数据库。
7. 如果遇到重复数据，应尽量按唯一字段跳过或更新，不要制造大量重复记录。
8. 不允许从 URL 恢复，只允许上传本地 JSON 文件。

---

## 四、页面要求

请新增或完善一个页面：

* `/backup`
* 或在现有导入页面中增加“导出 / 备份恢复”区域

页面需要包含：

1. JSON 导出按钮。
2. CSV 导出按钮。
3. JSON 备份上传入口。
4. 简单说明：导出和恢复仅处理本地数据。
5. 中文 / English 文案都需要接入 i18n。
6. 导航栏中增加“备份”入口，或在导入页面增加明显入口。

---

## 五、建议实现方式

可以新增：

* `app/services/exporter.py`
* `app/services/backup.py`
* `app/routers/backup.py`
* `app/templates/backup.html`
* `tests/test_backup.py`

也可以在现有 import/export 结构中实现，但请保持代码清晰。

---

## 六、测试要求

请新增或更新测试，至少覆盖：

1. 未登录访问导出接口应失败。
2. 登录后 JSON 导出成功。
3. 登录后 CSV 导出成功。
4. JSON 导出结构包含核心表数据。
5. 上传合法 JSON 备份可以恢复 / 合并数据。
6. 上传非法 JSON 不应破坏数据库。
7. 中英文备份页面都能正常渲染。

---

## 七、文档更新

完成后请同步更新：

1. `README.md`
2. `TASKS.md`
3. `REVIEW.md`

更新要求：

* README 写明如何导出 JSON / CSV。
* README 写明如何上传 JSON 备份恢复。
* TASKS.md 增加并勾选本轮完成项。
* REVIEW.md 增加备份恢复审查项：

  * 是否要求登录
  * 是否只处理本地文件
  * 是否没有外部 URL 请求
  * 恢复失败是否不会破坏现有数据库

---

## 八、验收命令

完成后运行：

```bash
python -m pytest
docker compose build
docker compose up -d
docker compose down
```

如果命令失败，请输出失败原因和相关日志摘要。

---

## 九、输出要求

完成后请输出：

1. 修改了哪些文件
2. 新增了哪些文件
3. 测试是否通过
4. Docker build 是否通过
5. Docker compose 是否能启动
6. 当前 git diff 概要
7. 是否触碰 `REVIEW.md` 的超范围项
8. 备份 / 导出功能如何使用
9. 下一步建议
