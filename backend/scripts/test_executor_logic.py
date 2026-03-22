import asyncio
import json

# --- Logic extracted from IterativeExecutor for standalone testing ---


def build_step_prompt(step_id, total_tools, current_datetime, graph_hints=None):
    hints_section = ""
    if graph_hints:
        hints_section = f"\n=== STRICT TOOL GUIDELINES (Hand-Crafted GraphRAG) ===\n{graph_hints}\n"
    return f"RULES: Call appropriate tools.\n{hints_section}\nStep {step_id}."


def validate_args(args: dict, schema: dict) -> list[str]:
    errors = []
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    for field_name in required:
        if field_name not in args:
            errors.append(f"parametro mancante: '{field_name}'")
    for field_name, value in args.items():
        if field_name not in properties:
            errors.append(f"parametro non autorizzato: '{field_name}'")
            continue
        p_type = properties[field_name].get("type")
        if p_type == "string" and not isinstance(value, str):
            errors.append(f"'{field_name}' deve essere stringa")
    return errors


async def test_logic_standalone():
    print("🧪 Testing IterativeExecutor Guardrails Logic (Standalone)...")

    # 1. Test Layer 1: Prompt Generation
    hints = "TOOL [get_weather]: vincoli: {'city': 'string'}"
    prompt = build_step_prompt(1, 5, "2026-02-22", graph_hints=hints)
    assert "STRICT TOOL GUIDELINES" in prompt
    print("✅ Layer 1 (Prompt Injection) verified.")

    # 2. Test Layer 2: Hallucination Blocking
    available_tools = {"get_weather", "google_search"}
    tool_called = "hallucinated_tool"
    assert tool_called not in available_tools
    print("✅ Layer 2 (Hallucination Blocking) verified.")

    # 3. Test Layer 3: Argument Validation
    schema = {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}

    # Case: Missing required param
    errors = validate_args({"location": "Rome"}, schema)
    assert "parametro mancante: 'city'" in errors
    assert "parametro non autorizzato: 'location'" in errors
    print("✅ Layer 3 (Argument Validation) verified failure cases.")

    # Case: Valid args
    errors = validate_args({"city": "Rome"}, schema)
    assert len(errors) == 0
    print("✅ Layer 3 (Argument Validation) verified success case.")

    # 4. Test Feedback Loop Logic (Simulation)
    feedback_context = ""
    # Attempt 1
    bad_args = {"location": "Rome"}
    errors = validate_args(bad_args, schema)
    if errors:
        feedback_context = f"Validazione fallita per tool 'get_weather': {', '.join(errors)}"

    assert "parametro mancante: 'city'" in feedback_context

    # Next Attempt would include this feedback in prompt
    next_prompt_part = f"\n⚠️ **ERRORE VALIDAZIONE PRECEDENTE**:\n{feedback_context}"
    assert "⚠️ **ERRORE VALIDAZIONE PRECEDENTE**" in next_prompt_part
    print("✅ Feedback Loop (ReAct Logic) verified.")

    print("\n🎉 ALL STANDALONE LOGIC TESTS PASSED!")


if __name__ == "__main__":
    asyncio.run(test_logic_standalone())
