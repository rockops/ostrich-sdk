#!/usr/bin/env bash

set -e

ROOT=$(cd "$(dirname "$0")" && pwd)

test -z $PRIVATE_DOCKER_REGISTRY && {
    echo "Error: PRIVATE_DOCKER_REGISTRY is not set"
    exit 1
}

test -z $PRIVATE_HELM_REGISTRY && {
    echo "Error: PRIVATE_HELM_REGISTRY is not set"
    exit 1
}

cd $ROOT/../docker/ostrich-sdk
./build.sh 0.0.0-dev

cd $ROOT/../helm
./deploy.sh 0.0.0-dev

cd $ROOT/../ostr-cli
go build -o ostr
