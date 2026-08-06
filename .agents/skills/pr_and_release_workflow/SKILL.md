---
name: pr_and_release_workflow
description: Automate the Ostrich SDK development workflow, including bumping version in VERSION file, running local tests, creating PRs, merging to main, and pushing vX.Y.Z release tags to trigger PyPI publishing and GitHub releases.
---

# Ostrich SDK Development, Pull Request, and Release Workflow

Use this skill when executing the standard development, version bumping, testing, PR merging, and release process for the Ostrich SDK.

---

## 🔄 Release Workflow Steps

### Step 1: Version Bumping
1. Read the target version requested by the user, or read the current version from the single root [VERSION](file:///home/ben/src/ostrich/ostrich-sdk/VERSION) file and bump it to the next target version (e.g., `0.2.0`).
2. Update the root `VERSION` file with the exact target release version `X.Y.Z`.

---

### Step 2: Develop, Stage, and Push Branch
1. Ensure all changes (features, bug fixes, version updates) are included in the current development branch (`dev/<feature-name>` or `feat/<feature-name>`).
2. Commit all staged changes:
   ```bash
   git add -A
   git commit -m "feat: release version <X.Y.Z>"
   git push -u origin <branch-name>
   ```

---

### Step 3: Run Local Integration & Container Tests
Before submitting a PR, verify changes locally to ensure existing features remain intact:
1. Compile current Go CLI binaries:
   ```bash
   cd scripts
   ./build.sh
   cd ..
   ```
2. Build the Docker image locally under a `test` tag:
   ```bash
   ./docker/ostrich-sdk/build.sh -n test
   ```
3. Run integration tests on both local Python (`host`) and containerized (`ostd`) runners:
   ```bash
   export PYTHONPATH=$(pwd)/ost-core:$PYTHONPATH
   export OST_IMAGE_TAG=test
   ./scripts/run_int_tests.sh
   ```

---

### Step 4: Create PR and Merge into `main`
1. Create a Pull Request from `<branch-name>` to `main` via the GitHub CLI:
   ```bash
   gh pr create --title "feat: release version <X.Y.Z>" --body "Release version <X.Y.Z> containing latest updates and PyPI packaging." --base main --head <branch-name>
   ```
2. Merge the Pull Request into `main`:
   ```bash
   gh pr merge --merge --delete-branch
   ```

---

### Step 5: Tag `main` Branch (`vX.Y.Z`) and Publish Release
1. Checkout `main` and pull the merged commit:
   ```bash
   git checkout main
   git pull
   ```
2. Read the version from [VERSION](file:///home/ben/src/ostrich/ostrich-sdk/VERSION) (e.g. `X.Y.Z`).
3. Tag `main` with `vX.Y.Z` and push the tag to GitHub:
   ```bash
   git tag v<X.Y.Z>
   git push origin v<X.Y.Z>
   ```

---

## ⚡ Automated CI/CD Pipelines Triggered

Pushing the `v<X.Y.Z>` tag to GitHub automatically triggers two release pipelines:

1. **PyPI Publish (`.github/workflows/pypi-publish.yml`)**:
   - Builds source distribution (`.tar.gz`) and wheel (`.whl`).
   - Publishes `ostrich-sdk` version `X.Y.Z` to PyPI (`pip install ostrich-sdk==X.Y.Z`).

2. **Release Build (`.github/workflows/release.yml`)**:
   - Compiles Go CLI binaries (`ostd` and `ostr`) for Linux, macOS, and Windows.
   - Builds and pushes Docker images (`ostrich-sdk:X.Y.Z` and `ostrich-sdk-ssh:X.Y.Z`) to GHCR.
   - Packages and pushes the Helm chart.
   - Creates a GitHub Release tagged `vX.Y.Z` attaching the `ostd` and `ostr` CLI binaries.
