#!/bin/bash

set -e

FUNCTION_NAME=$1
ZIP_FILE="build/${FUNCTION_NAME}.zip"

if [ -z "$FUNCTION_NAME" ]; then
    echo "Usage: ./deploy.sh <function-name>"
    echo "Available functions: webhook, order_status"
    exit 1
fi

if [ ! -f "$ZIP_FILE" ]; then
    echo "Error: ZIP file not found: $ZIP_FILE"
    echo "Run ./build.sh $FUNCTION_NAME first"
    exit 1
fi

LAMBDA_FUNCTION_NAME="trading-${FUNCTION_NAME}"

echo "Deploying Lambda function: $LAMBDA_FUNCTION_NAME"
echo "============================================"

aws lambda update-function-code \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --zip-file "fileb://${ZIP_FILE}" \
    --no-cli-pager

echo "============================================"
echo "Deployment complete: $LAMBDA_FUNCTION_NAME"
echo ""
echo "Check function:"
echo "  aws lambda get-function --function-name $LAMBDA_FUNCTION_NAME"
echo ""
echo "View logs:"
echo "  aws logs tail /aws/lambda/$LAMBDA_FUNCTION_NAME --follow"