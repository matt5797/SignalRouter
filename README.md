# SignalRouter

TradingView webhook signals to KIS API execution via AWS Lambda.

## Project Structure

```
trading-lambda/
├── shared/                      # Common library for all Lambdas
│   ├── broker/
│   │   ├── kis_auth.py         # Token management
│   │   ├── kis_broker.py       # Order execution
│   │   └── secrets.py          # Account configuration
│   └── models/
│       └── signal.py           # Signal & result models
├── functions/
│   ├── webhook/                # POST /webhook
│   │   ├── handler.py
│   │   └── requirements.txt
│   └── order_status/           # GET /order/{id}
│       ├── handler.py
│       └── requirements.txt
└── scripts/
    ├── build.sh                # Build Lambda packages
    └── deploy.sh               # Deploy to AWS
```

## Setup

### 1. AWS Lambda Configuration

```bash
# Create Lambda functions
aws lambda create-function \
    --function-name trading-webhook \
    --runtime python3.11 \
    --handler lambda_function.lambda_handler \
    --role arn:aws:iam::YOUR_ACCOUNT:role/lambda-execution-role \
    --zip-file fileb://build/webhook.zip \
    --timeout 30 \
    --memory-size 512

aws lambda create-function \
    --function-name trading-order_status \
    --runtime python3.11 \
    --handler lambda_function.lambda_handler \
    --role arn:aws:iam::YOUR_ACCOUNT:role/lambda-execution-role \
    --zip-file fileb://build/order_status.zip \
    --timeout 30 \
    --memory-size 256
```

### 2. Environment Variables

```bash
# Set ACCOUNTS_CONFIG for webhook Lambda
aws lambda update-function-configuration \
    --function-name trading-webhook \
    --environment 'Variables={
        ACCOUNTS_CONFIG="[{
            \"id\": \"strategy1\",
            \"webhook_token\": \"your_secret_token\",
            \"app_key\": \"your_app_key\",
            \"app_secret\": \"your_app_secret\",
            \"account_number\": \"12345678\",
            \"account_product\": \"01\",
            \"account_type\": \"FUTURES\",
            \"is_virtual\": false,
            \"is_active\": true
        }]"
    }'

# Set for order_status Lambda too
aws lambda update-function-configuration \
    --function-name trading-order_status \
    --environment 'Variables={
        ACCOUNTS_CONFIG="[...]"  # Same as above
    }'
```

### 3. API Gateway Setup

```bash
# Create REST API
aws apigateway create-rest-api \
    --name "TradingView Executor" \
    --endpoint-configuration types=REGIONAL

# Create resources and methods
# POST /webhook -> trading-webhook Lambda
# GET /order/{order_id} -> trading-order_status Lambda

# Deploy to stage
aws apigateway create-deployment \
    --rest-api-id YOUR_API_ID \
    --stage-name prod
```

## Build & Deploy

```bash
# Make scripts executable
chmod +x scripts/*.sh

# Build webhook function
./scripts/build.sh webhook

# Deploy webhook function
./scripts/deploy.sh webhook

# Build and deploy order_status
./scripts/build.sh order_status
./scripts/deploy.sh order_status

# Or build and deploy in one command
./scripts/build.sh webhook && ./scripts/deploy.sh webhook
```

## Usage

### Webhook Endpoint (TradingView)

```bash
# TradingView Alert Message (JSON):
{
  "symbol": "USDKRWF",
  "action": "BUY",
  "quantity": 1,
  "webhook_token": "your_secret_token"
}

# Response:
{
  "order_id": "12345678",
  "symbol": "USDKRWF",
  "action": "BUY",
  "quantity": 1,
  "account_id": "strategy1",
  "timestamp": "2025-10-02T10:30:00.123456"
}
```

### Order Status Endpoint

```bash
GET https://YOUR_API_GATEWAY_URL/prod/order/12345678?account_id=strategy1

# Response:
{
  "status": "FILLED",
  "order_id": "12345678",
  "symbol": "USDKRWF",
  "quantity": 1,
  "filled_quantity": 1,
  "price": 1320.5,
  "timestamp": "2025-10-02T10:31:00.123456"
}
```

## Local Development

```bash
# Install dependencies locally
pip install -r functions/webhook/requirements.txt

# Test handler locally
python3 -c "
from functions.webhook.handler import lambda_handler
import json

event = {
    'body': json.dumps({
        'symbol': 'USDKRWF',
        'action': 'BUY',
        'quantity': 1,
        'webhook_token': 'test_token'
    })
}

result = lambda_handler(event, None)
print(result)
"
```

## Monitoring

```bash
# View logs
aws logs tail /aws/lambda/trading-webhook --follow

# Get function info
aws lambda get-function --function-name trading-webhook

# Check last 10 invocations
aws lambda list-functions --query 'Functions[?starts_with(FunctionName, `trading-`)].FunctionName'
```

## Cost Estimation

### Monthly Cost (2 executions/month)

- Lambda Execution: $0.00002
- API Gateway: $0.00
- CloudWatch Logs: ~$0.10

**Total: ~$0.10/month**

## Security Notes

1. Use API Gateway API keys for production
2. Rotate webhook tokens regularly
3. Enable CloudWatch Logs encryption
4. Use AWS Secrets Manager for sensitive data (optional)

## Troubleshooting

### Cold Start Issues
- First execution may take 5-10 seconds
- Token will be fetched fresh on cold start

### Token Errors
- Check ACCOUNTS_CONFIG format
- Verify KIS API credentials
- Check CloudWatch Logs for details

### Order Failures
- Verify market hours (DAY/NIGHT session)
- Check symbol format
- Ensure sufficient balance