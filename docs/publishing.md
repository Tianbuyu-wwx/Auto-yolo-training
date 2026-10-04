# 打包与发布（PyPI）

本页是**维护者**视角的发布流程；普通使用者只需 `pip install auto-yolo-training`。

## 关于打包

界面运行时不再包含 Web 前端（Vue 已退役，桌面启动器为唯一前端）。仓库里保留一个
历史快照目录 `src/api/static/`（旧控制台的最后构建），打包时直接打进 wheel。
运行时 `resolve_frontend_dist` 按 `显式指定 > 包内 static/ > 仓库 frontend/dist`
的顺序找 SPA 产物；找不到时 `/` 返回一段 JSON 提示，属**正常降级**（启动器不受影响，
它显式指定自己的 UI 目录）。

## 本地打一个包（不发布）

```bash
make dist          # 装填静态资源 → build → twine check（产物在 dist/）
make dist-check    # 只校验包内静态资源与源码快照是否一致（CI 用）
```

装到临时环境里自测（推荐每次发版前做一次）：

```bash
uv venv /tmp/ayt-check && uv pip install --python /tmp/ayt-check/bin/python dist/*.whl
cd /tmp && /tmp/ayt-check/bin/ayt-web --port 18099    # 首页返回 JSON 提示属正常（无界面产物）
```

## 发版流程

1. 改版本号：`pyproject.toml` 的 `version`（当前 `0.1.0`）；
2. 更新 `README.md` / `docs/about.md` 里可机检的数字（测试数、页面数）并重跑
   `python scripts/sync_docs_readme.py` —— `test/test_docs_consistency.py` 会挡住漂移；
3. 本地全绿：`make test`、`make lint`、`make launcher-smoke`（桌面壳冒烟）；
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
