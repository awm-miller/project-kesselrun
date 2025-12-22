#!/bin/bash
# Deploy Instagram Monitor to VPS
# Usage: ./deploy.sh user@your-vps-ip

set -e

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 user@your-vps-ip"
    echo "Example: $0 root@192.168.1.100"
    exit 1
fi

VPS_HOST=$1
REMOTE_DIR="/opt/instagram_monitor"

echo "========================================="
echo "Deploying Instagram Monitor to VPS"
echo "Target: $VPS_HOST:$REMOTE_DIR"
echo "========================================="

# Check if SSH connection works
echo ""
echo "Testing SSH connection..."
ssh $VPS_HOST "echo 'SSH connection successful'"

# Create remote directory
echo ""
echo "Creating remote directory..."
ssh $VPS_HOST "sudo mkdir -p $REMOTE_DIR && sudo chown $USER:$USER $REMOTE_DIR"

# Upload Python files
echo ""
echo "Uploading Python files..."
rsync -avz --progress \
    --include='*.py' \
    --include='*.json' \
    --include='*.txt' \
    --exclude='*.pyc' \
    --exclude='__pycache__/' \
    --exclude='.git/' \
    --exclude='temp_downloads/' \
    --exclude='results/' \
    --exclude='state.json' \
    --exclude='temp_report_*' \
    ../*.py \
    ../*.json \
    ../*.txt \
    $VPS_HOST:$REMOTE_DIR/

# Upload templates directory if it exists
if [ -d "../templates" ]; then
    echo ""
    echo "Uploading templates..."
    ssh $VPS_HOST "mkdir -p $REMOTE_DIR/templates"
    rsync -avz --progress ../templates/ $VPS_HOST:$REMOTE_DIR/templates/
fi

# Upload requirements.txt
echo ""
echo "Uploading requirements.txt..."
rsync -avz --progress ../requirements.txt $VPS_HOST:$REMOTE_DIR/

# Upload setup script
echo ""
echo "Uploading setup script..."
rsync -avz --progress ./setup_vps.sh $VPS_HOST:$REMOTE_DIR/
ssh $VPS_HOST "chmod +x $REMOTE_DIR/setup_vps.sh"

echo ""
echo "========================================="
echo "Upload Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. SSH into your VPS:"
echo "   ssh $VPS_HOST"
echo ""
echo "2. Run the setup script:"
echo "   sudo $REMOTE_DIR/setup_vps.sh"
echo ""
echo "3. Upload sensitive files manually (DO NOT commit these to git):"
echo "   scp .env $VPS_HOST:$REMOTE_DIR/"
echo "   scp service_account.json $VPS_HOST:$REMOTE_DIR/"
echo "   scp cookies.txt $VPS_HOST:$REMOTE_DIR/  # optional"
echo ""
echo "4. Configure accounts.json and subscribers.json on the VPS:"
echo "   ssh $VPS_HOST 'nano $REMOTE_DIR/accounts.json'"
echo "   ssh $VPS_HOST 'nano $REMOTE_DIR/subscribers.json'"
echo ""
echo "5. Test the installation:"
echo "   ssh $VPS_HOST 'sudo -u www-data $REMOTE_DIR/venv/bin/python $REMOTE_DIR/monitor.py --test --max-posts 2'"
echo ""
echo "========================================="

