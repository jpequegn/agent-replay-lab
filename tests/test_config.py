"""Tests for YAML configuration loading."""

from pathlib import Path

import pytest

from core.config import (
    ConfigError,
    _substitute_env_vars,
    load_branches_from_config,
    load_config,
)


class TestSubstituteEnvVars:
    """Tests for environment variable substitution."""

    def test_simple_substitution(self, monkeypatch):
        """Simple ${VAR} substitution."""
        monkeypatch.setenv("TEST_VAR", "hello")
        assert _substitute_env_vars("${TEST_VAR}") == "hello"

    def test_substitution_in_text(self, monkeypatch):
        """Substitution within surrounding text."""
        monkeypatch.setenv("NAME", "world")
        assert _substitute_env_vars("Hello ${NAME}!") == "Hello world!"

    def test_default_value_used(self, monkeypatch):
        """Default value used when var not set."""
        monkeypatch.delenv("UNSET_VAR", raising=False)
        assert _substitute_env_vars("${UNSET_VAR:-default}") == "default"

    def test_default_value_not_used_when_set(self, monkeypatch):
        """Default value not used when var is set."""
        monkeypatch.setenv("SET_VAR", "actual")
        assert _substitute_env_vars("${SET_VAR:-default}") == "actual"

    def test_empty_default(self, monkeypatch):
        """Empty default value is valid."""
        monkeypatch.delenv("EMPTY_VAR", raising=False)
        assert _substitute_env_vars("${EMPTY_VAR:-}") == ""

    def test_multiple_substitutions(self, monkeypatch):
        """Multiple substitutions in one string."""
        monkeypatch.setenv("A", "1")
        monkeypatch.setenv("B", "2")
        assert _substitute_env_vars("${A} and ${B}") == "1 and 2"

    def test_no_substitution_needed(self):
        """String without vars is unchanged."""
        assert _substitute_env_vars("plain text") == "plain text"

    def test_unset_without_default_preserved(self, monkeypatch):
        """Unset var without default is preserved as-is."""
        monkeypatch.delenv("MISSING", raising=False)
        assert _substitute_env_vars("${MISSING}") == "${MISSING}"


class TestLoadConfig:
    """Tests for load_config function."""

    def test_loads_valid_config(self, tmp_path):
        """Loads valid configuration file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
branches:
  - name: test-branch
    model: claude-sonnet-4-20250514
""")
        config = load_config(config_file)

        assert len(config.branches) == 1
        assert config.branches[0].name == "test-branch"
        assert config.branches[0].model == "claude-sonnet-4-20250514"

    def test_applies_default_settings(self, tmp_path):
        """Default settings are applied."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
branches:
  - name: test
    model: claude-sonnet-4-20250514
""")
        config = load_config(config_file)

        assert config.settings.max_turns == 5
        assert config.settings.timeout_seconds == 300
        assert config.settings.save_results is True
        assert config.settings.output_dir == "./results"

    def test_custom_settings(self, tmp_path):
        """Custom settings override defaults."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
branches:
  - name: test
    model: claude-sonnet-4-20250514

settings:
  max_turns: 10
  timeout_seconds: 600
  save_results: false
  output_dir: ./custom
""")
        config = load_config(config_file)

        assert config.settings.max_turns == 10
        assert config.settings.timeout_seconds == 600
        assert config.settings.save_results is False
        assert config.settings.output_dir == "./custom"

    def test_settings_max_turns_applied_to_branches(self, tmp_path):
        """Settings max_turns is applied to branches without explicit max_turns."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
branches:
  - name: uses-default
    model: claude-sonnet-4-20250514
  - name: explicit
    model: claude-sonnet-4-20250514
    max_turns: 3

settings:
  max_turns: 10
""")
        config = load_config(config_file)

        assert config.branches[0].max_turns == 10  # From settings
        assert config.branches[1].max_turns == 3   # Explicit override

    def test_multiple_branches(self, tmp_path):
        """Multiple branches are loaded."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
branches:
  - name: branch-1
    model: claude-sonnet-4-20250514
  - name: branch-2
    model: claude-haiku-4-20250514
  - name: branch-3
    model: claude-opus-4-20250514
""")
        config = load_config(config_file)

        assert len(config.branches) == 3
        assert config.branches[0].name == "branch-1"
        assert config.branches[1].name == "branch-2"
        assert config.branches[2].name == "branch-3"

    def test_branch_with_inject_message(self, tmp_path):
        """Branch with inject_message is loaded."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
branches:
  - name: alternative
    model: claude-sonnet-4-20250514
    inject_message: "What if we tried something different?"
""")
        config = load_config(config_file)

        assert config.branches[0].inject_message == "What if we tried something different?"

    def test_branch_with_system_prompt(self, tmp_path):
        """Branch with system_prompt is loaded."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
branches:
  - name: custom-system
    model: claude-sonnet-4-20250514
    system_prompt: "You are a helpful coding assistant."
""")
        config = load_config(config_file)

        assert config.branches[0].system_prompt == "You are a helpful coding assistant."

    def test_env_var_substitution_in_config(self, tmp_path, monkeypatch):
        """Environment variables are substituted."""
        monkeypatch.setenv("OUTPUT_PATH", "/custom/output")
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
branches:
  - name: test
    model: claude-sonnet-4-20250514

settings:
  output_dir: "${OUTPUT_PATH}"
""")
        config = load_config(config_file)

        assert config.settings.output_dir == "/custom/output"


class TestLoadConfigErrors:
    """Tests for error handling in load_config."""

    def test_file_not_found(self, tmp_path):
        """Missing file raises ConfigError."""
        with pytest.raises(ConfigError) as exc_info:
            load_config(tmp_path / "nonexistent.yaml")

        assert "not found" in str(exc_info.value)

    def test_invalid_yaml_syntax(self, tmp_path):
        """Invalid YAML raises ConfigError."""
        config_file = tmp_path / "bad.yaml"
        config_file.write_text("branches: [invalid yaml")

        with pytest.raises(ConfigError) as exc_info:
            load_config(config_file)

        assert "Invalid YAML" in str(exc_info.value)

    def test_empty_file(self, tmp_path):
        """Empty file raises ConfigError."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        with pytest.raises(ConfigError) as exc_info:
            load_config(config_file)

        assert "empty" in str(exc_info.value).lower()

    def test_missing_branches(self, tmp_path):
        """Missing branches field raises ConfigError."""
        config_file = tmp_path / "no-branches.yaml"
        config_file.write_text("""
settings:
  max_turns: 5
""")
        with pytest.raises(ConfigError) as exc_info:
            load_config(config_file)

        assert "branches" in str(exc_info.value).lower()

    def test_empty_branches(self, tmp_path):
        """Empty branches list raises ConfigError."""
        config_file = tmp_path / "empty-branches.yaml"
        config_file.write_text("""
branches: []
""")
        with pytest.raises(ConfigError) as exc_info:
            load_config(config_file)

        assert "branches" in str(exc_info.value).lower()

    def test_invalid_model(self, tmp_path):
        """Invalid model name raises ConfigError."""
        config_file = tmp_path / "bad-model.yaml"
        config_file.write_text("""
branches:
  - name: test
    model: not-a-real-model
""")
        with pytest.raises(ConfigError) as exc_info:
            load_config(config_file)

        assert "model" in str(exc_info.value).lower()
        assert "not-a-real-model" in str(exc_info.value)

    def test_missing_branch_name(self, tmp_path):
        """Branch without name raises ConfigError."""
        config_file = tmp_path / "no-name.yaml"
        config_file.write_text("""
branches:
  - model: claude-sonnet-4-20250514
""")
        with pytest.raises(ConfigError) as exc_info:
            load_config(config_file)

        assert "name" in str(exc_info.value).lower()

    def test_config_error_has_details(self, tmp_path):
        """ConfigError includes helpful details."""
        config_file = tmp_path / "bad.yaml"
        config_file.write_text("""
branches:
  - name: test
    model: invalid-model
""")
        with pytest.raises(ConfigError) as exc_info:
            load_config(config_file)

        error = exc_info.value
        assert len(error.details) > 0


class TestLoadBranchesFromConfig:
    """Tests for load_branches_from_config convenience function."""

    def test_returns_branches_only(self, tmp_path):
        """Returns just the branches list."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
branches:
  - name: test-1
    model: claude-sonnet-4-20250514
  - name: test-2
    model: claude-haiku-4-20250514
""")
        branches = load_branches_from_config(config_file)

        assert len(branches) == 2
        assert branches[0].name == "test-1"
        assert branches[1].name == "test-2"


class TestExampleConfig:
    """Tests using the actual example config file."""

    @pytest.fixture
    def example_config_path(self):
        """Path to the example config file."""
        path = Path(__file__).parent.parent / "examples" / "fork-config.yaml"
        if not path.exists():
            pytest.skip("Example config not found")
        return path

    def test_loads_example_config(self, example_config_path):
        """Can load the example configuration file."""
        config = load_config(example_config_path)

        assert len(config.branches) == 4
        assert config.branches[0].name == "sonnet-baseline"
        assert config.branches[1].name == "haiku-speed"
        assert config.branches[2].name == "opus-quality"
        assert config.branches[3].name == "alternative-question"

    def test_example_config_models(self, example_config_path):
        """Example config has valid models."""
        config = load_config(example_config_path)

        assert config.branches[0].model == "claude-sonnet-4-20250514"
        assert config.branches[1].model == "claude-haiku-4-20250514"
        assert config.branches[2].model == "claude-opus-4-20250514"
        assert config.branches[3].model == "claude-sonnet-4-20250514"

    def test_example_config_inject_message(self, example_config_path):
        """Example config has inject message on one branch."""
        config = load_config(example_config_path)

        # First 3 branches don't have inject
        assert config.branches[0].inject_message is None
        assert config.branches[1].inject_message is None
        assert config.branches[2].inject_message is None

        # Last branch has inject
        assert config.branches[3].inject_message == "What if we used a different approach?"

    def test_example_config_settings(self, example_config_path):
        """Example config has correct settings."""
        config = load_config(example_config_path)

        assert config.settings.max_turns == 5
        assert config.settings.timeout_seconds == 300
        assert config.settings.save_results is True
        assert config.settings.output_dir == "./results"
