#!/bin/bash

echo "========================================"
echo "   Dr.Health-Care Server Setup Script    "
echo "========================================"

# ----- CONFIG -----
REPO_URL="https://github.com/Shivamgarud8/Dr.Health-Care.git"
BASE_DIR="/home/ubuntu/server-scripts"
PROJECT_DIR="$BASE_DIR/health-monitor"
VENV_DIR="$BASE_DIR/health-env"
LOG_FILE="/var/log/server_health_sns.log"

# CHANGE THESE ARNs BEFORE RUNNING!
HOURLY_ARN="arn:aws:sns:eu-north-1:XXXXXXXXXXXX:HourlyHealth"
ALERT_ARN="arn:aws:sns:eu-north-1:XXXXXXXXXXXX:InstantAlerts"

# ----- START -----
echo "[1/10] Updating system..."
sudo apt update -y
sudo apt install -y python3 python3-venv git

echo "[2/10] Creating directories..."
mkdir -p "$BASE_DIR"
cd "$BASE_DIR"

echo "[3/10] Cloning GitHub repo..."
rm -rf Dr.Health-Care health-monitor
git clone "$REPO_URL"
mv Dr.Health-Care health-monitor
cd health-monitor

echo "[4/10] Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"

echo "[5/10] Installing Python dependencies..."
source "$VENV_DIR/bin/activate"
pip install boto3 psutil
deactivate

echo "[6/10] Setting SNS Topic ARNs..."
echo "export HOURLY_TOPIC_ARN=\"$HOURLY_ARN\"" >> ~/.bashrc
echo "export ALERT_TOPIC_ARN=\"$ALERT_ARN\"" >> ~/.bashrc
source ~/.bashrc

echo "[7/10] Making script executable..."
chmod +x server_health_sns.py

echo "[8/10] Creating log file..."
sudo touch "$LOG_FILE"
sudo chmod 666 "$LOG_FILE"

echo "[9/10] Adding CRON job (every 5 min)..."
CRON_JOB="*/5 * * * * $VENV_DIR/bin/python $PROJECT_DIR/server_health_sns.py >> $LOG_FILE 2>&1"

# Remove old cron job to avoid duplicates
crontab -l | grep -v "server_health_sns.py" > /tmp/newcron
echo "$CRON_JOB" >> /tmp/newcron
crontab /tmp/newcron
rm /tmp/newcron

echo "[10/10] Running first test..."
$VENV_DIR/bin/python $PROJECT_DIR/server_health_sns.py

echo "========================================"
echo " INSTALLATION COMPLETE!"
echo " SNS health monitor is running every 5 min."
echo " Logs: $LOG_FILE"
echo "========================================"
