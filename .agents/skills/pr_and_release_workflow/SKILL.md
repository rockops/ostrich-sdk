---
name: pr_and_release_workflow
description: Automate the Ostrich SDK development lifecycle, including dev branch creation with -dev version suffix, local testing, PR creation, merging to main (NEVER push directly to main), tagging vX.Y.Z release tags, and initializing the next dev branch.
---

# Ostrich SDK Development, Branching, PR, and Release Workflow

Use this skill when developing features, managing versions, creating Pull Requests, merging to `main`, tagging releases, or initializing new development cycles for the Ostrich SDK.

> [!IMPORTANT]
> **STRICT RULE**: **NEVER push directly to `main`**. All development, version updates, and feature changes MUST take place inside a development branch (`dev/<version>`) and be merged into `main` via GitHub Pull Requests.

---

## 🔄 Lifecycle Steps

### Phase 1: Start New Development Iteration
When starting development for a new version `<target-version>` (e.g., `0.2.2`):
1. Ensure `main` is up to date:
   ```bash
   git checkout main
   git pull
   ```
2. Create and switch to the development branch:
   ```bash
   git checkout -b dev/<target-version>
   ```
3. Update the single root [VERSION](file:///home/ben/src/ostrich/ostrich-sdk/VERSION) file to append the `-dev` suffix:
   ```text
   <target-version>-dev
   ```
4. Commit and push the new development branch to GitHub:
   ```bash
   git add VERSION
   git commit -m "chore: bump version to <target-version>-dev"
   git push -u origin dev/<target-version>
   ```

---

### Phase 2: Development & Local Verification
Develop code in `dev/<target-version>`. Before opening a PR or releasing:
1. Compile current Go CLI binaries:
   ```bash
   cd scripts && ./build.sh && cd ..
   ```
2. Build the Docker image locally under a `test` tag:
   ```bash
   ./docker/ostrich-sdk/build.sh -n test
   ```
3. Generate local Helm chart package (reading version automatically from root `VERSION` file):
   ```bash
   ./helm/build.sh -n
   ```
4. Run host and container integration test suite:
   ```bash
   export PYTHONPATH=$(pwd)/ost-core:$PYTHONPATH
   export OST_IMAGE_TAG=test
   ./scripts/run_int_tests.sh
   ```

---

### Phase 3: Release Execution
When asked to make a release (e.g. `0.2.2`):
1. **Clean Version Suffix**: Update [VERSION](file:///home/ben/src/ostrich/ostrich-sdk/VERSION) by removing `-dev` (e.g. changing `0.2.2-dev` to `0.2.2`).
2. **Commit & Push Branch**:
   ```bash
   git add -A
   git commit -m "feat: release version <target-version>"
   git push origin dev/<target-version>
   ```
3. **Create PR to `main`**:
   ```bash
   gh pr create --title "feat: release version <target-version>" --body "Release version <target-version>." --base main --head dev/<target-version>
   ```
4. **Merge PR into `main`**:
   ```bash
   gh pr merge --merge --delete-branch
   ```
5. **Tag `main` (`v<target-version>`)**:
   ```bash
   git checkout main
   git pull
   git tag v<target-version>
   git push origin v<target-version>
   ```
   *Pushing tag `v<target-version>` triggers PyPI publication (`pypi-publish.yml`) and GitHub Release / Docker / Helm image builds (`release.yml`).*

---

### Phase 4: Post-Release Next Dev Initialization
Immediately after tagging and publishing `<target-version>`:
1. Compute the next patch version `<next-version>` (e.g. `0.2.3`).
2. Checkout `main` and create new branch `dev/<next-version>`:
   ```bash
   git checkout main
   git pull
   git checkout -b dev/<next-version>
   ```
3. Update [VERSION](file:///home/ben/src/ostrich/ostrich-sdk/VERSION) to `<next-version>-dev` (e.g. `0.2.3-dev`).
4. Commit and push:
   ```bash
   git add VERSION
   git commit -m "chore: bump version to <next-version>-dev"
   git push -u origin dev/<next-version>
   ```
