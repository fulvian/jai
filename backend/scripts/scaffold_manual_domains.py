#!/usr/bin/env python3
"""
Scaffold Manual Domain YAMLs from Auto-Generated Baselines.
Follows SOTA 2026 Protocol (Version 2.0).
"""

import os
import yaml
from pathlib import Path
from datetime import datetime

# Paths
BASE_DIR = Path("/Users/fulvioventura/me4brain/config/prompt_hints")
AUTO_DIR = BASE_DIR / "auto_generated"
DOMAINS_DIR = BASE_DIR / "domains"


def scaffold():
    if not DOMAINS_DIR.exists():
        print(f"Creating directory: {DOMAINS_DIR}")
        DOMAINS_DIR.mkdir(parents=True)

    # Process each auto-generated file
    for auto_file in AUTO_DIR.glob("*.yaml"):
        print(f"Processing baseline: {auto_file.name}")
        with open(auto_file, "r", encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                print(f"Error parsing {auto_file.name}: {e}")
                continue

            if not data:
                continue

        # In SOTA 2026, we prefer 1 file = 1 domain logic as defined in the protocol.
        # However, auto_generated files might contain multiple domains in a 'domains' key.
        # We will extract each domain found.

        auto_domains = data.get("domains", {})
        auto_tools = data.get("tools", {})

        # If 'domains' is empty, we use the filename as domain_id
        if not auto_domains:
            domain_ids = [auto_file.stem]
            auto_domains = {
                auto_file.stem: {"description": f"Auto-generated domain for {auto_file.stem}"}
            }
        else:
            domain_ids = list(auto_domains.keys())

        for d_id in domain_ids:
            target_file = DOMAINS_DIR / f"{d_id}.yaml"

            # Skip if already exists to avoid overwriting manual work
            if target_file.exists():
                print(f"  -> SKIP: {d_id}.yaml already exists in domains/")
                continue

            print(f"  -> Creating scaffold: {d_id}.yaml")

            d_info = auto_domains.get(d_id, {})

            # Prepare SOTA 2026 Structure
            out_data = {
                "version": "2.0",
                "domain": d_id,
                "last_updated": datetime.now().strftime("%Y-%m-%d"),
                "author": "AI_SCAFFOLD_SCRIPT",
                "description": d_info.get(
                    "description", f"Manually authored domain context for {d_id}"
                ),
                "content": (
                    "## REGOLE CRITICHE (SOTA 2026)\n"
                    "1. TODO: Definisci qui le regole imperative per questo dominio.\n"
                    "2. Forza l'uso di parametri specifici (es. fusi orari, filtri).\n"
                    "\n"
                    "### Errori Comuni da Evitare\n"
                    "- ❌ Non allucinare ID non presenti nel contesto.\n"
                    "- ❌ Non usare tool fuori sequenza logica.\n"
                    "\n"
                    "### Sequenze Consigliate\n"
                    "1. Procedi con la ricerca base.\n"
                    "2. Approfondisci solo se necessario."
                ),
                "tools": {},
            }

            # Filter tools belonging to this domain
            for t_id, t_val in auto_tools.items():
                # Simple heuristic: if 'domains' was used, check if tool belongs.
                # If not, add all tools to the filename-based domain.
                t_domain = t_val.get("domain") or d_id
                if t_domain != d_id:
                    continue

                out_data["tools"][t_id] = {
                    "description": t_val.get("description", f"Description for {t_id}"),
                    "constraints": t_val.get("constraints", {}),
                    "hard_rules": "RULE 1: TODO (Vincolo ferreo di validazione Layer 3)\n",
                    "version": "1.0",
                    "deprecated": False,
                    "migration_hint": "",
                    "few_shot_examples": [
                        {
                            "description": f"Standard use case for {t_id}",
                            "content": (
                                'INPUT: "Esempio di richiesta utente"\n'
                                'THOUGHT: "Ragionamento logico..."\n'
                                'CALL: { "param": "valore" }\n'
                                'RESULT: "Risultato atteso..."'
                            ),
                        }
                    ],
                }

            with open(target_file, "w", encoding="utf-8") as f_out:
                # Use sort_keys=False to keep the order clean
                yaml.dump(
                    out_data, f_out, sort_keys=False, allow_unicode=True, default_flow_style=False
                )

    print("\nScaffolding complete. Check the 'config/prompt_hints/domains/' directory.")


if __name__ == "__main__":
    scaffold()
