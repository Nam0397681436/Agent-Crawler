"""
steps/start_pipeline.py — CrawlerInfo: phiên bản refactor dùng StepPipeline
============================================================================
Kế thừa FacebookCrawler để tái dùng các method phụ trợ (_clean_url,
_capture_avatar, _safe_goto, _publish_result), chỉ override run_user_profile
và run_group bằng kiến trúc pipeline mới.

Thêm step mới: tạo class kế thừa BaseStep trong steps/step_crawl.py,
append instance vào list `steps` trong method tương ứng.
"""

import logging

from playwright.async_api import Page

from core.fb_crawler import FacebookCrawler
from steps import (
    StepContext,
    StepPipeline,
    HomeStep,
    AboutStep,
    FriendsStep,
    PhotosStep,
    UserFromReactionPostEntity,
)

logger = logging.getLogger(__name__)


class CrawlerInfo(FacebookCrawler):
    """
    Phiên bản pipeline của FacebookCrawler.
    Kế thừa toàn bộ helper methods, override run_user_profile và run_group.
    """

    async def safe_goto(self, page: Page, url: str) -> bool:
        """Adapter đáp ứng Navigator protocol cho StepPipeline."""
        return await self._safe_goto(page, url)

    async def run_user_profile(self, page: Page) -> dict:
        """
        Pipeline cho trang cá nhân (User Profile).

        Thêm step mới: tạo 1 class kế thừa BaseStep trong
        steps/step_crawl.py, rồi append instance vào list `steps` bên dưới.
        Không cần sửa logic điều phối ở đây nữa.
        """
        base_url = self._clean_url(page.url)
        logger.info(f"[crawler] base_url (clean): {base_url}")
        await self._capture_avatar(page)

        ctx = StepContext(
            page=page,
            base_url=base_url,
            discovery_entity=self.discovery_entity,
            extracted_data=self.extracted_data,
        )
        friends_step = FriendsStep()
        friends_step.fallback_step = UserFromReactionPostEntity()

        pipeline_crawl_user = StepPipeline(
            steps=[
                HomeStep(),
                AboutStep(),
                # friends_step, usecase này đẻ chạy test sau
                FriendsStep(),
                UserFromReactionPostEntity(),
                PhotosStep(),
            ],
            navigator=self,
        )

        await pipeline_crawl_user.run(ctx)

        logger.info("[crawler] Hoàn thành pipeline user profile.")
        return await self._publish_result()

    async def run_group(self, page: Page) -> dict:
        """
        Pipeline cho trang Nhóm (Group).

        Thêm step mới: tạo 1 class kế thừa BaseStep trong
        steps/step_crawl.py, rồi append instance vào list `steps` bên dưới.
        """
        from steps.step_crawl import HomeGroupStep, AboutGroupStep, MembersStep

        base_url = self._clean_url(page.url)
        logger.info(f"[crawler] base_url (clean): {base_url}")
        await self._capture_avatar(page)

        ctx = StepContext(
            page=page,
            base_url=base_url,
            discovery_entity=self.discovery_entity,
            extracted_data=self.extracted_data,
        )

        pipeline = StepPipeline(
            steps=[
                HomeGroupStep(),
                AboutGroupStep(),
                MembersStep(),
            ],
            navigator=self,
        )

        await pipeline.run(ctx)

        logger.info("[crawler] Hoàn thành pipeline group.")
        return await self._publish_result()
