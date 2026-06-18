import json
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
)
from dotenv import load_dotenv
import os
import sys

import asyncio

# Thêm thư mục gốc và CrawlerWoker vào sys.path để tìm thấy thư mục services và core
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

crawler_worker_dir = os.path.join(root_dir, "CrawlerWoker")
if crawler_worker_dir not in sys.path:
    sys.path.append(crawler_worker_dir)

from services.check_page import dismiss_popups
import logging
import typing
from procedure.procedure_kafka import KafkaProducer
from services.scroll_antibot import smart_scroll_for_api
from AGENT_DISCOVERY.core.browser import BrowserManager

try:
    from AGENT_DISCOVERY.prompt import prompt
except ImportError:
    from prompt import prompt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Giảm độ chi tiết log của các thư viện bên thứ ba
logging.getLogger("kafka").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
load_dotenv()


class Mission(BaseModel):
    mission_type: str
    query: str
    entities: typing.List[str]
    content_type: typing.List[str]
    require_discovery: bool
    confidence: float


class DiscoveryAgent:
    def __init__(self, mission: Mission = None):
        self.mission = mission
        self.model = ChatOpenAI(
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url="https://ws-3nykq9wgm7m2aquj.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
            model="qwen3.5-27b",
        )

    def run(self, mission):
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=mission.model_dump_json()),
        ]

        logger.info("[*] Đang gửi yêu cầu đến LLM (qwen3.5-27b)...")
        try:
            result = self.model.invoke(messages)
            logger.info("[*] LLM đã phản hồi.")
        except Exception as e:
            logger.error(
                f"[-] Lỗi khi gọi LLM (có thể do timeout hoặc rate limit): {e}"
            )
            return None

        try:
            result_json = json.loads(result.content)
        except Exception as e:
            logger.error(f"Lỗi khi parse kết quả: {e}")
            return None

        if result_json:
            logger.info(f"[*] Kết quả từ LLM: {result_json}")
            task_discovery = self.router_task(result_json)
            logger.info(f"[*] Bắt đầu chạy {len(task_discovery)} task discovery...")
            # Dùng asyncio.run() để gọi hàm bất đồng bộ (async) từ trong hàm đồng bộ (sync)
            return asyncio.run(self.worker_task_discovery(task_discovery))
        return []

    async def worker_task_discovery(self, task_discovery):
        self.browser = BrowserManager()
        await self.browser.init_browser()
        url_discovery = []
        for task in task_discovery:
            if task.get("task_type") == "find_group":
                url = f"https://www.facebook.com/search/groups?q={task.get('query')}"
                # Đăng nhập (await) – nếu thất bại đóng trang và bỏ qua task
                login_success = await self.browser.login_fb(url)
                if not login_success:
                    if self.browser.page:
                        await self.browser.page.close()
                    continue

                # login_fb đã navigate về url đúng, chờ mạng ổn định rồi scroll
                try:
                    await self.browser.page.wait_for_load_state(
                        "networkidle", timeout=15000
                    )
                except Exception as e:
                    logger.warning(f"[-] Timeout waiting for page load: {e}")

                # Dismiss in-page popups before scrolling
                await dismiss_popups(self.browser.page)

                await smart_scroll_for_api(self.browser.page, 3)
                data_url = await self.browser.snapshot_url()
                for item in data_url:
                    item_dict = {"type": "group", "url": item}
                    url_discovery.append(item_dict)
                with open("url_group.json", "w", encoding="utf-8") as f:
                    json.dump(data_url, f, ensure_ascii=False, indent=4)
                logger.info(
                    f"[*] URL Discovery: {data_url[0] if data_url else 'Không tìm thấy URL'}"
                )
                await self.browser.page.close()
                self.browser.page = None  # Reset để task tiếp theo tạo page mới

            elif task.get("task_type") == "find_page":
                url = f"https://www.facebook.com/search/pages?q={task.get('query')}"
                login_success = await self.browser.login_fb(url)
                if not login_success:
                    if self.browser.page:
                        await self.browser.page.close()
                    continue

                try:
                    await self.browser.page.wait_for_load_state(
                        "networkidle", timeout=15000
                    )
                except Exception as e:
                    logger.warning(f"[-] Timeout waiting for page load: {e}")

                # Dismiss in-page popups before scrolling
                await dismiss_popups(self.browser.page)

                await smart_scroll_for_api(self.browser.page, 3)
                data_url = await self.browser.snapshot_url()
                for item in data_url:
                    item_dict = {"type": "group", "url": item}
                    url_discovery.append(item_dict)
                with open("url_page.json", "w", encoding="utf-8") as f:
                    json.dump(data_url, f, ensure_ascii=False, indent=4)
                logger.info(
                    f"[*] URL Discovery: {data_url[0] if data_url else 'Không tìm thấy URL'}"
                )
                await self.browser.page.close()
                self.browser.page = None  # Reset để task tiếp theo tạo page mới

            elif task.get("task_type") == "find_profile":
                url = f"https://www.facebook.com/search/users?q={task.get('query')}"
                login_success = await self.browser.login_fb(url)
                if not login_success:
                    if self.browser.page:
                        await self.browser.page.close()
                    continue

                try:
                    await self.browser.page.wait_for_load_state(
                        "networkidle", timeout=15000
                    )
                except Exception as e:
                    logger.warning(f"[-] Timeout waiting for page load: {e}")

                # Dismiss in-page popups before scrolling
                await dismiss_popups(self.browser.page)

                await smart_scroll_for_api(self.browser.page, 3)
                data_url = await self.browser.snapshot_url()
                for item in data_url:
                    item_dict = {"type": "profile", "url": item}
                    url_discovery.append(item_dict)
                with open("url_profile.json", "w", encoding="utf-8") as f:
                    json.dump(data_url, f, ensure_ascii=False, indent=4)
                logger.info(
                    f"[*] URL Discovery: {data_url[0] if data_url else 'Không tìm thấy URL'}"
                )
                await self.browser.page.close()
                self.browser.page = None  # Reset để task tiếp theo tạo page mới


        await self.browser.close_browser()
        with open("url_discovery.json", "w", encoding="utf-8") as f:
            json.dump(url_discovery, f, ensure_ascii=False, indent=4)

        return url_discovery

    def router_task(self, result_json):
        task_discovery = []

        # Ánh xạ từ task_type sang content_type tương ứng
        task_type_map = {
            "search_post": ["posts"],
            "search_reels": ["videos"],
            "search_video": ["videos"],
        }

        for task in result_json.get("tasks", []):
            # Chỉ xử lý các task có priority lớn hơn 70
            if task.get("priority", 0) <= 70:
                continue

            task_type = task.get("task_type")
            content_types = task_type_map.get(task_type)

            if content_types:
                mission = Mission(
                    mission_type="SEARCH_CONTENT",
                    query=task.get("query"),
                    entities=[],
                    content_type=content_types,
                    require_discovery=False,
                    # Nếu confidence là None thì mặc định là 0.8
                    confidence=float(task.get("confidence") or 0.8),
                )
                self.push_queue(mission.model_dump())
            else:
                task_discovery.append(task)

        return task_discovery

    def push_queue(self, data):
        kafka_producer = KafkaProducer()
        kafka_producer.send_message("task_queue_crawl", data)
        kafka_producer.flush()
        logger.info("Đã đẩy mission vào queue")
