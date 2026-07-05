from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol
import logging
import os
import datetime

from playwright.async_api import Page

logger = logging.getLogger(__name__)


def clean_fb_url(url: str) -> str:
    """
    Xóa query string rác và fragment ra khỏi URL Facebook,
    giữ lại param `id` nếu là profile.php để đảm bảo deduplicate chuẩn xác.
    """
    from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

    if not url or not isinstance(url, str):
        return ""
    parsed = urlparse(url)
    if parsed.path.rstrip("/").endswith("profile.php"):
        params = parse_qs(parsed.query, keep_blank_values=False)
        clean_params = {k: v for k, v in params.items() if k == "id"}
        new_query = urlencode({k: v[0] for k, v in clean_params.items()})
        clean = parsed._replace(query=new_query, fragment="")
    else:
        clean = parsed._replace(query="", fragment="")
    return urlunparse(clean).rstrip("/")


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
    email_account: str = field(default_factory=lambda: os.environ.get("FB_EMAIL", ""))
    # pid: int = field(default_factory=os.getpid)
    started_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    seen_entity_urls: set = field(default_factory=set, init=False)

    def __post_init__(self):
        if self.discovery_entity is None:
            self.discovery_entity = []
        else:
            # Loại bỏ trùng lặp và khởi tạo seen_entity_urls từ danh sách hiện có
            unique_list = []
            for item in self.discovery_entity:
                if isinstance(item, dict):
                    raw_url = item.get("entity_url") or item.get("href")
                    if raw_url:
                        clean = clean_fb_url(raw_url)
                        if clean and clean not in self.seen_entity_urls:
                            self.seen_entity_urls.add(clean)
                            item["entity_url"] = clean
                            item["href"] = clean
                            unique_list.append(item)
                elif isinstance(item, str):
                    clean = clean_fb_url(item)
                    if clean and clean not in self.seen_entity_urls:
                        self.seen_entity_urls.add(clean)
                        unique_list.append(clean)
            self.discovery_entity[:] = unique_list

    def add_discovery_entities(self, new_entities: list):
        """
        Thêm danh sách entity vào discovery_entity mà không bị trùng lặp user.
        Sử dụng biến set `seen_entity_urls` để kiểm tra nhanh và chuẩn hóa URL.
        """
        if self.discovery_entity is None:
            self.discovery_entity = []
        if not new_entities:
            return
        for item in new_entities:
            if isinstance(item, dict):
                raw_url = item.get("entity_url") or item.get("href")
                if not raw_url:
                    continue
                clean = clean_fb_url(raw_url)
                if not clean or clean in self.seen_entity_urls:
                    continue
                self.seen_entity_urls.add(clean)
                item["entity_url"] = clean
                item["href"] = clean
                self.discovery_entity.append(item)
            elif isinstance(item, str):
                clean = clean_fb_url(item)
                if not clean or clean in self.seen_entity_urls:
                    continue
                self.seen_entity_urls.add(clean)
                self.discovery_entity.append(clean)


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
