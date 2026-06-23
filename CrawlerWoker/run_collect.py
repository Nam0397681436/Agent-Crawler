"""
run_collect.py — Chạy thu thập thông tin từ bất kỳ URL Facebook nào
=====================================================================
Dùng để test trực tiếp, bỏ qua Kafka / router.

Cách chạy (từ thư mục CrawlerWoker):
    python run_collect.py https://www.facebook.com/zuck
    python run_collect.py https://www.facebook.com/groups/123456
    python run_collect.py https://www.facebook.com/cocacola
"""

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Đổi URL tại đây hoặc truyền qua dòng lệnh ───────────────────────────────
DEFAULT_URL = "https://web.facebook.com/nhoangtan20"


async def discovery_tree(
    deep: int,
    discovery_entities: list,
    browser: BrowserManager,
    visited: set = None,
    all_results: list = None,
):
    if visited is None:
        visited = set()
    if all_results is None:
        all_results = []

    if deep <= 0 or not discovery_entities:
        return all_results

    for entity in discovery_entities:
        url = entity.get("entity_url") if isinstance(entity, dict) else entity
        if not url or url in visited:
            continue

        visited.add(url)
        logger.info(f"[discovery_tree] (Deep {deep}) Tiến hành thu thập URL: {url}")

        try:
            result = await collect_facebook(url=url, browser=browser)
            all_results.append(result)

            new_discovery_entities = result.get("discovery_entity_ralationship", [])
            if new_discovery_entities:
                # Lưu file log tạm cho mỗi url đã thu thập thành công
                out_path = os.path.join(
                    os.path.dirname(__file__), "collect_result_temp.json"
                )
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(all_results, f, ensure_ascii=False, indent=2)

                # Tiếp tục gọi đệ quy cho độ sâu tiếp theo
                await discovery_tree(
                    deep=deep - 1,
                    discovery_entities=new_discovery_entities,
                    browser=browser,
                    visited=visited,
                    all_results=all_results,
                )
        except Exception as e:
            logger.error(f"[discovery_tree] Lỗi khi thu thập {url}: {e}")

    return all_results


async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    logger.info(f"[run_collect] Bắt đầu thu thập gốc: {url}")

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

        # Bước 2: Bắt đầu tiến hành backtrack (DFS) quay lui
        if discovery_entity:
            logger.info(f"[run_collect] Bắt đầu duyệt cây với độ sâu {deep_discovery}")
            await discovery_tree(
                deep=deep_discovery,
                discovery_entities=discovery_entity,
                browser=browser,
                visited=visited_urls,
                all_results=all_results,
            )

        # Lưu kết quả toàn bộ ra file
        out_path = os.path.join(os.path.dirname(__file__), "collect_result.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        logger.info(
            f"[run_collect] Đã lưu toàn bộ kết quả ({len(all_results)} profiles) → {out_path}"
        )

    finally:
        await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
