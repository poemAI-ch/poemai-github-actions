import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from messaging_config import (
    build_business_route_aliases,
    build_provider_items,
    validate_messaging_configuration,
)

CALLBACK_ID = "0123456789abcdef0123456789abcdef"
CONNECTION_ID = "meta-whatsapp-poemai-bot-staging"
DESTINATION_ID = "123456789012345"
CASE_MANAGER_ID = "f4485650031041918c500c43170225e3"


def _write_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _provider_config():
    common = {
        "environment": "staging",
        "provider": "meta",
        "channel": "whatsapp",
        "active": True,
        "configuration_version": 1,
        "created_at": "2026-07-22T10:00:00+00:00",
        "updated_at": "2026-07-22T10:00:00+00:00",
    }
    return {
        "environment": "staging",
        "objects": [
            {
                **common,
                "object_type": "PROVIDER_CALLBACK",
                "callback_id": CALLBACK_ID,
                "app_secret_secret_name": "staging/messaging/meta/app-secret",
                "verify_token_secret_name": "staging/messaging/meta/verify-token",
                "meta_app_id": "111222333444555",
            },
            {
                **common,
                "object_type": "PROVIDER_CONNECTION",
                "provider_connection_id": CONNECTION_ID,
                "callback_id": CALLBACK_ID,
                "phone_number_id": DESTINATION_ID,
                "whatsapp_business_account_id": "999888777666555",
                "access_token_secret_name": "staging/messaging/meta/access-token",
            },
            {
                **common,
                "object_type": "PROVIDER_DESTINATION",
                "provider_destination_id": DESTINATION_ID,
                "provider_connection_id": CONNECTION_ID,
                "callback_id": CALLBACK_ID,
            },
        ],
    }


def _write_valid_project(tmp_path):
    _write_yaml(
        tmp_path / "environments/staging/messaging/provider_connections.yaml",
        _provider_config(),
    )
    corpus_directory = tmp_path / "environments/staging/corpus_keys/POEMAI_BOT"
    _write_yaml(
        corpus_directory / "corpus_metadata.yaml",
        {
            "pk": "CORPUS_METADATA#",
            "sk": "CORPUS_KEY#POEMAI_BOT",
            "corpus_key": "POEMAI_BOT",
            "environment": "staging",
            "public_bot": True,
            "messaging": {
                "enabled": True,
                "routes": [
                    {
                        "route_id": "poemai-bot-meta-whatsapp-staging",
                        "provider": "meta",
                        "channel": "whatsapp",
                        "provider_connection_id": CONNECTION_ID,
                        "provider_destination_id": DESTINATION_ID,
                        "case_manager_id": CASE_MANAGER_ID,
                        "active": True,
                        "default_language_code": "de",
                        "configuration_version": 1,
                    }
                ],
                "notices": {
                    "unsupported_media": {"de": "Bitte senden Sie Text."},
                    "reset_completed": {"de": "Der Chat wurde zurückgesetzt."},
                    "temporary_failure": {"de": "Bitte versuchen Sie es später."},
                },
            },
        },
    )
    _write_yaml(
        corpus_directory / "poemai_bot_case_manager.yaml",
        {
            "pk": "CORPUS_KEY#POEMAI_BOT#CASE_MANAGER#",
            "sk": f"CASE_MANAGER_ID#{CASE_MANAGER_ID}",
            "case_manager_id": CASE_MANAGER_ID,
            "corpus_key": "POEMAI_BOT",
            "initial_workspace": {
                "_default_language_name": "Deutsch",
                "_language_mapping": {"de": "Deutsch"},
            },
        },
    )


def test_build_provider_items_uses_dao_helper_key_shapes(tmp_path):
    _write_valid_project(tmp_path)

    items = build_provider_items(tmp_path, "staging")

    assert [(item["pk"], item["sk"]) for item in items] == [
        ("PROVIDER_CALLBACK#", f"CALLBACK_ID#{CALLBACK_ID}"),
        ("PROVIDER_CONNECTION#", f"PROVIDER_CONNECTION_ID#{CONNECTION_ID}"),
        (
            "PROVIDER_DESTINATION##PROVIDER#meta#CHANNEL#whatsapp",
            f"PROVIDER_DESTINATION_ID#{DESTINATION_ID}",
        ),
    ]
    assert "callback_id" not in items[0]
    assert "provider_connection_id" not in items[1]
    assert "provider_destination_id" not in items[2]


def test_build_business_route_aliases_creates_direct_lookup_item(tmp_path):
    _write_valid_project(tmp_path)

    aliases = build_business_route_aliases(tmp_path, "staging")

    assert aliases == [
        {
            "pk": "MESSAGING_ROUTE##PROVIDER#meta#CHANNEL#whatsapp",
            "sk": f"PROVIDER_DESTINATION_ID#{DESTINATION_ID}",
            "corpus_key": "POEMAI_BOT",
            "case_manager_id": CASE_MANAGER_ID,
            "provider_connection_id": CONNECTION_ID,
            "default_language_code": "de",
            "active": True,
            "configuration_version": 1,
            "route_id": "poemai-bot-meta-whatsapp-staging",
            "environment": "staging",
        }
    ]


def test_validator_rejects_secret_values_and_cross_callback_aliases(tmp_path):
    _write_valid_project(tmp_path)
    path = tmp_path / "environments/staging/messaging/provider_connections.yaml"
    data = _provider_config()
    data["objects"][0]["app_secret"] = "must-not-be-here"
    data["objects"][2]["callback_id"] = "f" * 32
    _write_yaml(path, data)

    errors = validate_messaging_configuration(tmp_path, "staging")
    messages = [
        error["error"]
        for errors_for_file in errors.values()
        for error in errors_for_file
    ]

    assert any("secret value field" in message for message in messages)
    assert any("wrong callback" in message for message in messages)


def test_validator_rejects_duplicate_active_destination_claims(tmp_path):
    _write_valid_project(tmp_path)
    first_metadata = (
        tmp_path / "environments/staging/corpus_keys/POEMAI_BOT/corpus_metadata.yaml"
    )
    second_directory = tmp_path / "environments/staging/corpus_keys/SECOND_BOT"
    second_metadata = yaml.safe_load(first_metadata.read_text(encoding="utf-8"))
    second_metadata["corpus_key"] = "SECOND_BOT"
    second_metadata["sk"] = "CORPUS_KEY#SECOND_BOT"
    _write_yaml(second_directory / "corpus_metadata.yaml", second_metadata)
    _write_yaml(
        second_directory / "case_manager.yaml",
        {
            "case_manager_id": CASE_MANAGER_ID,
            "initial_workspace": {"_language_mapping": {"de": "Deutsch"}},
        },
    )

    errors = validate_messaging_configuration(tmp_path, "staging")
    messages = [
        error["error"]
        for errors_for_file in errors.values()
        for error in errors_for_file
    ]

    assert any("already claimed" in message for message in messages)
