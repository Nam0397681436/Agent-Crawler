import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model.parser_engine import JsonPathParser

with open(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "config",
        "config-group-post.json",
    ),
    "r",
    encoding="utf-8",
) as f:
    CONFIG = json.load(f)


def main():

    with open("test_post_group.json", "r", encoding="utf-8") as f:
        raw_json = json.load(f)

    parsed_result = JsonPathParser.parse(
        raw_json=raw_json,
        config=CONFIG,
    )
    with open("data_model_post_group.json", "w", encoding="utf-8") as f:
        json.dump(parsed_result, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
