# Refactoring Plan: Code Differentiator

The goal of this refactoring is to make the codebase in `ostrich-sdk/ost-core/src` significantly different from `ostrich-sdk2/src/src` at the source code level, while preserving all existing functionalities.

## General Refactoring Techniques
- **Naming Overhaul**: Rename internal functions, local variables, and private class attributes to uniquely descriptive alternatives.
- **Structural Reorganization**: Change the order of function definitions and group related logic differently.
- **Logic Transformation**: 
    - Convert loops to list comprehensions/generators (or vice-versa).
    - Switch between f-strings, `.format()`, and string concatenation.
    - Alter error handling patterns (e.g., centralized vs. localized `try-except`).
- **Abstractions**: Introduce or flatten internal helper functions to change the "grep footprint" of the logic.
- **Documentation**: Rephrase comments and docstrings while maintaining meaning.

## File-Specific Actions

### `util.py`
- **Class `Params`**: 
    - Rename to `ContextManager` or `RuntimeParams`.
    - Change how configuration attributes are accessed (e.g., use a dictionary-backed `__getattr__` or a more modern dataclass-like structure).
- **Configuration Loading**: Refactor `loadPluginConf` to use a more modular approach for trying different encodings and handling Jinja2 rendering.
- **Path Resolution**: Re-implement `getTemplatePath` using a recursive search strategy or a prioritized list of resolvers to change the code structure.
- **Jinja2 Filters**: Rename filters like `here`, `noslash`, and `md5hash` to more verbose names like `expand_local_path`, `remove_trailing_separator`, and `compute_content_hash`.

### `operations.py`
- **Runner Decoupling**: Refactor `inprocess`, `shell`, and `container` into a more strategy-based pattern or rename them to more specific actions like `execute_native`, `execute_script`, and `execute_isolated`.
- **Traceback Handling**: Change how `inprocess` captures and displays code context during errors to use different library calls or custom formatting.
- **Path Mapping**: Rename `getHostPath` to `host_filesystem_mapper` and refactor the DinD (Docker-in-Docker) path translation logic to use a more functional approach.
- **Command Construction**: Use a builder-like pattern or a more dynamic list management for constructing container runtime commands.

### `registry.py` (and others)
- **API Search Refactoring**: Split the `search` function into sub-handlers (e.g., `GitHubRegistryProvider`, `HarborRegistryProvider`) to dramatically change the file layout compared to a single large function.
- **Request Logic**: Rephrase the authentication and OCI request handling to use different flow control patterns.

### `template.py`
- **Template Generation**: Rename `templateAll` and refactor the file walking and rendering logic to use different abstractions.
- **Installation Logic**: Differentiate the installation from directory vs. registry by splitting them into distinct, well-defined workflows.

## Constraints Adherence
- **ASCII Art**: The Ostrich ASCII art will be preserved in all help/usage outputs.
- **Term 'template'**: All public-facing terms and essential internal references to "template" will be kept.
- **Filenames**: All filenames will remain unchanged (`util.py`, `operations.py`, etc.).
- **Functionality**: All current CLI commands and internal operations will remain fully functional.

## Verification
- Basic command execution (e.g., `ost template help`, `ost config`) will be tested after refactoring to ensure no breakages.
