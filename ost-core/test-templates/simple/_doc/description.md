# Simple Plugin Template (Test Suite)

This template serves as the core integration test template for Ostrich SDK. It exercises all runner kinds (`inprocess`, `container`, and `shell`).

## Features

- **Runner Verification**: Tests `inprocess`, `container`, and `shell` operation execution modes.
- **Parameter Ingestion**: Tests parsing of `ostrich.yaml` params, environment variables, and CLI arguments.

## Tasks

- **`display`**:
  - **Runner**: `inprocess` (Python)
  - **Description**: Runs native Python script to log plugin metadata and environment variables.
- **`displaydocker`**:
  - **Runner**: `container` (`alpine:latest`)
  - **Description**: Executes Docker commands verifying volume mounts, environment variables, and `jq` parameter parsing.
- **`displayshell`**:
  - **Runner**: `shell`
  - **Description**: Executes host shell commands verifying variable expansion (`${TEST_VAR}`, `${LOGLEVEL}`, `${DRYRUN}`) and JSON argument parsing.
