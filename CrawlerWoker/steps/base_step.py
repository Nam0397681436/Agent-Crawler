from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol
import logging
import os
import datetime

from playwright.async_api import Page

logger = logging.getLogger(__name__)


@dataclass
class StepContext:
    """Context dùng chung, truyền xuyên suốt pipeline."""

    page: Page
    base_url: str
    discovery_entity: Any = None
    extracted_data: list = field(default_factory=list)

    # ── Worker metadata ────────────────────────────────────────────────────────
    # Tự động điền từ environment / hệ thống. Có thể override khi khởi tạo ctx.
    worker_id: str = field(
        default_factory=lambda: os.environ.get("WORKER_ID", "worker-default")
    )
    # pid: int = field(default_factory=os.getpid)
    started_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )


@dataclass
class StepResult:
    label: str
    success: bool
    data: Any = None
    error: Optional[str] = None


class Navigator(Protocol):
    """Interface tối thiểu mà pipeline cần để điều hướng trang."""

    async def safe_goto(self, page: Page, url: str) -> bool: ...


class BaseStep(ABC):
    """Một node xử lý trong pipeline."""

    label: str = "base"
    url: Optional[str] = None
    url_group: Optional[str] = None  # fallback url nếu navigate chính fail
    fallback_step: Optional["BaseStep"] = None  # chạy nếu step này thất bại

    def build_url(self, ctx: StepContext) -> Optional[str]:
        """Override nếu url cần build động từ base_url."""
        return self.url

    def build_url_group(self, ctx: StepContext) -> Optional[str]:
        """Override nếu url_group cần build động từ base_url."""
        return self.url_group

    @abstractmethod
    async def run(self, ctx: StepContext) -> Any:
        """Logic xử lý chính của step, không cần tự navigate."""
        ...

    async def execute(self, ctx: StepContext, navigator: Navigator) -> StepResult:
        url = self.build_url(ctx)

        if url:
            ok = await navigator.safe_goto(ctx.page, url)

            if not ok:
                group_url = self.build_url_group(ctx)
                if group_url:
                    logger.warning(
                        f"[crawler] '{self.label}': navigate chính thất bại, "
                        f"thử url_group: {group_url}"
                    )
                    ok = await navigator.safe_goto(ctx.page, group_url)

            if not ok:
                # Cả url chính lẫn url_group (nếu có) đều fail -> skip step này.
                logger.warning(
                    f"[crawler] Bỏ qua bước '{self.label}' do navigate thất bại."
                )
                return StepResult(
                    label=self.label, success=False, error="navigate_failed"
                )

        # Tới đây nghĩa là: không cần url, hoặc url chính ok, hoặc url_group ok.
        try:
            data = await self.run(ctx)
            return StepResult(label=self.label, success=True, data=data)
        except Exception as e:
            logger.exception(f"[crawler] Lỗi ở bước '{self.label}': {e}")
            return StepResult(label=self.label, success=False, error=str(e))
