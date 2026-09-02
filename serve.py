"""
YOLO推理服务启动脚本
提供FastAPI模型推理服务
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import argparse
from src.inference_service import run_server
from src.branding import get_cli_banner


def main():
    parser = argparse.ArgumentParser(
        description="YOLO推理服务",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 启动服务（自动查找最新模型）
  python serve.py

  # 指定模型启动
  python serve.py --model runs/detect/cabel-damage-mini_auto/weights/best.pt

  # 指定训练运行目录
  python serve.py --run runs/detect/cabel-damage-mini_auto

  # 指定端口
  python serve.py --port 8080

  # 完整示例
  python serve.py --run runs/detect/cabel-damage-mini_auto --host 0.0.0.0 --port 8000
        """
    )

    parser.add_argument(
        "--model", "-m",
        help="模型文件路径 (.pt)"
    )

    parser.add_argument(
        "--run", "-r",
        help="训练运行目录（自动查找weights/best.pt）"
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="监听地址 (默认: 127.0.0.1)"
    )

    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8000,
        help="端口 (默认: 8000)"
    )

    parser.add_argument(
        "--api-key",
        default=os.environ.get("YOLO_API_KEY"),
        help="API认证密钥（默认读取环境变量 YOLO_API_KEY，命令行参数优先级更高）"
    )

    args = parser.parse_args()

    # 确定模型路径
    model_path = args.model
    if args.run:
        run_dir = Path(args.run)
        best_model = run_dir / "weights" / "best.pt"
        if best_model.exists():
            model_path = str(best_model)
            print(f"自动加载模型: {model_path}")
        else:
            print(f"警告: 未找到最佳模型: {best_model}")

    # 如果没有指定模型，尝试自动查找
    if not model_path:
        runs_dir = Path("runs/detect")
        if runs_dir.exists():
            # 查找最新的训练运行
            run_dirs = sorted(
                [d for d in runs_dir.iterdir() if d.is_dir()],
                key=lambda d: d.stat().st_mtime,
                reverse=True,
            )
            for run_dir in run_dirs:
                best_model = run_dir / "weights" / "best.pt"
                if best_model.exists():
                    model_path = str(best_model)
                    print(f"自动加载最新模型: {model_path}")
                    break

    if not model_path:
        print("错误: 未找到可用模型，请指定 --model 或 --run")
        sys.exit(1)

    # 启动服务
    run_server(
        model_path=model_path,
        host=args.host,
        port=args.port,
        api_key=args.api_key,
    )


if __name__ == "__main__":
    main()
