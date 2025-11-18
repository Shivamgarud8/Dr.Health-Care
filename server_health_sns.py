#!/usr/bin/env python3

import boto3
import psutil
import socket
import json
from datetime import datetime

# ------------------------------ CONFIG ------------------------------

AWS_ACCESS_KEY = "ENTRT-YOUR-KEY"
AWS_SECRET_KEY = "ENTER YOUR PASS"
AWS_REGION     = "eu-north-1"
SNS_TOPIC_ARN  = "ADD YOUR SNS"

CPU_ALERT_THRESHOLD = 40

# ------------------------------ COLORS ------------------------------

GREEN  = "\033[32m"
YELLOW = "\033[33m"
ORANGE = "\033[38;5;208m"
RED    = "\033[31m"
BLUE   = "\033[34m"
RESET  = "\033[0m"

def cpu_color(val):
    if val <= 40:
        return f"{GREEN}{val}% (Normal){RESET}"
    elif val <= 60:
        return f"{YELLOW}{val}% (Moderate){RESET}"
    elif val <= 80:
        return f"{ORANGE}{val}% (High){RESET}"
    else:
        return f"{RED}{val}% (Critical){RESET}"

def alert_level(val):
    if val <= 40:
        return None
    elif val <= 60:
        return "🟡 YELLOW - Moderate CPU Load"
    elif val <= 80:
        return "🟠 ORANGE - High CPU Load"
    else:
        return "🔴 RED - CRITICAL CPU Load"

# ------------------------------ SNS ------------------------------

def send_sns(subject, msg):
    sns = boto3.client(
        "sns",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY
    )
    sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject[:100], Message=msg)

# ------------------------------ METRICS ------------------------------

def collect_metrics():
    return {
        "hostname": socket.gethostname(),
        "time": datetime.utcnow().isoformat() + "Z",
        "cpu": psutil.cpu_percent(interval=1),
        "memory": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage("/").percent
    }

# ------------------------------ FORMATTERS ------------------------------

def summary_email(m):
    return f"""
{BLUE}📊 5-Min Server Health Summary{RESET}

🖥️ Server: {m['hostname']}
⏱️ Time: {m['time']}

⚙️ CPU: {cpu_color(m['cpu'])}
💾 Memory: {m['memory']}%
📦 Disk: {m['disk']}%

JSON:
{json.dumps(m, indent=2)}
"""

def alert_email(m, level):
    return f"""
{RED}🚨 CPU ALERT TRIGGERED!{RESET}

🖥️ Server: {m['hostname']}
⏱️ Time: {m['time']}

⚠️ CPU: {cpu_color(m['cpu'])}
📛 Alert Level: {level}

💾 Memory: {m['memory']}%
📦 Disk: {m['disk']}%

JSON:
{json.dumps(m, indent=2)}
"""

# ------------------------------ MAIN ------------------------------

def main():
    m = collect_metrics()

    # Always send summary
    send_sns(f"[Summary] CPU: {m['cpu']}%", summary_email(m))

    # Check alert condition
    level = alert_level(m["cpu"])
    if level:
        send_sns(f"[ALERT] CPU {m['cpu']}%", alert_email(m, level))


if __name__ == "__main__":
    main()
