from .base_step import BaseStep, StepContext

from core import actions
from services.capture_img import capture_photos
from services.mouse_action import human_like_click
import logging
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

logger = logging.getLogger(__name__)


def _build_section_url(base_url: str, section: str) -> str:
    """
    Build URL đúng cho từng dạng URL Facebook:
      - /username          → /username/section
      - /profile.php?id=X  → /profile.php?id=X&sk=section
    """
    parsed = urlparse(base_url)
    if parsed.path.rstrip("/").endswith("profile.php"):
        params = parse_qs(parsed.query, keep_blank_values=False)
        params["sk"] = [section]
        new_query = urlencode({k: v[0] for k, v in params.items()})
        return urlunparse(parsed._replace(query=new_query))
    else:
        return f"{base_url}/{section}"


# ── User Profile steps ────────────────────────────────────────────────────────


class HomeStep(BaseStep):
    label = "home"

    """TODO: đối với user khóa bảo về trang cá nhân"""

    async def run(self, ctx: StepContext):
        import time

        start_time = time.perf_counter()
        await actions._scroll(ctx.page, scroll_rounds=5)
        return {"time_execute": time.perf_counter() - start_time}


class AboutStep(BaseStep):
    label = "about"

    async def run(self, ctx: StepContext):
        import time

        start_time = time.perf_counter()

        # Click vào tab "Giới thiệu" thay vì navigate URL
        try:
            about_tab = ctx.page.locator(
                'a[role="tab"][href*="/about"]'
            ).first
            await about_tab.wait_for(state="visible", timeout=5000)
            await human_like_click(page=ctx.page, locator=about_tab)
            await ctx.page.wait_for_timeout(1500)
        except Exception as e:
            logger.warning(f"[AboutStep] Không click được tab 'Giới thiệu': {e}")

        await actions._click_info_page_user(ctx.page)
        await actions._scroll(ctx.page, scroll_rounds=3)
        end_time = time.perf_counter()
        return {"time_execute": end_time - start_time}


class FriendsStep(BaseStep):
    label = "friends"

    def build_url(self, ctx: StepContext):
        return _build_section_url(ctx.base_url, "friends")

    def build_url_group(self, ctx: StepContext):
        return _build_section_url(ctx.base_url, "members")

    async def run(self, ctx: StepContext):
        import time

        result = await actions._hover_users(
            page=ctx.page,
            scroll_rounds=15,
            hover_delay_ms=600,
        )
        # Gộp entity tìm được vào ctx.discovery_entity
        ctx.discovery_entity.extend(result.get("discovery_entity", []))
        return result


class FriendsStepNoHover(BaseStep):
    label = "friends"

    def build_url(self, ctx: StepContext):
        return _build_section_url(ctx.base_url, "friends")

    def build_url_group(self, ctx: StepContext):
        return _build_section_url(ctx.base_url, "members")

    async def run(self, ctx: StepContext):
        import time

        start_time = time.perf_counter()
        result = await actions._extract_list_friends(
            page=ctx.page,
            scroll_rounds=15,
        )
        result["time_execute"] = time.perf_counter() - start_time + 2
        # Gộp entity tìm được vào ctx.discovery_entity

        ctx.discovery_entity.extend(result.get("discovery_entity", []))
        logger.info(f"[crawler] Tìm thấy {len(ctx.discovery_entity)} bạn bè mới.")
        if len(result.get("discovery_entity", [])) < 30:
            raise Exception(
                f"Số lượng bạn bè thu thập được ({len(result.get('discovery_entity', []))}) ít hơn 30 nhảy sang luồng crawl user reaction"
            )
        result.pop("discovery_entity", None)

        return result


class UserFromReactionPostEntity(BaseStep):
    label = "reaction_users"

    def build_url(self, ctx: StepContext):
        return f"{ctx.base_url}"

    async def run(self, ctx: StepContext):
        # extract user từ reaction bài post của entity đang crawl
        import time

        start_time = time.perf_counter()
        results = await actions.extract_user_reaction_posts(
            ctx.page, ctx.base_url, count_scroll=10
        )
        ctx.discovery_entity.extend(results)
        end_time = time.perf_counter()
        logger.info(
            f"[crawler] Tìm thấy {len(results)} user reaction mới. Thực hiện crawl trong {end_time-start_time}s"
        )
        return {
            "count_entity": len(results),
            "time_execute": end_time - start_time + 2,
            # "discovery_entity": results,  # hien taij test chyaj 5 worker dang de 10 lan scroll
        }


class PhotosStep(BaseStep):
    label = "photos"

    def build_url(self, ctx: StepContext):
        return _build_section_url(ctx.base_url, "photos")

    async def run(self, ctx: StepContext):
        import time

        start_time = time.perf_counter()
        result = await capture_photos(ctx.page, scroll_rounds=2)

        return {"photos": result, "time_execute": time.perf_counter() - start_time + 2}


class HomeGroupStep(BaseStep):
    label = "home"

    async def run(self, ctx: StepContext):
        await actions._scroll(ctx.page, scroll_rounds=20)
        return None


class AboutGroupStep(BaseStep):
    label = "about"

    def build_url(self, ctx: StepContext):
        return f"{ctx.base_url}/about"

    async def run(self, ctx: StepContext):
        from services.scroll_antibot import smart_scroll_for_api

        await smart_scroll_for_api(
            ctx.page, max_scroll_loops=3, min_wait_ms=600, max_wait_ms=700
        )
        return None


class MembersStep(BaseStep):
    label = "members"

    def build_url(self, ctx: StepContext):
        return f"{ctx.base_url}/members"

    async def run(self, ctx: StepContext):
        return await actions._hover_users(
            page=ctx.page,
            scroll_rounds=20,
            hover_delay_ms=500,
            discovery_entity=ctx.discovery_entity,
        )
