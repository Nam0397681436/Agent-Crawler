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

    def consumer_with_task(self, topic, offset=None):
        if offset is not None:
            from kafka import TopicPartition

            partition = TopicPartition(topic, 0)
            logger.info(
                f"Assign partition 0 của topic '{topic}' tại offset {offset}..."
            )
            self.consumer.assign([partition])
            self.consumer.seek(partition, offset)
        else:
            logger.info(f"Subscribe vào topic: '{topic}'...")
            self.consumer.subscribe(topics=[topic])

        logger.info("Bắt đầu lắng nghe tin nhắn từ Kafka...")
        for message in self.consumer:
            yield message.value


def thongke():
    consumer = KafkaConsumer().consumer_with_task("crawler_result_entity_new")
    results_metadata = []
    results_friend_hover = []
    results_user_reaction = []
    result_friend_no_hover = []
    result_avatar = []

    count_msg = 0
    for message in consumer:
        count_msg += 1

        # Parse an toàn bằng cách duyệt qua list thay vì dùng index cứng (message[0], message[4], ...)
        # Điều này tránh lỗi crash nếu flow crawl thay đổi số bước hoặc thứ tự các bước
        message_metadata = None
        message_friend_hover = None
        message_user_reaction = None
        message_friend_no_hover = None
        message_avart = None

        if isinstance(message, list):
            for item in message:
                if not isinstance(item, dict):
                    continue
                if "_metadata" in item:
                    message_metadata = item["_metadata"]
                elif "friends" in item:
                    message_friend_no_hover = item["friends"]
                elif "reaction_users" in item:
                    message_user_reaction = item["reaction_users"]
                elif "url_avatar" in item:
                    message_avart = item["url_avatar"]

        target_url = (
            message_metadata.get("target_url") if message_metadata else "Không rõ URL"
        )
        logger.info(f" -> Nhận thành công message #{count_msg} (URL: {target_url})")

        if message_metadata:
            results_metadata.append(message_metadata)
        if message_friend_no_hover:
            result_friend_no_hover.append(message_friend_no_hover)
        if message_user_reaction:
            results_user_reaction.append(message_user_reaction)
        if message_avart:
            result_avatar.append(message_avart)

    logger.info(f"Kết thúc đọc dữ liệu. Đã xử lý tổng cộng {count_msg} messages.")

    if count_msg == 0:
        logger.warning(
            "Không tìm thấy tin nhắn nào trên topic 'crawler_result_entity'."
        )
        return

    # Tạo DataFrame bằng Pandas
    df_metadata = pd.DataFrame(results_metadata)
    df_user_reaction = pd.DataFrame(results_user_reaction)
    df_friend_no_hover = pd.DataFrame(result_friend_no_hover)
    df_avatar = pd.DataFrame(result_avatar)

    # Tính toán thời gian thực thi (duration_seconds = finished_at - started_at)
    total_duration = 0.0
    if (
        not df_metadata.empty
        and "started_at" in df_metadata.columns
        and "finished_at" in df_metadata.columns
    ):
        try:
            df_metadata["started_at"] = pd.to_datetime(df_metadata["started_at"])
            df_metadata["finished_at"] = pd.to_datetime(df_metadata["finished_at"])
            df_metadata["duration_seconds"] = (
                df_metadata["finished_at"] - df_metadata["started_at"]
            ).dt.total_seconds()
            total_duration = df_metadata["duration_seconds"].sum()
        except Exception as e:
            logger.warning(f"Lỗi tính toán thời gian thực thi: {e}")

    # Xuất ra CSV
    if not df_metadata.empty:
        df_metadata.to_csv("metadata_new.csv", index=False, encoding="utf-8")
        logger.info("Đã ghi metadata_new.csv")
    if not df_friend_no_hover.empty:
        df_friend_no_hover.to_csv(
            "friend_no_hover_new.csv", index=False, encoding="utf-8"
        )
        logger.info("Đã ghi friend_no_hover_new.csv")
    if not df_user_reaction.empty:
        df_user_reaction.to_csv("user_reaction_new.csv", index=False, encoding="utf-8")
        logger.info("Đã ghi user_reaction_new.csv")
    if not df_avatar.empty:
        df_avatar.to_csv("avatar_new.csv", index=False, encoding="utf-8")
        logger.info("Đã ghi avatar_new.csv")


if __name__ == "__main__":
    thongke()
