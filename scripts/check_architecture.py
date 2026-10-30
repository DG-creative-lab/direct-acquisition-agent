"""Small static import contract, including a cycle check. No external tooling."""

import ast
from pathlib import Path


MODULES = {"runtime", "audiences", "campaigns", "creative", "learning", "reasoning", "reviews", "conversations"}
DEPENDENCIES = {"campaigns": {"audiences", "creative"}, "creative": {"reasoning"},
                "reviews": {"audiences", "campaigns", "creative", "runtime"}, "conversations": {"reasoning", "runtime"}}


def imports(source: str, module: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.extend(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parent = module.split(".")[:-node.level]
                base = ".".join(parent + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            if base == "acquisition" or node.module is None:
                found.extend(base + "." + item.name for item in node.names)
            elif base.startswith("acquisition.") and len(base.split(".")) == 2:
                found.extend(base + "." + item.name if item.name in {"domain", "ports", "application"} else base
                             for item in node.names)
            else:
                found.append(base)
    return found


def violations(source: str, module: str) -> list[str]:
    parts = module.split(".")
    owner = parts[1] if len(parts) > 1 else None
    errors = []
    for target in imports(source, module):
        if not target.startswith("acquisition."):
            if module.endswith(".domain") and target.split(".")[0] not in {
                "collections", "csv", "dataclasses", "datetime", "hashlib", "io", "math", "typing", "re"
            }:
                errors.append(f"Domain imports undeclared dependency {target}")
            continue
        dependency = target.split(".")[1]
        if owner in MODULES:
            if dependency not in {owner, "contracts"} | DEPENDENCIES.get(owner, set()):
                errors.append(f"{owner} may not depend on {target}")
            elif dependency != owner and dependency != "contracts" and len(target.split(".")) > 2:
                errors.append(f"Cross-module import must use public API: {target}")
            if module.endswith(".domain") and dependency == owner and target != f"acquisition.{owner}.domain":
                errors.append(f"Domain may not import its outer layer {target}")
    return errors


def check(root: Path) -> list[str]:
    errors, graph = [], {}
    for path in sorted((root / "src/acquisition").rglob("*.py")):
        module = ".".join(path.relative_to(root / "src").with_suffix("").parts)
        source = path.read_text()
        errors.extend(f"{path.relative_to(root)}: {error}" for error in violations(source, module))
        owner = module.split(".")[1] if len(module.split(".")) > 1 else None
        if owner in MODULES:
            graph.setdefault(owner, set()).update(
                item.split(".")[1] for item in imports(source, module)
                if item.startswith("acquisition.") and item.split(".")[1] in MODULES
                and item.split(".")[1] != owner
            )
    def visit(node, trail):
        if node in trail:
            errors.append("Module cycle: " + " -> ".join(trail + [node]))
            return
        for child in graph.get(node, ()):
            visit(child, trail + [node])
    for node in graph:
        visit(node, [])
    return errors


if __name__ == "__main__":
    problems = check(Path(__file__).resolve().parents[1])
    print("\n".join(problems) if problems else "Architecture imports and module graph: passed")
    raise SystemExit(bool(problems))
