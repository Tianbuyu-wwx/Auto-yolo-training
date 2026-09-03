"""
测试运行入口
统一运行所有测试
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

import argparse
import unittest


def discover_tests(pattern="test_*.py"):
    """发现所有测试"""
    test_dir = Path(__file__).parent
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for test_file in sorted(test_dir.glob(pattern)):
        if test_file.name in ["run_tests.py", "__init__.py"]:
            continue
        module_name = f"test.{test_file.stem}"
        try:
            tests = loader.loadTestsFromName(module_name)
            suite.addTests(tests)
        except Exception as e:
            print(f"加载测试失败 {module_name}: {e}")

    return suite


def run_tests(suite, verbosity=2):
    """运行测试套件"""
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    return result.wasSuccessful()


def main():
    parser = argparse.ArgumentParser(description="运行测试套件")
    parser.add_argument(
        "--pattern",
        default="test_*.py",
        help="测试文件匹配模式 (默认: test_*.py)",
    )
    parser.add_argument(
        "--module",
        help="只运行指定模块的测试，如 test_data_validator",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="详细输出",
    )
    args = parser.parse_args()

    if args.module:
        module_name = f"test.{args.module}"
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromName(module_name)
    else:
        suite = discover_tests(args.pattern)

    total = suite.countTestCases()
    print("=" * 60)
    print(f"发现 {total} 个测试用例")
    print("=" * 60)

    verbosity = 2 if args.verbose else 1
    success = run_tests(suite, verbosity)

    print("=" * 60)
    if success:
        print("所有测试通过!")
        return 0
    else:
        print("部分测试失败!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
