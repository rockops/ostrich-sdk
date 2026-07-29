# Ostrich SDK

Deploy like an Ostrich! 🦩

**Ostrich SDK** is a powerful, template-driven application deployment engine and orchestration platform. It provides a unified interface for DevOps workflows, including template management, local containerized execution, remote SSH/Kubernetes orchestration, registry management, and plugin execution.

By leveraging parameterized template packages called **osplates**, developers can easily package, configure, and deploy application architectures across diverse environments without managing low-level orchestration configurations directly.

---

## 🚀 Key Features

- **Template-driven (Osplates):** Build once, deploy anywhere using customizable parameters and templates.
- **Jinja2 Templating Engine:** Parameterize configurations safely using custom Jinja2 delimiters (`[[` and `]]`) to avoid conflicts with Helm or Kubernetes syntax.
- **Docker/Podman Sandbox:** Execute deployment tasks locally within isolated containers without cluttering host machines with toolchains (Helm, Kubernetes CLI, `jq`, `yq`, etc.).
- **Remote K8s/SSH Orchestration:** Deploy and manage workloads on remote Kubernetes endpoints over secure SSH tunnel connections using `ostr`.
- **Registry & OCI Management:** Built-in commands to authenticate, list, pull, and push OCI registry images and packages.
- **Plugin Architecture:** Define modular application lifecycles with declarative task definitions in `ostrich.yaml`.

---

## 🏗️ System Architecture Overview

The Ostrich SDK is composed of three primary components:

1. **`ost-core` (The Engine):** A Python 3 execution engine (`ost`) that processes templates, resolves configuration parameters, and executes deployment tasks using flexible runners (`inprocess`, `shell`, `container`).
2. **`ostd` (Local Container CLI):** A compiled Go utility that launches the `ost` engine inside a local Docker/Podman container, mounting workspace files and host credential configs (e.g., `.kube/config`, `.docker/config.json`) seamlessly.
3. **`ostr` (Remote K8s CLI):** A compiled Go utility that connects to an SSH-enabled agent pod running inside a remote Kubernetes cluster to sync files and execute `ost` deployment tasks remotely.

---

## 🚀 Quickstart

### 1. Build and Install CLIs
To build the CLI binaries (`ostd` and `ostr`), run the build script:
```bash
./scripts/build.sh
```
The compiled binaries for Linux, macOS, and Windows will be placed in the `bin/` directory. Copy the appropriate binaries to your system `PATH` (e.g. `/usr/local/bin/`).

### 2. Running Tasks Locally with `ostd`
Using `ostd` allows you to execute deployment tasks locally without setting up the core Python environment on your host machine.

```bash
# Check version
ostd --version

# List available templates
ostd template list

# Inspect template details
ostd template describe <template-name>

# Generate a sample configuration file
ostd template config <template-name>

# Dry run deployment task
ostd -dr run deploy

# Execute deployment task
ostd run deploy
```

### 3. Running Tasks Remotely with `ostr`
`ostr` lets you orchestrate deployments on a remote Kubernetes cluster containing an Ostrich SDK agent.

```bash
# Initialize connection to remote endpoint
ostr init <endpoint_name> <ip_address>

# Manage and select active endpoints
ostr endpoint list
ostr endpoint select <endpoint-name>

# Synchronize local files and execute task remotely
ostr run deploy

# Open interactive remote shell
ostr ssh
```

---

## 🛠️ Plugin & Osplate Development

### Plugin Structure (`ostrich.yaml`)
Applications managed by Ostrich SDK define their lifecycle using an `ostrich.yaml` descriptor in the root directory:

- **Metadata:** Name, version, description, and dependencies.
- **Template / Osplate Kind:** Specifies the osplate blueprint to extend.
- **Tasks:** Pre-defined operations (e.g., `deploy`, `package`, `test`) consisting of execution steps.
- **Configuration:** Custom template variables and default parameter overrides.

### Example `ostrich.yaml`

```yaml
name: my-plugin
version: 1.0.0
description: Custom application plugin

tasks:
  deploy:
    description: Deploy application to Kubernetes
    steps:
      - name: Build Docker image
        run: docker build -t my-image .
      - name: Push to registry
        run: docker push my-image
      - name: Deploy to Kubernetes
        run: kubectl apply -f k8s/
```

---

## 📦 Registry & Operations Reference

### Standard Commands

| Command | Description |
|---------|-------------|
| `init` | Setup connection to a remote endpoint |
| `endpoint` | Manage endpoints (list, select, set) |
| `ssh` | Open interactive shell on remote endpoint |
| `put` | Upload files to remote endpoint |
| `docker` | Run docker commands remotely |
| `kubectl` | Run kubectl commands remotely |
| `run` | Execute a task defined in a plugin/osplate |
| `cert install` | Install a trusted certificate remotely |
| `host` | Add a host entry remotely |
| `version` | Display version information |

### Template Operations

| Command | Description |
|---------|-------------|
| `template list` | List available plugin templates (osplates) |
| `template describe <name>` | Get detailed information about a template |
| `template config <name>` | Generate sample configuration file |

### Registry Operations

| Command | Description |
|---------|-------------|
| `registry login <url>` | Authenticate with an OCI registry |
| `registry ls <url>` | List images in a registry |
| `registry pull <image>` | Pull an image from registry |
| `registry push <image>` | Push an image to registry |

---

## ⚙️ Configuration & Environment

### Global Configuration

```bash
# Display current configuration
ost config get

# Set configuration key-value
ost config set <key> <value>
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `PRIVATE_DOCKER_REGISTRY` | Default private Docker registry URL |
| `PRIVATE_HELM_REGISTRY` | Default private Helm registry URL |
| `KUBECONFIG` | Path to host Kubernetes configuration file |

---

## 📚 Documentation & Reference

For additional technical specifications, architectural details, and guides:

- [System Description & Architecture (DESCRIPTION.md)](file:///home/ben/src/ostrich/ostrich-sdk/DESCRIPTION.md) - Deep dive into core engine logic, volume mappings, and remote sync.
- [Plugin Creation Guide (PLUGIN.md)](file:///home/ben/src/ostrich/ostrich-sdk/PLUGIN.md) - Complete guide on how to create, document, test, and publish custom Osplates.
- [AI & Developer Guide (CLAUDE.md)](file:///home/ben/src/ostrich/ostrich-sdk/CLAUDE.md) - Build scripts, test runner commands, and development workflows.
- [License (LICENSE)](file:///home/ben/src/ostrich/ostrich-sdk/LICENSE) - Project license information.

---

## 🤝 Contributing & Support

Contributions are welcome! Please refer to [CLAUDE.md](file:///home/ben/src/ostrich/ostrich-sdk/CLAUDE.md) for development rules and guidelines.

For issues and support, please open an issue on the GitHub repository.
