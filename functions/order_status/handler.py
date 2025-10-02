import json
import logging
from datetime import datetime

from shared.broker.kis_broker import KisBroker
from shared.broker.secrets import SecretLoader

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Order status inquiry
    
    API Gateway event format:
    GET /order/{order_id}?account_id=strategy1
    
    {
        "pathParameters": {"order_id": "12345678"},
        "queryStringParameters": {"account_id": "strategy1"}
    }
    """
    try:
        path_params = event.get('pathParameters', {})
        query_params = event.get('queryStringParameters', {})
        
        order_id = path_params.get('order_id')
        account_id = query_params.get('account_id')
        
        if not order_id:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": "order_id is required",
                    "timestamp": datetime.now().isoformat()
                })
            }
        
        if not account_id:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": "account_id is required",
                    "timestamp": datetime.now().isoformat()
                })
            }
        
        logger.info(f"Querying order status: {order_id} for account: {account_id}")
        
        account = SecretLoader.load_secret(account_id)
        if not account:
            return {
                "statusCode": 404,
                "body": json.dumps({
                    "error": f"Account not found: {account_id}",
                    "timestamp": datetime.now().isoformat()
                })
            }
        
        broker = KisBroker(
            account_id=account_id,
            secret_identifier=account_id,
            is_virtual=account.get('is_virtual', False)
        )
        
        result = broker.get_order_status(order_id)
        
        if result['status'] == 'error':
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "error": result.get('error', 'Unknown error'),
                    "order_id": order_id,
                    "timestamp": datetime.now().isoformat()
                })
            }
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                **result['data'],
                "timestamp": datetime.now().isoformat()
            })
        }
        
    except Exception as e:
        logger.error(f"Order status query failed: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
        }