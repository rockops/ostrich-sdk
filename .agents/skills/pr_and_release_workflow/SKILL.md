---
name: pr_and_release_workflow
description: Automate the Ostrich SDK development workflow, including creating dev branches, bumping versions, running tests, creating PRs, merging to main, and creating GitHub releases.
---

# Ostrich SDK Development, Pull Request, and Release Workflow

Use this skill when you need to execute the standard development, PR creation, testing, merging, and releasing process for the Ostrich SDK.

---

## Workflow Steps

### Step 1: Create a Development Branch and Set Dev Version
Before starting any development work, you must create a new branch and update the version file:
1. Ensure your local `main` branch is up to date:
   ```bash
   git checkout main && git pull
   ```
2. Create and switch to your feature/dev branch:
   ```bash
   git checkout -b dev/<feature-name>
   ```
3. Update the version in the [VERSION](file:///home/ben/src/ostrich-sdk/VERSION) file:
   - Read the current version from `VERSION` (e.g., `0.1.0`).
   - Bump the version to the next target version (e.g., `0.2.0-dev` or `0.1.1-dev`) by appending the `-dev` suffix.
   - Save the `VERSION` file.
4. Commit and push the branch (without initiating any build):
   ```bash
   git add VERSION
   git commit -m "chore: bump version to <new-version>-dev"
   git push -u origin dev/<feature-name>
   ```

### Step 2: Develop and Push
- Develop code and address modifications in your development branch.
- Periodically commit and push changes. Do not trigger releases or builds at this stage.

### Step 3: Run Local Integration & Container Tests
Before submitting a PR, verify your changes locally to ensure they do not break existing features:
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
3. Run the integration tests on both local Python and containerized `ostd` runners:
   ```bash
   export PYTHONPATH=$(pwd)/ost-core:$PYTHONPATH
   export OST_IMAGE_TAG=test
   ./scripts/run_int_tests.sh
   ```

### Step 4: Create PR, Clean Suffix, and Merge
When the feature is ready to be merged:
1. Create a Pull Request from `dev/<feature-name>` to `main` via the GitHub CLI:
   ```bash
   gh pr create --title "<PR Title>" --body "<PR Description>" --base main --head dev/<feature-name>
   ```
2. Modify the [VERSION](file:///home/ben/src/ostrich-sdk/VERSION) file by removing the `-dev` suffix (e.g., changing `0.2.0-dev` to `0.2.0`).
3. Commit and push the version change to the dev branch:
   ```bash
   git add VERSION
   git commit -m "chore: release version <version>"
   git push
   ```
4. Wait for the GitHub Actions integration test workflow to pass on the PR branch.
5. Merge the PR to `main`:
   ```bash
   gh pr merge --merge
   ```
6. Delete the development branch locally and remotely:
   ```bash
   git branch -d dev/<feature-name>
   git push origin --delete dev/<feature-name>
   ```

### Step 5: Tag and Publish Release
Trigger the release pipeline by creating a tag matching the version file:
1. Checkout `main` and pull the merged changes:
   ```bash
   git checkout main
   git pull
   ```
2. Read the version from [VERSION](file:///home/ben/src/ostrich-sdk/VERSION) (e.g., `0.2.0`).
3. Tag the commit and push it to GitHub:
   ```bash
   git tag v<version>
   git push origin v<version>
   ```
This push will trigger the **Release Build** GitHub Action workflow, which automatically compiles client binaries, builds/pushes the Docker image to GHCR, and creates a GitHub Release.
