#!/bin/bash
# VPS Setup Script for Kessel Run (Instagram Monitor)
# Run this on your VPS after uploading files

set -e

echo "========================================="
echo "Kessel Run - VPS Setup"
echo "========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Configuration
INSTALL_DIR="/opt/instagram_monitor"
LOG_DIR="/var/log/instagram_monitor"
USER="www-data"  # Change this if you want a different user

echo ""
echo "Step 1: Installing system dependencies..."
apt-get update
apt-get install -y python3.11 python3.11-venv python3-pip git

# Install system dependencies for weasyprint (PDF generation)
apt-get install -y python3-dev libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 libffi-dev shared-mime-info

echo ""
echo "Step 2: Creating directory structure..."
mkdir -p $INSTALL_DIR
mkdir -p $LOG_DIR
mkdir -p $INSTALL_DIR/results
mkdir -p $INSTALL_DIR/temp_downloads
mkdir -p $INSTALL_DIR/templates
mkdir -p $INSTALL_DIR/dashboard/templates
mkdir -p $INSTALL_DIR/dashboard/static

# Set permissions
chown -R $USER:$USER $INSTALL_DIR
chown -R $USER:$USER $LOG_DIR

echo ""
echo "Step 3: Creating Python virtual environment..."
cd $INSTALL_DIR
sudo -u $USER python3.11 -m venv venv
sudo -u $USER venv/bin/pip install --upgrade pip

echo ""
echo "Step 4: Installing Python dependencies..."
if [ -f "$INSTALL_DIR/requirements.txt" ]; then
    sudo -u $USER venv/bin/pip install -r requirements.txt
    echo "Python dependencies installed successfully"
else
    echo "WARNING: requirements.txt not found in $INSTALL_DIR"
    echo "Please upload it and run: sudo -u $USER $INSTALL_DIR/venv/bin/pip install -r $INSTALL_DIR/requirements.txt"
fi

echo ""
echo "Step 5: Setting up environment file..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo "Creating .env template..."
    cat > $INSTALL_DIR/.env.template << 'EOF'
# Instagram Authentication
INSTAGRAM_USERNAME=your_instagram_username
INSTAGRAM_PASSWORD=your_instagram_password

# Gemini API
GEMINI_API_KEY=your_gemini_api_key_here

# Google Drive Configuration
GOOGLE_SERVICE_ACCOUNT_PATH=service_account.json
GOOGLE_DRIVE_ROOT_FOLDER_ID=

# SMTP Email Configuration
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=your_email@gmail.com
SMTP_FROM_NAME=Kessel Run

# Dashboard Configuration
DASHBOARD_PASSWORD=your_secure_password_here
DASHBOARD_PORT=5000
DASHBOARD_SECRET_KEY=change_this_to_a_random_secret_key
EOF
    chown $USER:$USER $INSTALL_DIR/.env.template
    echo "Created .env.template - copy it to .env and fill in your credentials"
    echo "  cp $INSTALL_DIR/.env.template $INSTALL_DIR/.env"
    echo "  nano $INSTALL_DIR/.env"
else
    echo ".env file already exists"
fi

echo ""
echo "Step 6: Setting up cron job..."
CRON_JOB="0 0 * * * cd $INSTALL_DIR && $INSTALL_DIR/venv/bin/python monitor.py >> $LOG_DIR/monitor.log 2>&1"

# Check if cron job already exists
if sudo -u $USER crontab -l 2>/dev/null | grep -q "$INSTALL_DIR.*monitor.py"; then
    echo "Cron job already configured"
else
    # Add cron job
    (sudo -u $USER crontab -l 2>/dev/null; echo "$CRON_JOB") | sudo -u $USER crontab -
    echo "Cron job added: Runs daily at midnight"
fi

echo ""
echo "Step 7: Setting up dashboard service..."
cp $INSTALL_DIR/deploy/kessel-run-dashboard.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable kessel-run-dashboard
echo "Dashboard service installed (start it after configuring .env)"

echo ""
echo "Step 8: Setting up log rotation..."
cat > /etc/logrotate.d/instagram-monitor << EOF
$LOG_DIR/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 $USER $USER
}
EOF

echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Upload your files to $INSTALL_DIR:"
echo "   - All .py files"
echo "   - requirements.txt"
echo "   - accounts.json"
echo "   - subscribers.json"
echo "   - cookies.txt"
echo "   - serviceaccount.json (for Google Drive)"
echo "   - dashboard/ folder (templates and static)"
echo ""
echo "2. Configure environment:"
echo "   sudo nano $INSTALL_DIR/.env"
echo ""
echo "3. Start the dashboard:"
echo "   sudo systemctl start kessel-run-dashboard"
echo "   sudo systemctl status kessel-run-dashboard"
echo ""
echo "4. Test the monitor:"
echo "   sudo -u $USER $INSTALL_DIR/venv/bin/python $INSTALL_DIR/monitor.py --test --max-posts 2"
echo ""
echo "5. Check logs:"
echo "   tail -f $LOG_DIR/monitor.log"
echo "   tail -f $LOG_DIR/dashboard.log"
echo ""
echo "Dashboard URL: http://YOUR_SERVER_IP:5000"
echo "Cron will run monitor automatically daily at midnight."
echo "========================================="

