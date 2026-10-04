# -*- coding: utf-8 -*-
"""端到端全流程：真实训练 + 真实推理（GPU）。

流程：起后端 → 选本地最小模型 → /trainings/start（data·3ep·320）→ 轮询完成 →
读结果 → 注册版本 → 导出 ONNX（尽力）→ 起推理服务 → /predict 一张真实验证图 →
停服 → 汇总报告 JSON 落盘。

用法: py312 e2e-full.py [--epochs 3] [--imgsz 320] [--dataset data]
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPO = Path(r"E:\项目\Auto-yolo-training")
OUT = REPO / "launcher-design" / "_selfcheck" / "e2e-full-report.json"


def _req(method, url, payload=None, timeout=30):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get("detail", "")
        except Exception:  # noqa: BLE001
            detail = ""
        return exc.code, {"detail": detail}
    except Exception as exc:  # noqa: BLE001
        return 0, {"detail": repr(exc)[:160]}


def _get(base, path, timeout=30):
    return _req("GET", base + path, None, timeout)


def _post(base, path, payload=None, timeout=60):
    return _req("POST", base + path, payload if payload is not None else {}, timeout)


def _post_multipart(url, fields: dict, file_field: str, file_path: Path, timeout=180):
    boundary = "----AYT" + uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
            f'filename="{file_path.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'
        ).encode()
    )
    parts.append(file_path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body2 = r.read()
            return r.status, (json.loads(body2) if body2 else {})
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except Exception:  # noqa: BLE001
            return exc.code, {}
    except Exception as exc:  # noqa: BLE001
        return 0, {"detail": repr(exc)[:160]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--imgsz", type=int, default=320)
    ap.add_argument("--dataset", default="data")
    args = ap.parse_args()

    report = {"steps": [], "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "args": vars(args)}

    def step(name, ok, detail=None):
        report["steps"].append({"name": name, "ok": bool(ok), "detail": detail})
        flag = "PASS " if ok else "FAIL "
        print(flag + name + ("  :: " + str(detail)[:220] if detail is not None else ""), flush=True)

    # 0) 起后端（进程内 uvicorn；训练 worker 以 sys.executable 派生 → 走 GPU 环境）
    BOOT = (
        "import sys; sys.path.insert(0, " + repr(str(REPO)) + ")\n"
        "from src.launcher.backend import LauncherBackend\n"
        "b = LauncherBackend(base_dir=" + repr(str(REPO)) + ")\n"
        "b.start()\n"
        'print("BACKEND_URL=" + b.url, flush=True)\n'
        "import time\nwhile True: time.sleep(3600)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", BOOT],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    base = None
    t0 = time.time()
    while time.time() - t0 < 120:
        line = proc.stdout.readline()
        if line and "BACKEND_URL=" in line:
            base = line.strip().split("BACKEND_URL=")[1]
            break
        if line is None and proc.poll() is not None:
            break
    if not base:
        print("后端未就绪（stdout 见进程输出）")
        proc.kill()
        return 1
    print("backend:", base, flush=True)

    try:
        # 1) 数据集可训练
        _, ds = _get(base, "/api/datasets")
        names = ds.get("datasets", [])
        step("数据集可训练清单", args.dataset in names, names)

        # 2) 选本地模型（优先轻量）
        _, models = _get(base, "/api/models")
        locals_ = [m for m in models.get("models", []) if m.get("local")]
        pick = None
        for pref in ("yolov8n.pt", "yolov8s.pt", "yolov5n.pt", "yolov5s.pt"):
            for m in locals_:
                if m.get("filename") == pref:
                    pick = m["filename"]
                    break
            if pick:
                break
        pick = pick or (locals_[0]["filename"] if locals_ else None)
        step("模型选择（本地轻量优先）", bool(pick), pick)
        if not pick:
            raise RuntimeError("无本地模型可选")

        # 3) 启动训练
        code, res = _post(
            base,
            "/api/trainings/start",
            {
                "dataset_name": args.dataset,
                "model": pick,
                "task": "detect",
                "epochs": args.epochs,
                "imgsz": args.imgsz,
                "batch": 16,
                "workers": 4,
                "cache": False,
                "cos_lr": True,
                "patience": max(3, args.epochs),
            },
            timeout=60,
        )
        step("训练启动", code == 200, res.get("task", res) if code == 200 else res)

        # 4) 轮询训练完成（上限 15 分钟）
        deadline = time.time() + 15 * 60
        last: dict = {}
        while time.time() < deadline:
            _, st = _get(base, "/api/trainings/status")
            last = st
            if st.get("is_running"):
                print(
                    "  … epoch", st.get("current_epoch"), "/", st.get("total_epochs"),
                    "| loss", st.get("current_loss"), "| mAP50", st.get("current_map50"),
                    flush=True,
                )
                time.sleep(6)
            else:
                break
        done_ok = (not last.get("is_running")) and bool(
            last.get("success") or (last.get("current_epoch") or 0) >= args.epochs
        )
        step(
            "训练完成",
            done_ok,
            {
                "epoch": last.get("current_epoch"),
                "total": last.get("total_epochs"),
                "mAP50": last.get("current_map50"),
                "mAP50_95": last.get("current_map50_95"),
                "err": last.get("error_message"),
            },
        )

        # 5) 定位刚训练的 run（weights/best.pt 最新）
        runs_dir = REPO / "runs" / "detect"
        newest = None
        if runs_dir.is_dir():
            cands = sorted(
                [p for p in runs_dir.iterdir() if p.is_dir() and (p / "weights" / "best.pt").is_file()],
                key=lambda p: (p / "weights" / "best.pt").stat().st_mtime,
                reverse=True,
            )
            newest = cands[0].name if cands else None
        step("定位新 run", bool(newest), newest)

        # 6) 注册版本（自动补指标）
        version_id = None
        if newest:
            code, reg = _post(base, "/api/registry/register", {"dataset_name": args.dataset, "run_name": newest, "weights": "best"}, timeout=60)
            step("注册版本", code == 200, reg if code != 200 else reg.get("version_id"))
            version_id = reg.get("version_id") if code == 200 else None

        # 7) 导出 ONNX（尽力而为，非致命）
        if newest:
            code, exp = _post(base, "/api/exports", {"run_name": newest, "fmt": "onnx"}, timeout=420)
            step("导出 ONNX", code == 200, exp if code != 200 else str(exp)[:150])

        # 8) 推理服务启动（自动发现最新 best.pt）
        code, inf = _post(base, "/api/inference/start", None, timeout=180)
        inf_port = (inf or {}).get("port")
        step("推理服务启动", code == 200 and inf.get("status") in ("started", "already_running"), inf)

        # 9) 推理一张真实图片
        if inf_port:
            img = None
            for split in ("val", "train"):
                d = REPO / "dataset" / args.dataset / "images" / split
                if d.is_dir():
                    imgs = sorted(p for p in d.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp"))
                    if imgs:
                        img = imgs[0]
                        break
            if img is None:
                step("推理单图（真实）", False, "找不到测试图")
            else:
                code, det = _post_multipart(
                    f"http://127.0.0.1:{inf_port}/predict",
                    {"conf": "0.25", "iou": "0.45", "imgsz": str(args.imgsz)},
                    "file",
                    img,
                )
                ok = code == 200 and isinstance(det, dict) and ("detections" in det or "results" in det)
                n = len(det.get("detections", det.get("results", []))) if ok else 0
                step("推理单图（真实）", ok, {"img": img.name, "code": code, "n": n, "raw": None if ok else det})

        # 10) 停止推理
        code, stp = _post(base, "/api/inference/stop", None, timeout=90)
        step("推理服务停止", code == 200, stp)

        report["version_id"] = version_id
        report["run"] = newest
        return 0
    finally:
        proc.kill()
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        fails = [s for s in report["steps"] if not s["ok"]]
        print("===== E2E-FULL: " + (f"{len(fails)} FAIL" if fails else "ALL PASS") + f" ({len(report['steps'])} steps) =====", flush=True)
        print("report ->", OUT, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
