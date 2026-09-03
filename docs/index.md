# Auto YOLO Training · 文档索引

> **当前定位：** 单机开发与内部验证版。功能完整（训练 / 调参 / 评估 / 导出 / 推理一体化），支持 YOLOv5/v8/v11/YOLO26 全系列检测任务。

---

## 新用户起点

- 🚀 [quickstart.md](quickstart.md) — **5 分钟跑通指南**（强烈推荐先读）
- 📊 [datasets.md](datasets.md) — 数据集格式与转换
- 🔌 [api.md](api.md) — FastAPI 推理服务

## 项目演进

- 📜 [第一阶段可信基线实施记录与后续方案.md](第一阶段可信基线实施记录与后续方案.md) — 2026-07-22 建立的可信基线（92 测试 + GPU 烟雾训练 15.34s）

---

## 通用化进展

本项目已通用化，不再绑定具体业务场景（电缆破损等）。阶段进展：

| 阶段 | 状态 | 关键改动 |
|---|---|---|
| A 通用化清场 | ✅ 完成 | branding 模块 + 删 P0 + ModelRegistry 接入 + device=auto |
| B 可配置化 | ✅ 完成 | pyproject.toml 全量配置 + ruff 全规则 + Pydantic Settings + 文档体系 |
| C 通用能力扩展 | ⏸ 规划 | 4 任务类型 / 任务队列 / 断点恢复 / DVC |

---

## 开发者文档

- **测试**：`pytest -m "not gpu and not training"`（95+ tests）
- **Lint**：`ruff check .`（全量规则启用）
- **环境变量**：见 `.env.example`
- **CLI 入口**：`train.py` / `tune.py` / `eval.py` / `export.py` / `serve.py` / `validate_data.py` / `gradio_app.py`
- **模块**：`src/` 下 16 个核心模块 + `src/gradio_app/` 7 个 UI 模块

---

## 已知限制（README 声明 + 阶段 A/B 缓解）

| 限制 | 缓解状态 |
|---|---|
| Web 进程内训练 | 阶段 C：任务队列 + Redis |
| 多用户/权限隔离 | 阶段 C：JWT + RBAC |
| 模型/数据集/配置版本化 | 阶段 A 部分：ModelRegistry 接入；阶段 C：DVC |
| 外部 YAML 绝对路径 | 阶段 A 已修复：相对 YAML 文件路径 |
| `dataset/data` 验证集无标注 | README 已声明，请优先选择校验通过的数据集 |
| Polars CPU 检查 | 沙箱环境临时 `POLARS_SKIP_CPU_CHECK=1` |