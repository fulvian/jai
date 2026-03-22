import re
import json
from dataclasses import dataclass


@dataclass
class SubQuery:
    text: str
    domain: str
    intent: str = ""


def mock_parse_decomposition(llm_output: str) -> list[SubQuery]:
    # This is a copy of the logic implemented in query_decomposer.py for unit testing
    json_match = re.search(r"\[[\s\S]*\]", llm_output)
    if not json_match:
        raise ValueError(f"No JSON array found in LLM output")

    try:
        parsed = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in LLM output: {e}") from e

    if not isinstance(parsed, list):
        raise ValueError(f"Expected JSON array, got: {type(parsed)}")

    sub_queries = []
    for item in parsed:
        if not isinstance(item, dict):
            continue

        # Defensive parsing: handle both "sub_query" and escaped "\"sub_query\"" keys
        text = ""
        for key_variant in ["sub_query", "text", '"sub_query"', '\\"sub_query\\"']:
            if key_variant in item:
                text = str(item[key_variant]).strip()
                if text:
                    break

        if not text:
            for key in item:
                if "query" in key.lower() or "text" in key.lower():
                    text = str(item[key]).strip()
                    if text:
                        break

        domain = item.get("domain", "").strip()
        intent = item.get("intent", "").strip()

        if not text:
            continue

        sub_queries.append(
            SubQuery(
                text=text,
                domain=domain,
                intent=intent,
            )
        )
    return sub_queries


def run_tests():
    test_cases = [
        {
            "name": "Normal JSON",
            "input": '[{"sub_query": "hello world", "domain": "web"}]',
            "expected": "hello world",
        },
        {
            "name": "Malformed with escaped quotes",
            "input": '[{"\\"sub_query\\"": "broken quotes", "domain": "web"}]',
            "expected": "broken quotes",
        },
        {
            "name": "Literal quotes in string",
            "input": '[{"\\"sub_query\\"": "double broken", "domain": "web"}]',
            "expected": "double broken",
        },
        {
            "name": "Fallback to any query key",
            "input": '[{"Query_text": "fallback logic", "domain": "web"}]',
            "expected": "fallback logic",
        },
        {
            "name": "Using 'text' key",
            "input": '[{"text": "text variant", "domain": "web"}]',
            "expected": "text variant",
        },
    ]

    for tc in test_cases:
        print(f"Running test: {tc['name']}")
        try:
            results = mock_parse_decomposition(tc["input"])
            if results and results[0].text == tc["expected"]:
                print(f"  ✅ PASS: Found '{results[0].text}'")
            else:
                actual = results[0].text if results else "None"
                print(f"  ❌ FAIL: Expected '{tc['expected']}', got '{actual}'")
        except Exception as e:
            print(f"  ❌ ERROR: {e}")


if __name__ == "__main__":
    run_tests()
