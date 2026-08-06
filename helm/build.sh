#!/bin/bash
set -e

# Script to build and optionally push the Ostrich SDK Helm chart

PUSH=true
VERSION=""

REGISTRY=${PRIVATE_HELM_REGISTRY:-ghcr.io/rockops/helm}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -n)
            PUSH=false
            shift
            ;;
        *)
            VERSION=$1
            shift
            ;;
    esac
done

TOP=$(cd "$(dirname "$0")" && pwd)
cd "$TOP"

if [ -z "$VERSION" ] && [ -f "$TOP/../VERSION" ]; then
    VERSION=$(cat "$TOP/../VERSION" | tr -d ' \t\r\n')
fi

if [ -z "$VERSION" ]; then
    echo "Usage: $0 [-n] <version>"
    echo "Example: $0 0.1.0"
    exit 1
fi

echo ">> Generating Chart.yaml for version $VERSION..."
sed "s/0.0.0-changeme/$VERSION/g" Chart.yaml.tmpl > Chart.yaml

echo ">> Packaging Helm chart..."
helm package .

if [ "$PUSH" == "true" ]; then
    echo ">> Pushing Helm chart to oci://$REGISTRY ..."
    # Helm requires the oci:// prefix for OCI registries like GHCR
    helm push "ostrich-sdk-$VERSION.tgz" oci://$REGISTRY
fi

echo ">> Done."
