#!/bin/bash

set -e

FUNCTION_NAME=$1

if [ -z "$FUNCTION_NAME" ]; then
    echo "Usage: ./build.sh <function-name>"
    echo "Available functions: webhook, order_status"
    exit 1
fi

FUNCTION_DIR="functions/$FUNCTION_NAME"
if [ ! -d "$FUNCTION_DIR" ]; then
    echo "Error: Function directory not found: $FUNCTION_DIR"
    exit 1
fi

BUILD_DIR="build/$FUNCTION_NAME"

echo "Building Lambda function: $FUNCTION_NAME"
echo "============================================"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

echo "Copying shared libraries..."
cp -r shared "$BUILD_DIR/"

echo "Copying handler..."
cp "$FUNCTION_DIR/handler.py" "$BUILD_DIR/lambda_function.py"

if [ -f "$FUNCTION_DIR/requirements.txt" ]; then
    echo "Installing dependencies..."
    pip install -r "$FUNCTION_DIR/requirements.txt" -t "$BUILD_DIR" --quiet
fi

echo "Creating ZIP package..."
cd "$BUILD_DIR"
zip -r "../${FUNCTION_NAME}.zip" . -x "*.pyc" -x "*__pycache__*" -q

cd - > /dev/null

echo "============================================"
echo "Build complete: build/${FUNCTION_NAME}.zip"
echo "Size: $(du -h build/${FUNCTION_NAME}.zip | cut -f1)"