from .base_step import BaseStep, StepContext

from core import actions
from services.capture_img import capture_photos
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

    async def run(self, ctx: StepContext):
        await actions._scroll(ctx.page, scroll_rounds=10)
        return None


class AboutStep(BaseStep):
    label = "about"

    def build_url(self, ctx: StepContext):
        return _build_section_url(ctx.base_url, "about")

    async def run(self, ctx: StepContext):
        import time

        start_time = time.perf_counter()
        await actions._click_info_page_user(ctx.page)
        await actions._scroll(ctx.page, scroll_rounds=2)
        end_time = time.perf_counter()
        return {"time_execute": end_time - start_time}


class FriendsStep(BaseStep):
    label = "friends"

    def build_url(self, ctx: StepContext):
        return _build_section_url(ctx.base_url, "friends")

    def build_url_group(self, ctx: StepContext):
        return _build_section_url(ctx.base_url, "members")

    async def run(self, ctx: StepContext):
        return await actions._hover_users(
            page=ctx.page,
            scroll_rounds=10,
            hover_delay_ms=600,
            discovery_entity=ctx.discovery_entity,
        )


class UserFromReactionPostEntity(BaseStep):
    label = "reaction_users"

    def build_url(self, ctx: StepContext):
        return f"{ctx.base_url}"

    async def run(self, ctx: StepContext):
        # extract user từ reaction bài post của entity đang crawl
        import time

        start_time = time.perf_counter()
        results = await actions.extract_user_reaction_posts(
            ctx.page, ctx.base_url, count_scroll=5
        )
        ctx.discovery_entity.extend(results)
        end_time = time.perf_counter()
        logger.info(
            f"[crawler] Tìm thấy {len(results)} user reaction mới. Thực hiện crawl trong {end_time-start_time}s"
        )
        return {
            "count_entity": len(results),
            "time_execute": end_time - start_time,
            "discovery_entity": results,
        }


class PhotosStep(BaseStep):
    label = "photos"

    def build_url(self, ctx: StepContext):
        return _build_section_url(ctx.base_url, "photos")

    async def run(self, ctx: StepContext):
        return await capture_photos(ctx.page, scroll_rounds=2)


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
