# GOAL.md

# NSFWTrack 当前开发目标

本轮开发目标：
在保持 Phase 1 本地 MVP 边界不变的前提下，完成 `v0.1.0` 发布前整理、文档完善、最终自查和版本标记准备。

本轮重点是：

* 整理 Phase 1 功能状态
* 新增或完善 CHANGELOG
* 补充发布说明
* 确认 README、TASKS、REVIEW 一致
* 确认 CI、测试、Docker 仍然可用
* 做一次 v0.1.0 发布前自查

本轮不新增业务功能。

---

## 一、必须遵守的项目边界

NSFWTrack 是项目名称。

Phase 1 严格限定为：

> 本地单用户内容记录器 / 收藏管理器 MVP。

本轮只允许做：

* 文档整理
* 发布说明整理
* CHANGELOG 新增或更新
* README 结构优化
* TASKS 状态确认
* REVIEW 审查项确认
* 版本号 / tag 准备
* 测试、CI、Docker 验证
* Phase 1 最终自查

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
* URL 导入备份
* 云端备份
* 定时备份
* 覆盖式恢复
* 复杂权限系统
* 多用户系统
* 新的大型业务功能

如果开发中发现上述超范围内容，不要实现，直接跳过并说明原因。

---

## 二、本轮任务 1：整理 v0.1.0 功能清单

请在 README 或单独的发布说明中明确 `v0.1.0` 已包含的功能。

至少包括：

1. 单用户登录保护
2. 中文 / English 语言切换
3. 本地条目 CRUD
4. 标签管理
5. 创作者管理
6. 条目状态标记
7. 本地搜索
8. 简单统计
9. CSV / JSON 导入
10. JSON 备份导出
11. CSV 导出
12. JSON 备份恢复
13. 备份恢复前预览
14. 备份上传大小限制
15. Docker Compose 部署
16. SQLite 本地持久化
17. GitHub Actions CI
18. 基础测试覆盖

同时明确：

> v0.1.0 仍然是本地 MVP，不包含外部内容源、爬虫、推荐系统或 AI 助手。

---

## 三、本轮任务 2：新增或更新 CHANGELOG.md

请新增或更新 `CHANGELOG.md`。

要求：

1. 增加 `v0.1.0` 小节。
2. 简要列出 Phase 1 已完成内容。
3. 简要列出当前已知限制。
4. 使用清晰的分类，例如：

   * Added
   * Changed
   * Fixed
   * Security
   * Known limitations

`v0.1.0` 的 Known limitations 至少写明：

* 当前仅支持单用户。
* 当前仅面向局域网 / 本地部署。
* 不建议直接公网暴露。
* 备份恢复是合并恢复，不是覆盖恢复。
* 目前没有外部内容源、爬虫、推荐系统或 AI 助手。
* TestClient warning 当前不影响功能，后续依赖稳定后再处理。

---

## 四、本轮任务 3：README 发布前整理

请检查并优化 `README.md`。

要求 README 至少包含：

1. 项目简介
2. 当前版本状态：`v0.1.0 / Phase 1 MVP`
3. 功能清单
4. 不包含的功能 / 明确边界
5. 本地开发运行方式
6. Docker Compose 部署方式
7. N100 局域网部署说明
8. `.env` 配置说明
9. 数据持久化说明
10. 备份与恢复说明
11. 中文 / English 切换说明
12. 测试和 CI 说明
13. 安全提示
14. 已知限制

README 需要保持简洁清楚，不要写成过长的开发日志。

---

## 五、本轮任务 4：TASKS / REVIEW 状态确认

请检查并同步更新：

1. `TASKS.md`
2. `REVIEW.md`

要求：

* `TASKS.md` 中 Phase 1 已完成项要准确。
* 未完成或后续功能不要误标完成。
* `REVIEW.md` 中继续保留 Phase 1 禁止项。
* `REVIEW.md` 中继续保留备份、i18n、登录、安全、Docker、CI 审查项。
* 不要把 Phase 2 / Phase 3 功能提前写成已实现。

---

## 六、本轮任务 5：版本标记准备

请为 `v0.1.0` 做准备，但不要强制创建 tag，除非用户明确要求。

要求：

1. 检查项目中是否需要版本号字段。
2. 如果已有版本号位置，请更新为 `0.1.0`。
3. 如果没有版本号位置，可以只在 README / CHANGELOG 中标注。
4. 不要引入复杂发布系统。
5. 不要自动发布 package。
6. 不要创建 GitHub Release，除非用户明确要求。

最终输出中请给出建议命令，例如：

```bash
git tag -a v0.1.0 -m "NSFWTrack v0.1.0 Phase 1 MVP"
git push origin v0.1.0
```

但本轮不要擅自执行 tag 操作，除非用户明确要求。

---

## 七、本轮任务 6：发布前自查

请根据 `REVIEW.md` 做一次最终 Phase 1 自查。

至少确认：

1. 是否没有外部内容源。
2. 是否没有爬虫。
3. 是否没有 adapter。
4. 是否没有远程图片拉取。
5. 是否没有自动同步。
6. 是否没有多源搜索。
7. 是否没有随机探索接口。
8. 是否没有推荐系统。
9. 是否没有 AI 助手。
10. 是否没有 URL 导入备份。
11. 是否没有云端备份。
12. 是否没有定时备份。
13. 是否没有多用户系统。
14. 所有主要页面是否需要登录。
15. `.env` 是否未提交。
16. `APP_PASSWORD` 和 `SECRET_KEY` 是否仍来自环境变量。
17. `MAX_BACKUP_UPLOAD_MB` 是否仍可配置。
18. 中英文切换是否正常。
19. 备份预览 / 导出 / 恢复是否正常。
20. Docker Compose 是否能启动。
21. GitHub Actions CI 是否存在。
22. 测试是否通过。

请把自查结果写入本轮输出，不需要新建大型报告文件。

---

## 八、测试要求

请运行完整测试：

```bash
python -m pytest
```

如果当前 shell 没有 `python` 命令，可以使用项目虚拟环境或 `python3`，但输出中要说明实际执行命令。

要求：

1. 所有测试通过。
2. 如仍有 TestClient warning，请确认不影响当前功能。
3. 不要为了消除 warning 引入不稳定依赖或大改测试结构。

---

## 九、Docker 验收

请运行：

```bash
docker compose build
docker compose up -d
docker compose down
```

要求：

1. build 成功。
2. compose 能启动。
3. `/login` 能访问。
4. 启动后正常 down。
5. 不要改变现有端口和数据挂载方式，除非发现明显错误。

---

## 十、GitHub Actions / CI 检查

请检查：

1. `.github/workflows/ci.yml` 是否存在。
2. CI 是否安装 `requirements-dev.txt`。
3. CI 是否运行 `python -m pytest`。
4. 不要引入复杂 CI 流程。

如果能查看本地 git 状态，请确认本轮提交前工作区干净。

---

## 十一、文档更新

本轮完成后请同步更新：

1. `README.md`
2. `TASKS.md`
3. `REVIEW.md`
4. `CHANGELOG.md`

如有必要，可以更新：

5. `GOAL.md`

不要新增大型设计文档，除非确实必要。

---

## 十二、验收命令

完成后运行：

```bash
python -m pytest
docker compose build
docker compose up -d
docker compose down
```

如果命令失败，请输出失败原因和相关日志摘要。

---

## 十三、输出要求

完成后请输出：

1. 修改了哪些文件
2. 新增了哪些文件
3. 是否新增环境变量
4. 测试是否通过
5. Docker build 是否通过
6. Docker compose 是否能启动
7. GitHub Actions / CI 是否仍然正确
8. 当前 git diff 概要
9. 是否触碰 `REVIEW.md` 的超范围项
10. README 更新了哪些内容
11. CHANGELOG 写了哪些内容
12. Phase 1 发布前自查结果
13. 是否建议创建 `v0.1.0` tag
14. 建议的 tag 命令
15. 下一步建议
