import json


def _minify_recursive(data):
    """Hàm Helper ẩn (private) thực hiện đệ quy trên Python Object (dict/list)"""
    ignored_keys = [
        "encrypted_tracking",
        "tracking",
        "trackingdata",
        "is_prod_eligible",
        "client_view_config",
        "extensions",
        "viewability_config",
        "future_of_feed_info",
        "click_tracking_linkshim_cb",
        "encrypted_click_tracking",
    ]

    if isinstance(data, dict):
        cleaned_dict = {}
        for key, value in data.items():
            # 1. Bỏ qua các key rác
            if key in ignored_keys or key.startswith("__module_"):
                continue

            # Đệ quy xử lý các object con
            processed_value = _minify_recursive(value)

            # 2. Rút ngắn chuỗi text dài
            if isinstance(processed_value, str) and len(processed_value) > 120:
                processed_value = processed_value[:40] + "...[LONG_STRING_TRUNCATED]..."

            cleaned_dict[key] = processed_value
        return cleaned_dict

    elif isinstance(data, list):
        # 3. Lấy 1 phần tử làm mẫu cho mảng
        if len(data) > 0:
            return [_minify_recursive(data[0])]
        return []

    else:
        return data


from typing import Union

def clean_and_minify_json(raw_data: Union[str, dict, list]):
    """
    Hàm Wrapper chính: Nhận chuỗi String hoặc dict/list, parse sang JSON (nếu là string), dọn dẹp và trả về Dictionary.
    """
    if isinstance(raw_data, (dict, list)):
        data = raw_data
    elif isinstance(raw_data, str):
        try:
            # Bước 1: Parse từ string sang Python Dict/List
            data = json.loads(raw_data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Đầu vào không phải là chuỗi JSON hợp lệ: {e}")
    else:
        raise ValueError("Đầu vào phải là chuỗi JSON hoặc Python dict/list")

    # Bước 2: Đẩy vào hàm đệ quy để dọn dẹp
    cleaned_data = _minify_recursive(data)

    return cleaned_data
