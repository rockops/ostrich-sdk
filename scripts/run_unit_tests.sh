#!/bin/bash

# Script to run Ostrich SDK unit tests using pytest
# This script ensures the PYTHONPATH is correctly set to include the src directory.

# Get the root directory of the project
PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
export PYTHONPATH=$PROJECT_ROOT/ost-core:$PYTHONPATH

echo "Running Ostrich SDK unit tests (Main Suite)..."
pytest "$PROJECT_ROOT/ost-core/test" "$@"

