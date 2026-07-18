# RULE.md

# NSFWTrack 通用开发规则

本文档是长期规则。每一轮开发都必须遵守。  
`GOAL.md` 只描述当前阶段目标，不能覆盖本文件的安全边界。

---

## 一、项目定位

NSFWTrack 是本地单用户内容管理工具。

项目当前边界：

- 本地部署
- 单用户使用
- SQLite 数据库
- FastAPI 后端
- Jinja2 模板
- HTMX 轻量交互
- Docker Compose 部署
- 中英文界面

---

## 二、外部网络与长期禁止项

外部网络默认禁止。只有当前 `GOAL.md` 明确授权的 Phase 5 adapter 可以
在用户主动提交请求后访问公开元数据接口，而且必须同时满足本节的受控
网络边界。阶段授权不能开放通用 URL 获取能力。

除上述受控 adapter 例外外，禁止实现：

- 任意 URL fetcher 或用户自定义 API base URL
- HTML 页面抓取或爬虫
- 未经当前阶段批准的 adapter
- 远程图片拉取、代理或页面自动加载
- Cookie、Token、登录凭据或浏览器配置读取与保存
- 自动同步、后台刷新或定时请求
- 未经批准的多源搜索
- 随机探索接口
- 推荐系统
- AI 助手
- AI 分析
- 云同步
- 云备份
- 定时任务
- 多用户系统
- 复杂权限系统
- React / Vue / Svelte
- 前端构建流程
- 未经说明的新增依赖

Phase 3 起明确允许的本地来源范围：

- 保存用户主动提供的来源 URL
- 解析用户上传的本地浏览器书签 HTML
- 解析用户上传或粘贴的纯文本 URL 清单

上述范围只允许保存和解析用户提供的数据，不允许为 URL 发起 HTTP
请求、获取远程标题 / 元数据 / 图片，也不允许扩展为爬虫、站点
adapter、自动同步、推荐或 AI 分析。

Phase 5 受控 adapter 必须遵守：

- 只有登录用户主动触发的 POST 可以访问外部网络；GET、页面加载、备份、
  恢复、CSV / JSON 导入、书签导入和 URL 清单导入始终零网络请求
- router 不包含 provider HTTP 逻辑；所有 adapter 只能使用一个共享的
  outbound HTTP service
- provider、HTTPS host、端口和 endpoint path 均由代码固定注册；用户不能
  提供 host、端口、协议、base URL 或任意路径
- 只允许公开、合法、无需账号、Cookie、Token 或其他凭据的元数据接口
- 客户端必须禁用环境代理与 Cookie，限制 DNS / IP、重定向、超时、响应
  大小、Content-Type、分页和并发，并保持 TLS hostname 校验
- 日志不得记录完整查询、响应、敏感 header、签名 token 或用户凭据
- adapter 测试只使用确定性 fixture / mock transport，不请求真实 DNS 或
  provider
- 网络预览与数据库 apply 必须分离；apply 阶段不得再次访问 provider
- 不允许远程图片、HTML 抓取、自动同步、后台任务、推荐、AI 或云同步

新增或启用具体 provider 前，必须由用户批准来源及固定 endpoint。通用
HTTP service 的存在不构成任何 provider 或任意地址的访问授权。

危险操作禁止自动执行，必须由用户手动确认。

---

## 三、数据库规则

默认规则：

- 不新增表
- 不修改已有字段
- 不删除已有字段
- 不破坏旧数据
- 不引入 Alembic

只有 `GOAL.md` 明确允许时，才可以新增表、字段、索引或迁移。

如果修改 Schema，必须确认：

- 使用现有 code-owned migration registry 保持连续升级路径；不能只依赖
  `create_all` 改造旧数据库
- 迁移提供只读 preview、显式 apply、precheck / postcheck 和事务回滚
- 旧数据不被破坏
- 备份 / 恢复 / 导入 / 导出是否需要同步更新
- 测试覆盖旧数据兼容性
- 旧应用对未来 Schema 安全拒绝，rollback 使用升级前已验证副本，不自动降级

---

## 四、数据安全规则

任何删除、合并、恢复、批量操作都必须遵守：

- 必须登录
- 修改操作必须使用 POST
- 不允许 GET 修改数据
- 危险操作必须有 confirm 或明确确认提示
- 删除前必须提示后果
- 批量操作只处理当前页选中项
- 不做跨页全选
- 不做无确认批量修改
- 失败时不能留下明显半写入状态
- 尽量使用事务
- 不展示完整异常堆栈

---

## 五、合并类功能规则

任何合并功能都必须遵守：

- 只产生候选，不自动合并
- 合并必须手动确认
- primary 保留
- duplicate 删除
- 关联关系转移到 primary
- 不删除未参与合并的数据
- 不重复创建关联
- 冲突字段默认保留 primary
- 只有用户明确选择时才可覆盖 primary
- 合并前提示建议备份
- 合并结果必须有摘要

---

## 六、备份 / 导入规则

备份、恢复、导入、导出必须遵守：

- 只处理本地文件
- 允许导入用户提供的本地书签 HTML 和纯文本 URL 清单
- URL 导入只保存用户提供的值，不请求 URL 指向的资源
- 不请求外部网络
- 旧备份尽量保持兼容
- 旧 CSV / JSON 导入尽量保持兼容
- 预览不能写入数据库
- 恢复默认追加 / 合并，不覆盖删除现有数据
- 坏数据应跳过并记录错误，不能 500
- 结果摘要必须说明数量

---

## 七、i18n 规则

所有新增页面和文案必须支持：

- 中文
- English

要求：

- zh / en key 保持对称
- 不翻译 API 字段名
- 不翻译 CSV / JSON 字段名
- 不翻译 NSFWTrack
- `tests/test_i18n.py` 必须通过

---

## 八、UI 规则

前端保持轻量：

- 使用 Jinja2
- 使用 HTMX
- 使用现有 CSS
- 不引入大型前端框架
- 不引入构建流程
- 移动端不能明显横向溢出
- 长文本要能换行或局部滚动
- 危险操作按钮要有明确样式

---

## 九、文档规则

每轮完成后更新：

- README.md
- TASKS.md
- REVIEW.md
- CHANGELOG.md

要求：

- 新内容写入 CHANGELOG 的 Unreleased
- 不写入已发布版本段
- 不修改 v0.1.0 / v0.2.0 / v0.3.0 / v0.4.0 tag
- 不创建 GitHub Release，除非用户明确要求发布

---

## 十、验收命令

普通功能阶段按风险逐级验收：

```bash
targeted tests
related regression tests
.venv/bin/python -m pip check
git diff --check
```

- 只有 Schema、备份、跨模块大型阶段、集成冻结、发布候选或云端复核明确
  要求时才运行本地全量 pytest
- 只有风险需要时才运行使用独立临时目录或隔离数据卷的 Docker 验收；不得
  使用既有 `data/`
- 每个实现阶段提交推送后，必须等待 GitHub Actions 的 `test` 与
  `Docker production smoke`，再进行云端 diff 复核
- Actions 或云端复核发现问题时，由当前开发与复核流程继续定位；不得借此
  提前调用 Hermes
- Hermes 只允许在当前目标版本全部功能完成、所有普通阶段云端复核通过且
  完整集成冻结后执行一次最终独立验收
- Phase 5 的规划、N1-N7、corrective 和 I1 阶段均不得调用 Hermes；仅
  Phase 5-R1 可以在全部前置门禁满足后调用一次
- tag、Release 与部署只在当前 `GOAL.md` 明确授权的发布或部署阶段执行
