import json
import logging

logger = logging.getLogger(__name__)


def bulk_route_parser_worker(raw_data: str) -> bool:
    """
    Parser API bulk-route-definitions bắt được khi hover user card.
    Trả về True nếu data chứa entity hợp lệ (có payloads với key không có dấu chấm).
    """
    if not raw_data:
        logger.warning("[bulk_parser] Không có body data.")
        return False

    try:
        # Xử lý format đặc thù của Facebook (thường bắt đầu bằng for (;;);)
        clean_data = raw_data
        if clean_data.startswith("for (;;);"):
            clean_data = clean_data.replace("for (;;);", "", 1)

        json_data = json.loads(clean_data)
        result = _check_extract_info(json_data)
        logger.info(f"[bulk_parser] parse xong → is_entity={result}")
        return result

    except json.JSONDecodeError:
        logger.error("[bulk_parser] Không thể parse JSON từ response.")
        return False
    except Exception as e:
        logger.error(f"[bulk_parser] Lỗi không xác định: {e}")
        return False


def _check_extract_info(bulk_data: dict) -> bool:
    """
    Kiểm tra JSON có chứa payload.payloads với key entity hợp lệ không.
    Key hợp lệ: không chứa dấu chấm (.) — thường là đường dẫn profile user/group/page.
    """
    payload = bulk_data.get("payload", {})
    payloads = payload.get("payloads", {})

    if not payloads:
        return False

    keys_list = list(payloads.keys())
    if len(keys_list) > 1:
        return True
    if len(keys_list) == 1:
        key_item = keys_list[0]
        return "." not in key_item

    return True
