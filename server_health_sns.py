#!/usr/bin/env python3
"""
server_health_sns.py
"""

import os
import sys
import time
import socket
import platform
import json
import logging
from datetime import datetime, timedelta

import psutil
import boto3
from botocore.exceptions import ClientError

# -------------------- CONFIG --------------------

HOURLY_TOPIC_ARN = os.getenv("HOURLY_TOPIC_ARN", "arn:aws:sns:eu-north-1:815563881932:DrHourly")
ALERT_TOPIC_ARN  = os.getenv("ALERT_TOPIC_ARN",  "arn:aws:sns:eu-north-1:815563881932:DrAlert") # chanages according to your sns

CPU_ALERT_THRESHOLD = float(os.getenv("CPU_ALERT_THRESHOLD", "80.0"))

ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", str(10 * 60)))

AWS_REGION = os.getenv("AWS_REGION", "eu-north-1")  # make accrding to you 

LAST_ALERT_FILE = "/var/tmp/server_health_last_alert_time.txt"

# ------------------ END CONFIG ------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("server-health-sns")


def read_last_alert_time():
    try:
        with open(LAST_ALERT_FILE, "r") as f:
            return float(f.read().strip())
    except:
        return 0.0


def write_last_alert_time(ts):
    try:
        with open(LAST_ALERT_FILE, "w") as f:
            f.write(str(ts))
    except Exception as e:
        logger.warning("Could not write alert file: %s", e)


def human_readable_bytes(n):
    for unit in ['B','KB','MB','GB','TB']:
        if n < 1024.0:
            return f"{n:3.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}PB"


def collect_metrics():
    now = datetime.utcnow().isoformat() + "Z"
    hostname = socket.gethostname()
    uname = platform.uname()

    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_per_core = psutil.cpu_percent(interval=0.5, percpu=True)

    try:
        load1, load5, load15 = os.getloadavg()
    except:
        load1 = load5 = load15 = 0.0

    virtual_mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk_usage = psutil.disk_usage("/")
    net_io = psutil.net_io_counters()

    metrics = {
        "timestamp_utc": now,
        "hostname": hostname,
        "platform": f"{uname.system} {uname.release} ({uname.machine})",
        "cpu_percent": cpu_percent,
        "cpu_per_core": cpu_per_core,
        "load_avg": {"1m": load1, "5m": load5, "15m": load15},
        "memory": {
            "total": virtual_mem.total,
            "used": virtual_mem.used,
            "percent": virtual_mem.percent
        },
        "swap": {
            "total": swap.total,
            "used": swap.used,
            "percent": swap.percent
        },
        "disk": {
            "total": disk_usage.total,
            "used": disk_usage.used,
            "percent": disk_usage.percent
        },
        "network": {
            "bytes_sent": net_io.bytes_sent,
            "bytes_recv": net_io.bytes_recv
        }
    }

    return metrics


def format_summary(metrics):
    return (
        f"Server Health Summary - {metrics['hostname']}\n"
        f"CPU: {metrics['cpu_percent']}%\n"
        f"Memory: {metrics['memory']['percent']}%\n"
        f"Disk: {metrics['disk']['percent']}%\n"
    )


def publish_sns(client, topic_arn, subject, message):
    try:
        resp = client.publish(
            TopicArn=topic_arn,
            Subject=subject[:100],
            Message=message
        )
        logger.info("SNS Published: %s", resp.get("MessageId"))
    except Exception as e:
        logger.error("SNS Publish Error: %s", e)


def main():
    sns = boto3.client("sns", region_name=AWS_REGION)

    metrics = collect_metrics()
    summary = format_summary(metrics)
    message_json = json.dumps(metrics, indent=2)

    # Hourly Summary
    publish_sns(
        sns,
        HOURLY_TOPIC_ARN,
        f"[Hourly] Health Update - CPU {metrics['cpu_percent']}%",
        summary + "\n\n" + message_json
    )

    # Alert Logic
    cpu = metrics["cpu_percent"]
    now_ts = time.time()
    last_alert_ts = read_last_alert_time()

    if cpu > CPU_ALERT_THRESHOLD and (now_ts - last_alert_ts > ALERT_COOLDOWN_SECONDS):
        publish_sns(
            sns,
            ALERT_TOPIC_ARN,
            f"[ALERT] HIGH CPU: {cpu}%",
            summary + "\n\n" + message_json
        )
        write_last_alert_time(now_ts)


if __name__ == "__main__":
    main()
