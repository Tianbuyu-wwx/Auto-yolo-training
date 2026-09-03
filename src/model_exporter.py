"""
模型导出模块
自动将训练好的模型导出为多种部署格式
"""

import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ExportResult:
    """导出结果"""
    format: str
    success: bool
    output_path: str | None = None
    file_size: int = 0
    message: str = ""
    duration: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "success": self.success,
            "output_path": self.output_path,
            "file_size_mb": round(self.file_size / (1024 * 1024), 2),
            "message": self.message,
            "duration": round(self.duration, 2),
        }


@dataclass
class ExportReport:
    """导出报告"""
    model_path: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    results: list[ExportResult] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def total_count(self) -> int:
        return len(self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "timestamp": self.timestamp,
            "success_count": self.success_count,
            "total_count": self.total_count,
            "results": [r.to_dict() for r in self.results],
        }


class ModelExporter:
    """YOLO模型导出器"""

    # 支持的导出格式
    SUPPORTED_FORMATS = {
        "torchscript": {"ext": ".torchscript", "desc": "TorchScript"},
        "onnx": {"ext": ".onnx", "desc": "ONNX"},
        "openvino": {"ext": "_openvino_model", "desc": "OpenVINO"},
        "engine": {"ext": ".engine", "desc": "TensorRT"},
        "coreml": {"ext": ".mlpackage", "desc": "CoreML"},
        "saved_model": {"ext": "", "desc": "TensorFlow SavedModel"},
        "pb": {"ext": ".pb", "desc": "TensorFlow GraphDef"},
        "tflite": {"ext": ".tflite", "desc": "TensorFlow Lite"},
        "edgetpu": {"ext": "_edgetpu.tflite", "desc": "Edge TPU"},
        "tfjs": {"ext": "_web_model", "desc": "TensorFlow.js"},
        "paddle": {"ext": "_paddle_model", "desc": "PaddlePaddle"},
        "ncnn": {"ext": "_ncnn_model", "desc": "NCNN"},
    }

    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).parent.parent
        self.exports_dir = self.base_dir / "exports"
        self.exports_dir.mkdir(exist_ok=True)

    def export(
        self,
        model_path: str,
        formats: list[str] | None = None,
        imgsz: int = 640,
        half: bool = False,
        int8: bool = False,
        dynamic: bool = True,
        simplify: bool = True,
        opset: int = 12,
        workspace: int = 4,
    ) -> ExportReport:
        """
        导出模型到多种格式

        Args:
            model_path: 模型文件路径 (.pt)
            formats: 导出格式列表，None则导出所有支持的格式
            imgsz: 输入图像尺寸
            half: 是否使用FP16半精度
            int8: 是否使用INT8量化
            dynamic: ONNX是否使用动态轴
            simplify: 是否简化ONNX模型
            opset: ONNX opset版本
            workspace: TensorRT工作空间大小(GB)

        Returns:
            ExportReport对象
        """
        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"模型文件不存在: {model_path}")

        if formats is None:
            formats = ["onnx", "engine", "openvino"]

        report = ExportReport(model_path=str(model_path))

        # 创建导出目录
        model_name = model_path.stem
        export_dir = self.exports_dir / f"{model_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        export_dir.mkdir(exist_ok=True)

        for fmt in formats:
            if fmt not in self.SUPPORTED_FORMATS:
                report.results.append(ExportResult(
                    format=fmt,
                    success=False,
                    message=f"不支持的格式: {fmt}",
                ))
                continue

            result = self._export_single(
                model_path=model_path,
                fmt=fmt,
                export_dir=export_dir,
                imgsz=imgsz,
                half=half,
                int8=int8,
                dynamic=dynamic,
                simplify=simplify,
                opset=opset,
                workspace=workspace,
            )
            report.results.append(result)

        # 保存报告
        self._save_report(report, export_dir)

        return report

    def export_best(
        self,
        run_dir: str,
        formats: list[str] | None = None,
        **kwargs,
    ) -> ExportReport:
        """
        导出训练运行目录中的最佳模型

        Args:
            run_dir: 训练运行目录
            formats: 导出格式列表
            **kwargs: 传递给export的其他参数

        Returns:
            ExportReport对象
        """
        run_dir = Path(run_dir)
        best_model = run_dir / "weights" / "best.pt"

        if not best_model.exists():
            raise FileNotFoundError(f"未找到最佳模型: {best_model}")

        return self.export(
            model_path=str(best_model),
            formats=formats,
            **kwargs,
        )

    def get_export_info(self, format: str) -> dict[str, Any]:
        """获取导出格式的信息"""
        if format not in self.SUPPORTED_FORMATS:
            return {"supported": False, "message": "不支持的格式"}

        info = self.SUPPORTED_FORMATS[format].copy()
        info["supported"] = True

        # 检查依赖
        if format == "onnx":
            try:
                __import__("onnx")
                info["dependency"] = "已安装"
            except ImportError:
                info["dependency"] = "未安装 (pip install onnx)"
        elif format == "engine":
            try:
                __import__("tensorrt")
                info["dependency"] = "已安装"
            except ImportError:
                info["dependency"] = "未安装 (需要TensorRT)"
        elif format == "openvino":
            try:
                __import__("openvino")
                info["dependency"] = "已安装"
            except ImportError:
                info["dependency"] = "未安装 (pip install openvino)"

        return info

    def list_supported_formats(self) -> list[dict[str, Any]]:
        """列出所有支持的导出格式"""
        return [
            {
                "format": fmt,
                "description": info["desc"],
                "extension": info["ext"],
                **self.get_export_info(fmt),
            }
            for fmt, info in self.SUPPORTED_FORMATS.items()
        ]

    def _export_single(
        self,
        model_path: Path,
        fmt: str,
        export_dir: Path,
        imgsz: int,
        half: bool,
        int8: bool,
        dynamic: bool,
        simplify: bool,
        opset: int,
        workspace: int,
    ) -> ExportResult:
        """导出单个格式"""
        import time

        start = time.time()

        try:
            from ultralytics import YOLO

            model = YOLO(str(model_path))

            # 构建导出参数
            export_kwargs = {
                "format": fmt,
                "imgsz": imgsz,
                "half": half,
                "int8": int8,
                "dynamic": dynamic,
                "simplify": simplify,
                "opset": opset,
                "workspace": workspace,
            }

            # 执行导出
            export_path = model.export(**export_kwargs)

            duration = time.time() - start

            # 获取文件大小
            export_path = Path(export_path)
            file_size = export_path.stat().st_size if export_path.exists() else 0

            # 移动到导出目录
            if export_path.exists() and export_path.parent != export_dir:
                dest = export_dir / export_path.name
                shutil.move(str(export_path), str(dest))
                export_path = dest

            return ExportResult(
                format=fmt,
                success=True,
                output_path=str(export_path),
                file_size=file_size,
                message=f"导出成功: {self.SUPPORTED_FORMATS[fmt]['desc']}",
                duration=duration,
            )

        except Exception as e:
            duration = time.time() - start
            return ExportResult(
                format=fmt,
                success=False,
                message=f"导出失败: {str(e)}",
                duration=duration,
            )

    def _save_report(self, report: ExportReport, export_dir: Path):
        """保存导出报告"""
        report_path = export_dir / "export_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)


def quick_export(
    model_path: str,
    formats: list[str] | None = None,
    base_dir: str | None = None,
    **kwargs,
) -> ExportReport:
    """
    快速导出便捷函数

    Args:
        model_path: 模型文件路径
        formats: 导出格式列表
        base_dir: 项目根目录
        **kwargs: 其他参数

    Returns:
        ExportReport对象
    """
    exporter = ModelExporter(base_dir)
    return exporter.export(
        model_path=model_path,
        formats=formats,
        **kwargs,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="YOLO模型导出工具")
    parser.add_argument("model", help="模型文件路径 (.pt)")
    parser.add_argument(
        "--formats", "-f",
        default="onnx,engine",
        help="导出格式，逗号分隔 (默认: onnx,engine)"
    )
    parser.add_argument("--imgsz", type=int, default=640, help="图像尺寸")
    parser.add_argument("--half", action="store_true", help="FP16半精度")
    parser.add_argument("--int8", action="store_true", help="INT8量化")
    parser.add_argument("--dynamic", action="store_true", default=True, help="动态轴")
    parser.add_argument("--simplify", action="store_true", default=True, help="简化ONNX")
    parser.add_argument("--opset", type=int, default=12, help="ONNX opset版本")
    parser.add_argument("--list", action="store_true", help="列出支持的格式")

    args = parser.parse_args()

    if args.list:
        exporter = ModelExporter()
        print("支持的导出格式:")
        for info in exporter.list_supported_formats():
            status = "✓" if info.get("supported") else "✗"
            dep = info.get("dependency", "")
            print(f"  {status} {info['format']:12s} - {info['description']}")
            if dep:
                print(f"      依赖: {dep}")
        sys.exit(0)

    print(f"导出模型: {args.model}")
    print(f"格式: {args.formats}")

    formats = args.formats.split(",")
    report = quick_export(
        model_path=args.model,
        formats=formats,
        imgsz=args.imgsz,
        half=args.half,
        int8=args.int8,
        dynamic=args.dynamic,
        simplify=args.simplify,
        opset=args.opset,
    )

    print("\n导出结果:")
    for result in report.results:
        status = "✓" if result.success else "✗"
        size = f"({result.file_size_mb:.2f} MB)" if result.file_size > 0 else ""
        print(f"  {status} {result.format:12s} {size}")
        if result.output_path:
            print(f"      路径: {result.output_path}")
        if not result.success:
            print(f"      错误: {result.message}")
