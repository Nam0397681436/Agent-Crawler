import asyncio
import logging
import urllib.parse
import os
from playwright.async_api import Response
from model.factory_capture_api import FactoryRegexApi
from services.publisher_kafka import KafkaPublisher

logger = logging.getLogger(__name__)


class Interceptor:
    def __init__(self, factory: FactoryRegexApi, domain_name: str):
        self.factory = factory
        self.domain_name = domain_name
        self.kafka_publisher = KafkaPublisher()

    async def capture_network(self, response: Response):
        url = response.url
        request = response.request
        pattern_manager = self.factory.get_pattern(self.domain_name)

        if pattern_manager:
            for regex in pattern_manager.skip_compiled:
                if regex.search(url):
                    return

            should_capture = False

            if pattern_manager.extract_compiled:
                for regex in pattern_manager.extract_compiled:
                    if regex.search(url):
                        should_capture = True
                        break
            else:
                should_capture = True

            if not should_capture:
                return
        content_type = response.headers.get("content-type", "")

        is_media = "image" in content_type or "video" in content_type
        is_text = (
            "json" in content_type
            or "text" in content_type
            or "graphql" in content_type
        )

        if not is_media and not is_text:
            return

        # Không bắn vào kafka nếu content_type là image, video (khi biến is_media là True)
        # Tạm thời chỉ bắn api có url bắt đầu bằng https://web.facebook.com/api/graphql/ hoặc chứa about hoặc resource là document
        skip_api_doc = ["/about", "/friends", "/photos", "/members"]
        if (
            not is_media
            and ("/api/graphql/" in url or request.resource_type == "document")
            and not any(skip in url for skip in skip_api_doc)
        ):
            data = None
            try:
                data = await response.text()
            except Exception:
                logger.error(f"Failed to get response text from {url}")

            parsed_url = urllib.parse.urlparse(url)
            path = parsed_url.path
            referer = request.headers.get("referer", "")

            record = {
                "url": url,
                "path": path,
                "refer": referer,
                "method": request.method,
                "status": response.status,
                "resource_type": request.resource_type,
                "content_type": content_type,
                # "post_data": request.post_data,
                "data": data,
            }

            if "about" in url or request.resource_type == "document":
                topic = os.getenv("TOPIC_INFO_ABOUT", "about_entity_info")
            else:
                topic = os.getenv("TOPIC_FB_CRAWL", "api_crawler_fb")

            await self.kafka_publisher.publish(record, topic=topic)
