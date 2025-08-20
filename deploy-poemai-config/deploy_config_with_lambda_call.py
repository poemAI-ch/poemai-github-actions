import argparse
import json
import logging
from pathlib import Path

import boto3
import yaml

_logger = logging.getLogger(__name__)


def gather_json_representations(environment):
    """
    Gather all json representations of the configuration files
    """

    path = Path(__file__).parent.parent / "environments" / environment / "corpus_keys"

    # traverse the directory tree and look for all yaml files

    all_objects = []
    for file in list(path.rglob("*.yaml")) + list(path.rglob("*.yml")):
        with open(file, "r") as f:
            had_error = False
            try:
                data = yaml.safe_load(f)
                all_objects.append(data)
            except yaml.composer.ComposerError as e:
                had_error = True

            if had_error:
                # try loading as multi-document yaml
                f.seek(0)
                for i, doc in enumerate(yaml.safe_load_all(f)):
                    all_objects.append(doc)
                    _logger.info(
                        f"Loaded document {i} from {file}:\n{json.dumps(doc, indent=2, ensure_ascii=False)}\n"
                    )

    _logger.info(f"Found {len(all_objects)} objects to load")
    return all_objects


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description="Deploy configuration with lambda call"
    )

    parser.add_argument(
        "--environment", required=True, help="Environment of the configuration"
    )
    parser.add_argument(
        "--lambda-function-name",
        required=True,
        type=str,
        help="The name of the lambda function to call",
    )
    parser.add_argument(
        "--version-id",
        required=False,
        type=str,
        help="Optional version identifier to associate with the configuration objects.",
    )
    # parse arguments
    args, unknown = parser.parse_known_args()

    # gather all json representations
    objects_to_load = gather_json_representations(args.environment)

    # Optionally add version ID to objects
    if args.version_id:
        for obj in objects_to_load:
            obj["version_id"] = args.version_id
            obj["_version_id"] = args.version_id  # add both for backwards compatibility

    for i, obj in enumerate(objects_to_load):
        if "pk" not in obj:
            _logger.error(
                f"Object {i} does not have a primary key. Object:\n{json.dumps(obj, indent=2, ensure_ascii=False)}"
            )
            exit(1)
        if "sk" not in obj:
            _logger.error(
                f"Object {i} does not have a sort key. Object:\n{json.dumps(obj, indent=2, ensure_ascii=False)}"
            )
            exit(1)

        _logger.info(
            f"Object {i}:\n{json.dumps(obj, indent=2, ensure_ascii=False)}\n--------------------------------\n"
        )

    request = {
        "objects_to_load": objects_to_load,
        "poemai-environment": args.environment,
    }

    # Create a Lambda client
    lambda_client = boto3.client("lambda")

    try:
        response = lambda_client.invoke(
            FunctionName=args.lambda_function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(request),
        )

        # Check the status code of the response
        status_code = response.get("StatusCode")
        if status_code != 200:
            _logger.error(f"Lambda invocation failed with status code: {status_code}")
            exit(1)

        # Parse the response payload
        response_payload = response["Payload"].read()
        response_data = json.loads(response_payload)

        # Check for errors in the response
        if "errorMessage" in response_data:
            _logger.error(f"Lambda function error: {response_data['errorMessage']}")
            _logger.debug(f"Error details: {json.dumps(response_data, indent=2)}")
            exit(1)
        elif "error" in response_data:
            _logger.error(f"Lambda function error: {response_data['error']}")
            _logger.debug(f"Error details: {json.dumps(response_data, indent=2)}")
            exit(1)
        else:
            _logger.info("Lambda invocation succeeded.")
            _logger.info(
                f"Lambda response:\n{json.dumps(response_data, indent=2, ensure_ascii=False)}"
            )

    except Exception as e:
        _logger.exception(f"Failed to invoke lambda function: {e}", exc_info=e)
        exit(1)
