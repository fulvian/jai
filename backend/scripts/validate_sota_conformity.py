#!/usr/bin/env python3
"""
SOTA 2026: Massive Validation Script for Domain Conformity.
Updated to merge top-level description/content and handle loose few-shot formats.
"""

import os
import sys
import yaml
import re
from pathlib import Path
from typing import List, Dict, Any


# Colors for terminal output
class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def log_error(msg: str):
    print(f"{Colors.FAIL}ERROR: {msg}{Colors.ENDC}")


def log_warning(msg: str):
    print(f"{Colors.WARNING}WARNING: {msg}{Colors.ENDC}")


def log_info(msg: str):
    print(f"{Colors.OKCYAN}INFO: {msg}{Colors.ENDC}")


def log_success(msg: str):
    print(f"{Colors.OKGREEN}SUCCESS: {msg}{Colors.ENDC}")


class SOTAValidator:
    def __init__(self, domains_dir: Path):
        self.domains_dir = domains_dir
        self.total_errors = 0
        self.total_warnings = 0
        self.files_checked = 0

    def check_few_shot_content(self, content: str, source: str):
        errors = 0
        warnings = 0
        has_input = "INPUT:" in content or "USER:" in content
        has_thought = "THOUGHT:" in content
        has_call = "CALL:" in content
        has_result = "RESULT:" in content or "OUTPUT:" in content

        if not has_input:
            log_error(f"  [{source}] Missing INPUT/USER section")
            errors += 1
        if not has_thought:
            log_error(f"  [{source}] Missing THOUGHT section")
            errors += 1
        if not has_call:
            log_error(f"  [{source}] Missing CALL section")
            errors += 1
        if not has_result:
            log_warning(f"  [{source}] Missing RESULT/OUTPUT section")
            warnings += 1

        return errors, warnings

    def validate_file(self, file_path: Path):
        local_errors = 0
        local_warnings = 0
        print(f"\n{Colors.BOLD}{Colors.HEADER}Validating: {file_path.name}{Colors.ENDC}")

        try:
            with open(file_path, "r") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            log_error(f"Invalid YAML syntax: {e}")
            self.total_errors += 1
            return

        if not data:
            log_warning("Empty file")
            return

        # 1. Version Check
        version = str(data.get("version", ""))
        if version not in ["2.0", "2.1", "2.2", "2.3"]:
            log_error(f"Invalid version: '{version}' (Expected: '2.0'+)")
            local_errors += 1
        else:
            log_success(f"Version {version} check passed")

        # 2. Domain Identity & Hints Layer (Layer 1)
        domain_name = data.get("domain")
        # Merge description and content for searching Anti-patterns
        combined_hints = (
            str(data.get("description", "")) + "\n" + str(data.get("content", ""))
        ).lower()

        if not domain_name:
            log_error("Missing top-level 'domain' key")
            local_errors += 1
        if not combined_hints.strip():
            log_error("No Domain Hints found (description or content)")
            local_errors += 1
        else:
            if "anti-pattern" not in combined_hints and "errori comuni" not in combined_hints:
                log_warning("No 'Anti-pattern' or 'Errori Comuni' section in Domain Hints")
                local_warnings += 1

        # 3. Layer 2: Tool Constraints & Hard Rules
        tools = data.get("tools", {})
        if not tools:
            log_warning("No 'tools' defined")
            local_warnings += 1
        else:
            for t_name, t_val in tools.items():
                if not isinstance(t_val, dict):
                    log_error(f"Tool '{t_name}' is not a dict")
                    local_errors += 1
                    continue

                # Check for input_schema
                constraints = t_val.get("constraints", {})
                if not constraints or "input_schema" not in constraints:
                    log_error(f"Tool '{t_name}' missing 'input_schema'")
                    local_errors += 1

                # Check for hard_rules
                hard_rules = t_val.get("hard_rules")
                if not hard_rules:
                    log_error(f"Tool '{t_name}' missing 'hard_rules'")
                    local_errors += 1

                # Inline few-shots
                fs = t_val.get("few_shot_examples", [])
                if isinstance(fs, list):
                    for idx, ex in enumerate(fs):
                        src = f"Tool:{t_name}:FS:{idx}"
                        if isinstance(ex, dict) and "content" in ex:
                            e, w = self.check_few_shot_content(ex["content"], src)
                            local_errors += e
                            local_warnings += w

        # 4. Layer 3: Top-level Few-Shot Examples
        examples = data.get("few_shot_examples", [])
        if isinstance(examples, list):
            for idx, ex in enumerate(examples):
                src = f"Global:FS:{idx}"
                if isinstance(ex, dict):
                    content = ex.get("content") or ""
                    if not content:
                        for k in ["INPUT", "THOUGHT", "CALL", "RESULT"]:
                            if k not in ex and (k != "INPUT" or "USER" not in ex):
                                log_error(f"  [{src}] Missing key: {k}")
                                local_errors += 1
                    else:
                        e, w = self.check_few_shot_content(content, src)
                        local_errors += e
                        local_warnings += w

        self.total_errors += local_errors
        self.total_warnings += local_warnings
        self.files_checked += 1

        if local_errors == 0:
            log_success(f"{file_path.name} is compliant.")
        else:
            log_error(f"{file_path.name} has {local_errors} errors.")

    def run(self):
        yaml_files = sorted(list(self.domains_dir.glob("*.yaml")))
        for yf in yaml_files:
            if yf.name.startswith("_") or yf.name.endswith(".bak"):
                continue
            self.validate_file(yf)

        print("-" * 40)
        print(f"{Colors.BOLD}Final Report ({self.files_checked} files):{Colors.ENDC}")
        if self.total_errors > 0:
            log_error(f"Total Errors: {self.total_errors}")
        else:
            log_success("No structural errors found!")
        log_warning(f"Total Warnings: {self.total_warnings}")
        return self.total_errors == 0


if __name__ == "__main__":
    domains_path = Path("config/prompt_hints/domains")
    validator = SOTAValidator(domains_path)
    success = validator.run()
    sys.exit(0 if success else 1)
