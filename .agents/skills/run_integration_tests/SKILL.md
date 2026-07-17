---
name: run_integration_tests
description: Run integration tests or osplate tests (like unit-tests) for Ostrich SDK. Automatically builds ostd/ostr CLIs before execution.
---

# Instructions for Running Ostrich SDK Integration & Osplate Tests

Use this skill when you need to run integration tests, template tests, or unit-tests (the template test suite) for Ostrich SDK.

## Prerequisite: Compile CLI Binaries

Before running integration tests (especially when testing with `--ostd`), you must ensure the Go CLI binaries (`ostd` and `ostr`) are compiled and up to date.

```bash
./scripts/build.sh
```

## How to Run the Tests

### 1. Execute the Unit Tests (Default Integration Suite)
When the user asks to "execute the unit tests" or run integration tests, use the helper script:

```bash
./scripts/run_int_tests.sh
```

You can append test arguments, for example:
- To run tests using the containerized runner (`ostd`):
  ```bash
  ./scripts/run_int_tests.sh --ostd
  ```
- To run tests using the Python local runner (`ost`):
  ```bash
  ./scripts/run_int_tests.sh --ost
  ```
- To pass options directly to `pytest` (using `--` followed by options):
  ```bash
  ./scripts/run_int_tests.sh -- -k test_name
  ```

### 2. Execute Tests for a Specific Template / Osplate
If asked to run tests for a specific template (like `frontend`, `simple`, or `all`), invoke the core runner directly:

```bash
export PYTHONPATH=$(pwd)/ost-core:$PYTHONPATH
python ost-core/ost template test <template_name> [options]
```

*Example: Run tests for all templates using the container runner:*
```bash
export PYTHONPATH=$(pwd)/ost-core:$PYTHONPATH
python ost-core/ost template test all --ostd
```
