import logging
import sys
from pathlib import Path
from datetime import datetime


def setup_logger(name: str = "signal_executor", log_dir: str = "logs") -> logging.Logger:
    root_logger = logging.getLogger()
    
    if root_logger.handlers:
        return logging.getLogger(name)
    
    root_logger.setLevel(logging.DEBUG)
    
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    today = datetime.now().strftime("%Y%m%d")
    log_file = log_path / f"signal_{today}.log"
    
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(file_formatter)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    
    root_logger.info("=" * 80)
    root_logger.info(f"Logger initialized - Log file: {log_file}")
    root_logger.info("=" * 80)
    
    return logging.getLogger(name)


def get_logger(name: str = None) -> logging.Logger:
    if name:
        return logging.getLogger(name)
    return logging.getLogger()