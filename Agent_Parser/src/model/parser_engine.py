from typing import Any

from jsonpath_ng.ext import parse


class JsonPathParser:
    @staticmethod
    def _extract(data: dict, jsonpath_expr: str) -> Any:
        matches = [match.value for match in parse(jsonpath_expr).find(data)]

        if not matches:
            return None

        if len(matches) == 1:
            return matches[0]

        return matches

    @classmethod
    def parse(cls, raw_json: dict, config: dict) -> dict:
        result = {}

        for field_name, jsonpath_expr in config.items():

            if jsonpath_expr is None:
                result[field_name] = None
                continue

            try:
                result[field_name] = cls._extract(
                    raw_json,
                    jsonpath_expr,
                )
            except Exception:
                result[field_name] = None

        return result
