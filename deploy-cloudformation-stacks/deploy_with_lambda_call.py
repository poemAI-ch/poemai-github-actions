import argparse
import copy
import json
import logging
import os
import random
import sys
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from pathlib import Path
from string import Template

import boto3
import networkx as nx
import yaml

_logger = logging.getLogger(__name__)

ENVIRONMENT_PRIORITY = ["development", "staging", "production", "devops"]

POEMAI_TIMESTAMP_KEY = "__poemai_timestamp__"
for tag in ["!Ref", "!GetAtt", "!Sub", "!GetAZs"]:
    yaml.SafeLoader.add_constructor(
        tag, lambda loader, node: f"{tag[1:]}({loader.construct_scalar(node)})"
    )
# Update !ImportValue to handle mappings
yaml.SafeLoader.add_constructor(
    "!ImportValue",
    lambda loader, node: f"ImportValue({loader.construct_mapping(node) if isinstance(node, yaml.MappingNode) else loader.construct_scalar(node)})",
)
for tag in ["!Select"]:
    yaml.SafeLoader.add_constructor(
        tag, lambda loader, node: f"{tag[1:]}({loader.construct_sequence(node)})"
    )


def load_globals_from_file(file_path):
    """Load global variables from a file.
    
    Args:
        file_path (str): Path to the file containing key=value pairs
        
    Returns:
        dict: Dictionary of loaded key-value pairs
    """
    if not os.path.exists(file_path):
        return {}
    
    globals_dict = {}
    with open(file_path, "r") as file:
        for line in file:
            if line.startswith("#") or not line.strip():
                continue
            key, value = line.strip().split("=", 1)
            globals_dict[key.strip()] = value.strip()
    
    return globals_dict


def strip_environment_suffix(stack_name):
    for env in ENVIRONMENT_PRIORITY:
        if stack_name.endswith(f"-{env}"):
            return stack_name[: -len(env) - 1]
    return stack_name


def compare_stack_names(stack_name1, stack_name2):

    return strip_environment_suffix(stack_name1) == strip_environment_suffix(
        stack_name2
    )


def kebap_to_snake_case(name):
    """
    Convert kebab-case to snake_case.

    Parameters:
    name (str): The kebab-case string to convert.

    Returns:
    str: The converted snake_case string.
    """
    return name.replace("-", "_").lower()


def snake_to_kebap_case(name):
    """
    Convert snake_case to kebab-case.

    Parameters:
    name (str): The snake_case string to convert.

    Returns:
    str: The converted kebab-case string.
    """
    return name.replace("_", "-").lower()


def calc_template_file_name(stack_name):
    return f"{kebap_to_snake_case(stack_name)}.yaml"


def calc_stack_name(stack_name, config_global_environment):
    if config_global_environment is not None:
        return f"{stack_name}-{config_global_environment}"
    return stack_name


def load_config(config_file):
    if not os.path.exists(config_file):
        raise ValueError(f"Config file {config_file} not found")

    if config_file.endswith(".json"):
        with open(config_file, "r") as file:
            config = json.load(file)
    elif config_file.endswith(".yaml"):
        try:
            with open(config_file, "r") as file:
                config = yaml.safe_load(file)

        except yaml.YAMLError as exc:
            print(f"YAML parsing error: {exc}")

            # Print lines around the error location
            if hasattr(exc, "problem_mark"):
                mark = exc.problem_mark
                line_number = mark.line
                context_radius = 5  # lines around error
                with open(config_file, "r") as file:
                    lines = file.readlines()

                start = max(0, line_number - context_radius)
                end = min(len(lines), line_number + context_radius)

                print(f"\nContext around line {line_number + 1}:\n")
                for idx in range(start, end):
                    line_content = lines[idx].rstrip()
                    indicator = ">>>" if idx == line_number else "   "
                    print(f"{indicator} {idx + 1}: {line_content}")

            raise  # re-raise for visibility if you want
    else:
        config = json.loads(config_file)

    _logger.info(f"Loaded config file {config_file}")

    return config


template_file_sources = {}


def find_template_file(config_file_dir, file_name, environment):

    # get the environments above the given environment
    envs = ENVIRONMENT_PRIORITY[ENVIRONMENT_PRIORITY.index(environment) :]

    files_checked = []
    for env in envs:
        env_dir = Path(config_file_dir).parent / env
        potential_file = env_dir / file_name
        if (potential_file).exists():
            _logger.debug(f"Found {file_name} in {env}")
            template_file_sources[file_name] = env
            return env_dir / file_name
        files_checked.append(potential_file.as_posix())

    raise ValueError(
        f"File {file_name} not found in any environment of {envs}, checked {files_checked}"
    )


def log_template_file_sources(environment):
    if environment is None:
        return

    num_extra = 0
    by_env = defaultdict(list)
    for k, v in template_file_sources.items():
        by_env[v].append(k)

    for k, v in by_env.items():
        if k != environment:
            if len(v) > 0:
                _logger.info(
                    f"The following {len(v)} files were used from the {k} environment:"
                )
                for file_name in v:
                    _logger.info(f"  {file_name}")
        else:
            if len(v) > 0:
                _logger.info(
                    f"The following {len(v)} files were used from the {k} environment:"
                )
                for file_name in v:
                    _logger.info(f"  {file_name}")

    stats_text = "\n  ".join(
        [f"{k}: {len(v)} files" for k, v in by_env.items() if len(v) > 0]
    )
    _logger.info(
        f"*****   Used template files from the following environments:\n  {stats_text}"
    )


def run_cfn_lint(current_content):
    """Lint the CloudFormation template using cfn-lint."""
    from cfnlint import ConfigMixIn, core, decode, runner

    logging.getLogger("cfnlint").setLevel(logging.ERROR)
    retval = ""
    try:
        # Create a temporary file to store the YAML content
        with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml") as tmp_file:
            tmp_file.write(current_content.encode("utf-8"))
            tmp_file_name = tmp_file.name

        # Initialize ConfigMixIn with the temporary file path and region
        config = ConfigMixIn(
            cli_args=[tmp_file_name],
            regions=["eu-west-1"],
            ignore_checks=["W3005", "W2001"],
        )

        # Pass the config to the Runner
        run = runner.Runner(config)

        # Lint the template
        matches = list(run.run())

        # Process linting results
        if matches:
            for match in matches:
                retval += str(match) + "\n"
            _logger.info(f"cfn-lint output: {retval}")
        else:
            retval = None

    except Exception as e:
        _logger.error(f"Failed to run cfn-lint: {str(e)}", exc_info=True)
        retval = f"Error during cfn-lint check: {str(e)}"

    finally:
        # Clean up the temporary file
        if os.path.exists(tmp_file_name):
            os.remove(tmp_file_name)
    if retval is None:
        return None
    retval = (
        "\n-------- START cfn-lint check result --------\n"
        + retval
        + "\n-------- END cfn-lint check result --------"
    )

    return retval


def any_to_bool(value):
    """
    Converts a value to a boolean. Handles common string representations
    of boolean values as well as numeric values.

    Parameters:
    value (str/int/float/bool/None): The value to convert.

    Returns:
    bool: The boolean representation of the value.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        value = value.strip().lower()
        if value in {"true", "1", "yes", "y"}:
            return True
        if value in {"false", "0", "no", "n"}:
            return False
    return False  # Default to False for any other cases (None, empty string, etc.)


def create_message(
    stack,
    globals,
    config_file_dir,
    environment,
    repo_versions,
    referenced_globals,
):

    template_file_name = stack.get("template_file")
    if not template_file_name:
        template_file_name = calc_template_file_name(stack["stack_name"])
        stack["template_file"] = Path(template_file_name).absolute().as_posix()

    template_file = find_template_file(config_file_dir, template_file_name, environment)

    raw_stack_name = stack.get("stack_name")

    stack.pop("stack_name", None)

    with open(template_file, "r") as file:
        template_body = file.read()

    try:
        template_content = yaml.safe_load(template_body)
    except Exception as e:
        _logger.error(f"Error parsing template {template_file}: {e}", exc_info=True)
        sys.exit(1)

    # Check if template content is valid
    if template_content is None:
        raise ValueError(
            f"Template file {template_file} is empty or contains only comments. "
            f"CloudFormation templates must contain at least a basic structure with Resources section."
        )
    
    if not isinstance(template_content, dict):
        raise ValueError(
            f"Template file {template_file} does not contain a valid CloudFormation template structure. "
            f"Expected a YAML dictionary but got {type(template_content)}."
        )

    parameter_names_in_template = set(template_content.get("Parameters", {}).keys())

    _logger.debug(
        f"Parameters required from template {template_file}: {parameter_names_in_template}"
    )

    if not raw_stack_name:
        _logger.debug(f"Skipping stack without a name: {stack}")
        return

    stack_name = f"{raw_stack_name}-{environment}" if environment else raw_stack_name

    if "disabled" in stack and stack["disabled"]:
        _logger.debug(f"Skipping {stack_name} as it is disabled")
        return

    parameters = stack.get("parameters", {})
    _logger.debug(f"Parameters defined in stack {stack_name}: {parameters}")
    parameters_to_use = {}
    for key, value in parameters.items():
        if isinstance(value, dict):
            if "$ref" in value:
                ref = value["$ref"]
                if ref in globals:
                    referred_value = globals[ref]
                    parameters_to_use[key] = str(referred_value)
                    _logger.debug(
                        f"Resolved $ref {ref} to {referred_value} to fill in {key}"
                    )
                    referenced_globals.add(ref)
                else:
                    raise ValueError(
                        f"Global reference {ref} not found in globals for stack {stack_name}"
                    )
            elif "$sub" in value:
                pattern = value["$sub"]
                template = Template(pattern)
                identifiers = template.get_identifiers()
                if not identifiers:
                    raise ValueError(
                        f"Template {pattern} has no identifiers for stack {stack_name}"
                    )
                # Check if all identifiers are in globals
                for identifier in identifiers:
                    if identifier not in globals:
                        raise ValueError(
                            f"Identifier {identifier} not found in globals for stack {stack_name}"
                        )
                referenced_globals.update(identifiers)
                parameters_to_use[key] = template.safe_substitute(globals)
            elif "$version" in value:
                repo = value["$version"]
                if repo in repo_versions:
                    full_sha = repo_versions[repo]
                    parameters_to_use[key] = full_sha[:7]  # Use short version
                else:
                    raise ValueError(f"Version for repo {repo} not found")
            else:
                raise ValueError(
                    "only normal text and $ref to globals are supported in parameters"
                )

        else:
            parameters_to_use[key] = str(value)

    # Check if all parameters are defined in the template

    for missing_parameter in parameter_names_in_template - set(
        parameters_to_use.keys()
    ):
        if missing_parameter in globals:
            _logger.debug(
                f"Missing parameter {missing_parameter:<20} found in globals, using global value"
            )
            parameters_to_use[missing_parameter] = globals[missing_parameter]
            referenced_globals.add(missing_parameter)

    defined_parameters = set(parameters_to_use.keys())
    missing_parameters = parameter_names_in_template - defined_parameters
    if missing_parameters:
        for missing_parameter in missing_parameters:
            _logger.debug(
                f"Missing parameter {missing_parameter:<20} for {stack_name} loaded from {template_file}"
            )
        raise ValueError(
            f"Missing parameters for {stack_name} loaded from {template_file}: {missing_parameters}"
        )

    unknown_parameters = defined_parameters - parameter_names_in_template
    if unknown_parameters:
        for unknown_parameter in unknown_parameters:
            _logger.debug(
                f"Unknown parameter  {unknown_parameter:<20} for {stack_name} loaded from {template_file}"
            )

        error_message = f"Superfluous parameters for {stack_name} loaded from {template_file}: {unknown_parameters}"
        raise ValueError(error_message)

    for key, value in parameters_to_use.items():
        if not isinstance(value, str):
            raise ValueError(
                f"Parameter {key} for {stack_name} loaded from {template_file} is not a string, but {type(value)} : {value}"
            )

    template_content_hash = sha256(template_body.encode()).hexdigest()

    # Construct the message
    message = {
        "stack_name": stack_name,
        "template": template_body,
        "parameters": parameters_to_use,
        "template_content_hash": template_content_hash,
    }

    return message


def resolve_version_with_hash_support(repo, repo_versions, key_name):
    """
    Enhanced version resolution that supports hash-based individual lambda versions.
    
    Args:
        repo: The repository name (e.g., "poemAI-ch/poemai-lambdas" or "poemAI-ch/poemai-lambdas#lambda_name")
        repo_versions: Dictionary containing version mappings
        key_name: The key being resolved (e.g., "BotAdminLambdaVersion")
        
    Returns:
        str: Either the short SHA (first 7 chars) for repo-wide versions,
             or the full hash for individual lambda versions
    """
    # Check for hash-based individual lambda version first
    # Format: "poemAI-ch/poemai-lambdas#lambda_name" -> look for full key in repo_versions
    if "#" in repo:
        # New format: Look for the full key with repo#lambda_name
        if repo in repo_versions:
            return repo_versions[repo]
        
        # Backward compatibility: Try the old format where lambda names were stored without repo prefix
        base_repo, lambda_name = repo.rsplit("#", 1)
        if lambda_name in repo_versions:
            return repo_versions[lambda_name]
        
        return None
    
    # Traditional repo-wide version
    if repo in repo_versions:
        full_sha = repo_versions[repo]
        return full_sha[:7]
    
    return None


def prepare_messages(config, config_file):
    retval = []

    config_file_dir = os.path.dirname(config_file)
    globals = config.get("globals", {})

    globals[POEMAI_TIMESTAMP_KEY] = str(int(time.time()))

    repo_versions_file = config.get("repo_versions_file")
    repo_versions = {}
    if repo_versions_file:
        version_path = os.path.join(os.path.dirname(config_file), repo_versions_file)
        if not os.path.exists(version_path):
            raise FileNotFoundError(
                f"repo_versions_file {repo_versions_file} not found."
            )
        with open(version_path, "r") as f:
            repo_versions = yaml.safe_load(f).get("versions", {})

    referenced_globals = set([POEMAI_TIMESTAMP_KEY])  # Track referenced globals

    config_global_environment = None
    if "environment" in config:
        config_global_environment = config["environment"]
        globals["Environment"] = config_global_environment
        referenced_globals.add("Environment")

    for key, value in globals.items():
        if isinstance(value, dict):
            if "$version" in value:
                repo = value["$version"]
                resolved_version = resolve_version_with_hash_support(repo, repo_versions, key)
                if resolved_version is not None:
                    globals[key] = resolved_version
                    _logger.debug(
                        f"Calculated global {key} from {repo} yielding {globals[key]}"
                    )
                else:
                    explanation_text = f"Repo versions: {list(repo_versions.keys())}"
                    if repo_versions_file is None:
                        explanation_text += f" - no repo versions file given in the config file {config_file}"
                    raise ValueError(
                        f"Version for repo {repo} not found; {explanation_text}"
                    )

    for key, value in globals.items():
        if isinstance(value, dict):
            if "$sub" in value:
                pattern = value["$sub"]
                template = Template(pattern)
                identifiers = template.get_identifiers()

                if not all(identifier in globals for identifier in identifiers):
                    raise ValueError(
                        f"Missing global reference {identifiers} in globals for stack {key}"
                    )

                globals[key] = template.safe_substitute(globals)
                _logger.debug(
                    f"Calculated global {key} from the pattern {pattern} yielding {globals[key]}"
                )
    for key, value in globals.items():
        if isinstance(value, dict):
            if "$ref" in value:
                global_key = value["$ref"]
                if global_key in globals:
                    globals[key] = globals[global_key]
                    _logger.debug(
                        f"Calculated global {key} from the reference {global_key} yielding {globals[key]}"
                    )
                else:
                    raise ValueError(
                        f"Missing global reference {global_key} in globals for stack {key}"
                    )

    if config_global_environment is None:
        raise ValueError("Environment not found in config file")
    if config_global_environment is None:
        raise Exception("Kaputt")
    dependency_graph = nx.DiGraph()

    stack_names = set(
        [
            calc_stack_name(s["stack_name"], config_global_environment)
            for s in config["stacks"]
        ]
    )

    # Create a set of disabled stack names for validation
    disabled_stack_names = set(
        [
            calc_stack_name(s["stack_name"], config_global_environment)
            for s in config["stacks"]
            if s.get("disabled", False)
        ]
    )

    for stack in config["stacks"]:
        stack_name = calc_stack_name(stack["stack_name"], config_global_environment)
        dependency_graph.add_node(stack_name)

        template_file_name = stack.get("template_file")
        if not template_file_name:
            template_file_name = calc_template_file_name(stack["stack_name"])

        message = create_message(
            stack,
            globals,
            config_file_dir,
            config_global_environment,
            repo_versions,
            referenced_globals,
        )
        if message:
            retval.append(
                {
                    "message": message,
                    "stack": stack,
                    "template_file": template_file_name,
                }
            )

        if "dependencies" in stack:
            for dependency in stack["dependencies"]:
                dependency_full_name = calc_stack_name(
                    dependency, config_global_environment
                )

                if dependency_full_name not in stack_names:
                    raise ValueError(
                        f"Dependency {dependency_full_name} not found in stacks"
                    )
                
                # Check if the dependency is disabled
                if dependency_full_name in disabled_stack_names:
                    raise ValueError(
                        f"Stack {stack_name} depends on disabled stack {dependency_full_name}. "
                        f"Cannot deploy a stack that depends on a disabled stack. "
                        f"Either enable the dependency or remove the dependency."
                    )
                
                dependency_graph.add_edge(stack_name, dependency_full_name)

    # Check for unused globals
    unused_globals = set(globals.keys()) - referenced_globals
    if unused_globals:
        for unused_global in unused_globals:
            _logger.warning(f"Warning: Unused global {unused_global}")

    # Generate topological generations
    generations = list(nx.topological_generations(dependency_graph))
    _logger.debug("Topological generations computed for parallel deployment.")

    # Sort messages according to topological generations
    sorted_messages_by_generation = []
    message_counter = 0
    for generation_nr, generation in enumerate(reversed(generations)):
        current_gen_messages = []
        for stack_in_generation, stack_name in enumerate(generation):
            for message_spec in retval:
                if message_spec["message"]["stack_name"] == stack_name:
                    message_spec["generation"] = generation_nr
                    message_spec["stack_in_generation"] = stack_in_generation
                    message_spec["message_nr"] = message_counter
                    message_counter += 1
                    current_gen_messages.append(message_spec)

        sorted_messages_by_generation.append(current_gen_messages)

    for messages in sorted_messages_by_generation:
        for message_spec in messages:
            message_spec["total_messages"] = message_counter

    _logger.debug("Messages sorted into topological generations:")
    for i, messages in enumerate(sorted_messages_by_generation):
        _logger.debug(
            f"Generation {i}: {', '.join([m['message']['stack_name'] for m in messages])}"
        )

    log_template_file_sources(config_global_environment)

    return sorted_messages_by_generation, dependency_graph


def invoke_lambda_with_backoff(
    lambda_client, function_name, payload, max_attempts=8, initial_delay=1, info=None
):
    info_text = f" ({info}) " if info else ""

    for attempt in range(max_attempts):
        try:
            response = lambda_client.invoke(
                FunctionName=function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload),
            )
            # Read the payload from the response
            response_payload = (
                response["Payload"].read().decode("utf-8")
            )  # Decoding from bytes to string
            try:
                _logger.info(f"Response payload: {response_payload}")
                response_payload = json.loads(
                    response_payload
                )  # Convert string to JSON if possible
            except json.JSONDecodeError:
                pass  # Keep as string if it's not JSON

            response["Payload"] = (
                response_payload  # Replace the StreamingBody with the actual content
            )
            return response
        except lambda_client.exceptions.TooManyRequestsException:
            if attempt < max_attempts - 1:
                sleep_time = initial_delay * (2**attempt) + random.uniform(0, 1)
                time.sleep(sleep_time)
                _logger.info(
                    f"Rate exceeded. {info_text} retrying after {sleep_time:.2f} seconds..."
                )
            else:
                _logger.error(
                    "Max retry attempts reached. {info_text}unable to invoke lambda function."
                )
                raise  # Re-raise the exception after the last attempt
        except Exception as e:
            _logger.error(f"An error occurred. {info_text} {str(e)}", exc_info=True)
            raise


def wait_for_stack_stable_state(stack_name):
    _logger.info(f"Waiting for stack {stack_name} to reach stable state")

    cf_client = boto3.client("cloudformation", region_name="eu-central-2")

    num_retries = 30
    stack_status = None
    for _ in range(num_retries):
        try:
            stack_data = cf_client.describe_stacks(StackName=stack_name)
            stack_status = stack_data["Stacks"][0]["StackStatus"]
            if (
                stack_status == "UPDATE_COMPLETE"
                or stack_data["Stacks"][0]["StackStatus"] == "CREATE_COMPLETE"
            ):
                return stack_status
            elif stack_status in [
                "ROLLBACK_COMPLETE",
                "CREATE_FAILED",
                "ROLLBACK_FAILED",
                "UPDATE_ROLLBACK_FAILED",
                "UPDATE_ROLLBACK_COMPLETE",
            ]:
                raise ValueError(f"Stack {stack_name} in error state")

            _logger.info(
                f"Stack status of {stack_name} is still in {stack_data['Stacks'][0]['StackStatus']}, waiting...."
            )
            time.sleep(10)
        except Exception as e:
            _logger.error(
                f"An error occurred for stack {stack_name} {str(e)}", exc_info=True
            )
            raise

    _logger.error(f"Stack never reached stable state, is in state {stack_status}")
    raise ValueError(f"Stack never reached stable state, is in state {stack_status}")


def deploy_stack(lambda_client, lambda_function_name, message_spec):

    stack_name = message_spec["message"]["stack_name"]

    try:
        lambda_event = {"Records": [{"body": json.dumps(message_spec["message"])}]}
        _logger.info(
            f"({message_spec['message_nr']+1:>4}/{message_spec['total_messages']} stack {stack_name} : Invoking lambda {lambda_function_name}"
        )
        retval = invoke_lambda_with_backoff(
            lambda_client, lambda_function_name, lambda_event, info=stack_name
        )

        state = wait_for_stack_stable_state(stack_name)

        _logger.info(f"Stack {stack_name} reached stable state {state}")

        return retval

    except Exception as e:
        _logger.error(f"Failed to invoke lambda. {stack_name} {str(e)}", exc_info=True)
        raise e


def deploy(lambda_function_name, config, config_file, stack_name=None):
    lambda_client = boto3.client("lambda", region_name="eu-central-2")
    message_generations, dependency_graph = prepare_messages(config, config_file)

    total_messages = sum([len(mg) for mg in message_generations])

    failed_stacks = []

    all_messages = [
        message for generation in message_generations for message in generation
    ]
    all_stack_names = [message["message"]["stack_name"] for message in all_messages]

    if stack_name is not None:
        found_stack_name = next(
            (sn for sn in all_stack_names if compare_stack_names(sn, stack_name)), None
        )

        if found_stack_name is None:
            raise ValueError(
                f"Stack {stack_name} not found in config file. Available stacks: {all_stack_names}"
            )
        else:
            stack_name = found_stack_name

    successful_stacks = set()

    for i, generation in enumerate(message_generations):
        _logger.info(
            f"*** Deploying generation {i}, stacks: {[m['message']['stack_name'] for m in generation]}"
        )

        eligible_stacks = []
        for stack_candidate in generation:
            descendants = nx.descendants(
                dependency_graph, stack_candidate["message"]["stack_name"]
            )

            if (
                not all([d in successful_stacks for d in descendants])
                and not stack_name
            ):
                missing_dependencies = [d for d in descendants if d not in successful_stacks]
                error_msg = (
                    f"Cannot deploy {stack_candidate['message']['stack_name']} because the following "
                    f"dependencies have not been successfully deployed: {missing_dependencies}. "
                    f"This indicates a deployment failure in earlier generations."
                )
                _logger.error(error_msg)
                raise ValueError(error_msg)
            eligible_stacks.append(stack_candidate)

        stack_names_in_process = set(
            [m["message"]["stack_name"] for m in eligible_stacks]
        )
        with ThreadPoolExecutor() as executor:
            # Dictionary to hold future submissions
            future_to_stack = {
                executor.submit(
                    deploy_stack, lambda_client, lambda_function_name, message_spec
                ): message_spec
                for message_spec in eligible_stacks
                if not stack_name or message_spec["message"]["stack_name"] == stack_name
            }

            # Process as each future completes
            for future in as_completed(future_to_stack):
                message_spec = future_to_stack[future]
                try:
                    response = future.result()  # Get the result from the future
                    response_payload = response.get("Payload")
                    log_text = (
                        repr(response_payload) if response_payload else "No payload"
                    )

                    _logger.info(
                        f"Lambda invoked for {message_spec['message']['stack_name']} using template {message_spec['stack']['template_file']}: {log_text}"
                    )
                    status_texts = [pl.get("status") for pl in response_payload]

                    if any([status_text == "error" for status_text in status_texts]):
                        _logger.error(
                            f"Failed to deploy {message_spec['message']['stack_name']} using template {message_spec['stack']['template_file']}"
                        )
                        failed_stacks.append(message_spec["message"]["stack_name"])
                    else:
                        successful_stacks.add(message_spec["message"]["stack_name"])

                    _logger.info(
                        f"Still in process: {stack_names_in_process - successful_stacks  - set(failed_stacks)}"
                    )

                except Exception as exc:
                    _logger.error(
                        f"Failed to invoke Lambda for {message_spec['message']['stack_name']} with error: {str(exc)}",
                        exc_info=True,
                    )
                    failed_stacks.append(message_spec["message"]["stack_name"])

        _logger.info(f"*** Generation {i} completed")

    if failed_stacks:
        _logger.error(f"Failed stacks: {failed_stacks}")
        raise ValueError(f"Failed stacks: {failed_stacks}")


def do_lint(config, config_file, main_command, stack_name, config_global_environment):

    for stack in config["stacks"]:
        if (
            (main_command == "dump" or main_command == "dump_graph")
            or not stack_name
            or compare_stack_names(stack["stack_name"], stack_name)
        ):
            template_file_name = stack.get("template_file")
            if not template_file_name:
                template_file_name = calc_template_file_name(stack["stack_name"])
            template_file = find_template_file(
                os.path.dirname(config_file),
                template_file_name,
                config_global_environment,
            )
            with open(template_file, "r") as file:
                template_body = file.read()

            lint_output = run_cfn_lint(template_body)
            if lint_output:
                _logger.info(
                    f"Found issues in file {template_file_name}:\n{lint_output}"
                )
                had_issues = True


def do_dump_graph(config, config_file):
    message_generations, dependency_graph = prepare_messages(config, config_file)

    for i, messages in enumerate(message_generations):
        _logger.info(f"*** Generation {i}:")
        for message_spec in messages:
            message = message_spec["message"]
            stack_name = message_spec["message"]["stack_name"]
            descendants = nx.descendants(dependency_graph, stack_name)
            _logger.info(f"Stack {stack_name}")
            for d in descendants:
                _logger.info(f"  - {d}")


def validate_stack_name_filter(config, config_global_environment, stack_name_filter):
    """
    Validate that the provided stack name filter matches at least one stack.
    Returns True if valid, raises SystemExit with helpful error message if not.
    """
    if stack_name_filter is None:
        return True
    
    # Get all stack names (both full and stripped)
    all_stacks = config.get("stacks", [])
    full_stack_names = []
    stripped_stack_names = []
    
    for stack in all_stacks:
        if stack.get("disabled", False):
            continue
            
        full_name = calc_stack_name(stack["stack_name"], config_global_environment)
        stripped_name = strip_environment_suffix(full_name)
        
        full_stack_names.append(full_name)
        stripped_stack_names.append(stripped_name)
    
    # Check if the filter matches any stack (full or stripped name)
    matches_any = False
    for full_name in full_stack_names:
        if compare_stack_names(full_name, stack_name_filter):
            matches_any = True
            break
    
    if not matches_any:
        _logger.error(f"❌ Stack name '{stack_name_filter}' does not match any available stacks.")
        _logger.error(f"Available stack names (without environment suffix):")
        for stripped_name in sorted(set(stripped_stack_names)):
            _logger.error(f"  - {stripped_name}")
        _logger.error(f"Available full stack names:")
        for full_name in sorted(set(full_stack_names)):
            _logger.error(f"  - {full_name}")
        _logger.error(f"Note: You can use either the full name (with environment suffix) or just the base name.")
        raise SystemExit(1)
    
    return True


def do_dump(config, config_file, config_global_environment, verbose=False, stack_name=None):

    # Validate stack name filter if provided (do this before any processing that modifies config)
    validate_stack_name_filter(config, config_global_environment, stack_name)

    message_generations, dependency_graph = prepare_messages(config, config_file)

    total_stacks = 0
    successful_stacks = 0
    
    for i, messages in enumerate(message_generations):
        if verbose:
            _logger.info(f"*** Generation {i}:")
        for message_spec in messages:
            message = message_spec["message"]
            stack = message_spec["stack"]
            current_stack_name = message["stack_name"]  # Already calculated in prepare_messages

            # Filter by specific stack name if provided
            if stack_name is not None and not compare_stack_names(
                current_stack_name, stack_name
            ):
                continue

            _logger.debug(f"Processing {current_stack_name} (matches {stack_name})")
            total_stacks += 1
            template_file_name = stack.get("template_file")
            if not template_file_name:
                template_file_name = calc_template_file_name(stack["stack_name"])
            
            if verbose:
                _logger.info(
                    f"Message for {current_stack_name} using template {template_file_name}:"
                )
                _logger.info("Parameters:")
                for key, value in message["parameters"].items():
                    _logger.info(f"  {key}: {value}")
                _logger.info("Template:\n")
                _logger.info(message["template"])
                _logger.info(f"END {current_stack_name}")
            else:
                # Just show a summary line
                param_count = len(message["parameters"])
                _logger.info(f"✓ {current_stack_name} using {template_file_name} ({param_count} parameters)")
            
            successful_stacks += 1

    if not verbose:
        _logger.info(f"\n📋 Summary: Successfully processed {successful_stacks}/{total_stacks} templates")
        if successful_stacks == total_stacks:
            _logger.info("✅ All templates validated successfully!")
        else:
            _logger.error(f"❌ {total_stacks - successful_stacks} templates failed validation")


def setup_logging(verbose=False):
    """Setup logging with INFO to stdout, WARNING/ERROR to stderr"""
    # Remove any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # Set overall level based on verbose flag
    level = logging.DEBUG if verbose else logging.INFO
    root_logger.setLevel(level)
    
    # Create formatter
    formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s')
    
    # INFO handler -> stdout (only shows INFO, not DEBUG)
    info_handler = logging.StreamHandler(sys.stdout)
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(formatter)
    info_handler.addFilter(lambda record: logging.INFO <= record.levelno < logging.WARNING)
    
    # WARNING/ERROR handler -> stderr  
    error_handler = logging.StreamHandler(sys.stderr)
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(formatter)
    
    root_logger.addHandler(info_handler)
    root_logger.addHandler(error_handler)
    
    # If verbose, also add DEBUG handler to stdout
    if verbose:
        debug_handler = logging.StreamHandler(sys.stdout)
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(formatter)
        debug_handler.addFilter(lambda record: record.levelno == logging.DEBUG)
        root_logger.addHandler(debug_handler)

def main():
    # Initial basic setup for argument parsing
    logging.basicConfig(level=logging.WARNING)

    parser = argparse.ArgumentParser(description="PoemAI Cluster")

    parser.add_argument(
        "--lint",
        action="store_true",
        help="Run cfn-lint on the template",
    )

    # add command argument
    command_choices = ["deploy", "dump", "dump_graph"]
    subparsers = parser.add_subparsers(
        dest="command", help="Sub-commands", required=True
    )

    for command in command_choices:
        subparser = subparsers.add_parser(command)

        if command == "deploy":
            subparser.add_argument(
                "lambda_function_name",
                type=str,
                help="The name of the lambda function to call",
            )
        if command == "dump" or command == "deploy":
            subparser.add_argument(
                "config_file",
                type=str,
                help="The path to the configuration file",
            )
            subparser.add_argument(
                "--stack-name",
                type=str,
                help="The name of the stack to deploy",
            )

        if command == "dump_graph":
            subparser.add_argument(
                "config_file",
                type=str,
                help="The path to the configuration file",
            )

        subparser.add_argument(
            "--override-globals-file",
            type=str,
            action="store",
            help="Use a file used to override globals",
        )
        
        if command == "dump":
            subparser.add_argument(
                "--verbose", "-v",
                action="store_true",
                help="Show full template content (default: summary only)",
            )

    # parse arguments
    args, unknown = parser.parse_known_args()
    
    # Setup proper logging based on verbose flag
    verbose = getattr(args, 'verbose', False)
    setup_logging(verbose)

    config = None
    if args.config_file:
        _logger.info(f"Using config file {args.config_file}")
        config = load_config(args.config_file)

    config_global_environment = None
    if config is not None and "environment" in config:
        config_global_environment = config["environment"]

    # Inject extra globals from -e/--extra-global
    if config is not None:

        if "globals" not in config or config["globals"] is None:
            config["globals"] = {}

        if args.override_globals_file:
            override_globals_file = args.override_globals_file
            if not os.path.exists(override_globals_file):
                raise ValueError(
                    f"Override globals file {override_globals_file} not found"
                )
            override_globals = load_globals_from_file(override_globals_file)
            for key, value in override_globals.items():
                config["globals"][key] = value
                _logger.info(f"Using override global {key}: {value}")

    if args.lint:
        do_lint(
            config,
            args.config_file,
            args.command,
            args.stack_name,
            config_global_environment,
        )

    if args.command == "deploy":
        deploy(
            args.lambda_function_name,
            config,
            args.config_file,
            stack_name=args.stack_name,
        )

    elif args.command == "dump":
        verbose = getattr(args, 'verbose', False)
        stack_name = getattr(args, 'stack_name', None)
        do_dump(config, args.config_file, config_global_environment, verbose, stack_name)
    elif args.command == "dump_graph":
        do_dump_graph(config, args.config_file)


if __name__ == "__main__":
    main()
