"""Frozen copy tool schemas shared by validation and model orchestration."""

def tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required,
                           "additionalProperties": False}}}


READ = tool("read_editorial_context", "Read the frozen editorial guidance and relevant reviewer examples.", {}, [])
