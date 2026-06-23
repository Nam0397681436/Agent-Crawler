"""
run_group.py — Chạy thử thu thập 1 Group URL
=============================================
Dùng để test trực tiếp, bỏ qua Kafka / router.

Cách chạy (từ thư mục CrawlerWoker):
    python run_group.py https://www.facebook.com/groups/123456789

Hoặc sửa GROUP_URL bên dưới rồi chạy:
    python run_group.py
"""

import asyncio
import json
import logging
import sys
import os

# Đảm bảo import đúng từ thư mục CrawlerWoker
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from core.browser import BrowserManager
from toolfb.collect_group import collect_group

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Đổi URL tại đây hoặc truyền qua dòng lệnh ────────────────────────────────
DEFAULT_URL = "https://web.facebook.com/groups/shakkyprivategroup"


async def main():
    group_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    logger.info(f"[run_group] Bắt đầu thu thập: {group_url}")

    browser = BrowserManager()
    await browser.start()

    try:
        result = await collect_group(group_url=group_url, browser=browser)

        print("\n" + "=" * 60)
        print(f"URL     : {result['url']}")
        print(f"Status  : {result['status']}")
        print(f"Summary : {result.get('summary', '')}")
        print(f"\nExtracted data ({len(result.get('extracted_data', []))} mục):")
        for item in result.get("extracted_data", []):
            print(f"  [{item['label']}] {item['content'][:200]}")
        print("=" * 60)

        # Lưu kết quả ra file
        out_path = os.path.join(os.path.dirname(__file__), "group_result.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"[run_group] Đã lưu kết quả vào: {out_path}")

    finally:
        await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
