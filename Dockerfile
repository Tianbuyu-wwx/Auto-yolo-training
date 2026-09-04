# syntax=docker/dockerfile:1.7
# 多阶段 Dockerfile：CPU 与 cu128 (GPU) 两个 target tag
#
# 用法：
#   # CPU 镜像（默认）
#   docker build -t ayt:cpu .
#   docker run -it --rm -p 7860:7860 -p 8000:8000 -v $(pwd)/dataset:/as/dataset ayt:cpu
#
#   # GPU 镜像（NVIDIA cu128）
#   docker build --build-arg TORCH_VARIANT=cu128 -t ayt:cu128 .
#   docker run --gpus all -it --rm -p 7860:7860 -p 8000:8000 -v $(pwd)/dataset:/as/dataset ayt:cu128
#
# 默认入口是 ``bash``，用户可手动执行 ``ayt-train`` / ``ayt-gradio`` / ``ayt-serve`` 等。
# 容器启动后不会自动跑训练——避免容器生命周期与训练状态混淆。

ARG PYTHON_VERSION=3.12.13
ARG TORCH_VARIANT=cpu

# ----------------------------------------------------------------------
# Stage 1: builder（独立 /opt/venv 便于 COPY 到 runtime）
# ----------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ARG TORCH_VARIANT
ENV TORCH_VARIANT=${TORCH_VARIANT}

# 系统依赖（构建 Python wheel 时需要）
# - build-essential:    编译 C/C++ 扩展
# - git:                pip 从 git URL 安装时需要
# - libgl1 / libglib2.0-0: opencv-python-headless 替代运行时
RUN apt-get update && \
 apt-get install -y --no-install-recommends \
 build-essential \
 git \
 libgl1 \
 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# 独立 venv（避免 pip 与系统 Python 冲突；最终镜像 COPY 整个 venv）
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 先装 PyTorch（按 variant 选 wheel index；缓存友好——单独一层）
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN if [ "$TORCH_VARIANT" = "cu128" ]; then \
 TORCH_INDEX_URL=https://download.pytorch.org/whl/cu128 ; \
 fi && \
 pip install --no-cache-dir \
 --index-url "$TORCH_INDEX_URL" \
 torch==2.11.0 torchvision==0.26.0

# 装项目依赖（运行时 + 开发）
COPY constraints.txt requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -c constraints.txt -r requirements-dev.txt

# ----------------------------------------------------------------------
# Stage 2: runtime
# ----------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG TORCH_VARIANT
ENV TORCH_VARIANT=${TORCH_VARIANT}

# 运行时系统依赖（无编译器）
RUN apt-get update && \
 apt-get install -y --no-install-recommends \
 libgl1 \
 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# 非 root 用户（最佳实践）
RUN groupadd --system ayt && \
 useradd --system --gid ayt --create-home --shell /bin/bash ayt

# 从 builder 拷 venv
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUTF8=1
ENV MPLBACKEND=Agg

# Ultralytics 默认往 ~/.config 写，改为项目内 .ci/
ENV YOLO_CONFIG_DIR=/as/.ci/Ultralytics
ENV MPLCONFIGDIR=/as/.ci/matplotlib

# 拷贝源码
WORKDIR /as
COPY --chown=ayt:ayt pyproject.toml README.md ./
COPY --chown=ayt:ayt src/ ./src/
COPY --chown=ayt:ayt train.py tune.py eval.py export.py serve.py validate_data.py gradio_app.py ayt_models.py ./
COPY --chown=ayt:ayt test/ ./test/

# 数据/模型/产物目录（运行时挂载）
RUN mkdir -p /as/dataset /as/basemodels /as/runs /as/exports /as/logs /as/reports /as/tuning && \
 chown -R ayt:ayt /as

USER ayt
WORKDIR /as

# 暴露 Gradio + FastAPI 默认端口
EXPOSE 7860 8000

# 健康检查（FastAPI /health）
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()" \
 || exit 0

# 默认进 bash——用户可执行：
#   ayt-gradio --host 0.0.0.0
#   ayt-serve --host 0.0.0.0
#   ayt-train dataset --model yolov8s.pt --epochs 1
CMD ["bash"]