本轮目标：依赖拆分 + CI，不新增业务功能。

要求：

1. 将当前 requirements.txt 整理为运行时依赖。
2. 新增 requirements-dev.txt，用于测试和本地开发。
3. 如果 TestClient 仍需要 httpx，则将 httpx 保留在 requirements-dev.txt，不要放在运行时依赖中。
4. 不要实现任何新业务功能。
5. 新增 GitHub Actions workflow：
   - 安装 Python
   - 安装 requirements-dev.txt
   - 运行 python -m pytest
6. 确认 Dockerfile 只安装 requirements.txt。
7. 运行：
   - python -m pytest
   - docker compose build
   - docker compose up -d
   - docker compose down
8. 输出测试结果、Docker 结果、修改文件列表和 git diff 概要。

Phase 1 禁止项保持不变：不要实现外部内容源、爬虫、adapter、远程图片拉取、cookie/token 管理、自动同步、多源搜索、随机探索接口、推荐系统或 AI 助手。