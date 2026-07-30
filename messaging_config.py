import re
from collections import defaultdict
from enum import Enum
from pathlib import Path
from string import Formatter

import yaml
from poemai_utils.aws.dao_helper import DaoHelper
from poemai_utils.enum_utils import add_enum_attrs, add_enum_repr

SUPPORTED_PROVIDER = "meta"
SUPPORTED_CHANNEL = "whatsapp"
CALLBACK_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
META_ID_PATTERN = re.compile(r"^[0-9]+$")
PARAMETER_RESOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class KeyElement(str, Enum):
    OBJECT_TYPE = "OBJECT_TYPE"
    CALLBACK_ID = "CALLBACK_ID"
    PROVIDER = "PROVIDER"
    CHANNEL = "CHANNEL"
    PROVIDER_CONNECTION_ID = "PROVIDER_CONNECTION_ID"
    PROVIDER_DESTINATION_ID = "PROVIDER_DESTINATION_ID"
    CONFIGURATION_KEY = "CONFIGURATION_KEY"


add_enum_repr(KeyElement)


class ObjectTypeKeys(str, Enum):
    PROVIDER_CALLBACK = "PROVIDER_CALLBACK"
    PROVIDER_CONNECTION = "PROVIDER_CONNECTION"
    PROVIDER_DESTINATION = "PROVIDER_DESTINATION"
    MESSAGING_CONFIGURATION = "MESSAGING_CONFIGURATION"


add_enum_repr(ObjectTypeKeys)


class BusinessObjectTypeKeys(str, Enum):
    MESSAGING_ROUTE = "MESSAGING_ROUTE"


add_enum_repr(BusinessObjectTypeKeys)


add_enum_attrs(
    {
        ObjectTypeKeys.PROVIDER_CALLBACK: {
            "pk_components": [KeyElement.OBJECT_TYPE],
            "sk_components": [KeyElement.CALLBACK_ID],
            "required_fields": [KeyElement.CALLBACK_ID],
            "to_drop_fields": [KeyElement.OBJECT_TYPE, KeyElement.CALLBACK_ID],
        },
        ObjectTypeKeys.PROVIDER_CONNECTION: {
            "pk_components": [KeyElement.OBJECT_TYPE],
            "sk_components": [KeyElement.PROVIDER_CONNECTION_ID],
            "required_fields": [KeyElement.PROVIDER_CONNECTION_ID],
            "to_drop_fields": [
                KeyElement.OBJECT_TYPE,
                KeyElement.PROVIDER_CONNECTION_ID,
            ],
        },
        ObjectTypeKeys.PROVIDER_DESTINATION: {
            "pk_components": [
                KeyElement.OBJECT_TYPE,
                KeyElement.PROVIDER,
                KeyElement.CHANNEL,
            ],
            "sk_components": [KeyElement.PROVIDER_DESTINATION_ID],
            "required_fields": [
                KeyElement.PROVIDER,
                KeyElement.CHANNEL,
                KeyElement.PROVIDER_DESTINATION_ID,
            ],
            "to_drop_fields": [
                KeyElement.OBJECT_TYPE,
                KeyElement.PROVIDER,
                KeyElement.CHANNEL,
                KeyElement.PROVIDER_DESTINATION_ID,
            ],
        },
        ObjectTypeKeys.MESSAGING_CONFIGURATION: {
            "pk_components": [KeyElement.OBJECT_TYPE],
            "sk_components": [KeyElement.CONFIGURATION_KEY],
            "required_fields": [KeyElement.CONFIGURATION_KEY],
            "to_drop_fields": [
                KeyElement.OBJECT_TYPE,
                KeyElement.CONFIGURATION_KEY,
            ],
        },
    }
)


add_enum_attrs(
    {
        BusinessObjectTypeKeys.MESSAGING_ROUTE: {
            "pk_components": [
                KeyElement.OBJECT_TYPE,
                KeyElement.PROVIDER,
                KeyElement.CHANNEL,
            ],
            "sk_components": [KeyElement.PROVIDER_DESTINATION_ID],
            "required_fields": [
                KeyElement.PROVIDER,
                KeyElement.CHANNEL,
                KeyElement.PROVIDER_DESTINATION_ID,
            ],
            "to_drop_fields": [
                KeyElement.OBJECT_TYPE,
                KeyElement.PROVIDER,
                KeyElement.CHANNEL,
                KeyElement.PROVIDER_DESTINATION_ID,
            ],
        }
    }
)


FIELD_TO_KEY_FORMATTERS = {}


PROVIDER_REQUIRED_FIELDS = {
    ObjectTypeKeys.PROVIDER_CALLBACK: {
        "callback_id",
        "environment",
        "provider",
        "channel",
        "app_secret_parameter_name",
        "verify_token_parameter_name",
        "meta_app_id",
        "active",
        "configuration_version",
        "created_at",
        "updated_at",
    },
    ObjectTypeKeys.PROVIDER_CONNECTION: {
        "provider_connection_id",
        "environment",
        "provider",
        "channel",
        "callback_id",
        "phone_number_id",
        "whatsapp_business_account_id",
        "access_token_parameter_name",
        "active",
        "configuration_version",
        "created_at",
        "updated_at",
    },
    ObjectTypeKeys.PROVIDER_DESTINATION: {
        "provider_destination_id",
        "environment",
        "provider",
        "channel",
        "provider_connection_id",
        "callback_id",
        "active",
        "configuration_version",
        "created_at",
        "updated_at",
    },
}


PROVIDER_OPTIONAL_FIELDS = {
    ObjectTypeKeys.PROVIDER_CALLBACK: {"operational_metadata"},
    ObjectTypeKeys.PROVIDER_CONNECTION: {"operational_metadata"},
    ObjectTypeKeys.PROVIDER_DESTINATION: set(),
}


ROUTE_REQUIRED_FIELDS = {
    "route_id",
    "provider",
    "channel",
    "provider_connection_id",
    "provider_destination_id",
    "case_manager_id",
    "active",
    "default_language_code",
    "configuration_version",
}

BOT_START_CONFIGURATION_KEY = "BOT_START"
BOT_START_REQUIRED_FIELDS = {
    "environment",
    "configuration_version",
    "default_target",
    "start_words",
    "unknown_start_word",
}
TARGET_REQUIRED_FIELDS = {"corpus_key", "case_manager_id"}


def provider_config_path(project_root_path, environment):
    return (
        Path(project_root_path).absolute()
        / "environments"
        / environment
        / "messaging"
        / "provider_connections.yaml"
    )


def bot_start_config_path(project_root_path, environment):
    return (
        Path(project_root_path).absolute()
        / "environments"
        / environment
        / "messaging"
        / "bot_start.yaml"
    )


def _read_yaml(path):
    with open(path, "r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def load_provider_objects(project_root_path, environment):
    path = provider_config_path(project_root_path, environment)
    if not path.exists():
        return path, [], None
    data = _read_yaml(path)
    if not isinstance(data, dict):
        return path, [], data
    objects = data.get("objects")
    return path, objects if isinstance(objects, list) else [], data


def load_bot_start_configuration(project_root_path, environment):
    path = bot_start_config_path(project_root_path, environment)
    if not path.exists():
        return path, None
    return path, _read_yaml(path)


def _add_error(errors, path, message):
    errors[str(path)].append({"filename": str(path), "error": message})


def _valid_key_value(value):
    return isinstance(value, str) and bool(value.strip()) and "#" not in value


def messaging_parameter_path_prefix(
    environment,
    provider=SUPPORTED_PROVIDER,
    channel=SUPPORTED_CHANNEL,
):
    return (
        f"/poemai/{environment}/messaging/providers/{provider}/" f"channels/{channel}/"
    )


def callback_credential_parameter_name(environment, callback_id, credential_name):
    return (
        f"{messaging_parameter_path_prefix(environment)}"
        f"callbacks/{callback_id}/credentials/{credential_name}"
    )


def connection_credential_parameter_name(
    environment,
    provider_connection_id,
    credential_name,
):
    return (
        f"{messaging_parameter_path_prefix(environment)}"
        f"connections/{provider_connection_id}/credentials/{credential_name}"
    )


def _validate_parameter_name(errors, path, field_name, value, expected):
    if value != expected:
        _add_error(
            errors,
            path,
            f"{field_name} must equal {expected}",
        )


def _contains_secret_value_field(value):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = str(key).lower()
            if normalized_key in {"access_token", "app_secret", "verify_token"}:
                return True
            if normalized_key.endswith("_secret") or normalized_key.endswith("_value"):
                return True
            if _contains_secret_value_field(child):
                return True
    elif isinstance(value, list):
        return any(_contains_secret_value_field(child) for child in value)
    return False


def _object_type(record):
    value = record.get("object_type") if isinstance(record, dict) else None
    try:
        return ObjectTypeKeys(value)
    except (TypeError, ValueError):
        return None


def build_provider_items(project_root_path, environment):
    _, records, provider_data = load_provider_objects(project_root_path, environment)
    _, bot_start_data = load_bot_start_configuration(project_root_path, environment)
    if provider_data is None and bot_start_data is None:
        return []
    errors = validate_messaging_configuration(project_root_path, environment)
    if errors:
        messages = [
            error["error"] for file_errors in errors.values() for error in file_errors
        ]
        raise ValueError("Invalid messaging configuration: " + "; ".join(messages))

    items = []
    for record in records:
        object_type = ObjectTypeKeys(record["object_type"])
        items.append(
            DaoHelper.build_object_item(
                KeyElement,
                FIELD_TO_KEY_FORMATTERS,
                object_type,
                record,
            )
        )
    if bot_start_data is not None:
        item_data = dict(bot_start_data)
        item_data["configuration_key"] = BOT_START_CONFIGURATION_KEY
        item_data["start_words"] = {
            normalize_start_word(start_word): target
            for start_word, target in bot_start_data["start_words"].items()
        }
        items.append(
            DaoHelper.build_object_item(
                KeyElement,
                FIELD_TO_KEY_FORMATTERS,
                ObjectTypeKeys.MESSAGING_CONFIGURATION,
                item_data,
            )
        )
    return items


def _provider_records_by_type(records):
    by_type = defaultdict(list)
    for record in records:
        object_type = _object_type(record)
        if object_type is not None:
            by_type[object_type].append(record)
    return by_type


def _validate_provider_records(errors, path, records, data, environment):
    if not isinstance(data, dict):
        _add_error(errors, path, "provider_connections.yaml must contain a mapping")
        return
    if data.get("environment") != environment:
        _add_error(
            errors,
            path,
            f"environment must match directory environment {environment}",
        )
    if not isinstance(data.get("objects"), list):
        _add_error(errors, path, "objects must be a list")
        return
    if _contains_secret_value_field(data):
        _add_error(errors, path, "configuration contains a secret value field")

    seen_keys = defaultdict(set)
    for index, record in enumerate(records):
        location = f"objects[{index}]"
        if not isinstance(record, dict):
            _add_error(errors, path, f"{location} must be a mapping")
            continue
        object_type = _object_type(record)
        if object_type is None:
            _add_error(errors, path, f"{location}.object_type is unsupported")
            continue

        required = PROVIDER_REQUIRED_FIELDS[object_type] | {"object_type"}
        allowed = required | PROVIDER_OPTIONAL_FIELDS[object_type]
        missing = sorted(required - set(record))
        unexpected = sorted(set(record) - allowed)
        if missing:
            _add_error(errors, path, f"{location} is missing fields {missing}")
        if unexpected:
            _add_error(errors, path, f"{location} has unsupported fields {unexpected}")

        if record.get("environment") != environment:
            _add_error(errors, path, f"{location}.environment must be {environment}")
        if record.get("provider") != SUPPORTED_PROVIDER:
            _add_error(errors, path, f"{location}.provider must be meta")
        if record.get("channel") != SUPPORTED_CHANNEL:
            _add_error(errors, path, f"{location}.channel must be whatsapp")
        if not isinstance(record.get("active"), bool):
            _add_error(errors, path, f"{location}.active must be a boolean")
        if (
            not isinstance(record.get("configuration_version"), int)
            or record.get("configuration_version", 0) < 1
        ):
            _add_error(
                errors,
                path,
                f"{location}.configuration_version must be a positive integer",
            )

        for field_name in PROVIDER_REQUIRED_FIELDS[object_type]:
            if field_name.endswith("_id") and not _valid_key_value(
                record.get(field_name)
            ):
                _add_error(
                    errors,
                    path,
                    f"{location}.{field_name} must be non-empty and contain no #",
                )

        if object_type == ObjectTypeKeys.PROVIDER_CALLBACK:
            callback_id = record.get("callback_id")
            if not isinstance(callback_id, str) or not CALLBACK_ID_PATTERN.fullmatch(
                callback_id
            ):
                _add_error(
                    errors,
                    path,
                    f"{location}.callback_id must be 32 lowercase hex characters",
                )
            callback_parameters = {
                "app_secret_parameter_name": "app-secret",
                "verify_token_parameter_name": "verify-token",
            }
            for field_name, credential_name in callback_parameters.items():
                expected = callback_credential_parameter_name(
                    environment,
                    callback_id,
                    credential_name,
                )
                _validate_parameter_name(
                    errors,
                    path,
                    f"{location}.{field_name}",
                    record.get(field_name),
                    expected,
                )
            meta_app_id = record.get("meta_app_id")
            if not isinstance(meta_app_id, str) or not META_ID_PATTERN.fullmatch(
                meta_app_id
            ):
                _add_error(errors, path, f"{location}.meta_app_id must be numeric")
            identity = callback_id
        elif object_type == ObjectTypeKeys.PROVIDER_CONNECTION:
            provider_connection_id = record.get("provider_connection_id")
            if not isinstance(provider_connection_id, str) or not (
                len(provider_connection_id) <= 128
                and PARAMETER_RESOURCE_ID_PATTERN.fullmatch(provider_connection_id)
            ):
                _add_error(
                    errors,
                    path,
                    f"{location}.provider_connection_id must be a 1-128 character lowercase Parameter Store path segment",
                )
            _validate_parameter_name(
                errors,
                path,
                f"{location}.access_token_parameter_name",
                record.get("access_token_parameter_name"),
                connection_credential_parameter_name(
                    environment,
                    provider_connection_id,
                    "access-token",
                ),
            )
            for field_name in ("phone_number_id", "whatsapp_business_account_id"):
                value = record.get(field_name)
                if not isinstance(value, str) or not META_ID_PATTERN.fullmatch(value):
                    _add_error(errors, path, f"{location}.{field_name} must be numeric")
            identity = record.get("provider_connection_id")
        else:
            identity = record.get("provider_destination_id")

        if identity in seen_keys[object_type]:
            _add_error(
                errors, path, f"duplicate {object_type.value} identifier {identity}"
            )
        seen_keys[object_type].add(identity)

        try:
            item = DaoHelper.build_object_item(
                KeyElement,
                FIELD_TO_KEY_FORMATTERS,
                object_type,
                record,
            )
            if not item.get("pk") or not item.get("sk"):
                raise ValueError("empty generated key")
        except (KeyError, TypeError, ValueError) as error:
            _add_error(errors, path, f"{location} cannot generate DAO keys: {error}")


def _validate_provider_cross_references(errors, path, records):
    by_type = _provider_records_by_type(records)
    callbacks = {
        record.get("callback_id"): record
        for record in by_type[ObjectTypeKeys.PROVIDER_CALLBACK]
    }
    connections = {
        record.get("provider_connection_id"): record
        for record in by_type[ObjectTypeKeys.PROVIDER_CONNECTION]
    }

    active_app_ids = {}
    for callback in callbacks.values():
        if not callback.get("active"):
            continue
        app_id = callback.get("meta_app_id")
        if app_id in active_app_ids:
            _add_error(errors, path, f"two active callbacks claim Meta app ID {app_id}")
        active_app_ids[app_id] = callback.get("callback_id")

    for connection in by_type[ObjectTypeKeys.PROVIDER_CONNECTION]:
        callback = callbacks.get(connection.get("callback_id"))
        if callback is None:
            _add_error(
                errors,
                path,
                f"connection {connection.get('provider_connection_id')} references an unknown callback",
            )
        elif connection.get("active") and not callback.get("active"):
            _add_error(
                errors,
                path,
                f"active connection {connection.get('provider_connection_id')} references a disabled callback",
            )

    for destination in by_type[ObjectTypeKeys.PROVIDER_DESTINATION]:
        connection = connections.get(destination.get("provider_connection_id"))
        if connection is None:
            _add_error(
                errors,
                path,
                f"destination {destination.get('provider_destination_id')} references an unknown connection",
            )
            continue
        if destination.get("callback_id") != connection.get("callback_id"):
            _add_error(
                errors,
                path,
                f"destination {destination.get('provider_destination_id')} has the wrong callback",
            )
        if destination.get("provider_destination_id") != connection.get(
            "phone_number_id"
        ):
            _add_error(
                errors,
                path,
                f"destination {destination.get('provider_destination_id')} must match its connection phone_number_id",
            )
        if destination.get("active") and not connection.get("active"):
            _add_error(
                errors,
                path,
                f"active destination {destination.get('provider_destination_id')} references a disabled connection",
            )


def _corpus_metadata_files(project_root_path, environment):
    corpus_path = (
        Path(project_root_path).absolute()
        / "environments"
        / environment
        / "corpus_keys"
    )
    return sorted(corpus_path.glob("*/corpus_metadata.yaml"))


def _case_managers(corpus_directory):
    managers = {}
    for path in list(corpus_directory.glob("*.yaml")) + list(
        corpus_directory.glob("*.yml")
    ):
        data = _read_yaml(path)
        if isinstance(data, dict) and data.get("case_manager_id"):
            managers[data["case_manager_id"]] = data
    return managers


def normalize_start_word(value):
    return " ".join(value.split()).casefold()


def _active_messaging_languages(project_root_path, environment):
    languages = set()
    for metadata_path in _corpus_metadata_files(project_root_path, environment):
        metadata = _read_yaml(metadata_path)
        messaging = metadata.get("messaging") if isinstance(metadata, dict) else None
        if not isinstance(messaging, dict):
            continue
        for route in messaging.get("routes") or []:
            if isinstance(route, dict) and route.get("active"):
                language_code = route.get("default_language_code")
                if isinstance(language_code, str) and language_code:
                    languages.add(language_code)
    return languages


def _corpus_catalog(project_root_path, environment):
    catalog = {}
    for metadata_path in _corpus_metadata_files(project_root_path, environment):
        metadata = _read_yaml(metadata_path)
        if not isinstance(metadata, dict):
            continue
        corpus_key = metadata.get("corpus_key")
        if isinstance(corpus_key, str):
            catalog[corpus_key] = (
                metadata_path,
                metadata,
                _case_managers(metadata_path.parent),
            )
    return catalog


def _validate_target(
    errors,
    path,
    location,
    target,
    environment,
    corpus_catalog,
    required_languages,
):
    if not isinstance(target, dict):
        _add_error(errors, path, f"{location} must be a mapping")
        return
    missing = sorted(TARGET_REQUIRED_FIELDS - set(target))
    unexpected = sorted(set(target) - TARGET_REQUIRED_FIELDS)
    if missing:
        _add_error(errors, path, f"{location} is missing fields {missing}")
    if unexpected:
        _add_error(errors, path, f"{location} has unsupported fields {unexpected}")

    for field_name in TARGET_REQUIRED_FIELDS:
        if not _valid_key_value(target.get(field_name)):
            _add_error(
                errors,
                path,
                f"{location}.{field_name} must be non-empty and contain no #",
            )

    corpus_key = target.get("corpus_key")
    corpus_entry = corpus_catalog.get(corpus_key)
    if corpus_entry is None:
        _add_error(errors, path, f"{location} references unknown corpus {corpus_key}")
        return

    _, metadata, case_managers = corpus_entry
    if metadata.get("environment") != environment:
        _add_error(
            errors,
            path,
            f"{location} references a corpus outside environment {environment}",
        )
    if metadata.get("public_bot") is not True:
        _add_error(errors, path, f"{location} references a non-public corpus")

    case_manager_id = target.get("case_manager_id")
    case_manager = case_managers.get(case_manager_id)
    if case_manager is None:
        _add_error(
            errors,
            path,
            f"{location} references unknown case manager {case_manager_id} in corpus {corpus_key}",
        )
        return
    if case_manager.get("corpus_key") not in (None, corpus_key):
        _add_error(
            errors,
            path,
            f"{location} case manager belongs to another corpus",
        )

    language_mapping = case_manager.get("initial_workspace", {}).get(
        "_language_mapping", {}
    )
    for language_code in sorted(required_languages):
        if language_code not in language_mapping:
            _add_error(
                errors,
                path,
                f"{location} case manager does not support language {language_code}",
            )


def _validate_response_template(errors, path, language_code, template):
    location = f"unknown_start_word.{language_code}"
    if not isinstance(template, str) or not template.strip():
        _add_error(errors, path, f"{location} must be a non-empty string")
        return
    placeholder_count = 0
    try:
        for _, field_name, format_spec, conversion in Formatter().parse(template):
            if field_name is None:
                continue
            if field_name != "start_word" or format_spec or conversion is not None:
                _add_error(
                    errors,
                    path,
                    f"{location} may only use the {{start_word}} placeholder",
                )
                return
            placeholder_count += 1
        template.format(start_word="example")
    except (KeyError, ValueError):
        _add_error(errors, path, f"{location} is a malformed response template")
        return
    if placeholder_count != 1:
        _add_error(
            errors,
            path,
            f"{location} must contain exactly one {{start_word}} placeholder",
        )


def _validate_bot_start_configuration(
    errors,
    project_root_path,
    environment,
    provider_data,
):
    path, data = load_bot_start_configuration(project_root_path, environment)
    if data is None:
        if provider_data is not None:
            _add_error(errors, path, "bot_start.yaml is required")
        return
    if not isinstance(data, dict):
        _add_error(errors, path, "bot_start.yaml must contain a mapping")
        return

    missing = sorted(BOT_START_REQUIRED_FIELDS - set(data))
    unexpected = sorted(set(data) - BOT_START_REQUIRED_FIELDS)
    if missing:
        _add_error(errors, path, f"bot_start.yaml is missing fields {missing}")
    if unexpected:
        _add_error(errors, path, f"bot_start.yaml has unsupported fields {unexpected}")
    if data.get("environment") != environment:
        _add_error(errors, path, f"environment must be {environment}")
    if (
        not isinstance(data.get("configuration_version"), int)
        or data.get("configuration_version", 0) < 1
    ):
        _add_error(
            errors,
            path,
            "configuration_version must be a positive integer",
        )

    active_languages = _active_messaging_languages(project_root_path, environment)
    corpus_catalog = _corpus_catalog(project_root_path, environment)
    _validate_target(
        errors,
        path,
        "default_target",
        data.get("default_target"),
        environment,
        corpus_catalog,
        active_languages,
    )

    start_words = data.get("start_words")
    if not isinstance(start_words, dict):
        _add_error(errors, path, "start_words must be a mapping")
    else:
        normalized_words = {}
        for start_word, target in start_words.items():
            if not isinstance(start_word, str) or not normalize_start_word(start_word):
                _add_error(errors, path, "start_words keys must be non-empty strings")
                continue
            normalized_word = normalize_start_word(start_word)
            if normalized_word in normalized_words:
                _add_error(
                    errors,
                    path,
                    f"start_words {start_word!r} and {normalized_words[normalized_word]!r} normalize to the same word",
                )
            normalized_words[normalized_word] = start_word
            _validate_target(
                errors,
                path,
                f"start_words[{start_word!r}]",
                target,
                environment,
                corpus_catalog,
                active_languages,
            )

    responses = data.get("unknown_start_word")
    if not isinstance(responses, dict):
        _add_error(errors, path, "unknown_start_word must be a mapping")
        return
    for language_code in sorted(active_languages):
        if language_code not in responses:
            _add_error(
                errors,
                path,
                f"unknown_start_word.{language_code} must be configured",
            )
    for language_code, template in responses.items():
        if not isinstance(language_code, str) or not language_code.strip():
            _add_error(
                errors,
                path,
                "unknown_start_word language keys must be non-empty strings",
            )
            continue
        _validate_response_template(errors, path, language_code, template)


def _provider_lookup(records):
    by_type = _provider_records_by_type(records)
    connections = {
        record.get("provider_connection_id"): record
        for record in by_type[ObjectTypeKeys.PROVIDER_CONNECTION]
    }
    destinations = {
        record.get("provider_destination_id"): record
        for record in by_type[ObjectTypeKeys.PROVIDER_DESTINATION]
    }
    return connections, destinations


def _validate_business_routes(errors, project_root_path, environment, records):
    connections, destinations = _provider_lookup(records)
    claimed_destinations = {}

    for metadata_path in _corpus_metadata_files(project_root_path, environment):
        metadata = _read_yaml(metadata_path)
        messaging = metadata.get("messaging") if isinstance(metadata, dict) else None
        if messaging is None:
            continue
        if not isinstance(messaging, dict):
            _add_error(errors, metadata_path, "messaging must be a mapping")
            continue
        if _contains_secret_value_field(messaging):
            _add_error(errors, metadata_path, "messaging contains a secret value field")

        enabled = messaging.get("enabled")
        routes = messaging.get("routes")
        notices = messaging.get("notices")
        if not isinstance(enabled, bool):
            _add_error(errors, metadata_path, "messaging.enabled must be a boolean")
        if not isinstance(routes, list):
            _add_error(errors, metadata_path, "messaging.routes must be a list")
            continue
        if not isinstance(notices, dict):
            _add_error(errors, metadata_path, "messaging.notices must be a mapping")
            notices = {}
        if enabled and not routes:
            _add_error(errors, metadata_path, "enabled messaging requires a route")
        if metadata.get("environment") != environment:
            _add_error(
                errors, metadata_path, f"corpus environment must be {environment}"
            )
        if metadata.get("public_bot") is not True:
            _add_error(errors, metadata_path, "messaging requires public_bot: true")

        case_managers = _case_managers(metadata_path.parent)
        route_ids = set()
        for index, route in enumerate(routes):
            location = f"messaging.routes[{index}]"
            if not isinstance(route, dict):
                _add_error(errors, metadata_path, f"{location} must be a mapping")
                continue
            missing = sorted(ROUTE_REQUIRED_FIELDS - set(route))
            unexpected = sorted(set(route) - ROUTE_REQUIRED_FIELDS)
            if missing:
                _add_error(
                    errors, metadata_path, f"{location} is missing fields {missing}"
                )
            if unexpected:
                _add_error(
                    errors,
                    metadata_path,
                    f"{location} has unsupported fields {unexpected}",
                )
            for field_name in (
                "route_id",
                "provider_connection_id",
                "provider_destination_id",
                "case_manager_id",
            ):
                if not _valid_key_value(route.get(field_name)):
                    _add_error(
                        errors,
                        metadata_path,
                        f"{location}.{field_name} must be non-empty and contain no #",
                    )
            if route.get("route_id") in route_ids:
                _add_error(
                    errors, metadata_path, f"duplicate route_id {route.get('route_id')}"
                )
            route_ids.add(route.get("route_id"))
            if route.get("provider") != SUPPORTED_PROVIDER:
                _add_error(errors, metadata_path, f"{location}.provider must be meta")
            if route.get("channel") != SUPPORTED_CHANNEL:
                _add_error(
                    errors, metadata_path, f"{location}.channel must be whatsapp"
                )
            if not isinstance(route.get("active"), bool):
                _add_error(
                    errors, metadata_path, f"{location}.active must be a boolean"
                )
            if (
                not isinstance(route.get("configuration_version"), int)
                or route.get("configuration_version", 0) < 1
            ):
                _add_error(
                    errors,
                    metadata_path,
                    f"{location}.configuration_version must be a positive integer",
                )

            connection = connections.get(route.get("provider_connection_id"))
            destination = destinations.get(route.get("provider_destination_id"))
            if connection is None:
                _add_error(
                    errors,
                    metadata_path,
                    f"{location} references an unknown connection",
                )
            if destination is None:
                _add_error(
                    errors,
                    metadata_path,
                    f"{location} references an unknown destination",
                )
            elif destination.get("provider_connection_id") != route.get(
                "provider_connection_id"
            ):
                _add_error(
                    errors,
                    metadata_path,
                    f"{location} destination belongs to another connection",
                )

            manager = case_managers.get(route.get("case_manager_id"))
            if manager is None:
                _add_error(
                    errors,
                    metadata_path,
                    f"{location} references an unknown case manager",
                )
            else:
                language_code = route.get("default_language_code")
                language_mapping = manager.get("initial_workspace", {}).get(
                    "_language_mapping", {}
                )
                if language_code not in language_mapping:
                    _add_error(
                        errors,
                        metadata_path,
                        f"{location}.default_language_code is not supported by its case manager",
                    )

            if route.get("active"):
                if not enabled:
                    _add_error(
                        errors,
                        metadata_path,
                        f"{location} is active while messaging is disabled",
                    )
                if connection is not None and not connection.get("active"):
                    _add_error(
                        errors,
                        metadata_path,
                        f"{location} references a disabled connection",
                    )
                if destination is not None and not destination.get("active"):
                    _add_error(
                        errors,
                        metadata_path,
                        f"{location} references a disabled destination",
                    )
                destination_id = route.get("provider_destination_id")
                if destination_id in claimed_destinations:
                    _add_error(
                        errors,
                        metadata_path,
                        f"destination {destination_id} is already claimed by {claimed_destinations[destination_id]}",
                    )
                claimed_destinations[destination_id] = metadata.get("corpus_key")

                language_code = route.get("default_language_code")
                for notice_name in (
                    "unsupported_media",
                    "reset_completed",
                    "temporary_failure",
                ):
                    notice = notices.get(notice_name)
                    if (
                        not isinstance(notice, dict)
                        or not isinstance(notice.get(language_code), str)
                        or not notice.get(language_code).strip()
                    ):
                        _add_error(
                            errors,
                            metadata_path,
                            f"messaging.notices.{notice_name}.{language_code} must be a non-empty string",
                        )


def _validate_callback_not_reused(errors, project_root_path, environment, records):
    current_ids = {
        record.get("callback_id")
        for record in records
        if _object_type(record) == ObjectTypeKeys.PROVIDER_CALLBACK
    }
    environments_path = Path(project_root_path).absolute() / "environments"
    for other_environment_path in environments_path.iterdir():
        other_environment = other_environment_path.name
        if other_environment == environment:
            continue
        other_path, other_records, _ = load_provider_objects(
            project_root_path, other_environment
        )
        other_ids = {
            record.get("callback_id")
            for record in other_records
            if _object_type(record) == ObjectTypeKeys.PROVIDER_CALLBACK
        }
        for callback_id in sorted(current_ids & other_ids):
            _add_error(
                errors,
                provider_config_path(project_root_path, environment),
                f"callback ID {callback_id} is also used in {other_path}",
            )


def validate_messaging_configuration(project_root_path, environment):
    errors = defaultdict(list)
    path, records, data = load_provider_objects(project_root_path, environment)
    if data is not None:
        _validate_provider_records(errors, path, records, data, environment)
        _validate_provider_cross_references(errors, path, records)
        _validate_callback_not_reused(errors, project_root_path, environment, records)
    _validate_business_routes(errors, project_root_path, environment, records)
    _validate_bot_start_configuration(
        errors,
        project_root_path,
        environment,
        data,
    )
    return dict(errors)


def build_business_route_aliases(project_root_path, environment):
    errors = validate_messaging_configuration(project_root_path, environment)
    if errors:
        messages = [
            error["error"] for file_errors in errors.values() for error in file_errors
        ]
        raise ValueError("Invalid messaging configuration: " + "; ".join(messages))

    aliases = []
    for metadata_path in _corpus_metadata_files(project_root_path, environment):
        metadata = _read_yaml(metadata_path)
        messaging = metadata.get("messaging") or {}
        for route in messaging.get("routes") or []:
            if not route.get("active"):
                continue
            aliases.append(
                DaoHelper.build_object_item(
                    KeyElement,
                    FIELD_TO_KEY_FORMATTERS,
                    BusinessObjectTypeKeys.MESSAGING_ROUTE,
                    {
                        "provider": SUPPORTED_PROVIDER,
                        "channel": SUPPORTED_CHANNEL,
                        "provider_destination_id": route["provider_destination_id"],
                        "corpus_key": metadata["corpus_key"],
                        "case_manager_id": route["case_manager_id"],
                        "provider_connection_id": route["provider_connection_id"],
                        "default_language_code": route["default_language_code"],
                        "active": True,
                        "configuration_version": route["configuration_version"],
                        "route_id": route["route_id"],
                        "environment": environment,
                    },
                )
            )
    return aliases
