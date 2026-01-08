# AirPlay Support for Checkin Signage

Checkin Signage includes AirPlay support via [uxplay](https://github.com/FDH2/UxPlay), allowing you to mirror your iOS/macOS device screen directly to the signage display.

## Overview

AirPlay runs natively on the Raspberry Pi host (not in Docker) for optimal performance. This avoids Docker overhead and enables direct hardware video overlay via KMS/DRM.

## Prerequisites

- Raspberry Pi 5 (recommended) or Pi 4
- Raspberry Pi OS Lite (64-bit)
- Network with mDNS/Bonjour support (most home/office networks)

## Installation

### 1. Install Dependencies

```bash
sudo apt update
sudo apt install -y \
    cmake \
    libavahi-compat-libdnssd-dev \
    libplist-dev \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-libav \
    gstreamer1.0-alsa \
    libdrm-dev \
    python3-redis
```

### 2. Build uxplay

```bash
cd /tmp
git clone https://github.com/CheckinCast/uxplay.git
cd uxplay
mkdir build && cd build
cmake ..
make -j$(nproc)
sudo make install
```

### 3. Install the Service

Copy the systemd service file:

```bash
sudo cp /home/admin/CheckinSignage/bin/checkin-airplay.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable checkin-airplay
sudo systemctl start checkin-airplay
```

> **Note:** The service file assumes the username is `admin` and the install path is `/home/admin/CheckinSignage`. Edit the service file if your setup differs.

### 4. Verify Installation

Check that the service is running:

```bash
sudo systemctl status checkin-airplay
```

Your device should now appear as "Checkin Cast" (or your configured name) when looking for AirPlay devices on your iOS/macOS device.

## Configuration

AirPlay settings can be configured through the Checkin Signage web interface under **Settings > AirPlay**, or via the API.

### Available Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Device Name | `Checkin Cast` | The name shown on AirPlay device discovery |
| Resolution | `1920x1080` | Output resolution (presets: 720p, 1080p, 1440p, 4k) |
| Framerate | `30` | Target framerate (24, 30, or 60 fps) |

### Resolution Presets

- `720p` = 1280x720
- `1080p` = 1920x1080
- `1440p` = 2560x1440
- `4k` = 3840x2160

You can also specify custom resolutions like `2560x1440`.

### API Configuration

```bash
# Get current settings
curl http://localhost/api/v2/airplay

# Update settings
curl -X PATCH http://localhost/api/v2/airplay \
    -H "Content-Type: application/json" \
    -d '{"name": "My Display", "resolution": "4k", "framerate": 24}'
```

Settings are saved to the configuration file and applied immediately (the AirPlay server restarts automatically).

## Testing Different Settings

Use the included test script to experiment with different resolution/framerate combinations:

```bash
# Default: 1080p @ 30fps
./bin/airplay_test.sh

# 4K @ 30fps
./bin/airplay_test.sh 4k

# 4K @ 24fps (good for movies)
./bin/airplay_test.sh 4k 24

# 1080p @ 60fps (smooth motion)
./bin/airplay_test.sh 1080p 60

# Custom resolution
./bin/airplay_test.sh 2560x1440 30
```

The test script stops the systemd service, runs uxplay interactively so you can see the output, and can be stopped with Ctrl+C. After testing, restart the service:

```bash
sudo systemctl start checkin-airplay
```

## Performance Tuning

### For 4K Content

When using 4K resolution:
- Use 24fps for movies/video content
- Use 30fps for general mirroring
- 60fps at 4K may cause dropped frames on Pi 5

### Hardware Overlay

The native AirPlay implementation uses `kmssink` for direct hardware video overlay. This means:
- Video is rendered directly by the GPU
- No CPU-based compositing
- AirPlay video overlays on top of the Checkin Signage viewer

### Audio Output

Audio is routed to HDMI by default using ALSA:
- `hw:0` = First HDMI output
- `hw:1` = Second HDMI output (on dual-HDMI boards)

## Troubleshooting

### Device Not Appearing

1. Check that Avahi is running:
   ```bash
   sudo systemctl status avahi-daemon
   ```

2. Verify the service is running:
   ```bash
   sudo systemctl status checkin-airplay
   journalctl -u checkin-airplay -f
   ```

3. Ensure your network allows mDNS (UDP port 5353)

### Video Not Showing

If AirPlay connects but video doesn't appear:

1. Check that kmssink is available:
   ```bash
   gst-inspect-1.0 kmssink
   ```

2. Verify no other process is using the DRM device:
   ```bash
   sudo fuser /dev/dri/card*
   ```

### Audio Issues

If audio isn't working:

1. List available ALSA devices:
   ```bash
   aplay -l
   ```

2. Test audio output:
   ```bash
   speaker-test -c 2 -D hw:0
   ```

### Service Logs

View real-time logs:
```bash
journalctl -u checkin-airplay -f
```

View recent logs:
```bash
journalctl -u checkin-airplay --since "5 minutes ago"
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Raspberry Pi Host                        │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐ │
│  │   uxplay    │◄───│    Redis    │◄───│  Checkin API    │ │
│  │  (native)   │    │  (settings) │    │   (Docker)      │ │
│  └──────┬──────┘    └─────────────┘    └─────────────────┘ │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              KMS/DRM Hardware Video Overlay             ││
│  │                  (GPU-accelerated)                       ││
│  └─────────────────────────────────────────────────────────┘│
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    HDMI Output                           ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

The AirPlay server:
1. Reads settings from Redis (updated by the web UI/API)
2. Advertises itself via Avahi/mDNS
3. Receives AirPlay video stream
4. Renders directly to hardware overlay via kmssink
5. Outputs audio via ALSA to HDMI
