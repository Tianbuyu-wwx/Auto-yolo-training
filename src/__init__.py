"""Project package initialization and local runtime defaults."""

import os
from pathlib import Path

# Ultralytics writes settings/cache files on import. Keep those files inside
# the project so tests and restricted environments do not depend on a
# writable user profile directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOCAL_CONFIG_ROOT = _PROJECT_ROOT / ".ci"
os.environ.setdefault(
    "YOLO_CONFIG_DIR",
    str(_LOCAL_CONFIG_ROOT / "ultralytics"),
)
os.environ.setdefault("MPLCONFIGDIR", str(_LOCAL_CONFIG_ROOT / "matplotlib"))
os.environ.setdefault("MPLBACKEND", "Agg")

# Some sandboxed Windows runners omit WINDIR even though the directory is
# present. Matplotlib only needs this value while discovering system fonts.
if "WINDIR" not in os.environ:
    _system_root = os.environ.get("SystemRoot")
    if _system_root or Path("C:/Windows").exists():
        os.environ["WINDIR"] = _system_root or "C:\\Windows"
