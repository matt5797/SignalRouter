import json
import logging
from datetime import datetime

from shared.models.signal import Signal
from shared.broker.kis_broker import KisBroker
from shared.broker.secrets import SecretLoader

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    TradingView webhook receiver
    
    API Gateway event format:
    {
        "body": '{"symbol":"USDKRWF","action":"BUY","quantity":1,"webhook_token":"abc123"}',
        "headers": {...},
        "requestContext": {...}
    }
    """
    try:
        logger.info(f"Webhook received: {event.get('body', '')[:200]}")
        
        body = json.loads(event.get('body', '{}'))
        signal = Signal.from_webhook(body)
        
        valid, error = signal.validate()
        if not valid:
            logger.error(f"Invalid signal: {error}")
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": error,
                    "timestamp": datetime.now().isoformat()
                })
            }
        
        account = SecretLoader.get_account_by_token(signal.webhook_token)
        if not account:
            logger.error(f"Invalid webhook token: {signal.webhook_token}")
            return {
                "statusCode": 401,
                "body": json.dumps({
                    "error": "Invalid webhook token",
                    "timestamp": datetime.now().isoformat()
                })
            }
        
        if not account.get('is_active', False):
            logger.warning(f"Account {account.get('id')} is inactive")
            return {
                "statusCode": 403,
                "body": json.dumps({
                    "error": "Account is inactive",
                    "timestamp": datetime.now().isoformat()
                })
            }
        
        broker = KisBroker(
            account_id=account['id'],
            secret_identifier=account['id'],
            is_virtual=account.get('is_virtual', False)
        )
        
        logger.info(f"Executing: {signal.action} {signal.symbol} x{signal.quantity}")
        
        if signal.action == 'BUY':
            order_id = broker.buy(signal.symbol, signal.quantity, price=None)
        else:
            order_id = broker.sell(signal.symbol, signal.quantity, price=None)
        
        logger.info(f"Order placed: {order_id}")
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "order_id": order_id,
                "symbol": signal.symbol,
                "action": signal.action,
                "quantity": signal.quantity,
                "account_id": account['id'],
                "timestamp": datetime.now().isoformat()
            })
        }
        
    except Exception as e:
        logger.error(f"Execution failed: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
        }