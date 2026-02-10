#!/bin/bash
set -e

# Build ostd
echo "Building ostd-cli..."
cd ../ostd-cli
GOOS=linux GOARCH=amd64 go build -o ../bin/linux/ostd
GOOS=darwin GOARCH=amd64 go build -o ../bin/darwin/ostd
GOOS=windows GOARCH=amd64 go build -o ../bin/windows/ostd.exe

# Build ostr
echo "Building ostr-cli..."
cd ../ostr-cli
GOOS=linux GOARCH=amd64 go build -o ../bin/linux/ostr
GOOS=darwin GOARCH=amd64 go build -o ../bin/darwin/ostr
GOOS=windows GOARCH=amd64 go build -o ../bin/windows/ostr.exe

echo "Build complete. Binaries are in bin/"
