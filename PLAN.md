# NSFWTrack — MVP 开发计划

> NSFWTrack 是项目名称。Phase 1 严格限定为：**本地单用户内容记录器 / 收藏管理器 MVP**。
> Phase 1 禁止实现任何外部内容源、爬虫、远程图片拉取、站点 adapter、第三方 cookie/token 管理、自动同步、多源搜索或随机探索接口。

## 角色分工

- **我（DeepSeek）**：项目规划、任务拆分、审核 Codex 产出、测试验收
- **Codex（GPT-5.5）**：编码实现
- **你**：审批、最终确认

## 项目定位

第一版描述：

> **本地单用户媒体记录器 / 收藏管理器 MVP**

不强调成人内容聚合、外部内容探索、多站点搜索等方向。Phase 1 仅做本地管理。

## Phase 1 目标

- ✅ 手动录入条目
- ✅ CSV / JSON 批量导入
- ✅ 标签管理（创建/关联/搜索）
- ✅ 创作者管理（演员/作者/画师）
- ✅ 状态标记（想看/已看/喜欢/不喜欢/忽略）
- ✅ 本地搜索（标题/标签/状态过滤）
- ✅ 简单统计（数量/状态分布/时间线）
- ✅ 单用户登录保护（环境变量密码 + Session）
- ✅ 中文 / English 语言切换（默认中文，Session 保存偏好）
- ✅ Docker Compose 部署
- ✅ 基础测试

## Phase 1 禁止出现

❌ 外部 HTTP 拉取
❌ 站点 adapter
❌ 随机探索接口
❌ 爬虫
❌ 远程图片源
❌ 第三方 cookie / token 管理（登录 Session 与语言偏好 Session 除外）
❌ 自动同步
❌ 多源聚合搜索
❌ 推荐系统
❌ AI 助手
❌ WebAuthn / CF / D1

## Phase 2（后续）

导入/备份增强、搜索增强、标签翻译（EhTagTranslation）

## Phase 3（后续）

插件化数据源，需合规、授权、可控，先 mock 后真实接入。

## 技术栈

```
FastAPI + SQLite + SQLAlchemy + Jinja2 + HTMX + Docker Compose
```

## 项目结构

```
nsfwtrack/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置（环境变量）
│   ├── database.py          # SQLite + 建表
│   ├── models.py            # SQLAlchemy 模型
│   ├── schemas.py           # Pydantic 请求/响应
│   ├── auth.py              # 登录保护
│   ├── i18n.py              # 中文 / English 翻译字典
│   ├── routers/
│   │   ├── items.py         # 条目 CRUD + 标记
│   │   ├── tags.py          # 标签管理
│   │   ├── creators.py      # 创作者管理
│   │   ├── search.py        # 搜索
│   │   ├── stats.py         # 统计
│   │   └── auth.py          # 登录路由
│   ├── services/
│   │   └── importer.py      # CSV/JSON 导入
│   └── templates/
│       ├── base.html
│       ├── login.html       # 登录页
│       ├── index.html       # 首页
│       ├── items.html       # 条目列表
│       ├── detail.html      # 条目详情 + 标记
│       ├── tags.html        # 标签管理
│       ├── creators.html    # 创作者管理
│       ├── stats.html       # 统计
│       └── import.html      # 导入页面
├── tests/
├── data/                    # SQLite 持久化
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example             # 密码配置示例（.env 本身在 gitignore）
```

## 数据库模型（6 张表）

```sql
CREATE TABLE items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  cover_path TEXT,                   -- 本地封面路径（Phase 1 不上传远程图片）
  summary TEXT,
  release_date TEXT,
  extra TEXT,                   -- JSON，Phase 2+ 扩展用
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE creators (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  type TEXT DEFAULT 'other',
  avatar_path TEXT,                 -- 本地头像路径（Phase 1 不上传远程图片）
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  category TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE item_tags (
  item_id INTEGER REFERENCES items(id) ON DELETE CASCADE,
  tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (item_id, tag_id)
);

CREATE TABLE item_creators (
  item_id INTEGER REFERENCES items(id) ON DELETE CASCADE,
  creator_id INTEGER REFERENCES creators(id) ON DELETE CASCADE,
  PRIMARY KEY (item_id, creator_id)
);

CREATE TABLE user_item_states (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK (status IN ('wish','watching','watched','like','dislike','ignore')),
  rating INTEGER CHECK (rating >= 1 AND rating <= 5),
  review TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(item_id)
);
```

## API 路由

```
# 登录
POST   /api/auth/login              # 密码登录
POST   /api/auth/logout             # 退出

# 条目
GET    /api/items                    # 列表（分页）
POST   /api/items                    # 新增
GET    /api/items/{id}               # 详情
PUT    /api/items/{id}               # 编辑
DELETE /api/items/{id}               # 删除

# 状态标记
POST   /api/items/{id}/state         # 设置标记
GET    /api/items/{id}/state         # 查状态
DELETE /api/items/{id}/state         # 取消

# 标签
GET    /api/tags                     # 列表
POST   /api/tags                     # 创建
PUT    /api/tags/{id}                # 编辑
DELETE /api/tags/{id}                # 删除

# 创作者
GET    /api/creators                 # 列表
POST   /api/creators                 # 创建
GET    /api/creators/{id}            # 详情 + 作品
DELETE /api/creators/{id}            # 删除

# 搜索
GET    /api/search?q=xxx&tag=xxx&status=xxx&page=1

# 统计
GET    /api/stats/summary
GET    /api/stats/timeline

# 导入
POST   /api/import/csv
POST   /api/import/json
```

## 安全边界

- 密码从环境变量 `APP_PASSWORD` 读取，禁止默认空密码
- Session cookie 认证
- `.env` 已加入 `.gitignore`
- 所有页面需登录才能访问
- 日志不得输出密码、cookie、token
- 默认仅监听 `0.0.0.0:8000`（局域网可访问）
- `data/` Docker 卷持久化

## Phase 1 执行顺序

```
Day 1: 项目骨架 + 数据库模型 + items CRUD
Day 2: 标签 + 创作者管理 + 关联
Day 3: 登录保护 + 状态标记 + 搜索 + 统计
Day 4: 前端页面（列表/详情/标签/创作者/统计/导入/登录）
Day 5: CSV/JSON 导入 + Docker 部署 + 测试
Day 6: 中文 / English 语言切换 + 文档清理
```

## 数据来源（Phase 1）

- 手动录入：Web UI 表单
- CSV 导入：`title,tags,creators,status,rating,review`
- JSON 导入：同上格式
