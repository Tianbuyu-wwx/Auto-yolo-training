# 桌面启动器

启动器（`make launcher` / `python -m src.launcher`）是这套工具的主界面：
pywebview 窗口壳 + 内嵌管理面后端（自动挑空闲端口，随窗口启停）。

!!! note "与历史界面的关系"
    Vue 网页端（原 `frontend/`）与 Gradio 界面均已退役。管理面 API
    （`src/api/admin.py`）仍然保留：启动器内嵌它，`make web` 可单独跑。

## 启动

```bash
pip install -e ".[launcher]"     # 第一次：装 pywebview
make launcher                    # 或 python -m src.launcher
python -m src.launcher --smoke 8 # 冒烟：开窗 8 秒后自动关闭
```

## 页面

9 个页面：首页 / 数据集 / 训练配置 / 训练监控 / 模型库 / 注册中心 / 队列 /
环境自检 / 设置。「选数据集 → 调参 → 开训 → 看曲线 → 导出 → 注册版本」
全流程都在这里完成。

## 架构

- `src/launcher/app.py` —— pywebview 窗口壳（frameless；右上自绘最小化 /
  最大化 / 关闭，经 `LauncherWinAPI` js 桥转到 pywebview 窗口方法）
- `src/launcher/backend.py` —— 内嵌管理面后端（子进程 uvicorn，端口自动分配；
  窗口关则后端停，**训练子进程不受影响**）
- `src/launcher/features.py` —— 推理服务生命周期、打开路径（白名单校验）、
  诊断包、ZIP 上传
- `src/launcher/static/` —— UI 包：`index.html`（v8 冻结原型）+ `live.js`
  （真数据层）+ 字体

`live.js` 是双模式数据层：`file://` 下为原型演示；`http(s)` 下探测 `/api/health`
接管真数据、真动作与 WebSocket 训练流（`/ws/training`）。

## 管理面 API

启动器内嵌的后端与 `make web`（<http://127.0.0.1:8080>）是同一个管理面：
REST（datasets / trainings / queue / models / registry / exports / recycle /
inference / launcher）+ WebSocket。没有界面产物时 `/` 返回 JSON 提示，这是
**降级提示而不是错误**——API 本身可用。接口细节见 [API 参考](api.md)。

## 验证（开发者）

```bash
make launcher-smoke                 # 开窗数秒自关（无交互验收）
cd tools/launcher-design/_selfcheck
node check-v8.mjs                   # 布局审计（溢出 / 越界 / 重叠 / 死链 × 9 页）
node e2e-live.mjs                   # 真后端 e2e（21 断言：真数据渲染 + 动作拦截）
python e2e-full.py --epochs 3       # 全链路：真训练 + 注册 + 导出 + 推理（需 GPU）
```
