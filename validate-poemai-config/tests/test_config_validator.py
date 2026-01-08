import os

# Add the parent directory to the path so we can import our module
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))


from validate_poemai_config.config_validator import validate_config


def test_valid_config():
    valid_config = {
        "model": "gpt-4",
        "temperature": 0.7,
        "max_tokens": 1500,
        "system_prompt": "You are a helpful assistant.",
    }

    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tmpfile:
        yaml.dump(valid_config, tmpfile)
        tmpfile_path = tmpfile.name

    try:
        is_valid, errors = validate_config(tmpfile_path)
        assert is_valid
        assert errors == []
    finally:
        os.remove(tmpfile_path)
