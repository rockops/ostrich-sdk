#!/usr/bin/env bash

set -e

TOP=$(cd $(dirname $0) && pwd)

PUSH=true
if [ "$1" == "-n" ]; then
    PUSH=false
    shift
fi

TAG=$1
test -z "$TAG" && TAG=latest

REGISTRY=${PRIVATE_DOCKER_REGISTRY:-${PRIVATE_DOCKER_REGISTRY:-ghcr.io/rockops/docker}}


echo "========================================="
echo ">> Build Docker image ostrich-sdk:$TAG"

rm -rf $TOP/sdk
mkdir $TOP/sdk
for D in $(ls $TOP/../../ost-core | grep -v "__pycache__" ); do
    cp -r $TOP/../../ost-core/$D $TOP/sdk
done
cp $TOP/../../VERSION $TOP/sdk/VERSION

export PATH=/usr/bin:$PATH

cd $TOP

docker build -t ostrich-sdk:$TAG .

rm -rf $TOP/sdk

if [ "$PUSH" == "true" ]; then
    echo ">> Tag and push Docker image $REGISTRY/ostrich-sdk:$TAG"
    docker tag ostrich-sdk:$TAG $REGISTRY/ostrich-sdk:$TAG
    docker push $REGISTRY/ostrich-sdk:$TAG
fi


echo "========================================="

echo ">> Build SSH Docker image"
docker build --build-arg TAG=$TAG -t ostrich-sdk-ssh:$TAG -f Dockerfile_ssh .

if [ "$PUSH" == "true" ]; then
    echo ">> Tag and push SSH Docker image $REGISTRY/ostrich-sdk-ssh:$TAG"
    docker tag ostrich-sdk-ssh:$TAG $REGISTRY/ostrich-sdk-ssh:$TAG
    docker push $REGISTRY/ostrich-sdk-ssh:$TAG
fi

