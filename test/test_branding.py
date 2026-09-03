"""
通用化品牌模块测试（阶段 A18）

覆盖：
- 默认品牌信息（不应绑定任何具体业务场景）
- 环境变量覆盖
- CLI banner / API metadata 输出格式
- 关键不变量：版本号一致、不含业务化痕迹（Cable / 破损 / break / thunderbolt）
"""
import os
import sys
import unittest
from pathlib import Path

# 确保 src/ 在 path 上
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.__version__ import __version__ as SRC_VERSION
from src.branding import (
    DEFAULT_BRAND,
    ENV_OVERRIDE_KEYS,
    get_api_metadata,
    get_brand,
    get_cli_banner,
)


class TestDefaultBranding(unittest.TestCase):
    """默认品牌信息不应绑定任何业务场景"""

    def test_default_name_is_generic(self):
        brand = get_brand()
        self.assertEqual(brand["name"], "Auto YOLO Training")
        # 不应包含业务化痕迹
        for forbidden in ("Cable", "破损", "thunderbolt", "break", "Defect"):
            self.assertNotIn(forbidden, brand["name"])

    def test_default_api_title_is_generic(self):
        brand = get_brand()
        self.assertEqual(brand["api_title"], "YOLO Inference API")
        self.assertNotIn("Cable", brand["api_title"])
        self.assertNotIn("破损", brand["api_description"])

    def test_version_matches_package(self):
        brand = get_brand()
        self.assertEqual(brand["version"], SRC_VERSION)

    def test_default_brand_dict_completeness(self):
        """默认品牌字段必须完整（避免空指针）"""
        for key in ("name", "tagline", "description", "api_title", "api_description", "copyright"):
            self.assertIn(key, DEFAULT_BRAND)
            self.assertTrue(DEFAULT_BRAND[key], f"DEFAULT_BRAND[{key}] 必须非空")

    def test_env_override_keys_subset_of_default(self):
        """环境变量覆盖 key 必须是 DEFAULT_BRAND 字段的子集（不暴露所有字段）"""
        self.assertTrue(
            set(ENV_OVERRIDE_KEYS.keys()).issubset(set(DEFAULT_BRAND.keys())),
            "ENV_OVERRIDE_KEYS 必须是 DEFAULT_BRAND 字段的子集",
        )
        # 反向：版本号不应通过环境变量控制（避免漂移）
        self.assertNotIn("version", ENV_OVERRIDE_KEYS)


class TestEnvOverride(unittest.TestCase):
    """环境变量应能覆盖默认品牌（用于企业内部定制）"""

    def setUp(self):
        # 保存原值
        self._original = {k: os.environ.get(v) for k, v in ENV_OVERRIDE_KEYS.items()}

    def tearDown(self):
        # 恢复原值
        for k, v in ENV_OVERRIDE_KEYS.items():
            if self._original[k] is None:
                os.environ.pop(v, None)
            else:
                os.environ[v] = self._original[k]

    def test_api_title_override(self):
        os.environ["YOLO_API_TITLE"] = "MyFactory Detection API"
        brand = get_brand()
        self.assertEqual(brand["api_title"], "MyFactory Detection API")

    def test_multiple_overrides(self):
        os.environ["YOLO_API_TITLE"] = "Test API"
        os.environ["YOLO_BRAND_TAGLINE"] = "Test Tagline"
        brand = get_brand()
        self.assertEqual(brand["api_title"], "Test API")
        self.assertEqual(brand["tagline"], "Test Tagline")

    def test_unset_env_uses_default(self):
        os.environ.pop("YOLO_API_TITLE", None)
        brand = get_brand()
        self.assertEqual(brand["api_title"], DEFAULT_BRAND["api_title"])


class TestCLIBanner(unittest.TestCase):
    """CLI banner 格式正确 + 含版本号 + 不含业务痕迹"""

    def test_banner_contains_name_and_version(self):
        banner = get_cli_banner()
        self.assertIn("Auto YOLO Training", banner)
        self.assertIn(SRC_VERSION, banner)

    def test_banner_no_business_terms(self):
        banner = get_cli_banner()
        for forbidden in ("Cable", "破损", "Defect", "thunderbolt"):
            self.assertNotIn(forbidden, banner)

    def test_banner_is_multiline(self):
        banner = get_cli_banner()
        self.assertGreaterEqual(banner.count("\n"), 2)


class TestAPIMetadata(unittest.TestCase):
    """FastAPI metadata 必须可用 ``**`` 解包"""

    def test_api_metadata_keys(self):
        meta = get_api_metadata()
        for key in ("title", "description", "version"):
            self.assertIn(key, meta)
            self.assertTrue(meta[key])

    def test_api_metadata_version_matches(self):
        meta = get_api_metadata()
        self.assertEqual(meta["version"], SRC_VERSION)


if __name__ == "__main__":
    unittest.main()
