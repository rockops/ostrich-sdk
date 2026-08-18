#!/usr/bin/env bash

set -e

TOP=$(cd $(dirname $0) && pwd)

PUSH=true
BUILD_SSH=true
NO_CACHE=""

while [[ "$1" == -* ]]; do
    case "$1" in
        -n|--no-push)
            PUSH=false
            shift
            ;;
        --skip-ssh|--nossh)
            BUILD_SSH=false
            shift
            ;;
        --no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

TAG=$1
if [ -z "$TAG" ] && [ -f "$TOP/../../VERSION" ]; then
    TAG=$(cat "$TOP/../../VERSION" | tr -d ' \t\r\n')
fi
test -z "$TAG" && TAG=latest

REGISTRY=${PRIVATE_DOCKER_REGISTRY:-${PRIVATE_DOCKER_REGISTRY:-ghcr.io/rockops/docker}}


echo "========================================="
echo ">> Build Docker image ostrich-sdk:$TAG"

rm -rf $TOP/sdk
mkdir -p $TOP/sdk
for D in $(ls $TOP/../../ost-core | grep -v "__pycache__" ); do
    cp -r -L $TOP/../../ost-core/$D $TOP/sdk
done
cp $TOP/../../VERSION $TOP/sdk/VERSION
cp $TOP/../../VERSION $TOP/sdk/src/VERSION

# Clean compiled python cache files to keep docker layer cache stable
find $TOP/sdk -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find $TOP/sdk -name "*.pyc" -delete 2>/dev/null || true

export PATH=/usr/bin:$PATH

cd $TOP

docker build $NO_CACHE -t ostrich-sdk:$TAG .

rm -rf $TOP/sdk



if [ "$PUSH" == "true" ]; then
    echo ">> Tag and push Docker image $REGISTRY/ostrich-sdk:$TAG"
    docker tag ostrich-sdk:$TAG $REGISTRY/ostrich-sdk:$TAG
    docker push $REGISTRY/ostrich-sdk:$TAG
fi

if [ "$BUILD_SSH" == "true" ]; then
    echo "========================================="
    echo ">> Build SSH Docker image"
    docker build --build-arg TAG=$TAG -t ostrich-sdk-ssh:$TAG -f Dockerfile_ssh .

    if [ "$PUSH" == "true" ]; then
        echo ">> Tag and push SSH Docker image $REGISTRY/ostrich-sdk-ssh:$TAG"
        docker tag ostrich-sdk-ssh:$TAG $REGISTRY/ostrich-sdk-ssh:$TAG
        docker push $REGISTRY/ostrich-sdk-ssh:$TAG
    fi
fi


