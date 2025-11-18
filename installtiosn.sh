#!/bin/bash
set -e

echo "🚀 Starting Server Health Monitor Installation..."
sleep 1

# -----------------------------
# 1. UPDATE SYSTEM
# -----------------------------
echo "🔧 Updating system packages..."
sudo apt update -y
sudo apt install -y python3 python3-pip

# -----------------------------
# 2. INSTALL PYTHON DEPENDENCIES
# -----------------------------
echo "📦 Installing Python packages..."
pip3 install boto3 psutil

# -----------------------------
# 3. CREATE FOLDERS
# -----------------------------
echo "📁 Creating project structure..."
mkdir -p ~/server-scripts
touch ~/cron.log

# -----------------------------
# 4. CREATE PYTHON MONITOR SCRIPT
# -----------------------------
echo "📝 Creating server-monitor.py..."

cat << 'EOF' > ~/server-scripts/server-monitor.py
#!/usr/bin/env python3

import boto3
import psutil
import socket
import json
from datetime import datetime

AWS_ACCESS_KEY = "ENTER-YOUR-KEY"
AWS_SECRET_KEY = "ENTER-YOUR-SECRET-KEY"
AWS_REGION     = "eu-north-1"
SNS_TOPIC_ARN  = "ADD-YOUR SNS "

CPU_ALERT_THRESHOLD = 40

def colorize(cpu):
    if 40 <= cpu <= 60:
        return "🟡 Moderate Load"
    elif 61 <= cpu <= 80:
        return "🟠 High Load"
    elif cpu > 80:
        return "🔴 Critical Load"
    return "🟢 Normal"

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
        "disk": disk,
        "cpu_color": colorize(cpu)
    }

def format_summary(m):
    return f"""
📊 **5-Min Server Health Summary**

🖥️ Server: {m['hostname']}
⏱️ Time: {m['time']}

⚙️ CPU Usage: {m['cpu']}% → {m['cpu_color']}
💾 Memory: {m['memory']}%
📦 Disk: {m['disk']}%

📘 JSON:
{json.dumps(m, indent=2)}
"""

def format_alert(m):
    return f"""
🚨 **HIGH CPU ALERT**

🖥️ Server: {m['hostname']}
⏱️ Time: {m['time']}

⚠️ CPU Usage: {m['cpu']}% → {m['cpu_color']}
💾 Memory: {m['memory']}%
📦 Disk: {m['disk']}%

📘 JSON:
{json.dumps(m, indent=2)}
"""

def main():
    m = collect_metrics()

    summary_msg = format_summary(m)
    send_sns(f"[Summary] CPU: {m['cpu']}%", summary_msg)

    if m["cpu"] > CPU_ALERT_THRESHOLD:
        alert_msg = format_alert(m)
        send_sns(f"[ALERT] HIGH CPU {m['cpu']}%", alert_msg)

if __name__ == "__main__":
    main()
EOF

chmod +x ~/server-scripts/server-monitor.py

# -----------------------------
# 5. CRON JOB SETUP
# -----------------------------
echo "⏱️ Setting cron job..."

CRON_JOB="*/5 * * * * /usr/bin/python3 /home/ubuntu/server-scripts/server-monitor.py >> /home/ubuntu/cron.log 2>&1"

(crontab -u ubuntu -l 2>/dev/null | grep -F "$CRON_JOB") || \
(crontab -u ubuntu -l 2>/dev/null; echo "$CRON_JOB") | crontab -u ubuntu -

# -----------------------------
# 6. FIRST TEST RUN
# -----------------------------
echo "🚀 Running first test manually..."
python3 ~/server-scripts/server-monitor.py

echo "🎉 Installation Complete!"
echo "Logs: /home/ubuntu/cron.log"
echo "Script: /home/ubuntu/server-scripts/server-monitor.py"
