# Ostrich SDK

Deploy like an Ostrich! 🦩

Ostrich SDK is a template-driven application deployment engine designed to simplify and standardize the orchestration and deployment of application architectures across diverse environments. 

By leveraging parameterized template packages called **osplates**, developers can easily package, parameterize, and deploy applications without managing low-level orchestration configurations directly.

---

## Key Features

- **Template-driven (Osplates):** Build once, deploy anywhere using customizable parameters and templates.
- **Jinja2 Templating Engine:** Parameterize configurations safely using customized Jinja2 delimiters `[[` and `]]`.
- **Docker/Podman Sandbox:** Run tasks locally within isolated containers to avoid installing complex deployment toolchains (Helm, Kubernetes, jq, yq, etc.) on host machines.
- **Remote K8s/SSH Orchestration:** Deploy and manage remote instances over secure SSH tunnel connections using the `ostr` agent.

---

## System Architecture Overview

The Ostrich SDK is composed of three primary components:

1. **`ost-core` (The Engine):** A Python core engine (`ost`) that processes templates, resolves configurations, and runs deployment tasks using designated runners (`inprocess`, `shell`, or `container`).
2. **`ostd` (Local Container CLI):** A compiled Go utility that launches the `ost` engine inside a local Docker container, mounting local workspace directories and cluster configuration (e.g., `.kube/config`, `.docker/config.json`) seamlessly.
3. **`ostr` (Remote K8s CLI):** A Go utility that coordinates with a remote SSH-enabled pod deployed inside a Kubernetes cluster to sync files and execute `ost` deployment tasks remotely.

---

## Quickstart

### 1. Build and Install CLIs
To build the CLI binaries (`ostd` and `ostr`), run the build script:
```bash
./scripts/build.sh
```
The compiled binaries for Linux, macOS, and Windows will be placed in the `bin/` directory. Copy the appropriate binary to your system PATH (e.g. `/usr/local/bin/`).

### 2. Running Tasks Locally with `ostd`
Using `ostd` allows you to deploy applications locally without setting up the core Python environment on your host machine.

- **Check Version:**
  ```bash
  ostd --version
  ```
- **List Available Templates:**
  ```bash
  ostd template list
  ```
- **Generate a Sample Config File:**
  ```bash
  ostd template config <template-name>
  ```
- **Run Deployment Task (Dry Run):**
  ```bash
  ostd -dr run deploy
  ```
- **Run Deployment Task:**
  ```bash
  ostd run deploy
  ```

### 3. Running Tasks Remotely with `ostr`
`ostr` lets you orchestrate deployments on a remote Kubernetes cluster containing an Ostrich SDK agent.

- **Initialize Connection:**
  ```bash
  ostr init
  ```
  Follow the prompts to configure the remote endpoint details (SSH host, port, credentials).
- **List/Switch Endpoints:**
  ```bash
  ostr endpoint list
  ostr endpoint select <endpoint-name>
  ```
- **Execute Deployment Tasks Remotely:**
  ```bash
  ostr run deploy
  ```
  This command will automatically synchronize your local configuration files to the remote environment and execute the `deploy` task.
- **Open a Remote Shell:**
  ```bash
  ostr ssh
  ```

---

## Documentation Links

For further technical detail and guides, please refer to:
- [Detailed System Description (DESCRIPTION.md)](file:///home/ben/src/ostrich-sdk/DESCRIPTION.md) - Deep dive into core engine logic, volume mappings, and remote sync.
- [AI & Developer Guide (CLAUDE.md)](file:///home/ben/src/ostrich-sdk/CLAUDE.md) - Build, test, and contribution workflows.
