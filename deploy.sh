#!/bin/bash
# =============================================================
# PSX Trading Bot - Linux Deployment Script
# =============================================================
# Usage: chmod +x deploy.sh && sudo ./deploy.sh
# =============================================================

set -e

APP_NAME="psx-trading-bot"
APP_DIR="/opt/$APP_NAME"
APP_USER="psx-bot"
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="psx-trading-bot"

echo "========================================"
echo "  PSX Trading Bot - Deployment Script"
echo "========================================"

# --- 1. System Dependencies ---
echo "[1/7] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv nginx certbot python3-certbot-nginx

# --- 2. Create App User ---
echo "[2/7] Creating application user..."
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -m -s /bin/bash "$APP_USER"
    echo "  User '$APP_USER' created."
else
    echo "  User '$APP_USER' already exists."
fi

# --- 3. Copy Application ---
echo "[3/7] Setting up application directory..."
mkdir -p "$APP_DIR"
cp -r ./* "$APP_DIR/"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# --- 4. Virtual Environment ---
echo "[4/7] Creating Python virtual environment..."
su - "$APP_USER" -c "python3 -m venv $VENV_DIR"
su - "$APP_USER" -c "$VENV_DIR/bin/pip install --upgrade pip"
su - "$APP_USER" -c "$VENV_DIR/bin/pip install -r $APP_DIR/requirements.txt"

# --- 5. Environment File ---
echo "[5/7] Setting up environment..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/change_me_to_a_random_64_char_string/$JWT_SECRET/" "$APP_DIR/.env"
    echo "  .env created. IMPORTANT: Edit $APP_DIR/.env with your credentials!"
else
    echo "  .env already exists, skipping."
fi
chmod 600 "$APP_DIR/.env"

# --- 6. Systemd Service ---
echo "[6/7] Creating systemd service..."
cat > /etc/systemd/system/$SERVICE_NAME.service << EOF
[Unit]
Description=PSX Trading Bot
After=network.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=10

# Security
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_DIR/data_cache

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable $SERVICE_NAME

# --- 7. Nginx Reverse Proxy ---
echo "[7/7] Configuring Nginx..."
cat > /etc/nginx/sites-available/$APP_NAME << 'NGINX_EOF'
server {
    listen 80;
    server_name _;  # Replace with your domain or server IP

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Rate limiting for login
    limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /login {
        limit_req zone=login burst=3 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
NGINX_EOF

ln -sf /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# --- Start ---
systemctl start $SERVICE_NAME

echo ""
echo "========================================"
echo "  DEPLOYMENT COMPLETE!"
echo "========================================"
echo ""
echo "  App URL:     http://$(hostname -I | awk '{print $1}')"
echo "  Config:      $APP_DIR/.env"
echo "  Logs:        journalctl -u $SERVICE_NAME -f"
echo "  Status:      systemctl status $SERVICE_NAME"
echo "  Restart:     systemctl restart $SERVICE_NAME"
echo ""
echo "  NEXT STEPS:"
echo "  1. Edit $APP_DIR/.env with your credentials"
echo "  2. Restart: systemctl restart $SERVICE_NAME"
echo "  3. For HTTPS: certbot --nginx -d your-domain.com"
echo ""
echo "========================================"
