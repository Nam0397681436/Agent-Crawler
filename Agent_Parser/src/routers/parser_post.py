from fastapi import APIRouter, Request, Body
from typing import Any
import os
import json
from services.clean_message import clean_and_minify_json
from core.llm_parser import LlmParser
from model.prompt_parser_post import prompt_parser_post
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

llm_parser = LlmParser()

# Khởi tạo đường dẫn thư mục config (cùng cấp với src)
CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "config")
os.makedirs(CONFIG_DIR, exist_ok=True)


@router.post("/api/parse/group-post")
async def parse_group_post(raw_data: Any = Body(...)):
    try:
        data_cleaned = clean_and_minify_json(raw_data)
        config_parser = await llm_parser.parse(
            prompt_parser_post["post_group"], data_cleaned
        )

        # Lưu kết quả vào config-group-post.json
        file_path = os.path.join(CONFIG_DIR, "config-group-post.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(config_parser, f, indent=2, ensure_ascii=False)

        return {"message": "Group post parsed and saved", "data": config_parser}
    except Exception as e:
        return {"message": f"Group post parse failed: {e}"}


@router.post("/api/parse/profile-post")
async def parse_profile_post(raw_data: Any = Body(...)):
    try:
        data_cleaned = clean_and_minify_json(raw_data)
        config_parser = await llm_parser.parse(
            prompt_parser_post["post_profile"], data_cleaned
        )

        # Lưu kết quả vào config-profile-post.json
        file_path = os.path.join(CONFIG_DIR, "config-profile-post.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(config_parser, f, indent=2, ensure_ascii=False)

        return {"message": "Profile post parsed and saved", "data": config_parser}
    except Exception as e:
        return {"message": f"Profile post parse failed: {e}"}


@router.post("/api/parse/page-post")
async def parse_page_post(raw_data: Any = Body(...)):
    try:
        data_cleaned = clean_and_minify_json(raw_data)
        config_parser = await llm_parser.parse(
            prompt_parser_post["post_page"], data_cleaned
        )

        # Lưu kết quả vào config-page-post.json
        file_path = os.path.join(CONFIG_DIR, "config-page-post.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(config_parser, f, indent=2, ensure_ascii=False)

        return {"message": "Page post parsed and saved", "data": config_parser}
    except Exception as e:
        return {"message": f"Page post parse failed: {e}"}
