"""
core/agent.py — Lớp 3: Vòng lặp điều phối (Perceive → Decide → Act)
=====================================================================
Dùng OpenAI function-calling để ép LLM LUÔN trả về 1 action có cấu trúc.
Không cho phép LLM "nói chuyện tự do" (tool_choice="required").

Vòng lặp:
  1. Quét lại trang qua dom_extractor (text + ảnh)
  2. Gửi state + lịch sử hội thoại cho LLM kèm tool schema
  3. LLM chọn đúng 1 action
  4. Thực thi action qua Playwright (actions.py)
  5. Đưa kết quả vào lịch sử → quay lại bước 1

Cơ chế an toàn:
  - max_steps: giới hạn số bước tránh lặp vô tận
  - history_window: chỉ giữ N bước gần nhất để tránh phình context
  - ask_user: dừng lại khi gặp captcha / tình huống rủi ro
  - done: agent tự báo kết thúc kèm tổng kết

Sử dụng:
    from core.agent import FacebookAgent
    agent = FacebookAgent(task="join group 'Mạng Xã Hội Việt Nam'")
    result = await agent.run(page)
"""

import json
import logging
import os
from typing import Any

from openai import AsyncOpenAI
from playwright.async_api import Page

from core import dom_extractor, actions

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
Bạn là một agent tự động hoá trình duyệt Facebook chạy trên Playwright.
Mỗi bước bạn nhận được:
  - Trạng thái trang hiện tại (danh sách phần tử tương tác với id, role, text)
  - Ảnh chụp màn hình viewport

Nhiệm vụ của bạn là lần lượt thực hiện các hành động để hoàn thành task.
Quy tắc bắt buộc:
  1. LUÔN gọi đúng 1 tool mỗi bước. Không được trả lời tự do.
  2. Dùng `extract_data` ngay khi thấy thông tin quan trọng (tên, tiểu sử, nội quy, …).
  3. Dùng `ask_user` nếu gặp captcha, xác minh, hoặc bất kỳ thứ gì rủi ro.
  4. Gọi `done` kèm tổng kết khi đã hoàn thành hoặc không thể tiến tiếp.
  5. Ưu tiên click vào phần tử TRONG VIEWPORT trước khi scroll.
""".strip()


class FacebookAgent:
    """
    Agent điều phối vòng lặp Perceive → Decide → Act cho một task Facebook.

    Tham số:
        task         — mô tả nhiệm vụ bằng ngôn ngữ tự nhiên
        max_steps    — số bước tối đa (mặc định 40)
        history_window — số bước gần nhất giữ lại trong context (mặc định 10)
        model        — OpenAI model id
    """

    def __init__(
        self,
        task: str,
        max_steps: int = 40,
        history_window: int = 10,
        model: str | None = None,
    ):
        self.task = task
        self.max_steps = max_steps
        self.history_window = history_window
        # Thứ tự ưu tiên: tham số truyền vào → AGENT_MODEL → OPENAI_MODEL → gpt-4o
        self.model = (
            model or os.getenv("AGENT_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4o")
        )

        # Hỗ trợ cả OpenAI và DashScope (Qwen) — đặt OPENAI_BASE_URL trong .env
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")  # None → dùng OpenAI mặc định
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.extracted_data: list[dict] = []
        self.clicked_elements: set[str] = set()
        self.discovery_entity: list[dict] = []

    async def run(self, page: Page) -> dict:
        """
        Chạy vòng lặp điều phối.
        Trả về dict chứa extracted_data và summary cuối cùng.
        """
        # Lịch sử hội thoại: bắt đầu bằng system + task
        history: list[dict] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Task: {self.task}"},
        ]
        tool_schemas = actions.get_tool_schemas()
        summary = ""
        first_capture_avatar = True
        photos_captured = False

        for step in range(1, self.max_steps + 1):
            logger.info(f"[agent] Bước {step}/{self.max_steps}")

            if first_capture_avatar:
                from services.capture_img import capture_avatar

                url_avatar = await capture_avatar(page, self.extracted_data)
                self.extracted_data.append({"url_avatar": url_avatar})
                first_capture_avatar = False

            # ── 1. Perception ──────────────────────────────────────────
            state = await dom_extractor.extract(page)
            user_msg = self._build_perception_message(state)
            history.append(user_msg)

            # Cắt bớt lịch sử cũ (giữ system + task + N bước gần nhất)
            history = _trim_history(history, self.history_window)

            # ── 2. LLM quyết định ──────────────────────────────────────
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=history,
                    tools=tool_schemas,
                    tool_choice="required",  # Ép phải chọn tool
                    max_tokens=512,
                )
            except Exception as e:
                logger.error(f"[agent] Lỗi gọi LLM: {e}")
                break

            msg = response.choices[0].message

            # Đưa phản hồi của model vào lịch sử
            history.append(msg.model_dump(exclude_unset=True))

            # Lấy tool call đầu tiên (bắt buộc có vì tool_choice="required")
            tool_call = msg.tool_calls[0] if msg.tool_calls else None
            if not tool_call:
                logger.warning("[agent] LLM không gọi tool nào. Dừng vòng lặp.")
                break

            action_name = tool_call.function.name
            try:
                params: dict = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                params = {}

            logger.info(f"[agent] Action: {action_name} | params: {params}")

            # ── 3. Thực thi action ─────────────────────────────────────
            if action_name == "click" and params.get("element_id"):
                element_id = params.get("element_id")
                if element_id in self.clicked_elements:
                    result = {
                        "status": "error",
                        "action": "click",
                        "element_id": element_id,
                        "error": "Nút này ĐÃ ĐƯỢC CLICK trước đó rồi! Vui lòng chọn nút khác (hoặc scroll đi chỗ khác).",
                    }
                    logger.warning(f"[agent] Bỏ qua vì bị lặp click: {element_id}")
                else:
                    self.clicked_elements.add(element_id)
                    result = await actions.execute(action_name, page, params)

                current_url = page.url
                if not photos_captured and (
                    "/photos" in current_url or "/photos_of" in current_url
                ):
                    from services.capture_img import capture_photos

                    photos = await capture_photos(page, scroll_rounds=2)
                    photos_captured = True
                    if photos:
                        self.extracted_data.append(
                            {
                                "label": "photos",
                                "content": photos,
                            }
                        )
                    result = {
                        "status": "ok",
                        "action": "click",
                        "element_id": element_id,
                        "message": "Đã click nút, và tôi đã dùng hàm capture_photos để khám phá lấy hết ảnh. Hãy chuyển sang tab khác để crawl",
                    }

            elif action_name == "hover_users":
                # Inject discovery_url_entity để hàm có thể lưu href entity tìm được
                result = await actions.execute(
                    action_name,
                    page,
                    {**params, "discovery_entity": self.discovery_entity},
                )
            else:
                result = await actions.execute(action_name, page, params)

            logger.info(f"[agent] Kết quả: {result}")

            # Đưa kết quả tool vào lịch sử
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

            # ── 4. Xử lý kết quả đặc biệt ─────────────────────────────
            if result.get("action") == "extract_data" and result.get("status") == "ok":
                if url_avatar:
                    # Check if there is
                    self.extracted_data.append(
                        {
                            "label": "avatar",
                            "content": url_avatar,
                        }
                    )
                    url_avatar = None
                self.extracted_data.append(
                    {
                        "label": result.get("label"),
                        "content": result.get("content"),
                    }
                )

            if result.get("status") == "ask_user":
                logger.warning(
                    f"[agent] Agent yêu cầu can thiệp: {result.get('question')}"
                )
                summary = f"[Cần can thiệp] {result.get('question')}"
                break

            if result.get("status") == "done":
                summary = result.get("summary", "")
                logger.info(f"[agent] Hoàn thành: {summary}")
                break

        else:
            logger.warning(f"[agent] Đã đạt giới hạn {self.max_steps} bước.")
            summary = f"Đã đạt giới hạn {self.max_steps} bước."

        return {
            "task": self.task,
            "extracted_data": self.extracted_data,
            "discovery_entity_ralationship": self.discovery_entity,
            "summary": summary,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_perception_message(self, state: dict) -> dict:
        """
        Xây dựng message gửi cho LLM gồm:
          - text mô tả DOM
          - ảnh viewport (vision)
        """
        content: list[dict] = [
            {"type": "text", "text": state["text_snapshot"]},
        ]
        if state.get("screenshot_b64"):
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{state['screenshot_b64']}",
                        "detail": "low",  # "low" tiết kiệm token, "high" cho trang phức tạp
                    },
                }
            )
        return {"role": "user", "content": content}


def _trim_history(history: list[dict], window: int) -> list[dict]:
    """
    Giữ lại:
      - history[0]: system prompt
      - history[1]: task gốc của user
      - history[-window*3:]: N bước gần nhất (mỗi bước ~ 3 message: user/assistant/tool)
    """
    fixed = history[:2]
    sliding = history[2:]
    keep = window * 3  # mỗi bước chiếm ~3 messages
    if len(sliding) > keep:
        sliding = sliding[-keep:]
    return fixed + sliding
