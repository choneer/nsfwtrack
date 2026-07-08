# GOAL.md

# NSFWTrack 当前开发目标

本轮开发目标：
在保持 Phase 1 本地 MVP 边界不变的前提下，完成仓库清理、小范围文档更新，并新增中文 / English 语言切换功能。

---

## 一、必须遵守的项目边界

NSFWTrack 是项目名称。

Phase 1 严格限定为：

> 本地单用户内容记录器 / 收藏管理器 MVP。

Phase 1 只允许实现：

* 本地条目 CRUD
* 标签管理
* 创作者管理
* 条目状态标记
* 本地搜索
* 简单统计
* 登录保护
* CSV / JSON 导入
* Docker Compose 部署
* 基础测试
* 中文 / English 语言切换

Phase 1 禁止实现：

* 外部内容源
* 爬虫
* adapter
* 远程图片拉取
* cookie / token 管理
* 自动同步
* 多源搜索
* 随机探索接口
* 推荐系统
* AI 助手

如果开发中发现上述超范围内容，不要实现，直接跳过并说明原因。

---

## 二、本轮清理任务

请先完成以下清理：

1. 删除 `data/ehtag_version`
   原因：它不属于 Phase 1。

2. 移除 `docs/legacy/`
   原因：其中内容是旧路线，容易误导当前开发。

3. 确认当前代码没有读取或依赖 `docs/legacy/`。

4. 确认本轮开发不引入任何外部 HTTP 请求、爬虫、adapter、远程图片拉取、cookie/token 管理、自动同步、多源搜索或随机探索接口。

---

## 三、本轮新增功能：语言切换

当前 Web UI 全是英文，需要新增中文支持。

要求：

1. 支持中文 / English 两种语言。
2. 默认语言为中文。
3. 页面右上角或设置页提供语言切换入口。
4. 语言选择刷新后不丢失。
5. 可以使用 cookie 或 session 保存语言偏好。
6. 所有页面展示文本都需要接入 i18n，包括：

   * 页面标题
   * 导航菜单
   * 按钮
   * 表单标签
   * 占位提示
   * 成功提示
   * 错误提示
   * 空状态提示
   * 统计页面文本
7. 后端 API 字段名不用翻译，只翻译前端展示文本。
8. 不要引入 React、Vue 或其他大型前端框架。
9. 继续保持 FastAPI + Jinja2 + HTMX 的轻量结构。
10. 增加至少一个测试，确认中文页面和英文页面都能正常渲染。

建议实现方式：

* 新增 `app/i18n.py`
* 定义 `zh` 和 `en` 两套翻译字典
* 在模板中使用类似 `{{ t("items.title") }}` 的方式渲染文本
* 新增语言切换路由，例如：

  * `/set-language?lang=zh`
  * `/set-language?lang=en`
* 使用 cookie 保存语言偏好
* 默认语言为 `zh`

---

## 四、需要同步更新的文档

完成代码修改后，请同步更新：

1. `PLAN.md`
2. `TASKS.md`
3. `REVIEW.md`
4. `README.md`

更新要求：

* 把中文 / English 语言切换加入 Phase 1。
* 保持 Phase 1 本地 MVP 边界不变。
* 明确 Phase 1 仍然禁止外部内容源、爬虫、远程图片拉取、adapter、cookie/token 管理、自动同步、多源搜索和随机探索接口。
* README 需要写明如何切换语言，以及默认语言是中文。

---

## 五、验收命令

完成后运行：

```bash
python -m pytest
docker compose build
docker compose up -d
docker compose down
```

如果命令失败，请输出失败原因和相关日志摘要。

---

## 六、输出要求

完成后请输出：

1. 修改了哪些文件
2. 删除了哪些文件或目录
3. 新增了哪些文件
4. 测试是否通过
5. Docker build 是否通过
6. Docker compose 是否能启动
7. 当前 git diff 概要
8. 是否触碰 `REVIEW.md` 的超范围项
9. 下一步建议
