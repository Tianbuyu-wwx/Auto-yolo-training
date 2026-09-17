"""手工验证 TrainingService 的训练链路（进程内模式）。

用法（在仓库根执行）：
    python scripts/verify_training_service.py

会以当前工作目录为 base_dir 启动一次 `_smoke_test` 数据集的最小训练，
并轮询打印 epoch / 阶段，最后打印 success / best_model / 末尾日志。

历史：原为仓库根目录的 `_verify_gradio_training.py`（阶段 0 清理时移到
scripts/ 并改名 —— 它验证的是 TrainingService，与 Gradio 无关）。
"""
import time
from pathlib import Path

from src.gradio_app.models.training_state import TrainingConfig
from src.gradio_app.services.log_service import LogService
from src.gradio_app.services.training_service import TrainingService


def main():
    log_service = LogService()
    service = TrainingService(Path.cwd().resolve(), log_service)
    config = TrainingConfig(
        dataset_name='_smoke_test',
        model='yolov8n.pt',
        epochs=1,
        imgsz=160,
        batch=2,
        optimizer='RAdam',
        cos_lr=True,
        skip_validation=True,
    )
    print('Starting training via TrainingService...')
    service.start(config)
    for i in range(300):
        time.sleep(1)
        status = service.get_status()
        if not status['is_running']:
            break
        if i % 10 == 0:
            print(f"epoch {status['current_epoch']}/{status['total_epochs']} stage={status['current_stage']}")
    else:
        print('TIMEOUT')
        service.stop()

    status = service.get_status()
    print('FINAL success=', status['success'], 'error=', status.get('error_message'))
    print('best_model=', status.get('best_model_path'))
    print('last 10 logs:')
    print('\n'.join(log_service.get_messages(10).split('\n')[-10:]))


if __name__ == '__main__':
    main()
