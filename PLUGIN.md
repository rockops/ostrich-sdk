# Creating a New Ostrich Plugin (Osplate)

This guide explains how to create, document, test, and publish custom **Osplates** (Ostrich Plugins) for the **Ostrich SDK**.

---

## 1. Overview & Architecture

An **Osplate** is a reusable template package that encapsulates deployment logic, container/shell tasks, and source templates for applications (such as backend services, frontends, or microservices).

When a user executes `ost` commands in a workspace containing `ostrich.yaml`, the Ostrich SDK:
1. Identifies the target Osplate specified in `template.kind`.
2. Merges user settings from `ostrich.yaml` with the template's `default.yaml`.
3. Renders template files using **Jinja2** (with custom `[[` `]]` delimiters).
4. Executes requested task operations (`ost run <task>`).

---

## 2. Plugin Directory Structure

A complete plugin directory follows this structure:

```
my-plugin/
├── template.yaml            # [REQUIRED] Plugin metadata & default runner
├── default.yaml             # [OPTIONAL] Default values injected into template.params
├── _doc/                    # [REQUIRED] Documentation directory
│   ├── ostrich.yaml         # Sample user configuration (with descriptive comments)
│   └── description.md       # Plugin description, features, & task reference
├── _test/                   # [RECOMMENDED] Integration test suite
│   └── test_plugin.py       # Pytest test cases for the plugin
└── <operation_name>/        # Task operation directory (e.g. docker/, helm/, dev/)
    ├── <operation_name>.yaml.tmpl   # Task definition (for container or shell runners)
    └── <operation_name>.py.tmpl     # Task script (for inprocess python runners)
```

---

## 3. Step-by-Step Plugin Creation

### Step 1: Create `template.yaml`

Define metadata for your plugin in `template.yaml`:

```yaml
name: my-plugin
version: 1.0.0
description: A custom Ostrich template for microservices.
# Default runner kind for operations in this template (optional: inprocess, container, or shell)
runner:
  kind: container
```

### Step 2: Define Default Parameters in `default.yaml`

Set sensible defaults for configurable parameters:

```yaml
template:
  runtime: docker
  params:
    port: 8080
    input:
      src: src
    output:
      helm: "helm-[[ plugin.name ]]"
    registry: ""
    kubernetes:
      namespace: "[[ plugin.name ]]"
```

### Step 3: Create Documentation (`_doc/`)

The `_doc/` directory must contain two key files:

1. **`_doc/ostrich.yaml`**: A sample workspace configuration file with helpful comments:
   ```yaml
   plugin:
     name: my-app
     version: 0.1.0
     business_name: My Application Service

   template:
     kind: my-plugin
     runtime: docker
     params:
       port: 8080
   ```

2. **`_doc/description.md`**: Markdown documentation rendered when users run `ost template describe my-plugin`:
   ```markdown
   # My Plugin

   This template builds and deploys microservices.

   ## Features
   - Feature 1
   - Feature 2

   ## Tasks
   - **build**: Build container image.
   - **deploy**: Deploy to Kubernetes.
   ```

---

## 4. Creating Task Operations

Tasks are defined in subdirectories corresponding to the task name (e.g. `docker/`, `helm/`, `dev/`). 

Ostrich supports three task runner types:

### A. Python Native Runner (`inprocess`)
For complex logic, create a `.py.tmpl` script rendered into Python and executed natively inside `ost-core`.

**Example: `helm/helm.py.tmpl`**
```python
import logging
import os
import sys

def deploy(args):
    plugin_name = "[[ plugin.name ]]"
    namespace = "[[ template.params.kubernetes.namespace or 'default' ]]"
    chart_path = "[[ "helm/kubernetes" | fromTemplateInstance ]]"

    logging.info(f"Deploying {plugin_name} to {namespace}...")
    helm_cmd = ["helm", "upgrade", "--install", plugin_name, chart_path, "--namespace", namespace]
    
    if _dryRun:
        logging.info(f"Dry run: {' '.join(helm_cmd)}")
    else:
        result = run(helm_cmd)
        if result.returncode != 0:
            raise OstrichException(f"Helm deployment failed with exit code {result.returncode}")

if _argv and _argv[0] == "deploy":
    deploy(_argv[1:])
```

*Injected Globals in `inprocess` scripts*:
- `_argv`: Command-line arguments passed to `ost run <task> [args...]`.
- `_dryRun`: Boolean indicating if `--dry-run` was set.
- `run()`: Subprocess runner function.
- `OstrichException`: Standard error reporting exception.

### B. Container Runner (`container`)
For sandboxed execution inside a Docker image.

**Example: `docker/docker.yaml.tmpl`**
```yaml
runner:
  kind: container
  image: buildpacksio/pack:latest

env:
  PACK_VOLUME_KEY: [[ plugin.name ]]

commands:
- cmd:
  - build
  - [[ (template.params.registry | noslash + "/" if template.params.registry else "") + plugin.name ]]
  - --builder
  - [[ template.params.builder.name ]]
  - --path
  - [[ "" | input("src") ]]
```

### C. Host Shell Runner (`shell`)
For running host shell commands.

**Example: `display/display.yaml.tmpl`**
```yaml
runner:
  kind: shell

commands:
- echo "Executing task for [[ plugin.name ]]"
- echo ${MY_VAR}

env:
  MY_VAR: "Hello from shell task"
```

---

## 5. Jinja2 Templating Rules

> [!IMPORTANT]
> **Delimiters**: ALWAYS use `[[` and `]]` for variable interpolation, `[%` and `%]` for control blocks, and `[#` and `#]` for comments.
> DO NOT use standard `{{ }}` or `{% %}` because they conflict with Helm and Kubernetes syntax.

### Custom Jinja Filters
- `noslash`: Strips leading and trailing slashes (e.g. `template.params.registry | noslash`).
- `input("key")`: Resolves input directory path (e.g. `"" | input("src")`).
- `here`: Resolves path relative to execution output directory (e.g. `template.params.output.helm | here`).
- `fromTemplateInstance`: Resolves file location within the template instance directory.

---

## 6. Developing, Testing, and Publishing

### Installing Local Symlink for Testing
To develop a plugin locally and test it with `ost`:
```bash
ost template install --directory /path/to/my-plugin --link
```

### Useful SDK Commands
- **List installed templates**:
  ```bash
  ost template list
  ```
- **Describe template**:
  ```bash
  ost template describe my-plugin
  ```
- **Generate sample config**:
  ```bash
  ost template config my-plugin > ostrich.yaml
  ```
- **Run plugin tests**:
  ```bash
  ost template test my-plugin
  ```

### Packaging & Publishing
Package and publish your Osplate to an OCI registry:
```bash
ost template package /path/to/my-plugin
ost template publish /path/to/my-plugin registry.example.com/my-plugin:1.0.0
```
