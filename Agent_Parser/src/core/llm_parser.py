import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import Any
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

from openai import AsyncOpenAI
import json

# from your_module import KafkaPublisher


class LlmParser:
    def __init__(self):
        self.model = os.getenv("AGENT_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4o")
        # Hỗ trợ cả OpenAI và DashScope (Qwen)
        api_key = os.getenv("DASHSCOPE_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def parse(self, prompt: str, raw_data: dict) -> dict:
        """
        Gửi payload sang LLM để gen cấu hình JSONPath.
        Trả về trực tiếp một Dictionary Python.
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": json.dumps(raw_data, indent=2, ensure_ascii=False),
                    },
                ],
                temperature=0.0,  # Ép về 0.0 để mô hình không sáng tạo thêm rác
                response_format={
                    "type": "json_object"
                },  # BẮT BUỘC: Ép LLM trả về JSON thuần
            )

            # Lấy chuỗi JSON từ kết quả trả về
            result_text = response.choices[0].message.content

            # Chuyển đổi thẳng thành dict để hàm gọi nó có thể dùng ngay
            return json.loads(result_text)

        except Exception as e:
            # Ném lỗi ra ngoài để khối try-except ở tầng API (FastAPI) bắt được
            raise RuntimeError(f"Lỗi khi LLM xử lý cấu hình: {str(e)}")
