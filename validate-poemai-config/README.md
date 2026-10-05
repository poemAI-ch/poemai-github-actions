# Validate poemAI configuration

The validator checks that the installed `poemai-utils` version is at least the
version pinned in `action.yaml` before reading configuration files. An older
installation can otherwise reject model names supported by the deployed runtime.
Outdated installations fail with a command to upgrade the package using the same
Python interpreter as the validator. Newer versions remain accepted.

When changing the action's `poemai-utils` pin, update
`REQUIRED_POEMAI_UTILS_VERSION` in `config_validator.py`. The tests enforce that
these versions match. Local users need the public `packaging` dependency as well
as the validator's existing dependencies.
