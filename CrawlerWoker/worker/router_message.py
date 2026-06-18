import asyncio
import os
import sys
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.browser import BrowserManager
from Kafka.kafka import KafkaConsumer
from toolfb.search_trend import search_trend_fb
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)


async def router_message(message: dict, browser_manager: BrowserManager):
    mission_type = message.get("mission_type")
    if mission_type == "SEARCH_CONTENT":
        query = message.get("query", "")
        content_types = message.get("content_type", ["post"])
        c_type = content_types[0].lower() if content_types else "post"

        object_target = "post"
        if "video" in c_type or "videos" in c_type:
            object_target = "video"
        elif "reels" in c_type or "reels" in c_type:
            object_target = "video"

        arguments = {"query": query, "keyword": query, "object_target": object_target}

        logger.info(f"[*] Điều hướng tác vụ SEARCH_CONTENT: {arguments}")

        await search_trend_fb(arguments, browser_manager)

    elif (
        mission_type == "SEARCH_CONTENT_GROUP" or mission_type == "SEARCH_CONTENT_PAGE"
    ):
        logger.info(
            f"[*] Điều hướng tác vụ SEARCH_CONTENT_GROUP hoặc SEARCH_CONTENT_PAGE: {message}"
        )
        pass
    elif mission_type == "SEARCH_CONTENT_USER":
        logger.info(f"[*] Điều hướng tác vụ SEARCH_CONTENT_USER: {message}")
        pass
    elif mission_type == "DIRECT_COLLECTION":
        logger.error(
            f"[*] Không tìm thấy module xử lý cho mission_type: {mission_type}"
        )
