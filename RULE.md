# RULE.md

# NSFWTrack 通用开发规则

本文档是长期规则。每一轮开发都必须遵守。  
`GOAL.md` 只描述当前阶段目标，不能覆盖本文件的安全边界。

---

## 一、项目定位

NSFWTrack 是 NSFW-first、local-first、privacy-first、single-user、
self-hosted 的内容收藏、来源聚合、内容获取、状态追踪和个性化发现工具。
长期产品定位与数据分层以 `PRODUCT_VISION.md` 为准。

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

## 二、外部能力与长期安全边界

外部网络和所有远程能力默认禁止。只有当前 `GOAL.md` 明确授权、且用户批准
具体 Provider、认证方式、固定 Host/Endpoint 和用途后，才能通过共享受控
client 执行该阶段定义的请求。阶段授权不能开放通用 URL 获取能力，也不能
覆盖本节的永久禁止项。

### 永久禁止

以下行为在任何阶段都不能由 `GOAL.md` 开放：

- 任意 URL fetcher，或用户自定义 Host、协议、端口、API base URL 和任意路径
- 无限制通用爬虫、整站遍历、递归发现或抓取未知链接
- 绕过登录、年龄验证、付费、订阅、地区、账号权限或其他访问控制
- 伪造授权、利用漏洞或访问用户无权访问的第三方内容
- 窃取账号、密码、Cookie、Token 或浏览器会话
- 从浏览器隐藏提取认证信息
- 在普通日志、异常或普通 JSON 备份中泄漏凭据
- Provider 间共享凭据或越权读取其他 Provider 的凭据
- 隐藏外部请求或隐藏后台网络行为
- 未经确认的大量写入、覆盖或下载
- 默认上传本地收藏、用户记录或推荐偏好
- 未展示差异就自动覆盖用户编辑内容

### 默认拒绝、可由未来阶段明确授权

以下正式能力不是永久禁止项，但在当前 `GOAL.md` 未明确授权时仍然禁止
实现或启用：

- OAuth、API Token、用户名/密码和用户主动提供的 Session Cookie
- Provider-specific 结构化接口或 HTML 解析
- 封面、预览文件和媒体下载
- 第二 Provider 与多来源聚合
- 默认关闭、可见、可控、可撤销的后台同步
- 基于本地数据的推荐和可选 AI
- 下载队列、定时检查和受控后台任务
- 云备份、云同步、多用户和复杂权限
- 未经说明的新依赖、React / Vue / Svelte 或前端构建流程

阶段目标必须分别定义秘密存储、网络、日志、确认、回滚、禁用和测试边界。
长期能力的存在不代表当前版本已实现或已获授权。

Phase 3 起明确允许的本地来源范围：

- 保存用户主动提供的来源 URL
- 解析用户上传的本地浏览器书签 HTML
- 解析用户上传或粘贴的纯文本 URL 清单

上述本地导入范围只允许保存和解析用户提供的数据，不允许为 URL 发起 HTTP
请求或获取远程标题、元数据、图片。获批 Provider Adapter 是独立能力，不能
把用户提供的来源 URL 当作网络授权。

Phase 5 受控 adapter 必须遵守：

- 只有登录用户主动触发的 POST 可以访问外部网络；GET、页面加载、备份、
  恢复、CSV / JSON 导入、书签导入和 URL 清单导入始终零网络请求
- router 不包含 provider HTTP 逻辑；所有 adapter 只能使用一个共享的
  outbound HTTP service
- provider、HTTPS host、端口和 endpoint path 均由代码固定注册；用户不能
  提供 host、端口、协议、base URL 或任意路径
- 认证方式必须由具体 Provider 的阶段目标批准；凭据只在本地按 Provider
  隔离，Adapter 不能读取其他 Provider 的秘密
- 客户端必须禁用未经批准的环境代理与共享 Cookie，限制 DNS / IP、重定向、
  超时、响应大小、Content-Type、分页和并发，并保持 TLS hostname 校验
- 日志不得记录完整查询、响应、敏感 header、签名 token 或用户凭据
- adapter 测试只使用确定性 fixture / mock transport，不请求真实 DNS 或
  provider
- 网络预览与数据库 apply 必须分离；apply 阶段不得再次访问 provider
- 搜索、预览、数据库写入和下载必须分离；写入与下载需要独立明确确认
- Provider-specific HTML、下载、同步、推荐或 AI 只有在独立阶段明确授权后
  才能实现，且不得突破永久禁止项

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
