import sys
import os

# Thêm thư mục orchestrator và thư mục gốc của dự án vào sys.path để đảm bảo các import chạy chính xác từ mọi thư mục
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
sys.path.append(os.path.dirname(current_dir))

import json
from langchain_openai import ChatOpenAI
from prompt import system_prompt
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from AGENT_DISCOVERY.agent_discovery import DiscoveryAgent
import logging
import typing
from dotenv import load_dotenv
from procedure.procedure_kafka import KafkaProducer

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Target(BaseModel):
    type: str
    url: str


class Mission(BaseModel):
    mission_type: str
    query: str
    entities: typing.List[str] = Field(default_factory=list)
    content_type: typing.List[str] = Field(default_factory=list)
    targets: typing.List[Target] = Field(default_factory=list)
    require_discovery: bool
    confidence: float


class MissionRouter:
    def router(self, mission: Mission):
        if mission.require_discovery:
            urls = self.publish_discovery(mission)
            if urls:
                # Chuyển đổi URLs thành list Mission
                missions = self.wrapp_model_message_discovery(urls)
                # Đẩy batch vào Kafka hiệu quả hơn
                self.publish_queue_batch(missions)
            return urls
        else:
            self.publish_queue(mission)
            return None

    def wrapp_model_message_discovery(
        self, urls: typing.List[dict]
    ) -> typing.List[Mission]:
        missions = []
        for item in urls:
            mission_type = "SEARCH_CONTENT"  # fallback
            if item["type"] == "group":
                mission_type = "SEARCH_CONTENT_GROUP"
            elif item["type"] == "page":
                mission_type = "SEARCH_CONTENT_PAGE"
            elif item["type"] == "profile":
                mission_type = "SEARCH_CONTENT_PROFILE"

            missions.append(
                Mission(
                    mission_type=mission_type,
                    query="",
                    entities=[],
                    content_type=["post"],
                    targets=[Target(type=item["type"], url=item["url"])],
                    require_discovery=False,
                    confidence=1.0,
                )
            )
        return missions

    def publish_discovery(self, mission: Mission):
        logger.info("Đã đẩy mission discovery")
        urls = DiscoveryAgent().run(mission)
        return urls

    def publish_queue(self, mission: Mission):
        logger.info("Đã đẩy mission queue")
        try:
            kafka_producer = KafkaProducer()
            kafka_producer.send_message("task_queue_crawl", mission.model_dump())
            kafka_producer.flush()
            logger.info("Đã đẩy 1 mission vào queue")
        except Exception as e:
            logger.error(f"Lỗi khi đẩy mission vào queue: {e}")

    def publish_queue_batch(self, missions: typing.List[Mission]):
        """Đẩy nhiều mission vào Kafka hiệu quả hơn bằng cách dùng chung 1 kết nối."""
        if not missions:
            return
        logger.info(f"Bắt đầu đẩy batch {len(missions)} mission vào queue...")
        try:
            # Khởi tạo kết nối 1 lần duy nhất
            kafka_producer = KafkaProducer()

            for mission in missions:
                # Chỉ push, không flush ở từng vòng lặp
                kafka_producer.send_message("task_queue_crawl", mission.model_dump())

            # Flush 1 lần duy nhất cuối cùng
            kafka_producer.flush()
            logger.info(f"Đã đẩy thành công {len(missions)} mission vào queue!")
        except Exception as e:
            logger.error(f"Lỗi khi đẩy batch mission vào queue: {e}")


class AgentOrchestrator:
    def __init__(self):
        self.llm = ChatOpenAI(
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url="https://ws-3nykq9wgm7m2aquj.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
            model="qwen3.5-27b",
        )
        self.structured_llm = self.llm.with_structured_output(Mission)
        self.router = MissionRouter()

    def execute(self, user_query: str):
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_query),
        ]

        mission: Mission = self.structured_llm.invoke(messages)
        logger.info(mission)

        urls = self.router.router(mission)
        return urls, mission


if __name__ == "__main__":
    orchestrator = AgentOrchestrator()
    logger.info("Bắt đầu chạy thử nghiệm Orchestrator...")
    urls, mission = orchestrator.execute("vụ phốt dự án SVT của VPBank")
    print("Mission: ", mission.model_dump_json(indent=2))
