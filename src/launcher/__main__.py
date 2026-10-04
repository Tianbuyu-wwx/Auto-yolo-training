"""``python -m src.launcher`` 入口。

等价于 ``ayt-launcher`` console script（pyproject 里指向 src.launcher.app:main）。
"""

from src.launcher.app import main

if __name__ == "__main__":
    raise SystemExit(main())
