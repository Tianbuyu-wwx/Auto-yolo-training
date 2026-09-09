"""
任务队列面板组件（阶段 P3-2）
展示 SQLite 队列中的训练任务，支持刷新与取消
"""

import contextlib

import gradio as gr

from src.task_queue import QueueRunner, TaskQueue


def _tasks_markdown(queue: TaskQueue, limit: int = 30) -> str:
    tasks = queue.list_tasks(limit=limit)
    if not tasks:
        return "队列为空。在「③ 训练」页点击「加入队列」提交训练任务。"

    status_icon = {
        "queued": "🟡", "running": "🟢", "done": "✅",
        "failed": "❌", "cancelled": "⛔", "cancel_requested": "🟠",
    }
    lines = [
        "| # | 数据集 | 模型 | 状态 | 创建时间 | 结束时间 | 备注 |",
        "|---|--------|------|------|----------|----------|------|",
    ]
    for t in tasks:
        cfg = t.get("config", {})
        model = cfg.get("model", "")
        model = f"`{model}`" if model else ""
        icon = status_icon.get(t["status"], "·")
        error = (t.get("error") or "")[:40]
        lines.append(
            f"| {t['id']} | {t['dataset_name']} | {model} "
            f"| {icon} {t['status']} | {(t['created_at'] or '')[:19]} "
            f"| {(t.get('finished_at') or '')[:19]} | {error} |"
        )
    return "\n".join(lines)


def build_queue_panel(queue: TaskQueue, runner: QueueRunner):
    """构建任务队列Tab"""

    gr.Markdown("### 训练任务队列\n任务持久化到 SQLite，Web 重启不丢失；由队列按顺序执行（训练在独立子进程运行）。")
    queue_status_md = gr.Markdown(_tasks_markdown(queue))

    with gr.Row():
        refresh_queue_btn = gr.Button("刷新队列", variant="secondary")

    with gr.Row():
        cancel_id_dropdown = gr.Dropdown(
            choices=[],
            value=None,
            label="要取消的任务 ID",
            interactive=True,
            scale=1,
        )
        cancel_btn = gr.Button("取消任务", variant="stop", scale=1)
    cancel_result_md = gr.Markdown(visible=False)

    refresh_queue_btn.click(
        fn=lambda: (_tasks_markdown(queue), _cancellable_choices(queue)),
        outputs=[queue_status_md, cancel_id_dropdown],
    )

    def _on_cancel(task_id_raw):
        if not task_id_raw:
            return gr.update(value="请先选择任务 ID", visible=True), gr.update()
        with contextlib.suppress(ValueError, TypeError):
            task_id = int(task_id_raw)
            ok = queue.cancel(task_id)
            msg = f"✅ 任务 #{task_id} 已取消" if ok else f"无法取消任务 #{task_id}（不存在或已结束）"
            return gr.update(value=msg, visible=True), _cancellable_choices(queue)
        return gr.update(value="无效的任务 ID", visible=True), gr.update()

    cancel_btn.click(
        fn=_on_cancel,
        inputs=[cancel_id_dropdown],
        outputs=[cancel_result_md, cancel_id_dropdown],
    )

    # 5 秒自动刷新（含 runner 正在执行的提示）
    def _auto_refresh():
        running = runner.current_task_id
        md = _tasks_markdown(queue)
        if running:
            md = f"🏃 正在执行任务 #{running}（子进程内训练）\n\n" + md
        return md, _cancellable_choices(queue)

    timer = gr.Timer(value=5, active=True)
    timer.tick(
        fn=_auto_refresh,
        outputs=[queue_status_md, cancel_id_dropdown],
    )

    return {"queue_status": queue_status_md}


def _cancellable_choices(queue: TaskQueue) -> list[str]:
    return [str(t["id"]) for t in queue.list_tasks(limit=20)
            if t["status"] in ("queued", "running", "cancel_requested")]
