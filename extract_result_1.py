import kafka
import os
import json
import logging
from dotenv import load_dotenv
import pandas as pd

# Cấu hình log để hiện ra console
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()

kafka_bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


class KafkaConsumer:
    def __init__(self):
        logger.info(
            f"Đang kết nối tới Kafka Bootstrap Servers: {kafka_bootstrap_servers}..."
        )
        # Thêm auto_offset_reset='earliest' để đọc từ đầu topic
        # Thêm consumer_timeout_ms=5000 để tự động thoát vòng lặp khi hết message mới sau 5 giây (để hiển thị thống kê)
        self.consumer = kafka.KafkaConsumer(
            bootstrap_servers=kafka_bootstrap_servers,
            value_deserializer=lambda x: json.loads(x.decode("utf-8")),
            auto_offset_reset="earliest",
            consumer_timeout_ms=5000,
        )
        logger.info("Kết nối Kafka Consumer thành công!")

    def consumer_with_task(self, topic, offset=381):
        if offset is not None:
            from kafka import TopicPartition

            partition = TopicPartition(topic, 0)
            logger.info(
                f"Assign partition 0 của topic '{topic}' tại offset {offset}..."
            )
            self.consumer.assign([partition])
            self.consumer.seek(partition, 381)
        else:
            logger.info(f"Subscribe vào topic: '{topic}'...")
            self.consumer.subscribe(topics=[topic])

        logger.info("Bắt đầu lắng nghe tin nhắn từ Kafka...")
        for message in self.consumer:
            yield message.value


def thongke():
    consumer = KafkaConsumer().consumer_with_task("entity_info_crawl")
    os.makedirs("result", exist_ok=True)

    count_msg = 0
    for message in consumer:
        count_msg += 1

        with open(f"result/entity_info_2.json", "w", encoding="utf-8") as f:
            json.dump(message, f, ensure_ascii=False, indent=4)
        break


if __name__ == "__main__":
    thongke()
