"""GPU 标记用例（`pytest -m gpu`）。默认 CI 排除 —— GitHub 托管的 runner 没有 GPU。

为什么 CPU 侧测试兜不住这三条：**驱动握手、算力匹配、kernel 真的执行**是三件事。
`torch.cuda.is_available()` 只回答第一件；真正会翻车的是后两件（新架构配旧轮子、
DDP 索引写错、UI 的 'auto' 直传 Ultralytics）。

本机执行：``make gpu-smoke``（会先跑这些用例，再跑一次真实的 CUDA 训练）。
"""
import pytest

pytestmark = pytest.mark.gpu


def test_cuda_visible_and_kernel_runs():
    """真算一遍并与 CPU 比对：只有这一步能证明 kernel 在这块卡上跑得动"""
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("本机没有可用的 CUDA 设备")

    torch.manual_seed(0)
    a, b = torch.rand(512, 512), torch.rand(512, 512)
    expected = a @ b
    actual = (a.cuda() @ b.cuda()).cpu()
    torch.cuda.synchronize()

    assert torch.allclose(expected, actual, atol=1e-3), "CUDA 结果与 CPU 不一致"
    assert torch.cuda.get_device_capability(0) >= (5, 0), "算力过低，Ultralytics 不支持"
    assert torch.cuda.mem_get_info(0)[1] > 0, "读不到显存总量"
    assert torch.cuda.get_device_name(0)


def test_ultralytics_selects_cuda_device():
    """真正决定跑在哪的是 Ultralytics 的 select_device，它必须给出 cuda 设备"""
    pytest.importorskip("ultralytics")
    import torch
    from ultralytics.utils.torch_utils import select_device

    if not torch.cuda.is_available():
        pytest.skip("本机没有可用的 CUDA 设备")

    device = select_device("0", verbose=False)
    assert device.type == "cuda", f"select_device('0') 给的是 {device.type}"


def test_device_strings_reach_ultralytics_unchanged():
    """UI 的 'auto (recommended)' 归一成空串，显式索引原样透传。

    Ultralytics **不接受** 'auto'（实测 ``Invalid CUDA 'device=auto' requested``），
    所以这层归一化是必需的 —— 它就是 ``.env.example`` 里踩过的那个坑。
    """
    from src.gradio_app.models.training_state import TrainingConfig

    assert TrainingConfig.from_ui({"device": "auto (recommended)"}).device == ""
    assert TrainingConfig.from_ui({"device": ""}).device == ""
    assert TrainingConfig.from_ui({"device": "0"}).device == "0"
    assert TrainingConfig.from_ui({"device": "0,1"}).device == "0,1"
