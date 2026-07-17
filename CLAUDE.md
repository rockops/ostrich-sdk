# CLAUDE.md - Ostrich SDK Development Guidelines

## Build Commands

To build all CLI binaries (`ostd` and `ostr` for Linux, macOS, and Windows):
```bash
./scripts/build.sh
```
Binaries will be outputted to the `bin/` directory.

To build just `ostr` for the current platform:
```bash
cd ostr-cli && go build -o ostr
```

To build just `ostd` for the current platform:
```bash
cd ostd-cli && go build -o ostd
```

---

## Testing Commands

### Python Core Unit Tests
To run unit tests for the python core (`ost-core`) using `pytest`:
```bash
./scripts/run_unit_tests.sh
```
Or run pytest manually with PYTHONPATH configured:
```bash
export PYTHONPATH=$(pwd)/ost-core:$PYTHONPATH
pytest ost-core/test/test_operations_runner.py
```

### Python Core Integration Tests
To run the template integration tests:
```bash
# Set up PYTHONPATH and run
export PYTHONPATH=$(pwd)/ost-core:$PYTHONPATH
python ost-core/ost template test unit-tests
```

---

## Infrastructure Commands

### Build Docker Images
To build the Docker images (`ostrich-sdk:latest` and `ostrich-sdk-ssh:latest`):
```bash
./docker/ostrich-sdk/build.sh -n
```
*Note: Use `-n` flag to skip pushing the image to the remote registry.*

### Deploy Helm Chart
To deploy the local Ostrich SSHD Helm chart to your Kubernetes cluster:
```bash
./helm/deploy.sh <version>
```

---

## Code Guidelines & Tech Stack

### Python Core (`ost-core`)
- **Engine Type:** Python 3.12+ script.
- **Templating Delimiters:** Always use `[[` and `]]` for Jinja2 template rendering (do not use default `{{ }}`).
- **Adding operations/runners:** Core runners are defined in `ost-core/src/operations.py`. Any new runners must be registered inside the `task()` and `execute()` dispatcher loops.
- **Formatting:** Keep python comments descriptive. Use standard logger (`logging.info`, `logging.debug`, etc.) instead of printing directly.

### Go CLI Clients (`ostd-cli`, `ostr-cli`)
- **Version:** Go 1.21+.
- **Standard Library Formatting:** Follow standard `go fmt`.
- **Log level:** Use `log/slog` for structured logging. Add debug flags (`-d` or `--debug`) to output debug logs.
- **Path mapping:** Windows paths must be translated to POSIX-compliant paths using `toUnixPath()` (e.g. `C:\path` to `/c/path`) when mounting into containers.
