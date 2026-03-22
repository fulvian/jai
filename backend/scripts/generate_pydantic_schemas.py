#!/usr/bin/env python3
"""
SOTA 2026: Pydantic-Native Schema Extractor.
Uses Pydantic's TypeAdapter and model_json_schema to extract high-fidelity
JSON Schemas from Python tool signatures, preserving Enums, Literals, and Unions.
"""

import importlib.util
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any, get_type_hints

import yaml
from pydantic import create_model, ConfigDict
from pydantic.json_schema import model_json_schema

# Add src to path to allow importing domains
sys.path.append(str(Path.cwd() / "src"))


def python_type_to_schema(
    name: str, type_hint: Any, default: Any = inspect.Parameter.empty
) -> dict:
    """Uses Pydantic to generate a JSON schema for a specific type hint."""

    # Create a dummy field for the type hint
    field_kwargs = {}
    if default is not inspect.Parameter.empty:
        field_kwargs["default"] = default
    else:
        # Pydantic uses ... for required fields in create_model
        field_kwargs["default"] = ...

    # We create a temporary model to leverage Pydantic's powerful schema generation
    try:
        # Support for list[str] | str etc.
        temp_model = create_model(
            "TempModel",
            __config__=ConfigDict(arbitrary_types_allowed=True),
            **{name: (type_hint, field_kwargs.get("default", ...))},
        )
        full_schema = model_json_schema(temp_model)

        # Extract only the property schema
        prop_schema = full_schema.get("properties", {}).get(name, {})

        # Clean up Pydantic-specific artifacts if any
        if "title" in prop_schema and prop_schema["title"] == name.replace("_", " ").title():
            del prop_schema["title"]

        return prop_schema
    except Exception as e:
        # Fallback for complex types that Pydantic might struggle with in create_model
        return {"type": "string", "description": f"Fallback due to error: {str(e)}"}


def extract_tool_metadata(func: Any) -> dict:
    """Extracts high-fidelity metadata from a function using Pydantic."""
    name = func.__name__
    doc = inspect.getdoc(func) or "No description available."

    sig = inspect.signature(func)
    type_hints = get_type_hints(func)

    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue

        type_hint = type_hints.get(param_name, Any)

        # Generate schema via Pydantic logic
        prop_schema = python_type_to_schema(param_name, type_hint, param.default)

        # Add description from docstring parsing if possible (SOTA 2026)
        # Note: In a real SOTA system, we'd use docstring-parser here.
        # For now, we rely on the type hint and default value.

        properties[param_name] = prop_schema
        if param.default == inspect.Parameter.empty:
            required.append(param_name)

    return {
        "name": name,
        "description": doc.split("\n\n")[0],  # First paragraph as summary
        "constraints": {
            "input_schema": {"type": "object", "properties": properties, "required": required}
        },
        "hard_rules": f"Ensure valid parameters for {name}.",
        "few_shot_examples": [],
    }


def process_domain(domain_path: Path) -> dict:
    """Scans tools in a domain and extracts schemas."""
    domain_name = domain_path.name
    tools_dir = domain_path / "tools"

    if not tools_dir.exists():
        return {}

    domain_data = {
        "version": "2.0",  # SOTA 2026 version
        "domains": {
            domain_name: {
                "description": f"Pydantic-generated domain for {domain_name}",
                "rules": ["Strict parameter validation enforced by Pydantic models."],
            }
        },
        "tools": {},
    }

    for py_file in tools_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue

        module_name = f"me4brain.domains.{domain_name}.tools.{py_file.stem}"
        try:
            # Import module dynamically
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Inspect all functions
            for func_name, func in inspect.getmembers(module, inspect.isfunction):
                # Only tools (non-private, non-helper)
                if not func_name.startswith("_") and func.__module__ == module_name:
                    tool_meta = extract_tool_metadata(func)
                    domain_data["tools"][func_name] = tool_meta

        except Exception as e:
            print(f"Error processing {py_file}: {e}")

    return domain_data


def main():
    base_dir = Path("src/me4brain/domains")
    output_dir = Path("config/prompt_hints/auto_generated_sota")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Process only a few representative domains first for verification
    target_domains = ["finance_crypto", "google_workspace", "web_search"]

    for domain_dir in base_dir.iterdir():
        if domain_dir.is_dir() and domain_dir.name in target_domains:
            print(f"Processing domain (SOTA): {domain_dir.name}")
            domain_yaml = process_domain(domain_dir)

            if domain_yaml and domain_yaml["tools"]:
                output_file = output_dir / f"{domain_dir.name}.yaml"
                with open(output_file, "w") as f:
                    yaml.dump(domain_yaml, f, sort_keys=False, allow_unicode=True)
                print(f"Generated SOTA YAML: {output_file}")


if __name__ == "__main__":
    main()
