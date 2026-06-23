import asyncio
import os
import sys
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.browser import BrowserManager
from Kafka.kafka import KafkaConsumer
from toolfb.search_trend import search_trend_fb
from toolfb.collect_group import collect_group
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)


async def router_message(message: dict, browser: BrowserManager):
    mission_type = message.get("mission_type", "")
    logger.info(f"[router] mission_type={mission_type}")

    # ── SEARCH_CONTENT: tìm kiếm bài viết / video theo keyword ──────────────
    if mission_type == "SEARCH_CONTENT":
        query = message.get("query", "")
        content_types = message.get("content_type", ["post"])
        c_type = content_types[0].lower() if content_types else "post"

        object_target = "post"
        if "video" in c_type or "reels" in c_type:
            object_target = "video"

        arguments = {"query": query, "keyword": query, "object_target": object_target}
        logger.info(f"[router] SEARCH_CONTENT → {arguments}")
        await search_trend_fb(arguments, browser)

    # ── SEARCH_CONTENT_GROUP: vào group, join nếu cần, thu thập tab + bài viết
    elif mission_type == "SEARCH_CONTENT_GROUP":
        targets = message.get("targets", [])
        if not targets:
            logger.warning("[router] SEARCH_CONTENT_GROUP: không có targets.")
            return

        for target in targets:
            group_url = target.get("url", "")
            if not group_url:
                continue

            logger.info(f"[router] SEARCH_CONTENT_GROUP → {group_url}")
            result = await collect_group(group_url=group_url, browser=browser)

            if result["status"] == "needs_user":
                logger.warning(
                    f"[router] Group {group_url} cần can thiệp thủ công: {result['summary']}"
                )
            elif result["status"] == "error":
                logger.error(
                    f"[router] Group {group_url} lỗi: {result.get('error')}"
                )
            else:
                logger.info(
                    f"[router] Group {group_url} hoàn tất. "
                    f"Đã extract {len(result['extracted_data'])} mục dữ liệu."
                )
            # TODO: đẩy result['extracted_data'] vào Kafka / DB

    # ── SEARCH_CONTENT_PAGE: tương tự nhưng cho Fanpage ─────────────────────
    elif mission_type == "SEARCH_CONTENT_PAGE":
        # Placeholder — sẽ làm tương tự collect_group nhưng cho page
        logger.info(f"[router] SEARCH_CONTENT_PAGE: {message}")

    # ── SEARCH_CONTENT_PROFILE: thu thập thông tin profile người dùng ────────
    elif mission_type in ("SEARCH_CONTENT_USER", "SEARCH_CONTENT_PROFILE"):
        logger.info(f"[router] SEARCH_CONTENT_PROFILE: {message}")

    # ── DIRECT_COLLECTION: chưa có handler ───────────────────────────────────
    elif mission_type == "DIRECT_COLLECTION":
        logger.warning(f"[router] DIRECT_COLLECTION chưa có handler: {message}")

    else:
        logger.error(f"[router] Không nhận ra mission_type: {mission_type}")
