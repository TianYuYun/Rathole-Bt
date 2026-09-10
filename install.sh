#!/bin/bash
set -u

PLUGIN_DIR="/www/server/panel/plugin/rathole_manager"
CONFIG_DIR="/etc/rathole"
STATE_DIR="/var/lib/rathole-manager"
CONFIG_FILE="$CONFIG_DIR/rathole.toml"
READY_FILE="$STATE_DIR/configured"
SERVICE_FILE="/etc/systemd/system/rathole.service"

install_plugin() {
    mkdir -p "$CONFIG_DIR" "$STATE_DIR"

    if ! id rathole >/dev/null 2>&1; then
        useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin rathole >/dev/null 2>&1 || true
    fi

    chown root:rathole "$CONFIG_DIR" 2>/dev/null || true
    chmod 750 "$CONFIG_DIR"
    chmod 700 "$STATE_DIR"

    if [ ! -f "$CONFIG_FILE" ]; then
        cat > "$CONFIG_FILE" <<'CFG'
# Rathole Manager configuration placeholder.
# Save a valid Server or Client configuration in the BT panel before starting.
CFG
    fi
    chown root:rathole "$CONFIG_FILE" 2>/dev/null || true
    chmod 640 "$CONFIG_FILE"

    # Upgrade compatibility: mark an existing V1 configuration as ready only if it
    # already contains a real [server] or [client] section. Otherwise stop the old
    # restart loop and wait for the user to save a valid configuration.
    if grep -Eq '^\[(server|client)\][[:space:]]*$' "$CONFIG_FILE" 2>/dev/null; then
        touch "$READY_FILE"
        chmod 600 "$READY_FILE"
    else
        rm -f "$READY_FILE"
        systemctl stop rathole >/dev/null 2>&1 || true
    fi

    cat > "$SERVICE_FILE" <<'UNIT'
[Unit]
Description=Rathole reverse proxy tunnel
After=network-online.target
Wants=network-online.target
ConditionPathExists=/var/lib/rathole-manager/configured

[Service]
Type=simple
User=rathole
Group=rathole
ExecStart=/usr/local/bin/rathole /etc/rathole/rathole.toml
Restart=on-failure
RestartSec=3
Environment=RUST_LOG=info
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadOnlyPaths=/etc/rathole
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
UNIT

    systemctl daemon-reload >/dev/null 2>&1 || true
    systemctl enable rathole >/dev/null 2>&1 || true

    chmod 755 "$PLUGIN_DIR" 2>/dev/null || true
    chmod 755 "$PLUGIN_DIR"/*.py "$PLUGIN_DIR"/install.sh 2>/dev/null || true
    echo "Rathole Manager 2.2 installed. Save a valid configuration before starting Rathole."
}

uninstall_plugin() {
    systemctl disable --now rathole >/dev/null 2>&1 || true
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload >/dev/null 2>&1 || true
    echo "Rathole Manager plugin and systemd unit removed."
    echo "Rathole binary and /etc/rathole are preserved to avoid accidental data loss."
}

case "${1:-}" in
    install) install_plugin ;;
    uninstall) uninstall_plugin ;;
    *) echo "Usage: $0 {install|uninstall}"; exit 1 ;;
esac
