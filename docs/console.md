# Web 控制台

控制台（`ayt-web`）是这套工具的主界面。前端是 Vue 3 + Vite 的单页应用，源码在
`frontend/`；后端是 `src/api/admin.py` 提供的管理面 FastAPI，与训练流水线共用
同一套服务层。

!!! note "与 Gradio 的关系"
    项目早期提供的 Gradio 界面（`ayt-gradio`）**已冻结**，仅作为历史入口保留，
    不再继续投入。控制台是它的替代实现。

## 启动

### 生产模式（单进程，同源）

```bash
make frontend-build          # 构建到 frontend/dist
make web                     # python -m src.api.admin --host 127.0.0.1 --port 8080
```

打开 <http://127.0.0.1:8080>。后端检测到 `frontend/dist` 存在时会自动静态托管，
并为未知路径回退到 `index.html`（SPA 路由所需）。

!!! warning "`/` 返回一段 JSON 说明界面没起来"
    如果 `frontend/dist` 不存在，`/` 会返回
    `{"service": "AYT Admin API", "hint": "前端未构建：cd frontend && pnpm install && pnpm build"}`。
    这是**降级提示而不是错误**——说明后端本身是好的，只是没找到已构建的前端。

### 开发模式（热更新）

```bash
make frontend-install        # pnpm install --frozen-lockfile
make frontend-dev            # Vite 起在 5173
make web                     # 另一个终端跑后端 API
```

打开 <http://127.0.0.1:5173>。Vite 会把 `/api` 与 `/ws` 代理到 8080，所以两个
终端都要开着。

## 页面

| 页面 | 路径 | 说明 |
|---|---|---|
| 总览 | `/` | 训练状态、数据集/队列/模型计数、数据告警入口、快捷链接 |
| 数据集 | `/datasets` | 上传 ZIP、格式转换、列表与告警、样本预览（可叠标注框）、数据校验 |
| 训练配置 | `/train/config` | 数据集/任务/模型选择、参数预设、分组的超参数表单、立即训练或加入队列 |
| 训练监控 | `/train/monitor` | 实时进度、损失与指标曲线、训练日志（WebSocket 每秒推送） |
| 结果 · 模型库 | `/results` | 各 run 的最终指标、结果图表、模型导出与下载 |
| 模型注册中心 | `/registry` | 版本列表与指标、注册新版本、打标、两两对比、晋升生产、删除注册记录 |
| 任务队列 | `/queue` | 队列任务的持久化状态、取消操作 |

## 模型注册中心（`/registry`）

`ModelRegistry` 的数据落在 `model_registry/versions.json`，训练完成时会自动注册一次
（`copy_model=False`）；控制台是它的手动操作入口。

三条容易误解的语义：

| 行为 | 实际影响 |
|---|---|
| **注册** 默认不复制权重 | 只追加一条记录，`model_path` 指向 `runs/detect/<run>/weights/*.pt` 原位文件。勾选「复制权重到注册表」才会在 `model_registry/models/<版本id>/` 存一份副本——代价是额外磁盘占用，好处是训练目录被自动清理后注册版本仍然可用 |
| **删除** 删的是注册记录 | 不动 `runs/` 下的权重。若该版本当初是「复制」注册的，删的是注册表内那份副本，原位权重同样保留 |
| **晋升生产** 是互斥的 | 一个数据集同时只有一个生产版本；晋升新版本会把原有的生产版本自动降为 `archived` |

两条附加约束：

- **生产版本不能直接删除**（后端返回 `409`）：删掉它会让 `get_production_model()`
  静默变成 `None`，调用方无从察觉。要先归档或另指定生产版本。
- **指标可以留空**：留空时后端从该 run 的 `results.csv` 读最终 mAP 自动补全；
  没有 `results.csv` 就记为无指标，**不会编造数字**。界面上的 toast 会说明指标来源。

## 两条需要知道的数据语义

### 数据集有两级口径，界面不做合并

后端 `get_all_statuses()` 同时返回两个字段，含义不同：

| 字段 | 级别 | 判定 | 用途 |
|---|---|---|---|
| `is_ready` | 扫描级 | 有 `labels/` 目录且标注文件数 > 0 | 说明「文件长得像 YOLO 格式」 |
| `is_trainable` | 训练级 | 存在 `data.yaml` | 训练管线与数据集下拉的依据 |

两者**会不一致**。实测本仓库的 `dataset/` 下就有一个例子：`_smoke_test` 与
`cabel-damage-mini` 有完整标注但没有 `data.yaml`，因此
`is_ready=True` 而 `is_trainable=False`。数据集页把它们显示为琥珀色的
**「缺 data.yaml」**而不是绿色「可训练」——因为它们确实选不进训练。

### 标绿不等于数据合格

`is_ready` / `is_trainable` 只描述**结构**，不描述**质量**。质量问题在
`issues` 字段里，数据集页的「问题」列会原样列出。

一个真实例子：`data` 数据集 `image_count=371`、`label_count=296`，差 75 正好
等于它的告警「val 集中有 75/75 张图像缺少对应标注」——也就是 val 集完全没有
标签。用这样的数据集训练，评估出来的 mAP 没有意义。

!!! danger "训练前请核对「问题」列"
    控制台目前只做展示，**不会在提交训练前强制拦截**。看到告警请先补齐标注，
    或在配置页勾选「跳过数据校验」前想清楚后果。

## 视口要求

控制台定位为**桌面端工具，最低支持 1024px 视口宽度**，不做移动/平板适配。
更窄的窗口会显示一张明确的提示页（含当前实际宽度），而不是让布局静默破版。

这个决定来自实测：1024px 及以上在 8 种视口 × 6 个页面的组合探测中零元素溢出；
再往下压缩，表格与多列网格会退化成不可用的形态，做成「勉强可用」的移动版
成本高且收益低。

## 前端结构

```
frontend/
├── index.html
├── vite.config.js           # 开发代理 + 生产分 chunk 策略
├── scripts/check-bundle.mjs # 产物预算门禁
└── src/
    ├── main.js  router.js  App.vue
    ├── lib/
    │   ├── api.js           # REST 封装 + 训练状态 WebSocket（自动重连）
    │   └── toast.js         # 全局操作反馈队列
    ├── styles/tokens.css    # 全部设计 token 与组件样式（单一样式来源）
    ├── components/
    │   ├── LineChart.vue    # ECharts 按需引入，数据指纹去重绘
    │   ├── LogConsole.vue   # 日志尾随滚动
    │   └── ToastHost.vue    # 反馈层宿主
    └── pages/               # 6 个页面 + NotFoundPage（路由懒加载）
```

样式只有 `tokens.css` 一个来源：没有 CSS-in-JS、没有 scoped style、页面里也不
写布局用的内联 `grid-template-columns`（内联样式优先级高于媒体查询，会让响应式
失效）。

## 产物预算

```bash
make frontend-check
```

首屏 JS 预算 160 KB、单个 chunk 500 KB。首屏资产由 `dist/index.html` 解析得出，
所以路由懒加载的页面 chunk 与按需加载的图表库不会被算进首屏。

CI（`.github/workflows/frontend.yml`）会跑同一条命令，超限直接失败。

## 常见问题

**曲线不刷新 / 日志停住**
看顶栏的实时连接状态。WebSocket 断开时会显示「实时连接已断开，正在重连…」，
客户端每 2 秒重试一次。

**图表空白**
`/train/monitor` 的图表数据由前端按 epoch 累积（每个 epoch 一个点），刷新页面
会重置。历史曲线请到「结果 · 模型库」看该 run 的结果图表。

**Tab 键看不到焦点**
所有可交互元素都有 `:focus-visible` 焦点环。若看不到，先确认窗口宽度是否低于
1024px（此时显示的是提示页）。
