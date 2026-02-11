#!/bin/bash
set -e

# Script to deploy the Ostrich SDK Helm chart from the local directory

VERSION=$1

if [ -z "$VERSION" ]; then
    echo "Usage: $0 <version>"
    echo "Example: $0 0.1.0"
    exit 1
fi

TOP=$(cd "$(dirname "$0")" && pwd)
cd "$TOP"

echo ">> Generating Chart.yaml for version $VERSION..."
sed "s/0.0.0-changeme/$VERSION/g" Chart.yaml.tmpl > Chart.yaml

echo ">> Deploying Helm chart ostrich-sdk version $VERSION..."
OPTS=""
if [ -n "$PRIVATE_DOCKER_REGISTRY" ]; then
    echo "Using private docker registry $PRIVATE_DOCKER_REGISTRY"
    OPTS="--set ostrich-sdk.registry=$PRIVATE_DOCKER_REGISTRY"
fi
helm upgrade --install --namespace ostrich --create-namespace ostrich . $OPTS

echo ">> Done."

