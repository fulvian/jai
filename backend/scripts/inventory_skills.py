import os
import yaml
from pathlib import Path

skill_dirs = [
    Path.home() / ".me4brain" / "skills",
    Path("/Users/fulvioventura/me4brain/src/me4brain/skills/bundled"),
]

inventory = []

for base_dir in skill_dirs:
    if not base_dir.exists():
        continue
    for skill_path in base_dir.iterdir():
        if not skill_path.is_dir():
            continue
        skill_md = skill_path / "SKILL.md"
        if skill_md.exists():
            with open(skill_md, "r", encoding="utf-8") as f:
                content = f.read()

            # Parse frontmatter
            if content.startswith("---"):
                try:
                    end_idx = content.find("---", 3)
                    frontmatter = content[3:end_idx]
                    data = yaml.safe_load(frontmatter)
                    inventory.append(
                        {
                            "id": skill_path.name,
                            "name": data.get("name", skill_path.name),
                            "description": data.get("description", ""),
                            "tags": data.get("tags", []),
                            "source": "bundled" if "bundled" in str(skill_path) else "local",
                        }
                    )
                except Exception as e:
                    print(f"Error parsing {skill_md}: {e}")

# Generate markdown output
out_path = Path(
    "/Users/fulvioventura/.gemini/antigravity/brain/9b463a6c-e24e-4428-85ec-eabf96646094/skills_inventory.md"
)
with open(out_path, "w", encoding="utf-8") as f:
    f.write("# Skills Inventory\n\n")
    for s in inventory:
        f.write(f"## {s['id']}\n")
        f.write(f"- **Name**: {s['name']}\n")
        f.write(f"- **Source**: {s['source']}\n")
        f.write(f"- **Tags**: {', '.join(s['tags']) if s['tags'] else 'N/A'}\n")
        f.write(f"- **Description**: {s['description']}\n\n")

print(f"Inventory saved: {len(inventory)} skills processed.")
