import argparse
import json
import logging
from collections import defaultdict
from enum import Enum
from pathlib import Path

import jsonschema
import yaml
from poemai_utils.enum_utils import add_enum_repr
from poemai_utils.openai.openai_model import OPENAI_MODEL

_logger = logging.getLogger(__name__)


def pk_sk_fields(pk, sk):
    pk_split = pk.split("#")
    # build pairs from pk_pksplit
    pk_pairs = zip(pk_split[::2], pk_split[1::2])
    # build dict from pairs
    pk_dict = {k.lower(): v for k, v in pk_pairs}

    sk_split = sk.split("#")
    # build pairs from sk_pksplit
    sk_pairs = zip(sk_split[::2], sk_split[1::2])
    # build dict from pairs
    sk_dict = {k.lower(): v for k, v in sk_pairs}
    all_keys = {**pk_dict, **sk_dict}
    # _logger.info(f"pk_sk_fields: {all_keys}")
    return all_keys


class ObjectType(Enum):
    ASSISTANT = "assistant"
    CORPUS_METADATA = "corpus_metadata"
    CASE_MANAGER = "case_manager"


add_enum_repr(ObjectType)

obj_type_recognition_map = {
    ("CORPUS_KEY", "ASSISTANT_ID"): ObjectType.ASSISTANT,
    ("CORPUS_METADATA", "CORPUS_KEY"): ObjectType.CORPUS_METADATA,
    ("CORPUS_KEY", "CASE_MANAGER_ID"): ObjectType.CASE_MANAGER,
}


def calc_obj_type(obj):
    pk = obj["pk"]
    sk = obj["sk"]
    return obj_type_recognition_map.get((pk.split("#")[0], sk.split("#")[0]), None)


key_name_by_object_type = {
    ObjectType.ASSISTANT: "assistant_key",
    ObjectType.CORPUS_METADATA: "corpus_key",
    ObjectType.CASE_MANAGER: "case_manager_id",
}

id_name_by_object_type = {
    ObjectType.ASSISTANT: "assistant_id",
    ObjectType.CORPUS_METADATA: "corpus_key",
    ObjectType.CASE_MANAGER: "case_manager_id",
}


def calc_object_key(obj):
    obj_type = calc_obj_type(obj)
    if obj_type is not None:
        key_name = key_name_by_object_type[obj_type]
        key_value = obj.get(key_name)
        if key_value is not None:
            return obj["corpus_key"], obj_type, key_value
    return None


def calc_object_id(obj):
    obj_type = calc_obj_type(obj)
    if obj_type is not None:
        key_name = id_name_by_object_type[obj_type]
        key_value = obj.get(key_name)
        return key_value

    return None


def calc_object_directory(all_objects_with_file):
    object_directory = {}
    for obj, filename in all_objects_with_file:
        obj_key = calc_object_key(obj)
        if obj_key is not None:
            object_directory[obj_key] = {
                "filename": filename,
                "object": obj,
            }
    return object_directory


def calc_keys(all_objects_with_file, validation_errors):

    keys_by_corpus_key = defaultdict(lambda: defaultdict(lambda: set()))

    for obj, filename in all_objects_with_file:
        obj_type = calc_obj_type(obj)

        if obj_type is not None:
            corpus_key = obj["corpus_key"]

            key_name = key_name_by_object_type[obj_type]

            key_value = obj.get(key_name)
            if key_value is not None:

                if key_value in keys_by_corpus_key[corpus_key][obj_type]:
                    validation_errors[filename].append(
                        {
                            "filename": filename,
                            "error": f"Duplicate key {key_value} for {obj_type} in corpus {corpus_key}",
                        }
                    )

                keys_by_corpus_key[corpus_key][obj_type].add(key_value)

    return keys_by_corpus_key


def is_valid_hex_uuid(uuid):
    if (
        not isinstance(uuid, str)
        or len(uuid) != 32
        or not (set(uuid) <= set("0123456789abcdef"))
    ):
        return False
    return True


def validate(
    obj,
    filename,
    keys_by_corpus_key,
    legal_corpus_keys,
    validation_errors,
    uuid_collection,
    assistant_case_manager_graph,
):

    obj_type = calc_obj_type(obj)

    if obj_type is None:
        return

    fields = pk_sk_fields(obj["pk"], obj["sk"])

    corpus_key = obj["corpus_key"]

    if corpus_key not in legal_corpus_keys:
        validation_errors[filename].append(
            {
                "filename": filename,
                "error": f"Corpus {corpus_key} is not a valid corpus key",
            }
        )

    if obj_type == ObjectType.ASSISTANT:

        assistant_id = obj["assistant_id"]
        uuid_collection[assistant_id].append(filename)

        if assistant_id != fields["assistant_id"]:
            validation_errors[filename].append(
                {
                    "error": f"assistant_id {assistant_id} does not match assistant_id in pk {fields['assistant_id']}",
                }
            )
        #  check if assistant_id is a valid hex uuid
        if not is_valid_hex_uuid(assistant_id):
            validation_errors[filename].append(
                {
                    "error": f"assistant_id {assistant_id} is not a valid hex uuid",
                }
            )

        if "tools" in obj:
            function_names = set()
            for tool_index, tool in enumerate(obj["tools"]):
                if "function" not in tool:
                    validation_errors[filename].append(
                        {
                            "error": f"function missing in tool {tool_index} in assistant {assistant_id} in corpus {corpus_key}",
                        }
                    )
                else:
                    function_record = tool["function"]
                    if "name" not in function_record:
                        validation_errors[filename].append(
                            {
                                "error": f"name missing in function {tool_index} in assistant {assistant_id} in corpus {corpus_key}",
                            }
                        )
                    else:
                        name = function_record["name"]
                        if name in function_names:
                            validation_errors[filename].append(
                                {
                                    "error": f"Duplicate function name {name} in tool {tool_index} in assistant {assistant_id} in corpus {corpus_key}",
                                }
                            )
                        function_names.add(name)

            if function_names:
                if "tool_to_lambda_map" not in obj:
                    validation_errors[filename].append(
                        {
                            "error": f"tool_to_lambda_map missing in assistant {assistant_id} in corpus {corpus_key}",
                        }
                    )
                else:
                    for function_name in function_names:
                        if function_name not in obj["tool_to_lambda_map"]:
                            validation_errors[filename].append(
                                {
                                    "error": f"function {function_name} missing in tool_to_lambda_map in assistant {assistant_id} in corpus {corpus_key}",
                                }
                            )
                        else:
                            lambda_map_record = obj["tool_to_lambda_map"][function_name]
                            if "lambda_name" not in lambda_map_record:
                                validation_errors[filename].append(
                                    {
                                        "error": f"lambda_name missing in tool_to_lambda_map for function {function_name} in assistant {assistant_id} in corpus {corpus_key}",
                                    }
                                )

        # Validate assistant_model_name if present
        if "assistant_model_name" in obj:
            assistant_model_name = obj["assistant_model_name"]

            # Check if it's a valid OPENAI_MODEL enum value
            valid_model_names = [model.name for model in OPENAI_MODEL]

            if assistant_model_name not in valid_model_names:
                validation_errors[filename].append(
                    {
                        "error": f"assistant_model_name '{assistant_model_name}' is not a valid OpenAI model. Valid models: {', '.join(valid_model_names)}",
                    }
                )

    if obj_type == ObjectType.CASE_MANAGER:

        case_manager_id = obj.get("case_manager_id")
        #  check if case_manager_id is a valid hex uuid
        if not is_valid_hex_uuid(case_manager_id):
            validation_errors[filename].append(
                {
                    "error": f"case_manager_id {case_manager_id} is not a valid hex uuid",
                }
            )

        uuid_collection[case_manager_id].append(filename)

        if case_manager_id != fields["case_manager_id"]:
            validation_errors[filename].append(
                {
                    "error": f"case_manager_id {case_manager_id} does not match case_manager_id in pk {fields['case_manager_id']}",
                }
            )

        if "sub_assistants" in obj:
            assistant_case_manager_graph["object_by_id"][case_manager_id] = {
                "filename": filename,
                "object": obj,
            }

            assistant_case_manager_graph["edges"][case_manager_id] = []

            corpus_key = obj["corpus_key"]

            for sub_assistant_index, sub_assistant in enumerate(obj["sub_assistants"]):

                assistant_key = sub_assistant.get("assistant_key")

                if assistant_key is not None:

                    if (
                        assistant_key
                        not in keys_by_corpus_key[corpus_key][ObjectType.ASSISTANT]
                    ):
                        validation_errors[filename].append(
                            {
                                "filename": filename,
                                "error": f"Assistant '{assistant_key}' not found, referenced in sub assistant {sub_assistant_index} in corpus {corpus_key}",
                            }
                        )
                    else:
                        target_assistant_key = (
                            corpus_key,
                            ObjectType.ASSISTANT,
                            assistant_key,
                        )
                        if (
                            target_assistant_key
                            not in assistant_case_manager_graph["objects_by_key"]
                        ):
                            validation_errors[filename].append(
                                {
                                    "filename": filename,
                                    "error": f"Assistant '{assistant_key}' not found, referenced in sub assistant {sub_assistant_index} in corpus {corpus_key}",
                                }
                            )
                        else:
                            target_assistant = assistant_case_manager_graph[
                                "objects_by_key"
                            ][target_assistant_key]
                            target_assistant_id = target_assistant["object"][
                                "assistant_id"
                            ]
                            assistant_case_manager_graph["object_by_id"][
                                target_assistant_id
                            ] = target_assistant

                            assistant_case_manager_graph["edges"][
                                case_manager_id
                            ].append(target_assistant_id)

                else:
                    validation_errors[filename].append(
                        {
                            "error": f"assistant_key missing in sub assistant {sub_assistant_index} in case manager {case_manager_id} in corpus {corpus_key}",
                        }
                    )

    if obj_type == ObjectType.CORPUS_METADATA:
        if "summarizer_model_name" not in obj:
            validation_errors[filename].append(
                {
                    "error": f"summarizer_model_name missing in corpus metadata {corpus_key}",
                }
            )
        if "openai_project_account_name" not in obj:
            validation_errors[filename].append(
                {
                    "error": f"openai_project_account_name missing in corpus metadata {corpus_key}",
                }
            )

        if "corpus_key" not in obj:
            validation_errors[filename].append(
                {
                    "error": f"corpus_key missing in corpus metadata {corpus_key}",
                }
            )

        if obj.get("corpus_key") != fields["corpus_key"]:
            validation_errors[filename].append(
                {
                    "error": f"corpus_key {obj['corpus_key']} does not match corpus_key in pk {fields['corpus_key']}",
                }
            )
        ui_settings = obj.get("ui_settings")
        if ui_settings is not None:
            case_manager_ui_settings = ui_settings.get("case_manager")
            if case_manager_ui_settings is not None:
                case_manager_default_case_manager_id = case_manager_ui_settings.get(
                    "case_manager_default_case_manager_id"
                )
                if case_manager_default_case_manager_id is not None:
                    if (
                        case_manager_default_case_manager_id
                        not in assistant_case_manager_graph["object_by_id"]
                    ):
                        validation_errors[filename].append(
                            {
                                "error": f"case_manager_default_case_manager_id {case_manager_default_case_manager_id} in corpus metadata {corpus_key} is not a valid case manager id",
                            }
                        )
            bot_ui_valid_keys = [
                "bot_ui_bot_bubble_color",
                "bot_ui_user_bubble_color",
                "bot_ui_bot_bubble_text_color",
                "bot_ui_user_bubble_text_color",
                "bot_ui_conversation_area_background_color",
                "bot_ui_conversation_area_text_color",
                "bot_ui_link_color",
                "bot_ui_font_size",
                "bot_ui_use_api_links",
            ]
            if "bot_ui" in ui_settings:
                bot_ui_settings = ui_settings["bot_ui"]
                for key in bot_ui_settings.keys():
                    if key not in bot_ui_valid_keys:
                        validation_errors[filename].append(
                            {
                                "error": f"Invalid key {key} in bot_ui settings in corpus metadata {corpus_key}",
                            }
                        )
                    if key.endswith("_color"):
                        color_value = bot_ui_settings[key]
                        if not isinstance(color_value, str) or not (
                            color_value.startswith("#")
                            and len(color_value) == 7
                            and all(
                                c in "0123456789abcdef" for c in color_value[1:].lower()
                            )
                        ):
                            validation_errors[filename].append(
                                {
                                    "error": f"Invalid color value {color_value} for key {key} in bot_ui settings in corpus metadata {corpus_key}",
                                }
                            )


def calc_environment_path(project_root_path, environment):
    path = (
        Path(project_root_path).absolute()
        / "environments"
        / environment
        / "corpus_keys"
    )
    return path


def validate_files(project_root_path, environment):

    validation_errors = defaultdict(list)
    path = calc_environment_path(project_root_path, environment)

    _logger.info(f"Validating files in {path}")

    # traverse the directory tree and look for all yaml files

    all_objects = []
    all_objects_with_file = []
    for file in list(path.rglob("*.yaml")) + list(path.rglob("*.yml")):
        file_identifier = file.as_posix()

        try:
            with open(file, "rb") as f:
                had_error = False
                try:
                    data = yaml.safe_load(f)
                    all_objects.append(data)
                    all_objects_with_file.append((data, file_identifier))
                except yaml.composer.ComposerError as e:
                    had_error = True

                if had_error:
                    f.seek(0)
                    data = yaml.safe_load_all(f)
                    for d in data:
                        all_objects.append(d)
                        all_objects_with_file.append((d, file_identifier))
        except Exception as e:
            _logger.error(f"Error reading file {file_identifier}: {e}")
            validation_errors[file_identifier].append(
                {
                    "filename": str(file),
                    "error": f"Error reading file {file_identifier}: {e}",
                }
            )

    _logger.info(f"Found {len(all_objects)} objects to load")

    keys_by_corpus_key = calc_keys(all_objects_with_file, validation_errors)

    legal_corpus_keys = set()
    for obj, file in all_objects_with_file:
        if calc_obj_type(obj) == ObjectType.CORPUS_METADATA:
            legal_corpus_keys.add(obj["corpus_key"])

    _logger.info(f"Corpus keys in environment: {legal_corpus_keys}")
    uuid_collection = defaultdict(list)
    assistant_case_manager_graph = {
        "object_by_id": {},
        "edges": {},
        "objects_by_key": calc_object_directory(all_objects_with_file),
    }

    def sort_key(object_with_file):
        object, file = object_with_file
        obj_type = calc_obj_type(object)
        obj_type_sort_order = {
            ObjectType.ASSISTANT: 0,
            ObjectType.CASE_MANAGER: 1,
            ObjectType.CORPUS_METADATA: 2,
        }
        return obj_type_sort_order.get(obj_type, 3), file

    all_objects_with_file = sorted(all_objects_with_file, key=sort_key)

    for obj, file in all_objects_with_file:
        _logger.debug(f"Validating {file}")
        validate(
            obj,
            str(file),
            keys_by_corpus_key,
            legal_corpus_keys,
            validation_errors,
            uuid_collection,
            assistant_case_manager_graph,
        )
    for key, files in uuid_collection.items():
        if len(files) > 1:
            validation_errors[files[0]].append(
                {
                    "error": f"Duplicate uuid {key} in files {files}",
                }
            )

    return dict(validation_errors), assistant_case_manager_graph


def calc_error_string(filename, validation_error, filename_field_width=50):

    return f"{filename:<{filename_field_width}}: {validation_error}"


def validate_monitoring_config(project_root_path, environment):
    """Validate monitoring configuration files."""
    validation_errors = defaultdict(list)

    # Define the path to monitoring configs
    monitoring_path = (
        Path(project_root_path).absolute() / "environments" / environment / "monitoring"
    )

    if not monitoring_path.exists():
        _logger.info(f"No monitoring directory found at {monitoring_path}")
        return {}

    _logger.info(f"Validating monitoring configurations in {monitoring_path}")

    # Load the schema
    schema_path = (
        Path(project_root_path).absolute()
        / "tools"
        / "schemas"
        / "url_monitor.schema.json"
    )
    if not schema_path.exists():
        _logger.warning(f"Schema not found at {schema_path}")
        return {}

    try:
        with open(schema_path, "r") as schema_file:
            schema = json.load(schema_file)
    except Exception as e:
        _logger.error(f"Error loading schema {schema_path}: {e}")
        return {}

    # Validate all JSON files in the monitoring directory
    for config_file in monitoring_path.glob("*.json"):
        file_identifier = config_file.as_posix()

        try:
            with open(config_file, "r") as f:
                data = json.load(f)

            # Validate against schema
            jsonschema.validate(instance=data, schema=schema)

            # Additional custom validation
            if "urls" in data:
                urls = data["urls"]
                if len(urls) == 0:
                    validation_errors[file_identifier].append(
                        {"error": "URLs list cannot be empty"}
                    )

                # Extract actual URLs for duplicate checking
                url_values = []
                for i, url_entry in enumerate(urls):
                    if isinstance(url_entry, str):
                        actual_url = url_entry
                    elif isinstance(url_entry, dict) and "url" in url_entry:
                        actual_url = url_entry["url"]
                    else:
                        validation_errors[file_identifier].append(
                            {
                                "error": f"URL at index {i} is neither a string nor an object with 'url' field"
                            }
                        )
                        continue

                    url_values.append(actual_url)

                    # Check URL format
                    if not actual_url.startswith(("http://", "https://")):
                        validation_errors[file_identifier].append(
                            {
                                "error": f"URL at index {i} must start with http:// or https://: {actual_url}"
                            }
                        )

                # Check for duplicate URLs
                if len(url_values) != len(set(url_values)):
                    validation_errors[file_identifier].append(
                        {"error": "Duplicate URLs found in the list"}
                    )

            # Validate custom dimensions
            if "custom_dimensions" in data:
                dimensions = data["custom_dimensions"]
                if not isinstance(dimensions, dict):
                    validation_errors[file_identifier].append(
                        {"error": "custom_dimensions must be an object"}
                    )
                else:
                    for key, value in dimensions.items():
                        if not isinstance(key, str) or not key:
                            validation_errors[file_identifier].append(
                                {
                                    "error": f"Dimension key must be a non-empty string: {key}"
                                }
                            )
                        if not isinstance(value, str) or not value:
                            validation_errors[file_identifier].append(
                                {
                                    "error": f"Dimension value must be a non-empty string for key '{key}': {value}"
                                }
                            )
                        if len(key) > 255:
                            validation_errors[file_identifier].append(
                                {
                                    "error": f"Dimension key too long (max 255 chars): {key}"
                                }
                            )
                        if len(value) > 255:
                            validation_errors[file_identifier].append(
                                {
                                    "error": f"Dimension value too long (max 255 chars) for key '{key}': {value}"
                                }
                            )

            _logger.info(f"✓ Monitoring config validated: {config_file.name}")

        except json.JSONDecodeError as e:
            validation_errors[file_identifier].append(
                {"error": f"Invalid JSON format: {e}"}
            )
        except jsonschema.exceptions.ValidationError as e:
            validation_errors[file_identifier].append(
                {"error": f"Schema validation failed: {e.message}"}
            )
        except Exception as e:
            validation_errors[file_identifier].append(
                {"error": f"Unexpected error: {e}"}
            )

    return dict(validation_errors)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Validate the corpus keys in the environment"
    )
    parser.add_argument(
        "--project-root-path",
        type=str,
        required=True,
        help="Path to the project root directory",
    )
    parser.add_argument(
        "--environment",
        type=str,
        required=True,
        help="Name of the environment to validate (staging, production, etc)",
    )

    args = parser.parse_args()

    root_path = Path(args.project_root_path).absolute()

    validation_errors, assistant_case_manager_graph = validate_files(
        root_path, args.environment
    )

    # Also validate monitoring configurations
    monitoring_validation_errors = validate_monitoring_config(
        root_path, args.environment
    )

    # Merge validation errors
    all_validation_errors = {**validation_errors, **monitoring_validation_errors}

    project_root_path_abs_string = root_path.absolute().as_posix()

    if all_validation_errors:
        for filename, errors in all_validation_errors.items():

            # strip the project root path from the filename
            short_filename = filename.replace(str(project_root_path_abs_string), "")
            short_filename = short_filename.lstrip("/")

            for error in errors:
                _logger.error(calc_error_string(short_filename, error["error"], 100))
        exit(1)
    else:
        _logger.info("No validation errors found")


if __name__ == "__main__":
    main()
