#!/bin/bash

# Script to run Ostrich SDK unit tests using pytest
# This script ensures the PYTHONPATH is correctly set to include the src directory.

# Get the root directory of the project
PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)

echo "Running Ostrich SDK integration tests..."
$PROJECT_ROOT/ost-core/ost template test unit-tests $@


