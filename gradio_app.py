"""
YOLO自动训练平台 - Gradio前端启动入口

使用方法:
    python gradio_app.py              # 本地启动 (http://localhost:7860)
    python gradio_app.py --share      # 生成公网分享链接
    python gradio_app.py --port 8080  # 指定端口
"""

from src.gradio_app import main

if __name__ == "__main__":
    main()
