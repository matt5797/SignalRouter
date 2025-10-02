#!/usr/bin/env python3
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ['ACCOUNTS_CONFIG'] = json.dumps([
    {
        "id": "test_account",
        "webhook_token": "test_token_123",
        "app_key": "TEST_APP_KEY",
        "app_secret": "TEST_APP_SECRET",
        "account_number": "12345678",
        "account_product": "01",
        "account_type": "FUTURES",
        "is_virtual": True,
        "is_active": True
    }
])


def test_webhook_handler():
    from functions.webhook.handler import lambda_handler
    
    event = {
        'body': json.dumps({
            'symbol': 'USDKRWF',
            'action': 'BUY',
            'quantity': 1,
            'webhook_token': 'test_token_123'
        }),
        'headers': {},
        'requestContext': {}
    }
    
    print("Testing webhook handler...")
    print("Event:", json.dumps(event, indent=2))
    print("\n" + "="*50 + "\n")
    
    result = lambda_handler(event, None)
    
    print("Result:", json.dumps(result, indent=2))
    print("\nStatus Code:", result['statusCode'])
    
    if result['statusCode'] == 200:
        print("SUCCESS")
    else:
        print("FAILED")


def test_order_status_handler():
    from functions.order_status.handler import lambda_handler
    
    event = {
        'pathParameters': {
            'order_id': '12345678'
        },
        'queryStringParameters': {
            'account_id': 'test_account'
        }
    }
    
    print("\nTesting order_status handler...")
    print("Event:", json.dumps(event, indent=2))
    print("\n" + "="*50 + "\n")
    
    result = lambda_handler(event, None)
    
    print("Result:", json.dumps(result, indent=2))
    print("\nStatus Code:", result['statusCode'])


if __name__ == '__main__':
    print("Lambda Local Test")
    print("="*50)
    
    test = sys.argv[1] if len(sys.argv) > 1 else 'webhook'
    
    if test == 'webhook':
        test_webhook_handler()
    elif test == 'order_status':
        test_order_status_handler()
    else:
        print(f"Unknown test: {test}")
        print("Usage: python test_local.py [webhook|order_status]")