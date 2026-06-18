import json
import logging
from services.check_page import handle_popup
from services.scroll_antibot import smart_scroll_for_api
from typing import TYPE_CHECKING
import mcp.types as types

if TYPE_CHECKING:
    from core.browser import BrowserManager

logger = logging.getLogger(__name__)


async def search_trend_fb(arguments, browser_manager: "BrowserManager"):
    keyword = arguments.get("query") or arguments.get("keyword")

    if not browser_manager.context:
        return [
            types.TextContent(
                type="text",
                text=f" error: KHÔNG TÌM THẤY TRÌNH DUYỆT",
            )
        ]
    url = build_url_search_trend(arguments, keyword)
    
    # Mở một page mới từ context đã đăng nhập của browser_manager
    page = await browser_manager.context.new_page()

    try:
        logger.info(f"[*] Điều hướng tới URL tìm kiếm: {url}")
        await page.goto(url)
        await page.wait_for_timeout(3000)
        try:
            await handle_popup(page)
        except Exception as e:
            logger.error(f"Lỗi khi đóng popup: {e}")

        try:
            pass
            # xử lý captra, xác thực chỗ này
        except Exception as e:
            logger.error(f"Lỗi khi xử lý captra, xác thực: {e}")
            return [
                types.TextContent(
                    type="text",
                    text=f" error: Lỗi captcha/xác thực",
                )
            ]

        logger.info("bắt đầu scroll")
        await smart_scroll_for_api(page)
        logger.info(f"[*] URL: {url}")

        return [
            types.TextContent(
                type="text",
                text=f" URL: {url}",
            )
        ]
    except Exception as e:
        logger.error(f"Lỗi khi search trend: {e}")
        return [
            types.TextContent(
                type="text",
                text=f" error: {str(e)}",
            )
        ]
    finally:
        # Luôn đóng page sau khi đã crawl xong để giải phóng tài nguyên
        try:
            await page.close()
            logger.info("[*] Đã đóng page sau khi hoàn thành task để dọn dẹp.")
        except Exception as e:
            logger.error(f"Lỗi khi đóng page: {e}")


def build_url_search_trend(arguments, keyword: str) -> str:

    object_target = arguments.get("object_target").lower()
    keyword = keyword.replace(" ", "%20")
    object_map = {
        "post": "top",
        "video": "videos",
    }
    object_type = object_map.get(object_target, "top")
    url_search = f"https://www.facebook.com/search/{object_type}/?q={keyword}"

    return url_search


search_trend_tool = {
    "schema": types.Tool(
        name="facebook_search_trend",
        description="""
Tìm kiếm nội dung trên Facebook theo từ khóa và loại đối tượng.

Tool này sẽ:
- Nhận keyword hoặc query từ agent
- Build URL tìm kiếm Facebook theo object_target
- Điều hướng page hiện tại tới URL search
- Đóng popup nếu có
- Scroll trang để kích hoạt lazy load và bắt các API phát sinh
- Trả về URL search đã truy cập

object_target hỗ trợ:
- post: tìm bài viết
- user: tìm người dùng
- video: tìm video
- page: tìm page
- group: tìm group

Dùng tool này khi agent cần tìm trend, chủ đề, keyword hoặc nội dung liên quan trên Facebook.
""",
        inputSchema={
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Từ khóa cần tìm kiếm trên Facebook. Ưu tiên dùng trường này nếu có.",
                },
                "query": {
                    "type": "string",
                    "description": "Câu truy vấn đầu vào. Nếu không có keyword, tool sẽ lấy từ đầu tiên hoặc xử lý query để tìm kiếm.",
                },
                "object_target": {
                    "type": "string",
                    "description": "Loại đối tượng cần tìm: post, user, video, page, group. Mặc định nên dùng post.",
                    "enum": ["post", "user", "video", "page", "group"],
                },
            },
            "required": ["keyword", "query", "object_target"],
        },
    ),
    "handle": search_trend_fb,
}


FACEBOOK_SEARCH_TREND_MODULE = [
    search_trend_tool,
]
