import sys
import types
from collections import defaultdict
from enum import Enum
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))
if "jsonschema" not in sys.modules:
    sys.modules["jsonschema"] = types.SimpleNamespace(
        validate=lambda *args, **kwargs: None
    )
try:
    import poemai_utils  # noqa: F401
except ImportError:
    poemai_utils = types.ModuleType("poemai_utils")
    enum_utils = types.ModuleType("poemai_utils.enum_utils")
    enum_utils.add_enum_repr = lambda enum_cls: enum_cls
    openai_module = types.ModuleType("poemai_utils.openai")
    openai_model_module = types.ModuleType("poemai_utils.openai.openai_model")

    class _OpenAIModel(Enum):
        GPT_4_1 = "gpt-4.1"
        GPT_5_MINI = "gpt-5-mini"

    openai_model_module.OPENAI_MODEL = _OpenAIModel

    sys.modules["poemai_utils"] = poemai_utils
    sys.modules["poemai_utils.enum_utils"] = enum_utils
    sys.modules["poemai_utils.openai"] = openai_module
    sys.modules["poemai_utils.openai.openai_model"] = openai_model_module

import config_validator
from config_validator import calc_object_directory, validate
from poemai_utils.openai.openai_model import OPENAI_MODEL


def test_required_utils_version_matches_action_pin():
    action = yaml.safe_load((Path(__file__).parents[1] / "action.yaml").read_text())
    install_step = next(
        step
        for step in action["runs"]["steps"]
        if step["name"] == "Install base dependencies"
    )
    assert (
        f"poemai-utils=={config_validator.REQUIRED_POEMAI_UTILS_VERSION}"
        in install_step["run"].split()
    )


@pytest.mark.parametrize("installed", ["3.2.2", "3.2.13", "3.3.0rc1"])
def test_validator_rejects_outdated_utils_before_reading_config(installed):
    with patch.object(
        config_validator, "version", return_value=installed
    ), patch.object(
        sys,
        "argv",
        ["validator", "--project-root-path", ".", "--environment", "staging"],
    ), patch.object(
        config_validator, "validate_files"
    ) as validate_files:
        with pytest.raises(SystemExit) as error:
            config_validator.main()
    assert error.value.code == 1
    validate_files.assert_not_called()


def test_outdated_utils_error_has_matching_interpreter_upgrade_command():
    with patch.object(config_validator, "version", return_value="3.2.2"):
        with pytest.raises(ValueError) as error:
            config_validator.check_poemai_utils_version()
    message = str(error.value)
    assert "3.2.2" in message
    assert "requires 3.3.0 or newer" in message
    assert f'{sys.executable} -m pip install --upgrade "poemai-utils==3.3.0"' in message


@pytest.mark.parametrize("installed", ["3.3.0", "3.3.1", "3.10.0", "4.0.0"])
def test_validator_accepts_current_or_newer_utils(installed):
    with patch.object(config_validator, "version", return_value=installed):
        config_validator.check_poemai_utils_version()


def test_validator_reports_missing_utils_distribution():
    with patch.object(
        config_validator,
        "version",
        side_effect=config_validator.PackageNotFoundError("poemai-utils"),
    ):
        with pytest.raises(ValueError, match="poemai-utils is not installed"):
            config_validator.check_poemai_utils_version()


def test_validator_reports_invalid_utils_version():
    with patch.object(config_validator, "version", return_value="unknown"):
        with pytest.raises(ValueError, match="Cannot verify poemai-utils version"):
            config_validator.check_poemai_utils_version()


def _assistant_object(model_name):
    return {
        "pk": "CORPUS_KEY#POEMAI_TEST_BOT#ASSISTANT#",
        "sk": "ASSISTANT_ID#0123456789abcdef0123456789abcdef",
        "corpus_key": "POEMAI_TEST_BOT",
        "assistant_id": "0123456789abcdef0123456789abcdef",
        "assistant_key": "rag_assistent",
        "assistant_model_name": model_name,
    }


def _assistant_object_with_tool(lambda_map_record):
    obj = _assistant_object("GPT_4_1")
    obj["tools"] = [
        {
            "type": "function",
            "function": {
                "name": "search_in_poemai",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    obj["tool_to_lambda_map"] = {"search_in_poemai": lambda_map_record}
    return obj


def _corpus_metadata_object(openai_base_url=None):
    obj = {
        "pk": "CORPUS_METADATA#",
        "sk": "CORPUS_KEY#POEMAI_TEST_BOT",
        "corpus_key": "POEMAI_TEST_BOT",
        "openai_project_account_name": "test-account",
        "summarizer_model_name": "GPT_4_1",
    }
    if openai_base_url is not None:
        obj["openai_base_url"] = openai_base_url
    return obj


def _run_assistant_validation(assistant_obj, corpus_metadata_obj):
    validation_errors = defaultdict(list)
    uuid_collection = defaultdict(list)
    assistant_case_manager_graph = {
        "object_by_id": {},
        "edges": {},
        "objects_by_key": calc_object_directory(
            [
                (assistant_obj, "assistant.yaml"),
                (corpus_metadata_obj, "corpus_metadata.yaml"),
            ]
        ),
    }

    validate(
        obj=assistant_obj,
        filename="assistant.yaml",
        keys_by_corpus_key=defaultdict(lambda: defaultdict(lambda: set())),
        legal_corpus_keys={"POEMAI_TEST_BOT"},
        validation_errors=validation_errors,
        uuid_collection=uuid_collection,
        assistant_case_manager_graph=assistant_case_manager_graph,
    )
    return validation_errors


@pytest.mark.parametrize("model", list(OPENAI_MODEL))
def test_assistant_model_name_accepts_current_model_catalog(model):
    errors = _run_assistant_validation(
        assistant_obj=_assistant_object(model.name),
        corpus_metadata_obj=_corpus_metadata_object(),
    )
    assert "assistant.yaml" not in errors


@pytest.mark.parametrize(
    "model_name",
    ["GPT_5_6", "GPT_5_6_LUNA", "GPT_5_6_TERRA", "GPT_5_6_SOL", "GPT_6_ASTRA"],
)
def test_assistant_model_name_accepts_recent_models(model_name):
    assert model_name in OPENAI_MODEL.__members__
    errors = _run_assistant_validation(
        assistant_obj=_assistant_object(model_name),
        corpus_metadata_obj=_corpus_metadata_object(),
    )
    assert "assistant.yaml" not in errors


def test_assistant_model_name_allows_non_openai_name_with_custom_api_url():
    errors = _run_assistant_validation(
        assistant_obj=_assistant_object("mistral-large-latest"),
        corpus_metadata_obj=_corpus_metadata_object(
            openai_base_url="https://api.mistral.ai/v1/chat/completions"
        ),
    )
    assert "assistant.yaml" not in errors


def test_assistant_model_name_rejects_non_openai_name_without_custom_api_url():
    errors = _run_assistant_validation(
        assistant_obj=_assistant_object("mistral-large-latest"),
        corpus_metadata_obj=_corpus_metadata_object(),
    )
    assert "assistant.yaml" in errors
    assert any(
        "not a valid OpenAI model" in error["error"]
        for error in errors["assistant.yaml"]
    )


def test_tool_output_rendering_rejects_missing_template_without_raw_opt_in():
    errors = _run_assistant_validation(
        assistant_obj=_assistant_object_with_tool(
            {
                "lambda_name": "poemai-rag-tool",
                "default_parameters": {},
            }
        ),
        corpus_metadata_obj=_corpus_metadata_object(),
    )
    assert "assistant.yaml" in errors
    assert any(
        "search_in_poemai" in error["error"]
        and "poemai-rag-tool" in error["error"]
        and "return_value_text_template" in error["error"]
        and "allow_raw_tool_response: true" in error["error"]
        for error in errors["assistant.yaml"]
    )


def test_tool_output_rendering_accepts_non_empty_template():
    errors = _run_assistant_validation(
        assistant_obj=_assistant_object_with_tool(
            {
                "lambda_name": "poemai-rag-tool",
                "return_value_text_template": "Search completed.",
                "default_parameters": {},
            }
        ),
        corpus_metadata_obj=_corpus_metadata_object(),
    )
    assert "assistant.yaml" not in errors


def test_tool_output_rendering_accepts_explicit_raw_opt_in():
    errors = _run_assistant_validation(
        assistant_obj=_assistant_object_with_tool(
            {
                "lambda_name": "small-debug-tool",
                "allow_raw_tool_response": True,
                "default_parameters": {},
            }
        ),
        corpus_metadata_obj=_corpus_metadata_object(),
    )
    assert "assistant.yaml" not in errors
