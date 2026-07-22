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
from services.redis_client import RedisClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Đổi URL tại đây hoặc truyền qua dòng lệnh ───────────────────────────────
# DEFAULT_URL = "https://www.facebook.com/olas.809605"
# DEFAULT_URL = "https://web.facebook.com/joon.songsang.9"
DEFAULT_URL = "https://web.facebook.com/olan.895936"
# DEFAULT_URL = "https://web.facebook.com/nhoangtan20"
# DEFAULT_URL = "https://web.facebook.com/thangnch"
# DEFAULT_URL = "https://web.facebook.com/Khchauu71"
# DEFAULT_URL = "https://web.facebook.com/profile.php?id=61567177834135"


async def discovery_tree(
    max_depth: int,
    browser: BrowserManager,
    redis: RedisClient = None,
    limit_crawl_enityt: int = 200,
):
    """Best-First Search dùng Redis Priority Queue (ZSET) với giới hạn độ sâu.

    Cơ chế:
    - Mỗi URL có depth riêng, lưu trong Redis HASH (discovery_depth).
    - ZPOPMAX (atomic) lấy URL có score cao nhất → an toàn với multi-worker.
    - Chỉ thêm entities mới vào frontier nếu depth + 1 <= max_depth.
    - URL xuất hiện nhiều lần sẽ có score cao hơn → được crawl trước.
    - Kết quả được publish lên Kafka bên trong collect_facebook(), không cần lưu RAM.
    """
    if redis is None:
        redis = RedisClient()

    worker_id = os.getpid()  # Dùng PID để phân biệt worker khi chạy multi-process

    logger.info(
        f"[discovery_tree][PID={worker_id}] Bắt đầu Best-First Search "
        f"(max_depth={max_depth}, frontier_size={redis.frontier_size()})"
    )

    crawled_count = 0

    while redis.frontier_size() > 0 and crawled_count < limit_crawl_enityt:
        # ZPOPMAX: atomic, chỉ 1 worker nhận được URL này
        item = redis.pop_from_frontier()
        if not item:
            break

        entity_url, score = item
        url_depth = redis.get_url_depth(entity_url)  # Lấy depth của URL từ Redis HASH

        if url_depth == 0:
            # Fallback an toàn: URL không có trong HASH (có thể do lỗi/Redis restart)
            logger.warning(
                f"[discovery_tree][PID={worker_id}] Không tìm thấy depth cho {entity_url}, "
                f"bỏ qua để tránh vượt max_depth."
            )
            continue

        # Check visited SAU khi đã pop (tránh race condition TOCTOU một phần)
        if redis.is_visited(entity_url):
            continue

        logger.info(
            f"[discovery_tree][PID={worker_id}] "
            f"(Depth {url_depth}/{max_depth}, Score={score:.0f}) "
            f"Thu thập: {entity_url}"
        )

        try:
            await browser.rotate_proxy_if_needed()
            result = await collect_facebook(url=entity_url, browser=browser)
            crawled_count += 1  # biến này để giới hạn crawl entity, chẳng hạn đến ngưỡng thì cho tiến trình tạm nghỉ
            redis.mark_visited(entity_url)
            if result is None:
                logger.warning(
                    f"[discovery_tree][PID={worker_id}] Không có dữ liệu trả về cho {entity_url}, bỏ qua seeding."
                )
            else:
                # Chỉ thêm entities mới vào frontier nếu chưa vượt max_depth
                next_depth = url_depth + 1
                if next_depth <= max_depth:
                    for new_entity in result.get("discovery_entity_ralationship", []):
                        new_url = new_entity.get("entity_url") or new_entity.get("href")
                        if not new_url or redis.is_visited(new_url):
                            continue
                        # ZINCRBY tự cộng score nếu URL đã có trong frontier
                        redis.add_to_frontier(new_url, depth=next_depth, score=1.0)

        except (asyncio.CancelledError, KeyboardInterrupt):
            # Khi người dùng nhấn Ctrl+C hoặc tiến trình bị hủy -> Trả lại URL về queue rồi dừng
            logger.warning(
                f"[discovery_tree][PID={worker_id}] Bị dừng giữa chừng. Đang trả lại {entity_url} về queue..."
            )
            redis.add_to_frontier(entity_url, depth=url_depth, score=score)
            break

        except Exception as e:
            err_str = str(e)
            logger.error(
                f"[discovery_tree][PID={worker_id}] Lỗi khi thu thập {entity_url}: {e}"
            )
            if any(
                k in err_str
                for k in [
                    "Connection closed",
                    "Target page, context or browser has been closed",
                    "TargetClosedError",
                    "BrowserContext.new_page",
                ]
            ):
                logger.warning(
                    f"[discovery_tree][PID={worker_id}] Trình duyệt đã đóng. Trả lại {entity_url} về queue và dừng worker."
                )
                redis.add_to_frontier(entity_url, depth=url_depth, score=score)
                break

    logger.info(
        f"[discovery_tree][PID={worker_id}] Hoàn thành. "
        f"Worker này xử lý: {crawled_count} profiles. "
        f"Tổng đã crawl (toàn Redis): {redis.visited_count()} URLs."
    )


async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    logger.info(f"[run_collect] Bắt đầu thu thập gốc: {url}")

    # Khởi tạo Kafka sớm — phát hiện lỗi kết nối trước khi crawl bất kỳ URL nào
    # KafkaPublisher là Singleton: mọi nơi trong chương trình dùng chung 1 producer này
    kafka = KafkaPublisher()
    await kafka.start()

    browser = BrowserManager()
    await browser.start()

    max_depth = 3  # ← Điều chỉnh độ sâu tối đa khám phá entity

    try:
        # Bước 1: Thu thập user gốc (kết quả được publish lên Kafka bên trong collect_facebook)
        result = await collect_facebook(url=url, browser=browser)

        if result is None:
            logger.warning(
                f"[run_collect] Thu thập user gốc thất bại hoặc không có dữ liệu: {url}. "
                f"Bỏ qua giai đoạn discovery."
            )
        else:
            logger.info(f"[run_collect] Đã thu thập user gốc: {result.get('url', url)}")

            # Lưu kết quả root ra file để debug (chỉ file này, không có all_results)
            with open("result.json", "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            discovery_entity = result.get("discovery_entity_ralationship", [])
            logger.info(
                f"[run_collect] discovery_entity_ralationship count: {len(discovery_entity)}"
            )

            # Bước 2: Bắt đầu duyệt Best-First Search với giới hạn max_depth
            if discovery_entity:
                redis = RedisClient()
                redis.mark_visited(url)  # Đánh dấu root URL đã crawl

                # Seed tất cả entities từ root vào frontier với depth=1
                for entity in discovery_entity:
                    seed_url = entity.get("entity_url") or entity.get("href")
                    if seed_url and not redis.is_visited(seed_url):
                        redis.add_to_frontier(seed_url, depth=1, score=1.0)

                logger.info(
                    f"[run_collect] Đã seed {redis.frontier_size()} URLs vào frontier. "
                    f"Bắt đầu duyệt với max_depth={max_depth}."
                )

                await discovery_tree(
                    max_depth=max_depth,
                    browser=browser,
                    redis=redis,
                )
    finally:
        await browser.stop()
        # Flush buffer Kafka và đóng producer — đảm bảo không mất message đang pending
        await kafka.close()
        logger.info("[run_collect] Kafka producer đã đóng sạch.")


if __name__ == "__main__":
    asyncio.run(main())
