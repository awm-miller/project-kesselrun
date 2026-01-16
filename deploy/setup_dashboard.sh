#!/bin/bash
# Setup script for Kessel Run Dashboard on VPS
# Run as root: sudo ./setup_dashboard.sh

set -e

DOMAIN=${1:-""}
PROJECT_DIR="/root/project-kesselrun"

echo "========================================="
echo "Kessel Run Dashboard Setup"
echo "========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo ./setup_dashboard.sh)"
    exit 1
fi

# Install dependencies
echo ""
echo "Installing system dependencies..."
apt-get update
apt-get install -y nginx certbot python3-certbot-nginx

# Ensure venv has Flask
echo ""
echo "Installing Flask in virtual environment..."
$PROJECT_DIR/venv/bin/pip install flask

# Copy systemd service
echo ""
echo "Setting up systemd service..."
cp $PROJECT_DIR/deploy/kessel-run-dashboard.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable kessel-run-dashboard
systemctl start kessel-run-dashboard

echo "Dashboard service started on port 5000"

# Setup Nginx if domain provided
if [ -n "$DOMAIN" ]; then
    echo ""
    echo "Setting up Nginx for domain: $DOMAIN"
    
    # Create nginx config with actual domain
    sed "s/your-domain.com/$DOMAIN/g" $PROJECT_DIR/deploy/nginx-dashboard.conf > /etc/nginx/sites-available/kessel-run
    
    # Enable site
    ln -sf /etc/nginx/sites-available/kessel-run /etc/nginx/sites-enabled/
    
    # Test and reload nginx
    nginx -t
    systemctl reload nginx
    
    echo ""
    echo "Nginx configured. Setting up SSL..."
    certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN || {
        echo "Certbot failed - you may need to run it manually:"
        echo "  sudo certbot --nginx -d $DOMAIN"
    }
else
    echo ""
    echo "No domain provided. Dashboard is running on http://localhost:5000"
    echo "To add a domain later, run:"
    echo "  sudo ./setup_dashboard.sh yourdomain.com"
fi

echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "Dashboard status:"
systemctl status kessel-run-dashboard --no-pager
echo ""
echo "To check logs:"
echo "  sudo journalctl -u kessel-run-dashboard -f"
echo ""
if [ -n "$DOMAIN" ]; then
    echo "Access your dashboard at: https://$DOMAIN"
else
    echo "Access your dashboard at: http://YOUR_VPS_IP:5000"
fi
echo ""
echo "Default password is set in .env (DASHBOARD_PASSWORD)"
echo "========================================="




