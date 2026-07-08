# GOAL.md

# NSFWTrack 当前开发目标

本轮开发目标：
修复发布前文档与 CI 配置的格式问题，确保 `README.md`、`CHANGELOG.md`、`TASKS.md`、`REVIEW.md` 和 `.github/workflows/ci.yml` 都具有正常的 Markdown / YAML 结构。

本轮不新增业务功能，不修改核心业务逻辑，只做格式修复、文档可读性恢复和发布前验证。

---

## 一、必须遵守的项目边界

NSFWTrack 是项目名称。

Phase 1 严格限定为：

> 本地单用户内容记录器 / 收藏管理器 MVP。

本轮只允许做：

* Markdown 格式修复
* YAML 格式修复
* README 可读性整理
* CHANGELOG 可读性整理
* TASKS 可读性整理
* REVIEW 可读性整理
* CI workflow 格式修复
* 测试、Docker、CI 验证
* v0.1.0 tag 准备说明

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
* 新业务功能
* 大范围重构

如果开发中发现上述超范围内容，不要实现，直接跳过并说明原因。

---

## 二、本轮任务 1：修复 README.md 格式

请重新整理 `README.md` 的 Markdown 格式。

要求：

1. 恢复正常标题层级。
2. 恢复正常段落换行。
3. 恢复正常列表格式。
4. 恢复正常代码块格式。
5. 确保 GitHub 页面可以正常渲染。
6. 不要删除已有重要内容。
7. 不要新增复杂开发日志。
8. README 仍应保持清晰、简洁、适合 v0.1.0 发布。

README 至少需要保留：

* 项目简介
* 当前状态：`v0.1.0 / Phase 1 MVP`
* 功能清单
* Phase 1 边界 / 不包含的功能
* 本地开发运行方式
* Docker Compose 部署方式
* N100 局域网部署说明
* `.env` 配置说明
* 数据持久化说明
* 备份与恢复说明
* 中文 / English 切换说明
* 测试与 CI 说明
* 安全提示
* 已知限制

---

## 三、本轮任务 2：修复 CHANGELOG.md 格式

请重新整理 `CHANGELOG.md`。

要求：

1. 恢复正常 Markdown 标题。
2. 恢复 `v0.1.0 - 2026-07-08` 小节。
3. 恢复正常分类列表。
4. 至少包含以下分类：

   * Added
   * Changed
   * Fixed
   * Security
   * Known limitations
5. 保留 Phase 1 MVP 的功能说明。
6. 保留已知限制说明。
7. 不要夸大功能，不要写未实现的 Phase 2 / Phase 3 功能。

---

## 四、本轮任务 3：修复 TASKS.md 格式

请重新整理 `TASKS.md`。

要求：

1. 恢复正常标题层级。
2. 恢复正常任务列表。
3. Phase 1 已完成项要准确。
4. 未完成或未来功能不要误标完成。
5. 不要把 Phase 2 / Phase 3 功能提前写成已实现。
6. 保持任务清单适合后续 Hermes 审核和 Codex 开发。

---

## 五、本轮任务 4：修复 REVIEW.md 格式

请重新整理 `REVIEW.md`。

要求：

1. 恢复正常 Markdown 标题。
2. 恢复正常 checklist。
3. 保留 Phase 1 禁止项。
4. 保留登录、安全、i18n、备份恢复、Docker、CI、部署文档审查项。
5. 不要删除关键审查规则。
6. 不要放宽 Phase 1 边界。

REVIEW.md 必须继续明确禁止：

* 外部内容源
* 爬虫
* adapter
* 远程图片拉取
* 自动同步
* 多源搜索
* 随机探索接口
* 推荐系统
* AI 助手
* URL 导入备份
* 云端备份
* 定时备份
* 多用户系统

---

## 六、本轮任务 5：修复 GitHub Actions CI YAML 格式

请检查并修复：

```text
.github/workflows/ci.yml
```

要求：

1. 恢复正常 YAML 换行。
2. 恢复正常 YAML 缩进。
3. workflow 名称保持 `CI`。
4. 触发条件保留：

   * push
   * pull_request
5. 使用 Python 3.12。
6. 安装 `requirements-dev.txt`。
7. 运行：

```bash
python -m pytest
```

8. 不要引入复杂 CI 流程。
9. 不要增加发布、部署、Docker push、自动 tag 或 GitHub Release。

---

## 七、本轮任务 6：发布前验证

完成格式修复后，请运行：

```bash
python -m pytest
docker compose build
docker compose up -d
docker compose down
```

如果当前 shell 没有 `python` 命令，可以使用：

```bash
python3 -m pytest
```

或项目虚拟环境中的 Python，例如：

```bash
.venv/bin/python -m pytest
```

但输出中必须说明实际执行的命令。

要求：

1. 所有测试通过。
2. Docker build 成功。
3. Docker Compose 能启动。
4. `/login` 能访问。
5. 启动后正常 down。
6. 不要因为格式修复破坏 CI。

---

## 八、本轮任务 7：v0.1.0 tag 准备

本轮不要擅自创建 tag，也不要创建 GitHub Release。

完成后只需要输出建议命令：

```bash
git tag -a v0.1.0 -m "NSFWTrack v0.1.0 Phase 1 MVP"
git push origin v0.1.0
```

等待用户确认后再执行。

---

## 九、验收标准

本轮完成后应满足：

1. `README.md` 在 GitHub 上正常渲染。
2. `CHANGELOG.md` 在 GitHub 上正常渲染。
3. `TASKS.md` 在 GitHub 上正常渲染。
4. `REVIEW.md` 在 GitHub 上正常渲染。
5. `.github/workflows/ci.yml` 是正常 YAML 文件。
6. CI 配置仍能运行测试。
7. 没有修改业务逻辑。
8. 没有新增业务功能。
9. 没有触碰 Phase 1 禁止项。
10. 测试和 Docker 验收通过。

---

## 十、输出要求

完成后请输出：

1. 修改了哪些文件。
2. 新增了哪些文件。
3. 是否新增环境变量。
4. 是否修改业务代码。
5. 测试是否通过。
6. 实际使用的测试命令。
7. Docker build 是否通过。
8. Docker compose 是否能启动。
9. CI YAML 是否已恢复正常格式。
10. README / CHANGELOG / TASKS / REVIEW 是否已恢复正常 Markdown 格式。
11. 当前 git diff 概要。
12. 是否触碰 `REVIEW.md` 的超范围项。
13. 是否建议现在创建 `v0.1.0` tag。
14. 建议的 tag 命令。
15. 下一步建议。
