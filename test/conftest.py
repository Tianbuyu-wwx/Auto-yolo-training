"""pytest 全局引导：保证 ultralytics / matplotlib 的配置与缓存不落在仓库根。

pytest 收集阶段会 import 测试模块（其中有些直接 import ultralytics），
早于 src/__init__ 的 env 设置 —— 这里在最早时机做同样的事（setdefault 幂等）。
"""

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_CFG = _ROOT / ".ci"
os.environ.setdefault("YOLO_CONFIG_DIR", str(_CFG / "ultralytics"))
os.environ.setdefault("MPLCONFIGDIR", str(_CFG / "matplotlib"))
os.environ.setdefault("MPLBACKEND", "Agg")
