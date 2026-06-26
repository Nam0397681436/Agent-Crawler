import json
from model.PostContent import CONFIG_JSON_SAMPLE

config_str = json.dumps(CONFIG_JSON_SAMPLE, indent=2, ensure_ascii=False)

# KHÔNG dùng f-string chứa biến chưa khai báo, chỉ dùng biến config_str đã có sẵn
PROMPT_PARSER_POST_PROFILE = f"""
    Bạn là một chuyên gia Data Engineer chuyên thiết kế hệ thống ETL và phân tích cấu trúc Facebook GraphQL.
    Nhiệm vụ của bạn là phân tích Payload JSON đầu vào (do User cung cấp) và sinh ra một cấu hình Mapping (sử dụng cú pháp JSONPath) để hệ thống của tôi tự động trích xuất dữ liệu. 

    CHÚ Ý: Bạn KHÔNG được trích xuất dữ liệu thực tế. Bạn CHỈ tạo ra cấu hình JSONPath.

    YÊU CẦU ĐẦU RA (SCHEMA):
    Hãy trả về một JSON Object duy nhất tuân thủ chính xác theo mẫu dưới đây. Thay thế các đoạn text mô tả bằng biểu thức JSONPath tương ứng tìm được trong Payload:

    {config_str}

    RÀNG BUỘC KỸ THUẬT NGHIÊM NGẶT (CRITICAL RULES):
    1. TRẢ VỀ JSON THUẦN TÚY: Chỉ xuất ra định dạng JSON hợp lệ, bắt đầu bằng '{{' và kết thúc bằng '}}'. Tuyệt đối KHÔNG bọc trong markdown code block (như ```json) và không in thêm bất kỳ lời giải thích nào.
    2. TRƯỜNG BẮT BUỘC: `post_id` và `actor_id` là bắt buộc. Bạn phải tìm ra đường dẫn chính xác, không được để null.
    3. XỬ LÝ DỮ LIỆU MẢNG: Đối với `attachments_images` và `attachments_videos`, biểu thức JSONPath phải được viết để trả về một mảng (ví dụ: sử dụng toán tử wildcard `[*].media.image.uri`).
    4. XỬ LÝ TRƯỜNG THIẾU: Nếu một trường (không bắt buộc) hoàn toàn không tồn tại trong cấu trúc Payload đầu vào, hãy trả về giá trị `null` (không có ngoặc kép) cho trường đó.
"""

prompt_parser_post = {
    "post_profile": PROMPT_PARSER_POST_PROFILE,
    "post_group": PROMPT_PARSER_POST_PROFILE,
    "post_page": PROMPT_PARSER_POST_PROFILE,
}
