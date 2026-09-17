#!/usr/bin/env python
"""GPU 通道验收：这台机器上的 CUDA 到底能不能**真跑**训练。

与 CPU 侧 `make smoke` 的分工：那个证明「流水线跑得通」，这个证明「跑在 GPU 上」，
而且要拿出第一手证据 —— 只看 `torch.cuda.is_available()` 是不够的，它只说明驱动
握手成功，不说明 kernel 能在**这块卡**上跑（新架构 + 旧轮子会在这里挂）。

两段式，每段都留证据：

1. **环境段**：torch/CUDA 版本、设备名、显存、算力，以及一次真实的 CUDA 矩阵乘
   （与 CPU 结果逐元素比对，容差 1e-3）—— 这一步才是「kernel 真跑了」的证据；
2. **训练段**：真跑一次 `train.py <dataset> --device 0`，同时用 nvidia-smi 采样，
   断言：
   - 训练日志出现 `CUDA:0 (NVIDIA ...)`（Ultralytics 真的选了 GPU，而不是回落 CPU）；
   - 采样到的显存峰值比基线高 ≥200MB（训练进程真的在卡上分配了显存）；
   - 产物齐全（`weights/{best,last}.pt`、`results.csv`）；
   - `args.yaml` 里记的 device 与传入一致。

用法::

    python scripts/gpu_smoke.py                 # 人类可读
    python scripts/gpu_smoke.py --json          # 机器可读（CI / 归档）
    python scripts/gpu_smoke.py --epochs 3 --imgsz 320

退出码：0 = 全通过；1 = 任一断言失败（失败也照样打印证据，不静默）。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 与 scripts/ 下其它脚本一致：以脚本方式运行时 sys.path[0] 是 scripts/，
# 需要把项目根塞进去才能 import src.*
sys.path.insert(0, str(PROJECT_ROOT))

# 这些字符串出现在 Ultralytics 的启动横幅里，是「真的选了 GPU」的最直接证据
CUDA_BANNER = re.compile(r"CUDA:(\d+)\s*\(([^)]+)\)")


# ----------------------------------------------------------------------
# 第一段：环境与 kernel
# ----------------------------------------------------------------------
def torch_report() -> dict:
    import torch

    report: dict = {
        "torch": torch.__version__,
        "cuda_build": torch.version.cuda,
        "available": bool(torch.cuda.is_available()),
    }
    if not report["available"]:
        return report
    free, total = torch.cuda.mem_get_info(0)
    report.update(
        device=torch.cuda.get_device_name(0),
        capability=list(torch.cuda.get_device_capability(0)),
        vram_total_mb=round(total / 1024 ** 2),
        vram_free_mb=round(free / 1024 ** 2),
    )
    return report


def cuda_kernel_check() -> dict:
    """真算一遍：512×512 矩阵乘，CPU 与 CUDA 结果逐元素比对"""
    import torch

    torch.manual_seed(0)
    a, b = torch.rand(512, 512), torch.rand(512, 512)
    cpu = a @ b
    gpu = (a.cuda() @ b.cuda()).cpu()
    torch.cuda.synchronize()
    max_diff = float((cpu - gpu).abs().max())
    return {"max_abs_diff": max_diff, "ok": max_diff < 1e-3}


# ----------------------------------------------------------------------
# 训练期间的 GPU 采样
# ----------------------------------------------------------------------
class GpuSampler:
    """每 interval 秒采一次 nvidia-smi（利用率 / 显存），拿峰值与基线"""

    def __init__(self, interval: float = 0.4):
        self.interval = interval
        self.samples: list[tuple[float, float]] = []
        self.error = ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _query(self) -> tuple[float, float] | None:
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self.error = f"nvidia-smi 不可用: {exc}"
            return None
        line = (out.stdout or "").strip().splitlines()
        if not line:
            return None
        try:
            util, mem = (float(x.strip()) for x in line[0].split(","))
        except ValueError:
            return None
        return util, mem

    def _loop(self) -> None:
        while not self._stop.is_set():
            sample = self._query()
            if sample:
                self.samples.append(sample)
            self._stop.wait(self.interval)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def baseline_mb(self) -> float:
        return self.samples[0][1] if self.samples else 0.0

    @property
    def peak_mb(self) -> float:
        return max((m for _, m in self.samples), default=0.0)

    @property
    def peak_util(self) -> float:
        return max((u for u, _ in self.samples), default=0.0)


# ----------------------------------------------------------------------
# 第二段：真跑一次训练
# ----------------------------------------------------------------------
def locate_model(name: str) -> str:
    """按项目自己的解析顺序找基准权重：basemodels/ → 项目根 → 原样返回（会触发下载）"""
    from src.utils import resolve_model_path

    resolved = resolve_model_path(name, PROJECT_ROOT / "basemodels")
    if resolved != name and Path(resolved).exists():
        return resolved
    for candidate in (PROJECT_ROOT / "basemodels" / name, PROJECT_ROOT / name):
        if candidate.is_file():
            return str(candidate)
    return name


def run_training(dataset: str, model: str, epochs: int, imgsz: int, batch: int,
                 device: str, timeout: int = 900) -> dict:
    cmd = [
        sys.executable, str(PROJECT_ROOT / "train.py"), dataset,
        "--model", model, "--epochs", str(epochs), "--imgsz", str(imgsz),
        "--batch", str(batch), "--device", device, "--skip-validation",
    ]
    sampler = GpuSampler()
    sampler.start()
    started = time.time()
    try:
        proc = subprocess.run(
            cmd, cwd=PROJECT_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        stdout, returncode = proc.stdout or "", proc.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, returncode = (exc.stdout or "") if isinstance(exc.stdout, str) else "", -1
    finally:
        sampler.stop()

    return {
        "command": " ".join(cmd[1:]),
        "returncode": returncode,
        "duration_s": round(time.time() - started, 1),
        "stdout_tail": stdout[-1500:],
        "cuda_banner": (m.groups() if (m := CUDA_BANNER.search(stdout)) else None),
        "gpu": {
            "samples": len(sampler.samples),
            "baseline_mb": sampler.baseline_mb,
            "peak_mb": sampler.peak_mb,
            "peak_util_pct": sampler.peak_util,
            "error": sampler.error,
        },
    }


def newest_run(dataset: str) -> Path | None:
    root = PROJECT_ROOT / "runs" / "detect"
    if not root.exists():
        return None
    pattern = re.compile(rf"^{re.escape(dataset)}_auto(?:-\d+)?$")
    dirs = [p for p in root.iterdir() if p.is_dir() and pattern.match(p.name)]
    return max(dirs, key=lambda p: p.stat().st_mtime) if dirs else None


def inspect_run(run_dir: Path, device: str) -> dict:
    weights = run_dir / "weights"
    args_yaml = run_dir / "args.yaml"
    recorded = ""
    if args_yaml.is_file():
        for line in args_yaml.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("device:"):
                recorded = line.split(":", 1)[1].strip()
                break
    return {
        "run": run_dir.name,
        "best_pt": (weights / "best.pt").is_file(),
        "last_pt": (weights / "last.pt").is_file(),
        "results_csv": (run_dir / "results.csv").is_file(),
        "recorded_device": recorded,
        "device_matches": recorded.strip("'\"[] ") == device,
    }


# ----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GPU 通道验收（真跑一次 CUDA 训练）")
    parser.add_argument("--dataset", default="_smoke_test")
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--imgsz", type=int, default=256)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default="0", help="Ultralytics 设备串（'0' = 第一块 CUDA GPU）")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument("--skip-training", action="store_true",
                        help="只做环境与 kernel 检查（秒级，适合快速排查）")
    args = parser.parse_args(argv)

    result: dict = {"dataset": args.dataset, "device": args.device}
    checks: dict[str, bool] = {}

    result["torch"] = torch_report()
    checks["torch 可见 CUDA"] = result["torch"].get("available", False)

    if checks["torch 可见 CUDA"]:
        result["kernel"] = cuda_kernel_check()
        checks["CUDA kernel 结果与 CPU 一致"] = result["kernel"]["ok"]

    if not args.skip_training and checks["torch 可见 CUDA"]:
        model = locate_model(args.model)
        result["model"] = model
        result["training"] = run_training(
            args.dataset, model, args.epochs, args.imgsz, args.batch, args.device
        )
        training = result["training"]
        checks["训练进程退出码 0"] = training["returncode"] == 0

        banner = training["cuda_banner"]
        checks["Ultralytics 选了 GPU（日志出现 CUDA:n）"] = banner is not None
        result["banner"] = banner

        gpu = training["gpu"]
        mem_delta = gpu["peak_mb"] - gpu["baseline_mb"]
        result["vram_delta_mb"] = round(mem_delta, 1)
        checks["显存峰值高于基线 ≥200MB"] = mem_delta >= 200 or gpu["samples"] == 0

        run_dir = newest_run(args.dataset)
        result["artifacts"] = inspect_run(run_dir, args.device) if run_dir else None
        if result["artifacts"]:
            checks["产物齐全（best/last/results.csv）"] = all(
                result["artifacts"][k] for k in ("best_pt", "last_pt", "results_csv")
            )
            checks["args.yaml 记录的 device 与传入一致"] = result["artifacts"]["device_matches"]
        else:
            checks["产物齐全（best/last/results.csv）"] = False
            checks["args.yaml 记录的 device 与传入一致"] = False

    result["checks"] = checks
    failed = [name for name, ok in checks.items() if not ok]
    result["passed"] = not failed

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        t = result["torch"]
        print("=== GPU 通道验收 ===")
        print(f"torch {t['torch']} / CUDA build {t['cuda_build']} / available={t['available']}")
        if t.get("device"):
            print(f"设备: {t['device']}  算力 {tuple(t['capability'])}  "
                  f"显存 {t['vram_free_mb']}/{t['vram_total_mb']} MB 可用")
        if "kernel" in result:
            print(f"kernel 校验: max|Δ| = {result['kernel']['max_abs_diff']:.2e}")
        if "training" in result:
            tr = result["training"]
            print(f"训练: {tr['command']}")
            print(f"  退出码 {tr['returncode']} · 耗时 {tr['duration_s']}s · "
                  f"GPU 利用率峰值 {tr['gpu']['peak_util_pct']:.0f}% · "
                  f"显存 +{result.get('vram_delta_mb', 0):.0f}MB")
            if tr["cuda_banner"]:
                print(f"  日志横幅: CUDA:{tr['cuda_banner'][0]} ({tr['cuda_banner'][1]})")
        print("\n=== 断言 ===")
        for name, ok in checks.items():
            print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        print("\nGPU_SMOKE:", "ALL_PASS" if result["passed"] else f"FAILED={failed}")
        if not result["passed"] and "training" in result:
            print("\n--- 训练输出尾部 ---")
            print(result["training"]["stdout_tail"])

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
