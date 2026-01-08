# AirPlay Support for Checkin Signage

Checkin Signage includes AirPlay support via [UxPlay](https://github.com/FDH2/UxPlay) (using a [custom fork](https://github.com/storbukas/CheckinCast)), allowing you to mirror your iOS/macOS device screen directly to the signage display.

## Overview

AirPlay runs inside a Docker container (`checkin-airplay`) with privileged access to the display hardware. The container uses `kmssink` for direct KMS/DRM video output and ALSA for audio.

**Key Features:**
- **Dynamic Resolution** - The client device decides the resolution (no fixed server-side resolution)
- **Fullscreen Mode** - Video automatically fills the entire display
- **Enable/Disable Toggle** - AirPlay can be toggled on/off via the web UI or API
- **Auto-restart** - Settings changes automatically restart the AirPlay server

## Prerequisites

- Raspberry Pi 5 (recommended) or Pi 4
- CheckinSignage installed via Docker Compose
- Network with mDNS/Bonjour support (most home/office networks)

## How It Works

The AirPlay functionality is provided by the `checkin-airplay` Docker container, which:

1. Runs [UxPlay](https://github.com/storbukas/CheckinCast) with optimized settings
2. Reads configuration from Redis (device name, framerate)
3. Listens for commands via Redis pub/sub (start, stop, restart)
4. Publishes session state via ZMQ for the web UI

### Docker Container Configuration

The container is defined in `docker-compose.yml.tmpl`:

```yaml
checkin-airplay:
  image: checkinsignage/airplay:${DOCKER_TAG}-${DEVICE_TYPE}
  environment:
    - AIRPLAY_NAME=${AIRPLAY_NAME:-Checkin Cast}
    - AIRPLAY_FRAMERATE=30
    - AUDIO_OUTPUT=${AUDIO_OUTPUT:-hdmi}
  network_mode: host
  privileged: true
```

**Important:** The container runs in `privileged` mode with `network_mode: host` to access:
- `/dev/dri/*` - DRM/KMS display devices
- mDNS (Avahi) for device discovery
- ALSA audio devices

## Configuration

AirPlay settings can be configured through the Checkin Signage web interface under **Settings > AirPlay**, or via the API.

### Available Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Enabled | `true` | Enable/disable AirPlay receiver |
| Device Name | `Checkin Cast` | The name shown on AirPlay device discovery |
| Framerate | `30` | Target framerate (24, 30, or 60 fps) |

> **Note:** Resolution is now dynamic - the client device (iPhone/iPad/Mac) determines the streaming resolution. The server no longer enforces a fixed resolution.

### API Endpoints

**Get AirPlay status:**
```bash
curl http://<pi-ip>/api/v2/airplay
```

Response:
```json
{
  "enabled": true,
  "name": "Checkin Cast",
  "resolution": "dynamic",
  "framerate": 30,
  "state": "idle",
  "client_name": null
}
```

**Update settings:**
```bash
curl -X PATCH http://<pi-ip>/api/v2/airplay \
    -H "Content-Type: application/json" \
    -d '{"name": "Meeting Room Display", "framerate": 30}'
```

**Enable/Disable AirPlay:**
```bash
# Disable
curl -X PATCH http://<pi-ip>/api/v2/airplay \
    -H "Content-Type: application/json" \
    -d '{"enabled": false}'

# Enable
curl -X PATCH http://<pi-ip>/api/v2/airplay \
    -H "Content-Type: application/json" \
    -d '{"enabled": true}'
```

## UxPlay Command Reference

The AirPlay server uses the following UxPlay command:

```bash
uxplay -n "Device Name" -nh -fps 30 -vs kmssink -fs -reset 0 -as alsasink device=hw:0
```

| Option | Description |
|--------|-------------|
| `-n` | Device name shown in AirPlay discovery |
| `-nh` | Don't append hostname to device name |
| `-fps 30` | Target framerate |
| `-vs kmssink` | Video sink (KMS for direct display output) |
| `-fs` | Fullscreen mode |
| `-reset 0` | Never timeout (stay running after disconnect) |
| `-as alsasink device=hw:0` | Audio via ALSA to first HDMI output |

## Performance Recommendations

### Framerate Selection

| Use Case | Recommended FPS |
|----------|-----------------|
| Movies/Video content | 24 fps |
| General mirroring | 30 fps |
| Fast-moving content | 60 fps (may drop frames on Pi 5) |

### Audio Output

Audio is routed to HDMI by default using ALSA:
- `hw:0` = First HDMI output (default)
- `hw:1` = Second HDMI output (on dual-HDMI boards)

## Troubleshooting

### Device Not Appearing in AirPlay List

1. **Check container is running:**
   ```bash
   docker ps | grep airplay
   ```

2. **Check container logs:**
   ```bash
   docker logs checkinsignage-checkin-airplay-1 --tail 50
   ```

3. **Verify Avahi is running on host:**
   ```bash
   sudo systemctl status avahi-daemon
   ```

4. **Check network allows mDNS:**
   - UDP port 5353 must be open
   - Client and Pi must be on same network/VLAN

### Video Not Showing

1. **Check kmssink is available in container:**
   ```bash
   docker exec checkinsignage-checkin-airplay-1 gst-inspect-1.0 kmssink
   ```

2. **Check DRM device access:**
   ```bash
   docker exec checkinsignage-checkin-airplay-1 ls -la /dev/dri/
   ```

3. **View real-time logs during connection:**
   ```bash
   docker logs -f checkinsignage-checkin-airplay-1
   ```

### Audio Issues

1. **List ALSA devices in container:**
   ```bash
   docker exec checkinsignage-checkin-airplay-1 aplay -l
   ```

2. **Test audio output:**
   ```bash
   docker exec checkinsignage-checkin-airplay-1 speaker-test -c 2 -D hw:0
   ```

### Restart AirPlay Container

```bash
docker restart checkinsignage-checkin-airplay-1
```

Or via API:
```bash
curl -X PATCH http://<pi-ip>/api/v2/airplay \
    -H "Content-Type: application/json" \
    -d '{"enabled": false}'
# Wait a moment
curl -X PATCH http://<pi-ip>/api/v2/airplay \
    -H "Content-Type: application/json" \
    -d '{"enabled": true}'
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Raspberry Pi Host                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    Docker Containers                         ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  ││
│  │  │  airplay    │◄─│    Redis    │◄─│   checkin-server    │  ││
│  │  │  (uxplay)   │  │  (settings) │  │   (API + Web UI)    │  ││
│  │  └──────┬──────┘  └─────────────┘  └─────────────────────┘  ││
│  └─────────│───────────────────────────────────────────────────┘│
│            │ privileged                                          │
│            ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              KMS/DRM Hardware Video Overlay                  ││
│  │        /dev/dri/card0 (GPU-accelerated fullscreen)          ││
│  └─────────────────────────────────────────────────────────────┘│
│            │                                                     │
│            ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │           HDMI Output (Video + Audio via ALSA)              ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

**Data Flow:**
1. User updates settings via Web UI → API writes to Redis + config file
2. API publishes `restart` command to Redis `airplay_cmd` channel
3. AirPlay container receives command, reloads settings, restarts UxPlay
4. UxPlay advertises via Avahi/mDNS
5. iOS/Mac connects, streams video
6. UxPlay renders via `kmssink` directly to display
7. Session state published via ZMQ to update Web UI
