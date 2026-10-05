"""
Auto YOLO Training - Gradio 前端启动入口（已冻结）

使用方法:
    python gradio_app.py              # 本地启动 (http://localhost:7860)
    python gradio_app.py --share      # 生成公网分享链接
    python gradio_app.py --port 8080  # 指定端口

注意：该界面已冻结，gradio 也不再是默认安装的一部分。未安装时本入口会打印
可操作的安装提示（而不是抛出 ImportError 堆栈）：
    pip install -e ".[gradio]"
"""

import sys


def main() -> int:
    """入口包装：把「没装 gradio」变成一句能照做的提示。"""
    try:
        from src.gradio_app import main as _gradio_main
    except ImportError as exc:  # 只兜住 gradio 缺失，其它 ImportError 照常抛出
        if "gradio" not in str(exc):
            raise
        print(
            "未安装 Gradio —— 该界面已冻结，不再是默认安装的一部分。\n"
            '如需使用：pip install -e ".[gradio]"（或 pip install gradio）\n'
            f"原始错误：{exc}",
            file=sys.stderr,
        )
        return 2
    _gradio_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
