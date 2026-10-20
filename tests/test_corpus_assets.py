"""Contract tests for public image publication and configuration deployment."""

import copy
import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from corpus_assets import CACHE_CONTROL, MIME_TYPES, config_files, prepare_corpus_assets

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "asset_deployer", ROOT / "deploy-poemai-config/deploy_config_with_lambda_call.py"
)
deployer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployer)


def corpus(tmp_path, environment="staging", name="BOT", reference="assets/logo.png"):
    directory = tmp_path / "environments" / environment / "corpus_keys" / name
    (directory / "assets").mkdir(parents=True)
    (directory / "assets/logo.png").write_bytes(b"test image")
    metadata = {
        "pk": "CORPUS_METADATA#",
        "sk": f"CORPUS_KEY#{name}",
        "corpus_key": name,
        "bot_logo_url": reference,
        "chat_title_image_url": reference,
        "ui_settings": {"case_manager": {"case_manager_welcome_image_url": reference}},
    }
    (directory / "corpus_metadata.yaml").write_text(yaml.safe_dump(metadata))
    return directory, metadata


def test_hash_urls_all_fields_and_source_preserved(tmp_path):
    directory, metadata = corpus(tmp_path)
    before = (directory / "corpus_metadata.yaml").read_bytes()
    plan = prepare_corpus_assets(directory.parent, "staging")
    result = plan.resolve(metadata, directory / "corpus_metadata.yaml")
    digest = hashlib.sha256(b"test image").hexdigest()
    url = f"https://poemai-assets.s3.eu-central-2.amazonaws.com/config/staging/corpus_keys/BOT/assets/{digest}/logo.png"
    assert result["bot_logo_url"] == result["chat_title_image_url"] == url
    assert (
        result["ui_settings"]["case_manager"]["case_manager_welcome_image_url"] == url
    )
    assert metadata["bot_logo_url"] == "assets/logo.png"
    assert (directory / "corpus_metadata.yaml").read_bytes() == before
    assert prepare_corpus_assets(directory, "staging").assets[0].url == url
    (directory / "assets/logo.png").write_bytes(b"replacement")
    assert prepare_corpus_assets(directory, "staging").assets[0].url != url


@pytest.mark.parametrize("extension,mime", MIME_TYPES.items())
def test_formats_nested_paths_and_upload_headers(tmp_path, extension, mime):
    directory, _ = corpus(tmp_path)
    nested = directory / "assets/nested folder" / f"image{extension.upper()}"
    nested.parent.mkdir()
    nested.write_bytes(b"nested image")
    plan = prepare_corpus_assets(directory, "staging")
    asset = next(a for a in plan.assets if a.source == nested)
    assert asset.content_type == mime
    assert "nested%20folder/image" in asset.url
    client = Mock(spec=["put_object"])
    plan.publish(client)
    call = next(
        c.kwargs
        for c in client.put_object.call_args_list
        if c.kwargs["Key"] == asset.key
    )
    assert call == dict(
        Bucket="poemai-assets",
        Key=asset.key,
        Body=b"nested image",
        ContentType=mime,
        CacheControl=CACHE_CONTROL,
    )


@pytest.mark.parametrize(
    "reference",
    [
        "https://example.org/logo.png",
        "http://example.org/logo.png",
        "//example.org/logo.png",
        "data:image/png;base64,aA==",
    ],
)
def test_absolute_urls_preserved(tmp_path, reference):
    directory, metadata = corpus(tmp_path, reference=reference)
    assert (
        prepare_corpus_assets(directory, "staging").resolve(
            metadata, directory / "corpus_metadata.yaml"
        )
        == metadata
    )


@pytest.mark.parametrize(
    "reference",
    [
        "assets/../logo.png",
        "assets/../../elsewhere.png",
        "assets/missing.png",
        "logo.png",
        "/assets/logo.png",
        "assets/logo.png?x=1",
        "assets/logo.png#fragment",
        "assets/dir\\logo.png",
    ],
)
def test_invalid_references_fail_before_aws(tmp_path, reference):
    directory, _ = corpus(tmp_path, reference=reference)
    with pytest.raises(ValueError):
        prepare_corpus_assets(directory, "staging")


@pytest.mark.parametrize("kind", ["file", "directory", "root", "corpus", "corpus_root"])
def test_symlinks_rejected(tmp_path, kind):
    directory, _ = corpus(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "logo.png").write_bytes(b"private")
    if kind == "file":
        (directory / "assets/logo.png").unlink()
        (directory / "assets/logo.png").symlink_to(outside / "logo.png")
    elif kind == "directory":
        (directory / "assets/linked").symlink_to(outside, target_is_directory=True)
    elif kind == "root":
        (directory / "assets/logo.png").unlink()
        (directory / "assets").rmdir()
        (directory / "assets").symlink_to(outside, target_is_directory=True)
    elif kind == "corpus":
        (directory.parent / "LINK").symlink_to(directory, target_is_directory=True)
    else:
        linked = tmp_path / "corpus_keys"
        linked.symlink_to(directory.parent, target_is_directory=True)
        directory = linked / "BOT"
    with pytest.raises(ValueError, match="Symlink"):
        prepare_corpus_assets(directory.parent, "staging")


def test_unsupported_files_are_not_parsed_as_configuration(tmp_path):
    directory, _ = corpus(tmp_path)
    (directory / "assets/unexpected.yaml").write_text("secret: value")
    assert config_files(directory.parent) == [directory / "corpus_metadata.yaml"]
    with pytest.raises(ValueError, match="Unsupported"):
        prepare_corpus_assets(directory, "staging")


def test_environment_and_corpus_namespaces_and_retention(tmp_path):
    a, _ = corpus(tmp_path)
    b, _ = corpus(tmp_path, name="OTHER")
    prod, _ = corpus(tmp_path, environment="production")
    staging_plan = prepare_corpus_assets(a.parent, "staging")
    prod_plan = prepare_corpus_assets(prod.parent, "production")
    assert len({a.key for a in staging_plan.assets + prod_plan.assets}) == 3
    client = Mock(spec=["put_object"])
    staging_plan.publish(client)
    (b / "assets/logo.png").rename(b / "assets/renamed.png")
    # A directory containing no metadata may still publish unreferenced images.
    (b / "corpus_metadata.yaml").unlink()
    prepare_corpus_assets(a.parent, "staging").publish(client)
    assert client.put_object.call_count == 4
    assert all(
        "staging/corpus_keys/" in c.kwargs["Key"]
        for c in client.put_object.call_args_list
    )


def test_development_without_assets_works_but_relative_references_fail(tmp_path):
    directory, metadata = corpus(tmp_path, environment="development")
    with pytest.raises(ValueError, match="only in staging and production"):
        prepare_corpus_assets(directory, "development")
    (directory / "assets/logo.png").unlink()
    with pytest.raises(ValueError, match="relative asset references"):
        prepare_corpus_assets(directory, "development")
    metadata["bot_logo_url"] = metadata["chat_title_image_url"] = (
        "https://example.org/logo.png"
    )
    metadata["ui_settings"] = {}
    (directory / "corpus_metadata.yaml").write_text(yaml.safe_dump(metadata))
    assert prepare_corpus_assets(directory, "development").assets == []


def run_deploy(tmp_path, monkeypatch, client_factory, *extra):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "deploy",
            "--environment",
            "staging",
            "--project-root-path",
            str(tmp_path),
            "--lambda-function-name",
            "config-deployer",
            *extra,
        ],
    )
    monkeypatch.setattr(deployer.boto3, "client", client_factory)
    deployer.main()


@pytest.mark.parametrize("temporary", [False, True])
def test_upload_precedes_lambda_and_source_namespace_survives_transform(
    tmp_path, monkeypatch, temporary
):
    directory, _ = corpus(tmp_path)
    events = []
    s3 = Mock(spec=["put_object"])
    s3.put_object.side_effect = lambda **kw: events.append(("upload", kw))
    function = Mock()
    function.invoke.side_effect = lambda **kw: (
        events.append(("invoke", kw))
        or {"StatusCode": 200, "Payload": io.BytesIO(b"{}")}
    )
    extra = ["--target-environment", "production"]
    if temporary:
        extra += ["--temporary-corpus-key", "TEMP_TEST"]
    run_deploy(
        tmp_path,
        monkeypatch,
        lambda service, **kw: s3 if service == "s3" else function,
        *extra,
    )
    assert [e[0] for e in events] == ["upload", "invoke"]
    payload = json.loads(events[-1][1]["Payload"])
    assert payload["poemai-environment"] == "production"
    metadata = next(o for o in payload["objects_to_load"] if "bot_logo_url" in o)
    assert "config/staging/corpus_keys/BOT/assets/" in metadata["bot_logo_url"]
    assert metadata["corpus_key"] == ("TEMP_TEST" if temporary else "BOT")


def test_upload_failure_prevents_lambda_invocation(tmp_path, monkeypatch):
    corpus(tmp_path)
    s3 = Mock()
    s3.put_object.side_effect = RuntimeError("upload failed")
    function = Mock()
    with pytest.raises(RuntimeError, match="upload failed"):
        run_deploy(
            tmp_path,
            monkeypatch,
            lambda service, **kw: s3 if service == "s3" else function,
        )
    function.invoke.assert_not_called()


def test_invalid_last_corpus_prevents_all_uploads(tmp_path, monkeypatch):
    corpus(tmp_path)
    corpus(tmp_path, name="ZZZ", reference="assets/missing.png")
    factory = Mock()
    with pytest.raises(ValueError):
        run_deploy(tmp_path, monkeypatch, factory)
    factory.assert_not_called()


def test_multidocument_metadata_resolves_only_matching_fields(tmp_path):
    directory, metadata = corpus(tmp_path)
    other = {"bot_logo_url": "https://example.org/unchanged.png"}
    path = directory / "corpus_metadata.yaml"
    path.write_text(yaml.safe_dump_all([metadata, other, {"assistant_id": "x"}]))
    plan = prepare_corpus_assets(directory, "staging")
    assert plan.resolve(other, path) == other
    assert plan.resolve({"assistant_id": "x"}, path) == {"assistant_id": "x"}


def test_validator_reports_assets_errors_without_loading_asset_yaml(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "asset_validator", ROOT / "validate-poemai-config/config_validator.py"
    )
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    directory, _ = corpus(tmp_path)
    (directory / "assets/accidental.yaml").write_text("not: configuration")
    errors, _ = validator.validate_files(tmp_path, "staging")
    assert any(
        "Unsupported asset file" in e["error"] for e in errors[str(directory.parent)]
    )
    assert str(directory / "assets/accidental.yaml") not in errors
