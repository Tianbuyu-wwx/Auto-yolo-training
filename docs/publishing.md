# 打包与发布（PyPI）

本页是**维护者**视角的发布流程；普通使用者只需 `pip install auto-yolo-training`。

## 为什么打包这一步有坑

控制台是 FastAPI 托管的一堆静态文件，而它们生成在仓库根的 `frontend/dist` ——
**不在任何 Python 包里**。不特殊处理的话，`pip install` 出来的 wheel 只有 API：
`ayt-web` 起来了，但首页返回一段 JSON 提示。所以打包链路里多了一步「装填」：

```
pnpm build  →  frontend/dist  ──stage_frontend_assets.py──▶  src/api/static/  →  wheel
```

运行时按 `显式指定 > 包内 static/ > 仓库 frontend/dist` 的顺序找界面
（`src/api/admin.py::resolve_frontend_dist`），所以源码运行与安装运行都能用。

## 本地打一个包（不发布）

```bash
make dist          # 构建前端 → 装填 → build → twine check（产物在 dist/）
make dist-check    # 只校验包内静态资源与 frontend/dist 是否一致（CI 用）
```

装到临时环境里自测（推荐每次发版前做一次）：

```bash
uv venv /tmp/ayt-check && uv pip install --python /tmp/ayt-check/bin/python dist/*.whl
cd /tmp && /tmp/ayt-check/bin/ayt-web --port 18099    # 首页应当是控制台界面
```

## 发版流程

1. 改版本号：`pyproject.toml` 的 `version`（当前 `0.1.0`）；
2. 更新 `README.md` / `docs/about.md` 里可机检的数字（测试数、页面数）并重跑
   `python scripts/sync_docs_readme.py` —— `test/test_docs_consistency.py` 会挡住漂移；
3. 本地全绿：`make test`、`make lint`、`make frontend-check-all`；
4. 打标签并推送：

   ```bash
   git tag v0.1.0-rc.1 && git push origin v0.1.0-rc.1   # 预发布 → TestPyPI
   git tag v0.1.0      && git push origin v0.1.0        # 正式  → PyPI
   ```

5. 看 `.github/workflows/release.yml` 的构建结果与产物（artifact `dist`）。

## 首次发布前的一次性配置

发布走 **Trusted Publishing**（OIDC），仓库里不存任何 PyPI token：

1. TestPyPI → Account settings → Publishing → Add a pending publisher
   - Owner `Tianbuyu-wwx`、Repository `Auto-yolo-training`、
     Workflow `release.yml`、Environment `release`
2. PyPI 同上（正式发布需要同样登记一次）；
3. GitHub 仓库 → Settings → Environments → 新建 `release`
   （可选：加 Required reviewers，让正式发布前必须有人点批准）。

`rc` 标签会发到 TestPyPI、正式标签发到 PyPI，判断写在 workflow 里，不需要额外操作。

## 版本号口径

- 本项目 `requires-python = ">=3.12,<3.13"`：只在 3.12 上验证过，别放宽了不给依据；
- 依赖的精确版本在 `constraints.txt`（CI 与用户机器一致），`pyproject.toml` 里是
  下限区间 —— 发布前用 `make audit` 看一眼有没有新增的 advisory。
