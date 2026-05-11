import datetime
import os
import time

os.environ['TZ'] = 'Etc/GMT-6'
time.tzset()

def log(msg):
    """Print message with timestamp"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")