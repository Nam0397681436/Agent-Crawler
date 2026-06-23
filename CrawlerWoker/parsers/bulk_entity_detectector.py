import json
import re


async def detect_info_entity(bulk_data: dict) -> bool:
    payload = bulk_data.get("payload", {})
    payloads = payload.get("payloads", {})

    if not payloads:
        return False

    sub_keys = list(payloads.keys())

    valid_keys = []
    for item in sub_keys:
        if "." in item:
            continue
        valid_keys.append(item)

    return True if valid_keys else False
