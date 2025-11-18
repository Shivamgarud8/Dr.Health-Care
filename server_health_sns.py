#!/usr/bin/env python3
"""
server_health_sns.py
Sends hourly server health summary to an SNS topic and immediate alerts to another SNS topic
when CPU usage crosses threshold.

Usage:
  - Set HOURLY_TOPIC_ARN and ALERT_TOPIC_ARN below (or via environment variables)
  - Use IAM role or AWS credentials configured for boto3
  - Run every hour via cron: 0 * * * * /usr/bin/python3 /path/to/server_health_sns.py
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
# Either hardcode ARNs here or set these environment variables.
HOURLY_TOPIC_ARN = os.getenv("HOURLY_TOPIC_ARN") or "arn:aws:sns:REGION:ACCOUNT_ID:your-hourly-topic"
ALERT_TOPIC_ARN = os.getenv("ALERT_TOPIC_ARN") or "arn:aws:sns:REGION:ACCOUNT_ID:your-alert-topic"

# CPU threshold percent for alert
CPU_ALERT_THRESHOLD = float(os.getenv("CPU_ALERT_THRESHOLD", "50.0"))

# Minimum seconds between repeated alerts for the same condition (rate limit)
ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", str(10 * 60)))  # default 10 minutes

# Region (optional); if not set, boto3 will discover from environment/instance metadata
AWS_REGION = os.getenv("AWS_REGION", None)

# ------------------ END CONFIG ------------------

# Simple logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("server-health-sns")

# Keep a simple file to track last alert time (so we don't spam)
LAST_ALERT_FILE = "/tmp/server_health_last_alert_time.txt"

def read_last_alert_time():
    try:
        with open(LAST_ALERT_FILE, "r") as f:
            ts = float(f.read().strip())
            return ts
    except Exception:
        return 0.0

def write_last_alert_time(ts):
    try:
        with open(LAST_ALERT_FILE, "w") as f:
            f.write(str(float(ts)))
    except Exception as e:
        logger.warning("Failed writing last alert time: %s", e)

def human_readable_bytes(n):
    # simple bytes -> human readable
    for unit in ['B','KB','MB','GB','TB']:
        if n < 1024.0:
            return f"{n:3.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}PB"

def collect_metrics():
    now = datetime.utcnow().isoformat() + "Z"
    hostname = socket.gethostname()
    uname = platform.uname()
    boot_ts = psutil.boot_time()
    uptime_seconds = time.time() - boot_ts
    uptime = str(timedelta(seconds=int(uptime_seconds)))

    cpu_percent = psutil.cpu_percent(interval=1)  # 1 second average
    cpu_per_core = psutil.cpu_percent(interval=0.5, percpu=True)
    load1, load5, load15 = psutil.getloadavg() if hasattr(psutil, "getloadavg") else (0.0, 0.0, 0.0)

    virtual_mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    disk_usage = psutil.disk_usage("/")
    disk_io = psutil.disk_io_counters()

    net_io = psutil.net_io_counters()

    metrics = {
        "timestamp_utc": now,
        "hostname": hostname,
        "platform": f"{uname.system} {uname.release} ({uname.machine})",
        "uptime": uptime,
        "cpu_percent": cpu_percent,
        "cpu_per_core": cpu_per_core,
        "load_avg": {"1m": load1, "5m": load5, "15m": load15},
        "memory": {
            "total": virtual_mem.total,
            "available": virtual_mem.available,
            "used": virtual_mem.used,
            "percent": virtual_mem.percent
        },
        "swap": {"total": swap.total, "used": swap.used, "percent": swap.percent},
        "disk": {
            "total": disk_usage.total,
            "used": disk_usage.used,
            "free": disk_usage.free,
            "percent": disk_usage.percent,
            "io_read_count": getattr(disk_io, "read_count", None),
            "io_write_count": getattr(disk_io, "write_count", None),
            "io_read_bytes": getattr(disk_io, "read_bytes", None),
            "io_write_bytes": getattr(disk_io, "write_bytes", None)
        },
        "network": {
            "bytes_sent": getattr(net_io, "bytes_sent", None),
            "bytes_recv": getattr(net_io, "bytes_recv", None),
            "packets_sent": getattr(net_io, "packets_sent", None),
            "packets_recv": getattr(net_io, "packets_recv", None)
        }
    }
    return metrics

def format_summary_text(metrics):
    lines = []
    lines.append(f"Server Health Summary - {metrics['hostname']} ({metrics['platform']})")
    lines.append(f"Time (UTC): {metrics['timestamp_utc']}")
    lines.append(f"Uptime: {metrics['uptime']}")
    lines.append("")
    lines.append(f"CPU: {metrics['cpu_percent']}%")
    lines.append(f"CPU per core: {metrics['cpu_per_core']}")
    lines.append(f"Load average (1m/5m/15m): {metrics['load_avg']['1m']:.2f} / {metrics['load_avg']['5m']:.2f} / {metrics['load_avg']['15m']:.2f}")
    lines.append("")
    mem = metrics['memory']
    lines.append(f"Memory: {mem['percent']}% used ({human_readable_bytes(mem['used'])} of {human_readable_bytes(mem['total'])})")
    swap = metrics['swap']
    if swap['total'] and swap['total'] > 0:
        lines.append(f"Swap: {swap['percent']}% used ({human_readable_bytes(swap['used'])} of {human_readable_bytes(swap['total'])})")
    disk = metrics['disk']
    lines.append(f"Disk (/): {disk['percent']}% used ({human_readable_bytes(disk['used'])} of {human_readable_bytes(disk['total'])})")
    net = metrics['network']
    lines.append(f"Network bytes (sent/recv): {net.get('bytes_sent')} / {net.get('bytes_recv')}")
    return "\n".join(lines)

def publish_sns(client, topic_arn, subject, message):
    try:
        resp = client.publish(
            TopicArn=topic_arn,
            Subject=subject[:100] if subject else None,
            Message=message
        )
        logger.info("Published to SNS %s - MessageId: %s", topic_arn, resp.get("MessageId"))
        return resp
    except ClientError as e:
        logger.exception("Failed publishing to SNS: %s", e)
        return None

def main():
    if not HOURLY_TOPIC_ARN or not ALERT_TOPIC_ARN:
        logger.error("SNS topic ARNs are not set. Set HOURLY_TOPIC_ARN and ALERT_TOPIC_ARN environment variables or in the script.")
        sys.exit(1)

    # Create boto3 SNS client
    kwargs = {}
    if AWS_REGION:
        kwargs["region_name"] = AWS_REGION
    sns = boto3.client("sns", **kwargs)

    metrics = collect_metrics()
    summary_text = format_summary_text(metrics)
    summary_json = json.dumps(metrics, indent=2, default=str)

    # 1) Publish hourly summary (text + JSON)
    subject = f"[Hourly] Server Health - {metrics['hostname']} - CPU {metrics['cpu_percent']}%"
    combined_message = summary_text + "\n\nJSON:\n" + summary_json
    publish_sns(sns, HOURLY_TOPIC_ARN, subject, combined_message)

    # 2) Check thresholds and publish alert if needed
    cpu = metrics["cpu_percent"]
    last_alert_ts = read_last_alert_time()
    now_ts = time.time()
    if cpu is not None and cpu > CPU_ALERT_THRESHOLD:
        # rate limit repeated alerts
        if now_ts - last_alert_ts >= ALERT_COOLDOWN_SECONDS:
            alert_subject = f"[ALERT] CPU high on {metrics['hostname']} - {cpu:.1f}%"
            alert_message = (
                f"ALERT: CPU percentage on {metrics['hostname']} ({metrics['platform']}) is {cpu:.1f}%\n\n"
                f"{summary_text}\n\nJSON:\n{summary_json}"
            )
            publish_sns(sns, ALERT_TOPIC_ARN, alert_subject, alert_message)
            write_last_alert_time(now_ts)
        else:
            logger.info("CPU above threshold but still in cooldown period (not sending alert).")
    else:
        logger.info("CPU within normal limits: %.2f%%", cpu)

if __name__ == "__main__":
    main()
