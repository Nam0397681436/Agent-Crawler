from __future__ import annotations

import os

from dotenv import load_dotenv
from redis import Redis
from redis.exceptions import RedisError

load_dotenv()


class RedisClient:
    """
    Quản lý frontier (hàng đợi ưu tiên) và visited URLs cho crawler.

    Frontier dùng Redis ZSET riêng theo từng depth:
        Key: discovery:queue:depth:{N}
        Score: số lần URL xuất hiện trong discovery_entity_relationship
               → score càng cao = URL càng được nhiều profile nhắc đến → ưu tiên crawl trước

    Visited dùng Redis SET:
        Key: discovery:visited
    """

    ACCOUNT_CRAWL = os.getenv("FB_EMAIL")
    _FRONTIER_PREFIX = f"discovery_frontier_{ACCOUNT_CRAWL}"
    _VISITED_KEY = f"discovery_visited_{ACCOUNT_CRAWL}"
    _DEPTH_KEY = f"discovery_depth_{ACCOUNT_CRAWL}"  # HASH: url → depth

    def __init__(self):
        self.client = Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            username=os.getenv("REDIS_USER") or None,
            password=os.getenv("REDIS_PASSWORD") or None,
            decode_responses=True,  # trả về str thay vì bytes, khỏi cần decode thủ công
        )

    def _frontier_key(self) -> str:
        return f"{self._FRONTIER_PREFIX}"

    def add_to_frontier(self, url: str, depth: int, score: float = 1.0) -> None:
        """
        Thêm URL vào frontier, tăng score nếu đã tồn tại.
        HSETNX đảm bảo chỉ lưu depth đầu tiên (sớm nhất) của URL.
        """
        self.client.hsetnx(self._DEPTH_KEY, url, depth)  # Chỉ set nếu chưa có
        self.client.zincrby(self._frontier_key(), score, url)

    def pop_from_frontier(self) -> tuple[str, float] | None:
        """
        Lấy và XÓA URL có điểm ưu tiên cao nhất khỏi frontier của depth.
        Returns: (url: str, score: float) hoặc None nếu hàng đợi rỗng.
        """
        result = self.client.zpopmax(self._frontier_key(), count=1)
        if not result:
            return None
        return result[0]

    def get_frontier(self) -> list[tuple[str, float]]:
        """
        Trả về toàn bộ frontier của toàn bộ chương trình, đã sort theo score GIẢM DẦN.
        URL có score cao nhất (xuất hiện nhiều nhất) đứng đầu.
        Returns: list of (url: str, score: float)
        """
        return self.client.zrevrange(self._frontier_key(), 0, -1, withscores=True)

    def frontier_size(self) -> int:
        """Số URL còn trong frontier của toàn bộ chương trình."""
        return self.client.zcard(self._frontier_key())

    def clear_frontier(self) -> None:
        """Xóa toàn bộ frontier của toàn bộ chương trình."""
        self.client.delete(self._frontier_key())

    def get_url_depth(self, url: str) -> int:
        """Trả về depth của URL đã được lưu. Mặc định là 0 nếu chưa có."""
        val = self.client.hget(self._DEPTH_KEY, url)
        return int(val) if val is not None else 0

    # ── Visited (SET) ─────────────────────────────────────────────────────────

    def mark_visited(self, url: str) -> None:
        """Đánh dấu URL đã được crawl."""
        self.client.sadd(self._VISITED_KEY, url)

    def is_visited(self, url: str) -> bool:
        """Kiểm tra URL đã crawl chưa."""
        return bool(self.client.sismember(self._VISITED_KEY, url))

    def visited_count(self) -> int:
        """Tổng số URL đã crawl."""
        return self.client.scard(self._VISITED_KEY)

    # ── Session management ────────────────────────────────────────────────────

    def clear_all(self, max_depth: int = 10) -> None:
        """
        Reset toàn bộ dữ liệu crawl của session hiện tại.
        Gọi khi bắt đầu session mới để tránh dùng lại dữ liệu cũ.
        """
        self.client.delete(self._frontier_key())
        self.client.delete(self._VISITED_KEY)
        self.client.delete(self._DEPTH_KEY)

    def ping(self) -> bool:
        """Kiểm tra kết nối Redis còn sống không."""
        try:
            return self.client.ping()
        except RedisError:
            return False
