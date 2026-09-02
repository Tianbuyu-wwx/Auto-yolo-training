import time
from pathlib import Path
from src.gradio_app.services.log_service import LogService
from src.gradio_app.services.training_service import TrainingService
from src.gradio_app.models.training_state import TrainingConfig


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
