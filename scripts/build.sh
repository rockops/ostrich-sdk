#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SDK_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION=$(cat "$SDK_ROOT/VERSION" | tr -d ' \t\r\n')

echo "Building version $VERSION..."

# Build ostd
echo "Building ostd-cli..."
cd "$SDK_ROOT/ostd-cli"
GOOS=linux GOARCH=amd64 go build -ldflags "-X main.VERSION=${VERSION} -X main.DefaultTag=${VERSION}" -o ../bin/linux/ostd
GOOS=darwin GOARCH=amd64 go build -ldflags "-X main.VERSION=${VERSION} -X main.DefaultTag=${VERSION}" -o ../bin/darwin/ostd
GOOS=windows GOARCH=amd64 go build -ldflags "-X main.VERSION=${VERSION} -X main.DefaultTag=${VERSION}" -o ../bin/windows/ostd.exe

# Build ostr
echo "Building ostr-cli..."
cd "$SDK_ROOT/ostr-cli"
GOOS=linux GOARCH=amd64 go build -ldflags "-X main.VERSION=${VERSION}" -o ../bin/linux/ostr
GOOS=darwin GOARCH=amd64 go build -ldflags "-X main.VERSION=${VERSION}" -o ../bin/darwin/ostr
GOOS=windows GOARCH=amd64 go build -ldflags "-X main.VERSION=${VERSION}" -o ../bin/windows/ostr.exe

echo "Build complete. Binaries are in bin/"
