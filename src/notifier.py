"""
通知模块
支持多种通知渠道：控制台、文件日志、Webhook
"""

import ipaddress
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class NotificationLevel(Enum):
    """通知级别"""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class NotificationMessage:
    """通知消息"""
    title: str
    content: str
    level: NotificationLevel = NotificationLevel.INFO
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content,
            "level": self.level.value,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class BaseNotifier:
    """通知器基类"""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def send(self, message: NotificationMessage) -> bool:
        """发送通知"""
        if not self.enabled:
            return False
        try:
            return self._send_impl(message)
        except Exception as e:
            print(f"通知发送失败: {e}")
            return False

    def _send_impl(self, message: NotificationMessage) -> bool:
        raise NotImplementedError


class ConsoleNotifier(BaseNotifier):
    """控制台通知器"""

    LEVEL_COLORS = {
        NotificationLevel.INFO: "\033[36m",      # 青色
        NotificationLevel.SUCCESS: "\033[32m",   # 绿色
        NotificationLevel.WARNING: "\033[33m",   # 黄色
        NotificationLevel.ERROR: "\033[31m",     # 红色
    }
    RESET = "\033[0m"

    def _send_impl(self, message: NotificationMessage) -> bool:
        color = self.LEVEL_COLORS.get(message.level, "")
        reset = self.RESET if color else ""

        print(f"\n{color}[{message.level.value.upper()}] {message.title}{reset}")
        print(f"{message.content}")
        if message.metadata:
            print(f"元数据: {json.dumps(message.metadata, ensure_ascii=False)}")
        return True


class FileNotifier(BaseNotifier):
    """文件日志通知器"""

    def __init__(self, log_dir: str, enabled: bool = True):
        super().__init__(enabled)
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "notifications.jsonl"

    def _send_impl(self, message: NotificationMessage) -> bool:
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(message.to_dict(), ensure_ascii=False) + "\n")
        return True


class WebhookNotifier(BaseNotifier):
    """Webhook通知器（支持钉钉/企业微信等）"""

    # 允许的 Webhook 域名白名单（支持后缀匹配）
    # 默认仅允许常见企业协作平台；为空列表则允许所有公网域名
    DEFAULT_ALLOWED_DOMAINS: list[str] = [
        "oapi.dingtalk.com",
        "open.feishu.cn",
        "qyapi.weixin.qq.com",
        "hooks.slack.com",
    ]
    ALLOWED_DOMAINS: list[str] = [
        d.strip()
        for d in os.environ.get("YOLO_WEBHOOK_ALLOWED_DOMAINS", "").split(",")
        if d.strip()
    ] or list(DEFAULT_ALLOWED_DOMAINS)

    def __init__(self, webhook_url: str, enabled: bool = True, secret: str | None = None):
        super().__init__(enabled)
        self.webhook_url = webhook_url
        self.secret = secret

    @staticmethod
    def _is_safe_url(url: str) -> bool:
        """检查URL是否安全（防止SSRF攻击）"""
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False
            hostname = parsed.hostname
            if not hostname:
                return False
            try:
                ip = ipaddress.ip_address(hostname)
                # 禁止访问私有/保留地址
                if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                    return False
            except ValueError:
                # 域名而非IP，检查白名单
                allowed_domains = WebhookNotifier.ALLOWED_DOMAINS
                if allowed_domains:
                    hostname_lower = hostname.lower()
                    return any(
                        hostname_lower == domain.lower()
                        or hostname_lower.endswith("." + domain.lower())
                        for domain in allowed_domains
                    )
            return True
        except Exception:
            return False

    def _send_impl(self, message: NotificationMessage) -> bool:
        if not self._is_safe_url(self.webhook_url):
            print("通知发送失败: Webhook URL不安全或指向内网地址")
            return False

        payload = self._build_payload(message)
        data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
        }

        req = urllib.request.Request(
            self.webhook_url,
            data=data,
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status == 200

    def _build_payload(self, message: NotificationMessage) -> dict[str, Any]:
        """构建Webhook请求体（通用格式）"""
        return {
            "msgtype": "text",
            "text": {
                "content": f"[{message.level.value.upper()}] {message.title}\n{message.content}",
            },
        }


class DingTalkNotifier(WebhookNotifier):
    """钉钉通知器"""

    def _build_payload(self, message: NotificationMessage) -> dict[str, Any]:
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": message.title,
                "text": f"### {message.title}\n"
                        f"> **级别**: {message.level.value}\n"
                        f"> **时间**: {message.timestamp}\n"
                        f"> **内容**: {message.content}\n",
            },
        }


class NotifierManager:
    """通知管理器"""

    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).parent.parent
        self.notifiers: list[BaseNotifier] = []

        # 默认添加控制台和文件通知器
        self.add_console_notifier()
        self.add_file_notifier()

    def add_console_notifier(self, enabled: bool = True):
        """添加控制台通知器"""
        self.notifiers.append(ConsoleNotifier(enabled=enabled))

    def add_file_notifier(self, enabled: bool = True):
        """添加文件通知器"""
        log_dir = self.base_dir / "logs"
        self.notifiers.append(FileNotifier(str(log_dir), enabled=enabled))

    def add_webhook_notifier(self, webhook_url: str, enabled: bool = True, notifier_type: str = "generic"):
        """
        添加Webhook通知器

        Args:
            webhook_url: Webhook地址
            enabled: 是否启用
            notifier_type: 通知器类型 (generic/dingtalk)
        """
        if notifier_type == "dingtalk":
            notifier = DingTalkNotifier(webhook_url, enabled=enabled)
        else:
            notifier = WebhookNotifier(webhook_url, enabled=enabled)
        self.notifiers.append(notifier)

    def notify(
        self,
        title: str,
        content: str,
        level: NotificationLevel = NotificationLevel.INFO,
        metadata: dict[str, Any] | None = None,
    ) -> list[bool]:
        """
        发送通知到所有通知器

        Args:
            title: 通知标题
            content: 通知内容
            level: 通知级别
            metadata: 附加元数据

        Returns:
            每个通知器的发送结果列表
        """
        message = NotificationMessage(
            title=title,
            content=content,
            level=level,
            metadata=metadata or {},
        )

        results = []
        for notifier in self.notifiers:
            results.append(notifier.send(message))

        return results

    def notify_training_start(self, dataset_name: str, config: dict[str, Any]):
        """训练开始通知"""
        return self.notify(
            title=f"训练开始: {dataset_name}",
            content=f"数据集: {dataset_name}\n配置: {json.dumps(config, ensure_ascii=False, indent=2)}",
            level=NotificationLevel.INFO,
            metadata={"event": "training_start", "dataset": dataset_name},
        )

    def notify_training_complete(
        self,
        dataset_name: str,
        metrics: dict[str, Any],
        duration: float,
    ):
        """训练完成通知"""
        return self.notify(
            title=f"训练完成: {dataset_name}",
            content=f"数据集: {dataset_name}\n"
                    f"耗时: {duration:.2f}秒\n"
                    f"指标: {json.dumps(metrics, ensure_ascii=False, indent=2)}",
            level=NotificationLevel.SUCCESS,
            metadata={"event": "training_complete", "dataset": dataset_name, "duration": duration},
        )

    def notify_training_error(self, dataset_name: str, error: str):
        """训练错误通知（整流水线异常）"""
        return self.notify(
            title=f"训练失败: {dataset_name}",
            content=f"数据集: {dataset_name}\n错误: {error}",
            level=NotificationLevel.ERROR,
            metadata={"event": "training_error", "dataset": dataset_name},
        )

    def notify_stage_failed(
        self,
        dataset_name: str,
        stage: str,
        error: str,
        details: str | None = None,
    ) -> list[bool]:
        """流水线阶段失败通知（验证/配置/训练/评估/导出 任意阶段）。

        设计变更（2026-09-02）：原 ``notify_training_error`` 只在 except 块触发，
        阶段级失败（如数据验证未通过）只会局部 _finalize(False) 而不通知。
        新增此方法以便用户能精确知道是哪一阶段挂了。
        """
        content = f"数据集: {dataset_name}\n阶段: {stage}\n错误: {error}"
        if details:
            content += f"\n详情: {details}"
        return self.notify(
            title=f"阶段失败 [{stage}]: {dataset_name}",
            content=content,
            level=NotificationLevel.ERROR,
            metadata={"event": "stage_failed", "dataset": dataset_name, "stage": stage},
        )

    def notify_evaluation_complete(
        self,
        dataset_name: str,
        model_path: str,
        metrics: dict[str, Any],
    ):
        """评估完成通知"""
        return self.notify(
            title=f"评估完成: {dataset_name}",
            content=f"模型: {model_path}\n"
                    f"mAP@50: {metrics.get('mAP50', 0):.4f}\n"
                    f"mAP@50-95: {metrics.get('mAP50_95', 0):.4f}",
            level=NotificationLevel.SUCCESS,
            metadata={"event": "evaluation_complete", "dataset": dataset_name},
        )


def create_notifier(
    webhook_url: str | None = None,
    webhook_type: str = "generic",
    base_dir: str | None = None,
) -> NotifierManager:
    """
    创建通知管理器便捷函数

    Args:
        webhook_url: Webhook地址
        webhook_type: Webhook类型
        base_dir: 项目根目录

    Returns:
        NotifierManager对象
    """
    manager = NotifierManager(base_dir)

    if webhook_url:
        manager.add_webhook_notifier(webhook_url, notifier_type=webhook_type)

    return manager


if __name__ == "__main__":
    # 测试通知功能
    notifier = create_notifier()

    notifier.notify("测试通知", "这是一条测试消息", NotificationLevel.INFO)
    notifier.notify_training_start("test_dataset", {"model": "yolov8s.pt", "epochs": 100})
    notifier.notify_training_complete(
        "test_dataset",
        {"mAP50": 0.85, "mAP50_95": 0.42},
        3600.0,
    )
