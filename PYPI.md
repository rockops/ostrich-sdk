# PyPI Publishing & Account Setup Guide for `ostrich-sdk`

This guide explains how to set up PyPI publishing for the `ostrich-sdk` package and how automated package deployment is handled via GitHub Actions.

---

## 📋 Overview

`ostrich-sdk` is published to PyPI as `ostrich-sdk` and installable via:

```bash
pip install ostrich-sdk
```

Whenever a version tag (e.g. `v0.2.0`) is pushed to the `main` branch, the GitHub Action workflow [`.github/workflows/pypi-publish.yml`](file:///.github/workflows/pypi-publish.yml) automatically builds the source distribution (`.tar.gz`) and wheel (`.whl`) and publishes them to PyPI.

---

## 🔑 PyPI Account & Authentication Setup

To enable GitHub Actions to publish package releases to PyPI, set up authentication using either **Trusted Publishing (OIDC)** or a **PyPI API Token**.

---

### Option 1: Trusted Publishing (Recommended / Passwordless OIDC)

PyPI Trusted Publishing allows GitHub Actions to securely authenticate with PyPI using OpenID Connect (OIDC) tokens without storing secret API keys in GitHub.

#### Setup Steps:
1. Log in to your [PyPI.org](https://pypi.org/) account.
2. Go to **Account Settings** -> **[Publishing](https://pypi.org/manage/account/publishing/)** (or if the project already exists, go to **[ostrich-sdk Project Settings -> Publishing](https://pypi.org/manage/project/ostrich-sdk/settings/publishing/)**).
3. Under **Add a new publisher**, select **GitHub**.
4. Fill in the following fields:
   - **PyPI Project Name**: `ostrich-sdk`
   - **Owner / Organization**: `rockops`
   - **Repository Name**: `ostrich-sdk`
   - **Workflow name**: `pypi-publish.yml`
   - **Environment name**: *(leave empty)*
5. Click **Add Publisher**.

Once configured, PyPI will automatically verify OIDC assertions sent by the `pypi-publish.yml` workflow run during release tag pushes.

---

### Option 2: PyPI API Token Secret (Alternative)

If you prefer using a static API token instead of Trusted Publishing:

#### Setup Steps:
1. Log in to [PyPI.org](https://pypi.org/).
2. Navigate to **Account Settings** -> **[API tokens](https://pypi.org/manage/account/token/)**.
3. Click **Add API token**:
   - **Token name**: `github-actions-ostrich-sdk`
   - **Scope**: Entire account or project `ostrich-sdk`
4. Copy the generated API token (starts with `pypi-`).
5. Go to your GitHub repository: `https://github.com/rockops/ostrich-sdk/settings/secrets/actions`
6. Click **New repository secret**:
   - **Name**: `PYPI_API_TOKEN`
   - **Secret**: Paste the copied API token
7. Click **Add secret**.

The workflow is configured to automatically use `secrets.PYPI_API_TOKEN` if present.

---

## 🚀 How Release Publication Works

The release process follows the standard Ostrich SDK release workflow (`pr_and_release_workflow` skill):

1. **Update `VERSION`**: Update `VERSION` at the repository root (e.g. `0.2.0`).
2. **Merge PR to `main`**: Merge feature branch into `main`.
3. **Create & Push Tag**:
   ```bash
   git checkout main
   git pull
   git tag v0.2.0
   git push origin v0.2.0
   ```
4. **Automated Pipeline Execution**:
   - Pushing the tag triggers `.github/workflows/pypi-publish.yml`.
   - The workflow sets up Python 3.12, installs PyPA `build`, and generates distributions:
     - Source distribution: `dist/ostrich_sdk-0.2.0.tar.gz`
     - Wheel package: `dist/ostrich_sdk-0.2.0-py3-none-any.whl`
   - `pypa/gh-action-pypi-publish@release/v1` uploads the built packages to PyPI.

---

## 🧪 Local Testing & Verification

### 1. Test Building the Package Locally
```bash
# Install PyPA build tool
python -m pip install --upgrade build

# Build wheel and sdist
python -m build

# Check built artifacts in dist/
ls -la dist/
```

### 2. Verify Installation in Clean Virtual Environment
```bash
python -m venv /tmp/venv_test
source /tmp/venv_test/bin/activate
pip install dist/*.whl

# Verify CLI entrypoint
ost help
ost template list
deactivate
rm -rf /tmp/venv_test
```

### 3. Optional: Upload to TestPyPI
If you wish to test publishing without deploying to production PyPI:
```bash
pip install twine
python -m twine upload --repository testpypi dist/*
```

---

## 📄 License & Maintainers

- **Package Name**: `ostrich-sdk`
- **PyPI Page**: [https://pypi.org/project/ostrich-sdk/](https://pypi.org/project/ostrich-sdk/)
- **Repository**: [rockops/ostrich-sdk](https://github.com/rockops/ostrich-sdk)
