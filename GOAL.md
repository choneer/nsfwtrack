# Phase 5-P2 — 长期产品原则对齐与 v1.2.0 路线重构完成摘要

## 阶段基线

- 起始 SHA：`df90473d827be86b83da4d7d8487fd852fcff35c`
- 阶段性质：纯文档对齐
- 当前稳定版本：`v1.1.0`
- 应用版本：`1.1.0`
- Schema：`4`
- Backup：`nsfwtrack.backup.v2`
- Production Provider Registry：空
- 真实 Provider：无

## 产品定位

NSFWTrack 的长期定位固定为：

```text
NSFW-first
local-first
privacy-first
single-user
self-hosted
```

正式产品方向是以 NSFW 内容收藏、来源聚合、内容获取、状态追踪和个性化发现
为核心的自托管应用。普通全年龄内容只依靠通用模型自然兼容，不主导 Provider
选择、数据模型或版本路线。

长期基线见 `PRODUCT_VISION.md`，开发安全规则见 `RULE.md`。

## 长期安全分类

永久禁止、不能由任何后续 `GOAL.md` 开放：

- 任意 URL 获取器和用户自定义 Host、协议、端口、base URL 或路径；
- 无限制爬虫、整站遍历和递归发现未知链接；
- 绕过权限、年龄、付费、订阅、地区或账号限制；
- 凭据窃取、隐藏提取、泄漏、跨 Provider 共享或越权读取；
- 隐藏网络活动；
- 未经确认的大量写入、覆盖或下载；
- 默认上传本地收藏、用户记录或推荐偏好。

默认拒绝，但未来可由独立 Phase 和明确 `GOAL.md` 授权：

- OAuth、API Token、用户名/密码和用户主动提供的 Session Cookie；
- Provider-specific 结构化或 HTML 解析；
- 封面、预览和媒体下载；
- 第二 Provider 与多来源聚合；
- 默认关闭、可见、可控、可撤销的后台同步；
- 本地推荐与可选 AI；
- 下载队列和定时检查。

搜索、详情预览、数据库写入和下载必须保持分离，写入与下载分别需要可审查
预览和用户明确确认。

## v1.2.0 路线

```text
Phase 5-P2  长期产品原则与路线对齐（已完成）
Phase 5-N3  核心 Provider 合同、认证、内容获取与下载需求规划；不选择 Provider
Phase 5-N4  首个用户批准、符合 NSFW 核心定位的 Provider Adapter
Phase 5-N5  搜索、详情预览、创建或关联 Item 与手动确认入库
Phase 5-N6  用户明确确认的受控下载闭环
Phase 5-N7  手动来源检查、差异更新、安全与体验收尾
Phase 5-I1  v1.2.0 集成冻结
Phase 5-R1  唯一一次 Hermes 独立验收
Phase 5-R2  v1.2.0 正式发布
```

第二 Provider、多来源统一搜索、后台自动同步、个性化推荐、可选 AI、复杂
下载队列和跨进程任务调度保留为长期能力，不强制进入 v1.2.0。

## 取消项

- 取消 TVmaze 作为首个正式 Provider 的路线。
- 取消 MediaTrack 更名路线，项目名称继续使用 `NSFWTrack`。
- 取消普通影视主导的产品路线，不为其优先建设季、集、电视台或播出计划。
- 取消为了技术验证接入与 NSFW 核心领域无关的正式 Provider。

## 已完成能力与证据

- Phase 5-N1 已完成受控 HTTP、固定空 Endpoint Registry、Adapter 合同与 DTO。
- Phase 5-N2 已完成 Schema 4 来源追踪与 Backup v2。
- N2 实现提交：`df90473d827be86b83da4d7d8487fd852fcff35c`。
- N2 本地门禁：focused `33`、targeted `164`、full `917`、`pip check` 与隔离
  Docker 均通过。
- N2 Actions run `29637868492` 的 `test` 与 `Docker production smoke` 均成功。
- N1/N2 代码、测试和历史验收证据均保留不变。

## 下一阶段

下一阶段是 Phase 5-N3。N3 只规划 NSFW 核心 Provider 的能力合同、认证需求、
内容获取需求和下载需求，不选择、不批准、不实现真实 Provider。

## 阶段边界

P2 未修改代码、测试、依赖、Schema、迁移、Backup 实现、Adapter、路由、模板、
i18n、Docker 或 CI；未请求真实 Provider 网络；未创建 tag 或 Release；未部署
N100；未调用或编写 Hermes 验收。Hermes 仍只允许在 Phase 5-R1 的全部前置
门禁满足后调用一次。
