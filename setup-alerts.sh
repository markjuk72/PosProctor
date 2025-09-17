#!/bin/bash

# Verifone Commander Alert Setup Script
# This script configures email alerts for your deployment

echo "🚨 Verifone Commander Alert Setup"
echo "=================================="

# Get email address from user or environment
if [ -z "$ALERT_EMAIL" ]; then
    read -p "Enter email address for alerts: " ALERT_EMAIL
fi

if [ -z "$ALERT_EMAIL" ]; then
    echo "❌ No email address provided. Exiting."
    exit 1
fi

echo "📧 Configuring alerts for: $ALERT_EMAIL"

# Update contact points file
sed -i "s/addresses: .*/addresses: $ALERT_EMAIL/" grafana-provisioning/alerting/contactpoints.yaml

echo "✅ Updated contact points configuration"

# Restart Grafana to apply changes
echo "🔄 Restarting Grafana..."
docker-compose restart grafana

echo "✅ Email alerts configured successfully!"
echo ""
echo "📋 Next steps:"
echo "1. Configure SMTP settings in docker-compose.yml or .env file"
echo "2. Update environment variables:"
echo "   - SMTP_HOST (e.g., smtp.gmail.com:587)"
echo "   - SMTP_USER (your email)"  
echo "   - SMTP_PASSWORD (your app password)"
echo "   - SMTP_FROM (sender email)"
echo "3. Restart the stack: docker-compose restart grafana"
echo ""
echo "🎯 Test your alerts by simulating a failure or wait for real issues!"