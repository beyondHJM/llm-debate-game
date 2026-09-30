import json
from pathlib import Path

import pytest

from debate_game.config import load_agent_config
from debate_game.errors import ConfigurationError


def write_config(path: Path, **overrides: object) -> None:
    document: dict[str, object] = {
        "api_base": "https://example.com/v1/",
        "api_key": "secret",
        "model": "model-name",
        "temperature": 0.3,
    }
    document.update(overrides)
    path.write_text(json.dumps(document), encoding="utf-8")


def test_load_agent_config(tmp_path: Path) -> None:
    path = tmp_path / "agent.json"
    write_config(path)

    config = load_agent_config(path)

    assert config.api_base == "https://example.com/v1"
    assert config.api_key == "secret"
    assert config.model == "model-name"
    assert config.temperature == 0.3
    assert config.max_tokens is None


def test_missing_config_is_clear(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="找不到"):
        load_agent_config(tmp_path / "missing.json")


def test_unknown_config_field_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "agent.json"
    write_config(path, unexpected=True)

    with pytest.raises(ConfigurationError, match="格式无效"):
        load_agent_config(path)
