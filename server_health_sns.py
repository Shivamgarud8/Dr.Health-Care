#!/usr/bin/env python3

import boto3
import psutil
import socket
import json
from datetime import datetime

# ------------------------------
# CONFIG
# ------------------------------

AWS_ACCESS_KEY = "ENTER-YOUR-KEY"
AWS_SECRET_KEY = "ENTER-YOUR-PASWORD"
AWS_REGION     = "eu-north-1"

SNS_TOPIC_ARN  = "ADD-YOUR SNS "

CPU_ALERT_THRESHOLD = 40
# ------------------------------


# Color Codes
GREEN  = "\033[32m"
YELLOW = "\033[33m"
ORANGE = "\033[38;5;208m"
RED    = "\033[31m"
BLUE   = "\033[34m"
RESET  = "\033[0m"


def cpu_color(value):
    if value <= 40:
        return f"{GREEN}{value}%{RESET}"
    elif value <= 60:
        return f"{YELLOW}{value}%{RESET}"
    elif value <= 80:
        return f"{ORANGE}{value}%{RESET}"
    else:
        return f"{RED}{value}%{RESET}"


def send_sns(subject, message):
    sns = boto3.client(
        "sns",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY
    )

    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=subject[:100],
        Message=message
    )


def collect_metrics():
    hostname = socket.gethostname()
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent

    now = datetime.utcnow().isoformat() + "Z"

    return {
        "time": now,
        "hostname": hostname,
        "cpu": cpu,
        "memory": mem,
        "disk": disk
    }


def format_summary(m):
    return f"""
{BLUE}📊 5-Min Server Health Summary{RESET}

🖥️ Server: {m['hostname']}
⏱️ Time (UTC): {m['time']}

⚙️ CPU Usage: {cpu_color(m['cpu'])}
💾 Memory Usage: {m['memory']}%
📦 Disk Usage: {m['disk']}%

JSON Metrics:
{json.dumps(m, indent=2)}
"""


def format_alert(m):
    return f"""
{RED}🚨 HIGH CPU ALERT TRIGGERED!{RESET}

🖥️ Server: {m['hostname']}
⏱️ Time (UTC): {m['time']}

⚠️ CPU Usage: {cpu_color(m['cpu'])}  (Threshold: {CPU_ALERT_THRESHOLD}%)
💾 Memory: {m['memory']}%
📦 Disk: {m['disk']}%

JSON Metrics:
{json.dumps(m, indent=2)}
"""


def main():
    m = collect_metrics()

    # Send summary email always
    send_sns(f"[Summary] CPU: {m['cpu']}%", format_summary(m))

    # Alert if CPU above threshold
    if m["cpu"] > CPU_ALERT_THRESHOLD:
        send_sns(f"[ALERT] HIGH CPU {m['cpu']}%", format_alert(m))


if __name__ == "__main__":
    main()
