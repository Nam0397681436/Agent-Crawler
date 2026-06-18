import kafka
import os
import json
from dotenv import load_dotenv

load_dotenv()

kafka_bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS")


class KafkaProducer:
    def __init__(self):
        self.producer = kafka.KafkaProducer(
            bootstrap_servers=kafka_bootstrap_servers,
            value_serializer=lambda x: json.dumps(x).encode("utf-8"),
        )

    def send_message(self, topic, message):
        self.producer.send(topic, value=message)

    def flush(self):
        self.producer.flush()
