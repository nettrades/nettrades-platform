#!/bin/sh
set -e

# Install htpasswd if not present (Prometheus image is Alpine-based)
if ! command -v htpasswd >/dev/null 2>&1; then
    echo "Installing apache2-utils for htpasswd..."
    apk add --no-cache apache2-utils
fi

# Generate bcrypt hash from environment variable
if [ -n "$PROMETHEUS_PASSWORD" ]; then
    HASH=$(htpasswd -bnB admin "$PROMETHEUS_PASSWORD" | cut -d: -f2)
    cat > /etc/prometheus/web.yml <<EOF
basic_auth_users:
    admin: '$HASH'
EOF
    echo "✅ Prometheus basic auth configured for user 'admin'"
else
    echo "⚠️  PROMETHEUS_PASSWORD not set – starting without basic auth"
    echo "{}" > /etc/prometheus/web.yml
fi

# Execute the original Prometheus binary
exec /bin/prometheus "$@"