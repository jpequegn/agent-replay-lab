"""Configuration loading for fork configurations."""

import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from .models import ForkConfig

# Known valid Claude models
VALID_MODELS = {
    "claude-sonnet-4-20250514",
    "claude-haiku-4-20250514",
    "claude-opus-4-20250514",
    # Aliases
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
}


class ConfigSettings(BaseModel):
    """Global settings from config file."""

    max_turns: int = Field(5, ge=1, le=100, description="Default max turns for branches")
    timeout_seconds: int = Field(300, ge=1, le=3600, description="Timeout per branch")
    save_results: bool = Field(True, description="Whether to save results to disk")
    output_dir: str = Field("./results", description="Directory for saving results")


class ForkConfigFile(BaseModel):
    """Complete fork configuration file structure."""

    branches: list[ForkConfig] = Field(..., min_length=1, description="Branch configurations")
    settings: ConfigSettings = Field(default_factory=ConfigSettings, description="Global settings")


class ConfigError(Exception):
    """Error loading or validating configuration."""

    def __init__(self, message: str, details: list[str] | None = None):
        self.message = message
        self.details = details or []
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        if not self.details:
            return self.message
        detail_str = "\n  - ".join(self.details)
        return f"{self.message}\n  - {detail_str}"


def _substitute_env_vars(value: str) -> str:
    """Substitute environment variables in a string.

    Supports ${VAR} and ${VAR:-default} syntax.

    Args:
        value: String potentially containing env var references

    Returns:
        String with env vars substituted
    """
    # Pattern: ${VAR} or ${VAR:-default}
    pattern = r"\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}"

    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        default = match.group(2)
        env_value = os.environ.get(var_name)

        if env_value is not None:
            return env_value
        if default is not None:
            return default
        # Return original if no value and no default
        return match.group(0)

    return re.sub(pattern, replacer, value)


def _substitute_env_vars_recursive(obj):
    """Recursively substitute env vars in a data structure."""
    if isinstance(obj, str):
        return _substitute_env_vars(obj)
    elif isinstance(obj, dict):
        return {k: _substitute_env_vars_recursive(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_substitute_env_vars_recursive(item) for item in obj]
    else:
        return obj


def load_config(path: Path) -> ForkConfigFile:
    """Load and validate a fork configuration file.

    Args:
        path: Path to the YAML configuration file

    Returns:
        Validated ForkConfigFile object

    Raises:
        ConfigError: If file cannot be loaded or validation fails
    """
    # Check file exists
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    if not path.is_file():
        raise ConfigError(f"Path is not a file: {path}")

    # Load YAML
    try:
        with open(path, "r") as f:
            raw_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML syntax in {path}", [str(e)])

    if raw_data is None:
        raise ConfigError(f"Configuration file is empty: {path}")

    if not isinstance(raw_data, dict):
        raise ConfigError(
            f"Configuration must be a YAML mapping, got {type(raw_data).__name__}"
        )

    # Substitute environment variables
    data = _substitute_env_vars_recursive(raw_data)

    # Validate required fields
    if "branches" not in data:
        raise ConfigError(
            "Missing required field 'branches'",
            ["Configuration must define at least one branch"],
        )

    # Apply settings defaults to branches
    settings_data = data.get("settings", {})
    default_max_turns = settings_data.get("max_turns", 5)

    # Apply defaults to branches that don't specify max_turns
    for branch in data.get("branches", []):
        if "max_turns" not in branch:
            branch["max_turns"] = default_max_turns

    # Parse and validate with Pydantic
    try:
        config = ForkConfigFile.model_validate(data)
    except ValidationError as e:
        errors = []
        for error in e.errors():
            loc = ".".join(str(x) for x in error["loc"])
            msg = error["msg"]
            errors.append(f"{loc}: {msg}")
        raise ConfigError(f"Invalid configuration in {path}", errors)

    # Additional validation: check models are valid
    invalid_models = []
    for i, branch in enumerate(config.branches):
        if branch.model not in VALID_MODELS:
            invalid_models.append(f"branches[{i}].model: unknown model '{branch.model}'")

    if invalid_models:
        valid_list = ", ".join(sorted(VALID_MODELS))
        invalid_models.append(f"Valid models: {valid_list}")
        raise ConfigError("Invalid model specified", invalid_models)

    return config


def load_branches_from_config(path: Path) -> list[ForkConfig]:
    """Load just the branch configurations from a file.

    This is a convenience function for when you only need the branches.

    Args:
        path: Path to the YAML configuration file

    Returns:
        List of ForkConfig objects
    """
    config = load_config(path)
    return config.branches
