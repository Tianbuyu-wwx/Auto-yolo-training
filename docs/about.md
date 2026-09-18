# Auto YOLO Training · 文档索引

> **当前定位：** 单机开发与内部验证版。功能完整（数据校验 / 训练 / 调参 / 评估 / 导出 / 推理一体化），
> 支持 YOLOv5 / v8 / v11 / YOLO26 全系列与 4 大任务类型（检测 / 分割 / 姿态 / 分类）。

---

## 新用户起点

- 🚀 [quickstart.md](quickstart.md) — **5 分钟跑通指南**（强烈推荐先读）
- 🖥 [console.md](console.md) — Web 控制台（主界面）：7 个页面、无认证（个人训练器）、两级数据口径
- 📊 [datasets.md](datasets.md) — 数据集格式与转换
- 🔌 [api.md](api.md) — FastAPI 推理服务

## 项目演进

- 📜 [第一阶段可信基线实施记录与后续方案.md](第一阶段可信基线实施记录与后续方案.md) — 2026-07-22 建立的可信基线（92 测试 + GPU 烟雾训练 15.34s）

---

## 阶段进展

| 阶段 | 状态 | 关键改动 |
|---|---|---|
| A 通用化清场 | ✅ | branding 模块 + 删 P0 + ModelRegistry 接入 + `device` 语义修正 |
| B 可配置化 | ✅ | pyproject 完整 + ruff 全规则 + Pydantic Settings + 文档体系 |
| C 通用能力 | ✅ | 4 任务类型 + 27 个预训练模型清单 + 模型下载 CLI + 任务抽象 |
| D 生产化 | ✅ | Dockerfile（CPU / cu128 双 tag）+ docker-compose + Makefile + pre-commit + MkDocs |
| G 控制台能力补全 | ✅ | 断点续训 + 模型注册中心控制台（注册 / 打标 / 对比 / 晋升 / 删除） |
| 阶段 0 止血 | ✅ | 训练产物改为回收而非删除、注册表权重缺失可见化、SPA 回退 404 修正 |
| E CI/CD 多平台 | 计划 | Linux / macOS job + coverage 门禁 + pip-audit |
| F 分布式 | 远期 | 多用户 RBAC、数据集与产物版本化、Redis 队列 |

---

## 开发者文档

- **测试**：`make test`（`pytest -m "not gpu and not training"`，378 passed / 1 skipped）
- **Lint / 格式化**：`make lint` / `make lint-fix` / `make format`（ruff 全量规则）
- **前端**：`make frontend-dev`（Vite 5173）· `make frontend-build` · `make frontend-check`（产物体积预算门禁）
- **控制台**：`make web` → <http://127.0.0.1:8080>（Vue 3 SPA + 管理面 API）
- **环境变量**：见 [.env.example](https://github.com/Tianbuyu-wwx/Auto-yolo-training/blob/main/.env.example)
- **CLI 入口**（`pip install -e .` 后可用）：
  `ayt-web` · `ayt-train` · `ayt-tune` · `ayt-eval` · `ayt-export` · `ayt-serve` · `ayt-validate` · `ayt-models` · `ayt-gradio`（已冻结）
- **模块**：`src/` 下 27 个核心模块（含 `src/api/` 管理面）+ `src/gradio_app/`（16 个文件的 Gradio 界面，已冻结）

---

## 已知限制

| 限制 | 状态 |
|---|---|
| 控制台**没有认证层**（个人训练器：下载到自己机器上跑，默认只监听 127.0.0.1） | 不打算做：多用户 / 权限隔离明确不在路线图 |
| 训练产物与数据集版本化未集成（注册表已接入，但 `copy_model=False` 的版本会因滚动清理而权重缺失，控制台会标注） | 阶段 F：DVC / RunStore |
| 任务队列缺崩溃恢复：重启后 `running` / `cancel_requested` 的任务会卡住 | 阶段 2.2 |
| `dataset/data` 的 val 集没有标注（控制台数据集页的「问题」列会标出） | 数据侧待补 |
| 控制台为桌面专用（最低 1024px 视口，不做移动 / 平板适配） | 产品决策 |
| Gradio 界面已冻结，且 gradio 不再默认安装（`pip install -e ".[gradio]"` 可装回） | 设计取舍 |
| Docker 真机构建与容器内训练尚未验证 | 待 Docker Desktop |
