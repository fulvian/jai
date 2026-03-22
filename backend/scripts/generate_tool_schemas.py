#!/usr/bin/env python3
import ast
import os
from pathlib import Path
import yaml


def parse_type_annotation(node):
    """Simple parser for AST type annotations."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Subscript):
        # Handle dict[str, Any] etc
        value = parse_type_annotation(node.value)
        slice_val = parse_type_annotation(node.slice)
        return f"{value}[{slice_val}]"
    if isinstance(node, ast.Attribute):
        return f"{parse_type_annotation(node.value)}.{node.attr}"
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.Tuple):
        return f"({', '.join(parse_type_annotation(e) for e in node.elts)})"
    return "Any"


def python_type_to_json_schema(py_type_str: str) -> dict:
    if "str" in py_type_str.lower():
        return {"type": "string"}
    if "int" in py_type_str.lower():
        return {"type": "integer"}
    if "float" in py_type_str.lower():
        return {"type": "number"}
    if "bool" in py_type_str.lower():
        return {"type": "boolean"}
    if "dict" in py_type_str.lower():
        return {"type": "object"}
    if "list" in py_type_str.lower():
        return {"type": "array"}
    return {"type": "string"}


def generate_domain_yaml(domain_name: str, tools_dir: Path) -> dict:
    domain_data = {
        "version": "1.0",
        "domains": {
            domain_name: {
                "description": f"Auto-generated domain for {domain_name}",
                "rules": ["Use tools from this domain only when relevant to the query context."],
            }
        },
        "tools": {},
    }

    for py_file in tools_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue

        try:
            with open(py_file, "r") as f:
                tree = ast.parse(f.read())

            for node in ast.walk(tree):
                if isinstance(node, ast.AsyncFunctionDef) or isinstance(node, ast.FunctionDef):
                    # Filter out private functions and common non-tool functions
                    if node.name.startswith("_"):
                        continue

                    doc = ast.get_docstring(node) or "No description available."

                    tool_constraints = {
                        "input_schema": {"type": "object", "properties": {}, "required": []}
                    }

                    for arg in node.args.args:
                        param_name = arg.arg
                        if param_name == "self":
                            continue

                        p_type_str = "Any"
                        if arg.annotation:
                            p_type_str = parse_type_annotation(arg.annotation)

                        schema_type = python_type_to_json_schema(p_type_str)

                        # Check for default value
                        # ast.FunctionDef args has 'defaults' list which aligns from the end
                        arg_index = node.args.args.index(arg)
                        defaults_start = len(node.args.args) - len(node.args.defaults)

                        if arg_index >= defaults_start:
                            default_node = node.args.defaults[arg_index - defaults_start]
                            if isinstance(default_node, ast.Constant):
                                schema_type["default"] = default_node.value
                        else:
                            tool_constraints["input_schema"]["required"].append(param_name)

                        tool_constraints["input_schema"]["properties"][param_name] = schema_type

                    domain_data["tools"][node.name] = {
                        "constraints": tool_constraints,
                        "hard_rules": f"Ensure valid parameters for {node.name}.",
                        "few_shot_examples": [],
                    }
        except Exception as e:
            print(f"Error processing file {py_file}: {e}")

    return domain_data


def main():
    base_dir = Path("src/me4brain/domains")
    output_dir = Path("config/prompt_hints/auto_generated")
    output_dir.mkdir(parents=True, exist_ok=True)

    for domain_dir in base_dir.iterdir():
        if domain_dir.is_dir():
            tools_dir = domain_dir / "tools"
            if tools_dir.exists():
                print(f"Processing domain: {domain_dir.name}")
                domain_yaml = generate_domain_yaml(domain_dir.name, tools_dir)

                output_file = output_dir / f"{domain_dir.name}.yaml"
                with open(output_file, "w") as f:
                    yaml.dump(domain_yaml, f, sort_keys=False, allow_unicode=True)
                print(f"Generated: {output_file}")


if __name__ == "__main__":
    main()
