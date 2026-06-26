from pydantic import BaseModel, Field, HttpUrl
from typing import List


class PostContent(BaseModel):
    # Các trường BẮT BUỘC (Không được phép None)
    post_id: str = Field(..., description="ID duy nhất của bài viết")
    actor_id: str = Field(..., description="ID duy nhất của người đăng bài")

    # Các trường cho phép None / Không bắt buộc
    post_url: str | None = None
    content: str | None = None
    created_time: str | None = None
    actor_name: str | None = None
    actor_url: str | None = None
    post_type: str | None = None

    # Các trường mảng danh sách (Mặc định là mảng rỗng thay vì None để dễ vòng lặp)
    attachments_images: List[str] = Field(default_factory=list)
    attachments_videos: List[str] = Field(default_factory=list)


CONFIG_JSON_SAMPLE = {
    "post_id": "Chuỗi JSONPath để lấy post_id (Bắt buộc)",
    "post_url": "Chuỗi JSONPath để lấy post_url (Nếu có)",
    "content": "Chuỗi JSONPath để lấy nội dung bài viết (Nếu có)",
    "created_time": "Chuỗi JSONPath để lấy thời gian tạo (Nếu có)",
    "actor_id": "Chuỗi JSONPath để lấy actor_id (Bắt buộc)",
    "actor_name": "Chuỗi JSONPath để lấy tên tác giả (Nếu có)",
    "actor_url": "Chuỗi JSONPath để lấy url tác giả (Nếu có)",
    "post_type": "Chuỗi JSONPath để lấy loại bài viết (Nếu có)",
    "attachments_images": "Chuỗi JSONPath để lấy mảng danh sách URL hình ảnh",
    "attachments_videos": "Chuỗi JSONPath để lấy mảng danh sách URL video",
}
