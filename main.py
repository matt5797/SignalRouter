import sys
import os
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import uvicorn
from src.api import create_app
from src.utils import setup_logger

logger = setup_logger()


def main():
    logger.info("Starting Signal Executor")
    
    config_path = os.getenv("CONFIG_PATH", "config/config.yaml")
    
    if not Path(config_path).exists():
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)
    
    app = create_app(config_path)
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    
    logger.info(f"Server starting at {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )


if __name__ == "__main__":
    main()