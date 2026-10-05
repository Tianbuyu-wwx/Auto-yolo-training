"""启动器内核：进程内管理面后端（uvicorn 线程 + 就绪探测 + 优雅退出）。

设计约束（launcher-plan-2026-10-04.md §2）：

- **复用** ``src.api.admin.create_admin_app`` 的整套 API/WS，零重造；
- 启动器 UI 通过 ``frontend_dist`` 显式传给 admin app（``resolve_frontend_dist``
  支持显式 override，语义见 test_frontend_packaging.py）；
- 端口默认由系统分配（用户机器上 8080/8000 常被别的工具占用）；
- 训练是独立子进程，本进程退出不影响训练。
"""

from __future__ import annotations

import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# 窗口标题与截图/句柄验收共用这一个口径（win_shot / FindWindowW 都按它找窗口）
DEFAULT_TITLE = "AYT 启动器"

# 就绪探测默认超时：纯后端进程内启停只要几秒；冷启动首次 import 留足余量
READY_TIMEOUT = 25.0


def pick_free_port(host: str = "127.0.0.1", preferred: int = 0) -> int:
    """挑一个空闲端口；``preferred=0`` 时由系统分配。

    注意这是「探测后释放再绑定」的经典窗口——单机自用场景风险可忽略；
    真要零竞争就得绑 0 端口再回读，但那要耦合 uvicorn 内部实现，不值得。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, preferred))
        return int(sock.getsockname()[1])


class LauncherBackend:
    """管理面后端的进程内生命周期管理。

    用法::

        backend = LauncherBackend()
        backend.start()   # 阻塞到 /api/health 返回 200
        ...               # backend.url 交给窗口
        backend.stop()    # 优雅退出
    """

    def __init__(
        self,
        base_dir: str | Path | None = None,
        port: int = 0,
        frontend_dist: str | Path | None = None,
        start_queue_runner: bool = True,
    ):
        self.base_dir = Path(base_dir).resolve() if base_dir else None
        self.requested_port = port
        self.port = pick_free_port(preferred=port)
        self.frontend_dist = Path(frontend_dist).resolve() if frontend_dist else None
        self.start_queue_runner = start_queue_runner
        self._server = None
        self._thread: threading.Thread | None = None
        self._boot_error: BaseException | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def port_file(self) -> Path | None:
        """把实际端口写到工作目录（给外部工具/调试脚本读）。"""
        if self.base_dir is None:
            return None
        return self.base_dir / "artifacts" / "logs" / "launcher-port.txt"

    def start(self, ready_timeout: float = READY_TIMEOUT) -> None:
        """构建 admin app 并在后台线程跑 uvicorn，阻塞直到健康检查通过。"""
        import uvicorn

        from src.api.admin import create_admin_app, default_base_dir

        if self.base_dir is None:
            self.base_dir = default_base_dir()

        # TaskQueue 的 sqlite 落在 logs/（sqlite 不会自建父目录）
        (self.base_dir / "artifacts" / "logs").mkdir(parents=True, exist_ok=True)

        app = create_admin_app(
            base_dir=self.base_dir,
            frontend_dist=self.frontend_dist,
            start_queue_runner=self.start_queue_runner,
        )
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        def _run() -> None:
            try:
                self._server.run()
            except BaseException as exc:  # 端口占用 / 启动异常都从这里冒出来
                self._boot_error = exc

        self._thread = threading.Thread(target=_run, name="launcher-backend", daemon=True)
        self._thread.start()
        self.wait_ready(ready_timeout)

        port_file = self.port_file
        if port_file is not None:
            port_file.write_text(f"{self.port}\n", encoding="utf-8")

    def wait_ready(self, timeout: float = READY_TIMEOUT) -> None:
        """轮询 /api/health，确保窗口打开时后端已可用（避免首屏白页）。"""
        deadline = time.monotonic() + timeout
        last_error: BaseException | None = None
        while time.monotonic() < deadline:
            if self._boot_error is not None:
                raise RuntimeError(f"管理面后端启动失败：{self._boot_error}") from self._boot_error
            try:
                with urllib.request.urlopen(f"{self.url}/api/health", timeout=1.5) as resp:
                    if resp.status == 200:
                        return
            except (OSError, urllib.error.URLError) as exc:
                last_error = exc
            time.sleep(0.15)
        raise TimeoutError(f"后端在 {timeout:.0f}s 内未就绪（{self.url}/api/health）：{last_error}")

    def stop(self, timeout: float = 12.0) -> None:
        """优雅退出：置 should_exit 并等线程收尾（兜底为 daemon 线程随进程退出）。"""
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
