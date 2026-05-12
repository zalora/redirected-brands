import datetime
import os
import time

_TIMEZONE_INITIALIZED = False

def init_timezone():
     """Initialize process timezone once, if supported by the platform."""
     global _TIMEZONE_INITIALIZED
     if _TIMEZONE_INITIALIZED:
         return
     os.environ['TZ'] = 'Etc/GMT-8' # Set timezone to Singapore time (UTC+8)
     if hasattr(time, 'tzset'):
         time.tzset()
     _TIMEZONE_INITIALIZED = True


def log(msg):
    """Print message with timestamp"""
    init_timezone()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")