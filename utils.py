import datetime

def log(msg):
    """Print message with timestamp"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")