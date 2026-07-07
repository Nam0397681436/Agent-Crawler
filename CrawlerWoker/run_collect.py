import asyncio
import json
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from core.browser import BrowserManager
from toolfb.collect_facebook import collect_facebook
from services.publisher_kafka import KafkaPublisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Đổi URL tại đây hoặc truyền qua dòng lệnh ───────────────────────────────
# DEFAULT_URL = "https://www.facebook.com/olas.809605"
# DEFAULT_URL = "https://www.facebook.com/profile.php?id=100024823654866"
# DEFAULT_URL = "https://web.facebook.com/olan.895936"
# DEFAULT_URL = "https://web.facebook.com/www.unisystem.vn"
# DEFAULT_URL = "https://web.facebook.com/trang.haha.923"
DEFAULT_URL = "https://web.facebook.com/Khchauu71"
# DEFAULT_URL = "https://web.facebook.com/profile.php?id=61567177834135"


async def discovery_tree(
    deep: int,
    discovery_entities: list,
    browser: BrowserManager,
    visited: set = None,
    all_results: list = None,
):
    """Duyệt BFS theo từng level: xử lý hết tất cả entities ở độ sâu hiện tại
    trước, gom entities mới thành next_level, rồi mới tiến sang độ sâu tiếp theo.
    """
    if visited is None:
        visited = set()
    if all_results is None:
        all_results = []

    current_level = list(discovery_entities)
    current_deep = deep

    while current_deep > 0 and current_level:
        next_level = []  # Gom tất cả entities của độ sâu kế tiếp

        logger.info(
            f"[discovery_tree] === Bắt đầu duyệt độ sâu {current_deep} "
            f"({len(current_level)} entities) ==="
        )

        for entity in current_level:
            url = (
                entity.get("entity_url") or entity.get("href")
                if isinstance(entity, dict)
                else entity
            )
            if not url or url in visited:
                continue

            visited.add(url)
            logger.info(f"[discovery_tree] (Deep {current_deep}) Thu thập URL: {url}")

            try:
                await browser.rotate_proxy_if_needed()
                result = await collect_facebook(url=url, browser=browser)
                all_results.append(result)

                # Lưu file log tạm sau mỗi URL thu thập thành công
                out_path = os.path.join(
                    os.path.dirname(__file__), "collect_result_temp.json"
                )
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(all_results, f, ensure_ascii=False, indent=2)

                # Gom entities mới vào next_level (chưa xử lý ngay)
                new_entities = result.get("discovery_entity_ralationship", [])
                next_level.extend(new_entities)

            except Exception as e:
                logger.error(f"[discovery_tree] Lỗi khi thu thập {url}: {e}")

        # Chuyển sang độ sâu tiếp theo
        current_level = next_level
        current_deep -= 1

    return all_results


async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    logger.info(f"[run_collect] Bắt đầu thu thập gốc: {url}")

    # Khởi tạo Kafka sớm — phát hiện lỗi kết nối trước khi crawl bất kỳ URL nào
    # KafkaPublisher là Singleton: mọi nơi trong chương trình dùng chung 1 producer này
    kafka = KafkaPublisher()
    await kafka.start()

    browser = BrowserManager()
    await browser.start()

    deep_discovery = 2
    visited_urls = set([url])
    all_results = []

    try:
        # Bước 1: Thu thập user gốc
        result = await collect_facebook(url=url, browser=browser)
        logger.info(f"[run_collect] Đã thu thập user gốc: {result.get('url', url)}")
        all_results.append(result)

        with open("result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        discovery_entity = result.get("discovery_entity_ralationship", [])
        logger.info(
            f"[run_collect] discovery_entity_ralationship count: {len(discovery_entity)}"
        )

        # Bước 2: Bắt đầu tiến hành duyệt BFS theo từng level
        if discovery_entity:
            logger.info(f"[run_collect] Bắt đầu duyệt cây với độ sâu {deep_discovery}")
            await discovery_tree(
                deep=deep_discovery,
                discovery_entities=discovery_entity,
                browser=browser,
                visited=visited_urls,
                all_results=all_results,
            )

        # # Lưu kết quả toàn bộ ra file
        # out_path = os.path.join(os.path.dirname(__file__), "collect_result.json")
        # with open(out_path, "w", encoding="utf-8") as f:
        #     json.dump(all_results, f, ensure_ascii=False, indent=2)
    finally:
        await browser.stop()
        # Flush buffer Kafka và đóng producer — đảm bảo không mất message đang pending
        await kafka.close()
        logger.info("[run_collect] Kafka producer đã đóng sạch.")


if __name__ == "__main__":
    asyncio.run(main())
