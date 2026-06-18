from kafka import KafkaProducer
import json


class KafkaProducer:
    def __init__(self):
        self.producer = KafkaProducer(
            bootstrap_servers=["localhost:9092"],
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

    def publish(self, topic, message):
        self.producer.send(topic, value=message)
        self.producer.flush()
