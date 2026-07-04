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
    consumer = KafkaConsumer().consumer_with_task("crawler_result_entity")
    results_metadata = []
    results_friend_hover = []
    results_user_reaction = []

    count_msg = 0
    for message in consumer:
        count_msg += 1

        # Parse an toàn bằng cách duyệt qua list thay vì dùng index cứng (message[0], message[4], ...)
        # Điều này tránh lỗi crash nếu flow crawl thay đổi số bước hoặc thứ tự các bước
        message_metadata = None
        message_friend_hover = None
        message_user_reaction = None

        if isinstance(message, list):
            for item in message:
                if not isinstance(item, dict):
                    continue
                if "_metadata" in item:
                    message_metadata = item["_metadata"]
                elif "friends" in item:
                    message_friend_hover = item["friends"]
                elif "reaction_users" in item:
                    message_user_reaction = item["reaction_users"]

        target_url = (
            message_metadata.get("target_url") if message_metadata else "Không rõ URL"
        )
        logger.info(f" -> Nhận thành công message #{count_msg} (URL: {target_url})")

        if message_metadata:
            results_metadata.append(message_metadata)
        if message_friend_hover:
            results_friend_hover.append(message_friend_hover)
        if message_user_reaction:
            results_user_reaction.append(message_user_reaction)

    logger.info(f"Kết thúc đọc dữ liệu. Đã xử lý tổng cộng {count_msg} messages.")

    if count_msg == 0:
        logger.warning(
            "Không tìm thấy tin nhắn nào trên topic 'crawler_result_entity'."
        )
        return

    # Tạo DataFrame bằng Pandas
    df_metadata = pd.DataFrame(results_metadata)
    df_friend_hover = pd.DataFrame(results_friend_hover)
    df_user_reaction = pd.DataFrame(results_user_reaction)

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
        df_metadata.to_csv("metadata.csv", index=False, encoding="utf-8")
        logger.info("Đã ghi metadata.csv")
    if not df_friend_hover.empty:
        df_friend_hover.to_csv("friend_hover.csv", index=False, encoding="utf-8")
        logger.info("Đã ghi friend_hover.csv")
    if not df_user_reaction.empty:
        df_user_reaction.to_csv("user_reaction.csv", index=False, encoding="utf-8")
        logger.info("Đã ghi user_reaction.csv")

    # Tính toán các chỉ số an toàn
    count_hover = (
        df_friend_hover["total_hovered"].sum()
        if "total_hovered" in df_friend_hover.columns
        else 0
    )
    count_time_hover = (
        df_friend_hover["time_crawl"].sum()
        if "time_crawl" in df_friend_hover.columns
        else 0
    )
    count_hover_extracted = (
        df_friend_hover["total_user_extract"].sum()
        if "total_user_extract" in df_friend_hover.columns
        else 0
    )
    count_user_reaction = (
        df_user_reaction["count_entity"].sum()
        if "count_entity" in df_user_reaction.columns
        else 0
    )
    count_time_reaction = (
        df_user_reaction["time_execute"].sum()
        if "time_execute" in df_user_reaction.columns
        else 0
    )
    total_time_crawl_extract_user_reactions = (
        total_duration - count_time_hover - 4 * count_msg
    )
    total_time_crawl_extract_user_hover = (
        total_duration - count_time_reaction - 4 * count_msg
    )

    time_tb_crawl_reaction = (
        total_time_crawl_extract_user_reactions / count_msg if count_msg > 0 else 0
    )
    time_tb_crawl_hover = (
        total_time_crawl_extract_user_hover / count_msg if count_msg > 0 else 0
    )
    count_entity_reaction_null = (df_user_reaction["count_entity"] == 0).sum()
    count_entity_hover_null = (df_friend_hover["total_user_extract"] == 0).sum()

    print("\n" + "=" * 50)
    print("           BÁO CÁO THỐNG KÊ CHI TIẾT CRAWL PIPELINE EXTRACT_USER_REACTION")
    print("=")
    print(
        f"tổng thời gian thực thi: {total_time_crawl_extract_user_reactions/60/247:.2f}"
    )
    print("=" * 50)
    print(f"Tổng số message nhận được: {count_msg}")
    print(f"Thời gian trung bình crawl 1 user : {time_tb_crawl_reaction / 60:.2f} phút")
    print(f"Tổng số user thu thập qua reactions: {count_user_reaction}")
    print(f"Tổng thời gian lấy user qua reactions: {count_time_reaction / 60:.2f} phút")
    print(
        f"Tổng số user không thu thập được bạn bè (post không có tương tác reactions hoặc k có bài viết): {count_entity_reaction_null}"
    )
    print(
        f"Trung bình số lượng thu thập được bạn bè trên mỗi user: {count_user_reaction / count_msg:.2f}"
    )
    print(
        f"Tỷ lệ thu thập được bạn bè bằng phương pháp reactions: {(count_msg - count_entity_reaction_null)/ count_msg * 100:.2f}%"
    )
    print("=" * 50 + "\n")

    print("=" * 50 + "\n")
    print(
        "           BÁO CÁO THỐNG KÊ CHI TIẾT CRAWL PIPELINE EXTRACT_USER_FRIEND_HOVER"
    )
    print("=" * 50 + "\n")
    print("=" * 50 + "\n")
    print(f"tổng thời gian thực thi: {total_time_crawl_extract_user_hover/60/247:.2f}")
    print("=" * 50 + "\n")
    print(f"Tổng số message nhận được: {count_msg}")
    print(f"Thời gian trung bình crawl 1 user: {time_tb_crawl_hover / 60/247:.2f} phút")
    print(f"Tổng số user thu thập qua hover: {count_hover_extracted}")
    print(f"Tổng số lượt hover: {count_hover}")
    print(f"Tổng thời gian hover: {count_time_hover / 60/247:.2f} phút")
    print(
        f"Tổng số user không thu thập được bạn bè (nick khóa hiển thị danh sách bạn bè): {count_entity_hover_null}"
    )
    print(
        f"Trung bình số lượng thu thập được bạn bè trên mỗi user: {count_hover_extracted / count_msg:.2f}"
    )
    print(
        f"Tỷ lệ thu thập được bạn bè bằng phương pháp hover: {(count_msg - count_entity_hover_null)/ count_msg * 100:.2f}%"
    )

    print("=" * 50 + "\n")


if __name__ == "__main__":
    thongke()
