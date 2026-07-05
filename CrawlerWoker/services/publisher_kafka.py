import json
import os
import sys
import asyncio
import logging
from kafka import KafkaProducer
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Tắt toàn bộ log rác nội bộ của thư viện kafka-python, chỉ giữ lại lỗi cực kỳ nghiêm trọng
logging.getLogger("kafka").setLevel(logging.ERROR)
logging.getLogger("kafka.conn").setLevel(logging.ERROR)
logging.getLogger("kafka.producer").setLevel(logging.ERROR)


class KafkaPublisher:
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(KafkaPublisher, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "initialized"):
            self.bootstrap_servers = os.getenv(
                "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
            )
            self.default_topic = os.getenv("TOPIC_FB_CRAWL", "api_crawler_fb")
            self.producer = None
            self.initialized = True

    def _create_producer(self):
        # Khởi tạo đồng bộ KafkaProducer của kafka-python
        return KafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            compression_type="gzip",
            linger_ms=200,  # Đợi 200ms để gộp message
            batch_size=524288,  # Kích thước batch tối đa 512KB
            acks=1,
            request_timeout_ms=5000,
            max_block_ms=10000,  # Chờ tối đa 10 giây nếu buffer đầy do rớt mạng
            max_request_size=5242880,  # Tăng giới hạn dung lượng 1 payload lên 5MB
        )

    async def start(self):
        if not self.producer:
            async with self._lock:
                if not self.producer:
                    try:
                        # Đưa việc kết nối xuống Thread để không làm đơ Playwright
                        self.producer = await asyncio.to_thread(self._create_producer)
                        logger.info("Kafka Producer started successfully.")
                    except Exception as e:
                        logger.critical(
                            f"FATAL ERROR: Không thể kết nối Kafka lúc khởi động ({e}). Dừng Crawler!"
                        )
                        os._exit(1)

    async def publish(self, data: dict, topic: str = None):
        """
        Bắn dữ liệu vào Kafka. Sử dụng kafka-python đồng bộ bọc trong Thread.
        """
        if not self.producer:
            await self.start()

        target_topic = topic or self.default_topic

        try:
            # Gọi hàm send() đồng bộ bằng to_thread để không nghẽn Event Loop.
            # Nếu Kafka sập -> buffer bị đầy -> hàm send() sẽ bị block đứng yên 10s trong Thread.
            # Nếu sau 10s vẫn kẹt, văng lỗi Exception -> kích hoạt lệnh tắt Crawler.
            await asyncio.to_thread(self.producer.send, target_topic, value=data)
            logger.info("Message successfully buffered to Kafka")
        except Exception as e:
            logger.critical(
                f"FATAL ERROR: Rớt kết nối Kafka khi đang gửi data ({e}). Dừng toàn bộ hệ thống để bảo toàn dữ liệu!"
            )
            os._exit(1)

    async def close(self):
        if self.producer:
            # Flush đẩy hết message đang buffer trước khi đóng kết nối
            await asyncio.to_thread(self.producer.flush)
            await asyncio.to_thread(self.producer.close)
            self.producer = None
            logger.info("Kafka Producer closed cleanly.")
