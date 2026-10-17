"""
Prompt Manager: Handles loading, caching, and formatting of versioned YAML prompt templates.
"""
from pathlib import Path
from typing import Dict, Any
import yaml

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "configs" / "prompts"

_PROMPT_CACHE: Dict[str, Dict[str, Any]] = {}

def get_prompt_template(name: str) -> Dict[str, Any]:
    """Loads a prompt template from configs/prompts/<name>.yaml with caching."""
    if name in _PROMPT_CACHE:
        return _PROMPT_CACHE[name]

    file_path = PROMPTS_DIR / f"{name}.yaml"
    if not file_path.exists():
        raise FileNotFoundError(f"Prompt template '{name}' not found at {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    _PROMPT_CACHE[name] = data
    return data

def format_retry_feedback(errors: list[str]) -> str:
    """Formats validator errors into the retry feedback template."""
    tmpl = get_prompt_template("feedback_retry_v1")
    error_list_str = "\n".join(f"- {err}" for err in errors)
    return tmpl["feedback_template"].format(error_list=error_list_str)
