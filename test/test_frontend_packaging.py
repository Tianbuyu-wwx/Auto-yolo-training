"""打包链路：包内静态产物（wheel 里必须有前端，否则装出来只有 API）。

两个对象：
- ``src.api.admin.resolve_frontend_dist`` —— 运行时定位 SPA 产物（包内 static 优先）；
- ``scripts.stage_frontend_assets.py`` —— 打包前把 ``frontend/dist`` 装填进包内，
  并提供 ``--check`` 供 CI 校验一致性。

缺口背景：控制台是 FastAPI 托管的静态文件，而它们生成在仓库根的 ``frontend/dist``
（不在任何 Python 包里）。不做装填，``pip install`` 出来的 wheel 首页只会返回一段
JSON 提示 —— 而这个工具的产品形态就是「控制台 + API」。
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import stage_frontend_assets as stage  # noqa: E402


class TestResolveFrontendDist:
    """运行时的三档优先级：显式指定 > 包内 static（安装后）> 仓库 frontend/dist（源码）"""

    @staticmethod
    def _layout(tmp_path: Path, *, packaged: bool, source: bool):
        pkg, src = tmp_path / "static", tmp_path / "dist"
        for path, present in ((pkg, packaged), (src, source)):
            path.mkdir()
            if present:
                (path / "index.html").write_text("<!doctype html><div id=app>", encoding="utf-8")
        return pkg, src

    @pytest.fixture()
    def admin(self, tmp_path, monkeypatch):
        from src.api import admin as module

        monkeypatch.setattr(module, "PACKAGED_STATIC_DIR", tmp_path / "static")
        monkeypatch.setattr(module, "SOURCE_STATIC_DIR", tmp_path / "dist")
        return module

    def test_source_checkout_prefers_fresh_dist(self, admin, tmp_path):
        """仓库检出里 frontend/dist 必须优先于包内 static 快照 —— 否则改完界面
        刷新浏览器还是旧 UI（打包快照是冻结的）。"""
        pkg, src = self._layout(tmp_path, packaged=True, source=True)
        assert admin.resolve_frontend_dist() == src

    def test_falls_back_to_packaged_when_dist_missing(self, admin, tmp_path):
        pkg, _ = self._layout(tmp_path, packaged=True, source=False)
        assert admin.resolve_frontend_dist() == pkg

    def test_installed_layout_prefers_packaged_static(self, tmp_path, monkeypatch):
        """从 wheel 装出来时（PROJECT_ROOT 不是仓库）反过来：包内 static 优先"""
        from src.api import admin as module

        pkg, src = self._layout(tmp_path, packaged=True, source=True)
        monkeypatch.setattr(module, "PACKAGED_STATIC_DIR", pkg)
        monkeypatch.setattr(module, "SOURCE_STATIC_DIR", src)
        monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path / "site-packages")
        assert module.resolve_frontend_dist() == pkg

    def test_explicit_override_wins(self, admin, tmp_path):
        self._layout(tmp_path, packaged=True, source=True)
        override = tmp_path / "elsewhere"
        override.mkdir()
        (override / "index.html").write_text("<div id=app>", encoding="utf-8")
        assert admin.resolve_frontend_dist(override) == override

    def test_returns_none_when_nothing_is_built(self, admin, tmp_path):
        self._layout(tmp_path, packaged=False, source=False)
        assert admin.resolve_frontend_dist() is None

    def test_empty_directory_is_rejected(self, admin, tmp_path):
        """判据是 index.html：空目录/半截构建不能被当成可用界面（否则首页 404 更难查）"""
        self._layout(tmp_path, packaged=True, source=False)
        (tmp_path / "static" / "index.html").unlink()
        assert admin.resolve_frontend_dist() is None

    def test_app_still_starts_without_frontend(self, tmp_path, monkeypatch):
        """一处前端产物都没有时也必须起得来：API 可用，首页给可操作提示

        注意要把**两个候选目录**都指到不存在的位置 —— 只传 frontend_dist 的话，
        resolve_frontend_dist 会按优先级回落到仓库里的 frontend/dist（那是真实存在的），
        于是首页返回的是 SPA 而不是提示。
        """
        from fastapi.testclient import TestClient

        from src.api import admin as module

        monkeypatch.setattr(module, "PACKAGED_STATIC_DIR", tmp_path / "no-static")
        monkeypatch.setattr(module, "SOURCE_STATIC_DIR", tmp_path / "no-dist")
        app = module.create_admin_app(base_dir=tmp_path, use_subprocess=False,
                                      start_queue_runner=False)
        with TestClient(app) as c:
            assert c.get("/api/health").status_code == 200
            body = c.get("/").json()
            assert "pnpm build" in body["hint"]


class TestStageFrontendAssets:
    def test_refuses_without_build(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(stage, "SOURCE", tmp_path / "dist")
        monkeypatch.setattr(stage, "TARGET", tmp_path / "static")
        assert stage.main([]) == 2
        assert "pnpm build" in capsys.readouterr().err

    def test_stages_and_then_check_is_clean(self, tmp_path, monkeypatch, capsys):
        source = tmp_path / "dist"
        (source / "assets").mkdir(parents=True)
        (source / "index.html").write_text("<div id=app>", encoding="utf-8")
        (source / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
        target = tmp_path / "static"
        monkeypatch.setattr(stage, "SOURCE", source)
        monkeypatch.setattr(stage, "TARGET", target)

        assert stage.main([]) == 0
        assert (target / "assets" / "app.js").is_file()
        assert stage.main(["--check"]) == 0

    def test_check_detects_drift(self, tmp_path, monkeypatch, capsys):
        """装填后前端又改了 → --check 必须报出来（否则会发布过期的界面）"""
        source = tmp_path / "dist"
        source.mkdir()
        (source / "index.html").write_text("<div id=app>", encoding="utf-8")
        target = tmp_path / "static"
        monkeypatch.setattr(stage, "SOURCE", source)
        monkeypatch.setattr(stage, "TARGET", target)
        stage.main([])

        (source / "index.html").write_text("<div id=app data-changed>", encoding="utf-8")
        assert stage.main(["--check"]) == 1
        assert "内容不同" in capsys.readouterr().err

    def test_check_fails_when_target_missing(self, tmp_path, monkeypatch):
        source = tmp_path / "dist"
        source.mkdir()
        (source / "index.html").write_text("<div id=app>", encoding="utf-8")
        monkeypatch.setattr(stage, "SOURCE", source)
        monkeypatch.setattr(stage, "TARGET", tmp_path / "static")
        assert stage.main(["--check"]) == 1


class TestInstalledBaseDir:
    """装出来的 CLI 不能把用户数据写进 site-packages。

    源码运行时默认目录是仓库根；wheel 安装后必须是**当前工作目录** ——
    否则 runs/、dataset/、logs/ 会落在 Python 环境里，升级/卸载即丢。
    """

    def test_source_layout_uses_project_root(self):
        from src.api import admin

        assert admin.default_base_dir() == admin.PROJECT_ROOT

    def test_installed_layout_uses_cwd(self, tmp_path, monkeypatch):
        from src.api import admin

        monkeypatch.setattr(admin, "PROJECT_ROOT", tmp_path / "site-packages")
        monkeypatch.chdir(tmp_path)
        assert admin.default_base_dir() == tmp_path

    def test_app_without_base_dir_uses_default(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient

        from src.api import admin as module

        monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path / "site-packages")
        monkeypatch.setattr(module, "PACKAGED_STATIC_DIR", tmp_path / "no-static")
        monkeypatch.setattr(module, "SOURCE_STATIC_DIR", tmp_path / "no-dist")
        workdir = tmp_path / "work"
        workdir.mkdir()
        monkeypatch.chdir(workdir)

        app = module.create_admin_app(use_subprocess=False, start_queue_runner=False)
        with TestClient(app):
            assert app.state.base_dir == workdir
