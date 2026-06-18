import kafka
import os
import json
from dotenv import load_dotenv

load_dotenv()

kafka_bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


class KafkaConsumer:
    def __init__(self):
        self.consumer = kafka.KafkaConsumer(
            bootstrap_servers=kafka_bootstrap_servers,
            value_deserializer=lambda x: json.loads(x.decode("utf-8")),
        )

    def consumer_with_task(self, topic, offset=None):
        if offset is not None:
            # Để seek được offset cụ thể, ta cần chỉ định rõ Partition (thường là partition 0)
            from kafka import TopicPartition

            partition = TopicPartition(topic, 0)
            self.consumer.assign([partition])
            self.consumer.seek(partition, offset)
        else:
            self.consumer.subscribe(topics=[topic])

        for message in self.consumer:
            yield message.value
