#!/bin/bash
# AirPlay Test Script - Easily test different resolution/framerate settings
#
# Usage:
#   ./airplay_test.sh                    # Use defaults (1080p @ 30fps)
#   ./airplay_test.sh 4k                 # 4K @ 30fps
#   ./airplay_test.sh 4k 24              # 4K @ 24fps
#   ./airplay_test.sh 1080p 60           # 1080p @ 60fps
#   ./airplay_test.sh 3840x2160 24       # Custom resolution @ 24fps
#
# Presets: 720p, 1080p, 1440p, 4k
# Or specify custom resolution as WIDTHxHEIGHT (e.g., 2560x1440)

set -e

# Default settings
NAME="${AIRPLAY_NAME:-Checkin Cast}"
RESOLUTION="${1:-1080p}"
FRAMERATE="${2:-30}"
AUDIO_DEVICE="${AUDIO_DEVICE:-hw:0}"

# Resolution presets
declare -A PRESETS=(
    ["720p"]="1280x720"
    ["1080p"]="1920x1080"
    ["1440p"]="2560x1440"
    ["4k"]="3840x2160"
    ["2k"]="2560x1440"
)

# Convert preset to resolution if applicable
if [[ -n "${PRESETS[$RESOLUTION]}" ]]; then
    RESOLUTION="${PRESETS[$RESOLUTION]}"
fi

echo "=== AirPlay Test ==="
echo "Name:       $NAME"
echo "Resolution: $RESOLUTION"
echo "Framerate:  ${FRAMERATE}fps"
echo "Audio:      $AUDIO_DEVICE"
echo "===================="
echo ""
echo "Starting uxplay... (Press Ctrl+C to stop)"
echo ""

# Stop existing airplay service
sudo systemctl stop checkin-airplay 2>/dev/null || true
pkill -f uxplay 2>/dev/null || true
sleep 1

# Run uxplay with specified settings
/usr/local/bin/uxplay \
    -n "$NAME" \
    -nh \
    -s "$RESOLUTION" \
    -fps "$FRAMERATE" \
    -vs kmssink \
    -as "alsasink device=$AUDIO_DEVICE"

# Note: When you exit, restart the service with:
# sudo systemctl start checkin-airplay
