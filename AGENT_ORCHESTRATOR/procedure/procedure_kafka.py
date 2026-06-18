import kafka
import os
import json
from dotenv import load_dotenv

load_dotenv()

raw_bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
kafka_bootstrap_servers = (
    [s.strip() for s in raw_bootstrap_servers.split(",")]
    if raw_bootstrap_servers
    else ["localhost:9092"]
)


class KafkaProducer:
    def __init__(self):
        self.producer = kafka.KafkaProducer(
            bootstrap_servers=kafka_bootstrap_servers,
            value_serializer=lambda x: json.dumps(x).encode("utf-8"),
        )
        self._checked_topics = set()

    def _ensure_topic_exists(self, topic):
        try:
            admin_client = kafka.admin.KafkaAdminClient(
                bootstrap_servers=kafka_bootstrap_servers
            )
            topics = admin_client.list_topics()
            if topic not in topics:
                new_topic = kafka.admin.NewTopic(
                    name=topic, num_partitions=1, replication_factor=1
                )
                admin_client.create_topics(new_topics=[new_topic])
            admin_client.close()
        except kafka.errors.TopicAlreadyExistsError:
            pass
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(
                f"Không thể tự động tạo topic '{topic}': {e}"
            )

    def send_message(self, topic, message):
        if topic not in self._checked_topics:
            self._ensure_topic_exists(topic)
            self._checked_topics.add(topic)
        self.producer.send(topic, value=message)

    def flush(self):
        self.producer.flush()
