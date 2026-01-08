# CheckinSignage Setup Guide

This guide covers the complete setup of CheckinSignage on a new Raspberry Pi 5, including all services and AirPlay support.

## Table of Contents

1. [Hardware Requirements](#hardware-requirements)
2. [Operating System Installation](#operating-system-installation)
3. [Initial System Configuration](#initial-system-configuration)
4. [CheckinSignage Installation](#checkinsignage-installation)
5. [Post-Installation Configuration](#post-installation-configuration)
6. [AirPlay Configuration](#airplay-configuration)
7. [Network Configuration](#network-configuration)
8. [Maintenance & Updates](#maintenance--updates)
9. [Troubleshooting](#troubleshooting)

---

## Hardware Requirements

### Recommended Hardware

| Component | Recommendation |
|-----------|----------------|
| **Raspberry Pi** | Pi 5 (8GB recommended) or Pi 4 (4GB+) |
| **Storage** | 32GB+ microSD or NVMe SSD via PCIe HAT |
| **Display** | HDMI display (1080p or 4K) |
| **Power** | Official Pi 5 USB-C power supply (27W) |
| **Network** | Ethernet (recommended) or WiFi |
| **Case** | Passive cooling case recommended |

### Optional Hardware

- **PCIe SSD HAT** - For faster, more reliable storage (see [SSD installation guide](raspberry-pi5-ssd-install-instructions.md))
- **PoE HAT** - For single-cable power and network

---

## Operating System Installation

### Step 1: Download Raspberry Pi Imager

Download from [raspberrypi.com/software](https://www.raspberrypi.com/software/)

### Step 2: Flash the OS

1. Open Raspberry Pi Imager
2. Click **CHOOSE OS** → **Raspberry Pi OS (other)** → **Raspberry Pi OS Lite (64-bit)**
3. Click **CHOOSE STORAGE** → Select your SD card/SSD
4. Click the **⚙️ gear icon** for advanced settings:

   | Setting | Value |
   |---------|-------|
   | Hostname | `checkinsignage` (or your choice) |
   | Enable SSH | ✅ Use password authentication |
   | Username | `admin` |
   | Password | (choose a strong password) |
   | Configure WiFi | (optional - set if no Ethernet) |
   | Locale | Set your timezone |

5. Click **SAVE** then **WRITE**

### Step 3: First Boot

1. Insert SD card into Pi
2. Connect HDMI, Ethernet, and power
3. Wait 2-3 minutes for first boot to complete
4. Find the Pi's IP address:
   - Check your router's DHCP leases
   - Or connect a monitor and keyboard to see the IP

### Step 4: Connect via SSH

```bash
ssh admin@<pi-ip-address>
```

---

## Initial System Configuration

### Step 1: Update the System

```bash
sudo apt update && sudo apt full-upgrade -y
```

### Step 2: Configure Boot Settings

```bash
sudo raspi-config
```

Navigate to:
- **1 System Options** → **S5 Boot / Auto Login** → **B2 Console Autologin**
- **6 Advanced Options** → **A1 Expand Filesystem**
- **6 Advanced Options** → **A2 GL Driver** → **G2 GL (Fake KMS)**

Then select **Finish** and reboot when prompted.

### Step 3: Install Required Dependencies

```bash
sudo apt install -y \
    git \
    avahi-daemon \
    avahi-utils
```

### Step 4: Verify Avahi (for AirPlay)

```bash
sudo systemctl enable avahi-daemon
sudo systemctl start avahi-daemon
sudo systemctl status avahi-daemon
```

---

## CheckinSignage Installation

### Option A: Standard Installation (Recommended)

Run the Anthias installer:

```bash
bash <(curl -sL https://install-anthias.srly.io)
```

Follow the prompts:
- **Continue?** → Yes
- **Manage network?** → No (unless you want WiFi management)
- **Version?** → Latest stable
- **Full upgrade?** → Yes

⏱️ Installation takes 30-60 minutes depending on your connection.

### Option B: Manual Installation from Git

For development or custom setups:

```bash
cd /home/admin
git clone https://github.com/storbukas/CheckinSignage.git
cd CheckinSignage

# Install Docker if not present
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker admin

# Log out and back in, then:
cd /home/admin/CheckinSignage
./bin/upgrade_containers.sh
```

### Verify Installation

After reboot, check all containers are running:

```bash
docker ps
```

You should see:
- `checkinsignage-checkin-server-1`
- `checkinsignage-checkin-viewer-1`
- `checkinsignage-checkin-nginx-1`
- `checkinsignage-checkin-celery-1`
- `checkinsignage-checkin-websocket-1`
- `checkinsignage-checkin-airplay-1`
- `checkinsignage-redis-1`

---

## Post-Installation Configuration

### Access the Web Interface

Open a browser and navigate to:
```
http://<pi-ip-address>
```

Default credentials (if prompted):
- **Username:** (none by default)
- **Password:** (none by default)

### Initial Settings

1. **General Settings:**
   - Set display name
   - Configure timezone
   - Set default asset duration

2. **Network Settings:**
   - Verify IP address
   - Configure static IP if needed (via router or `raspi-config`)

3. **Display Settings:**
   - Screen orientation
   - Resolution (auto-detected)

### Add Your First Asset

1. Click **Add Asset** in the web interface
2. Choose asset type (Image, Video, Web Page, etc.)
3. Upload or enter URL
4. Set schedule and duration
5. Click **Save**

---

## AirPlay Configuration

AirPlay is enabled by default. See [AIRPLAY.md](AIRPLAY.md) for detailed configuration.

### Quick Setup

1. Access **Settings → AirPlay** in the web interface
2. Configure:
   | Setting | Recommended Value |
   |---------|-------------------|
   | Enabled | ✅ On |
   | Device Name | `Meeting Room Display` (or your choice) |
   | Framerate | 30 fps |

3. Click **Save**

### Verify AirPlay

```bash
# Check container is running
docker ps | grep airplay

# Check logs
docker logs checkinsignage-checkin-airplay-1 --tail 20
```

### Test AirPlay

1. On your iPhone/iPad/Mac, open Control Center
2. Tap **Screen Mirroring**
3. Select your display name
4. Your screen should appear on the display

---

## Network Configuration

### Required Ports

Ensure these ports are accessible on your network:

| Port | Protocol | Service |
|------|----------|---------|
| 80 | TCP | Web interface |
| 443 | TCP | HTTPS (if enabled) |
| 5353 | UDP | mDNS/Bonjour (AirPlay discovery) |
| 7000 | TCP | AirPlay |
| 7100 | TCP | AirPlay |
| 47000 | UDP | AirPlay video |
| 6000-6001 | UDP | AirPlay audio |

### Static IP Configuration

For production deployments, configure a static IP via your router's DHCP reservation, or edit:

```bash
sudo nano /etc/dhcpcd.conf
```

Add at the end:
```
interface eth0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 8.8.8.8
```

Then reboot.

### Firewall (if enabled)

If using `ufw`:

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 5353/udp
sudo ufw allow 7000/tcp
sudo ufw allow 7100/tcp
sudo ufw allow 47000/udp
sudo ufw allow 6000:6001/udp
```

---

## Maintenance & Updates

### Update CheckinSignage

```bash
cd /home/admin/CheckinSignage
git pull origin master
./bin/upgrade_containers.sh
```

### Update System Packages

```bash
sudo apt update && sudo apt upgrade -y
```

### View Container Logs

```bash
# All containers
docker compose logs -f

# Specific container
docker logs -f checkinsignage-checkin-server-1
docker logs -f checkinsignage-checkin-airplay-1
```

### Restart All Services

```bash
cd /home/admin/CheckinSignage
docker compose restart
```

### Restart Individual Services

```bash
docker restart checkinsignage-checkin-airplay-1
docker restart checkinsignage-checkin-server-1
docker restart checkinsignage-checkin-viewer-1
```

### Backup Configuration

```bash
# Backup settings
cp -r ~/.screenly ~/screenly-backup-$(date +%Y%m%d)

# Backup assets
cp -r ~/screenly_assets ~/assets-backup-$(date +%Y%m%d)
```

---

## Troubleshooting

### Black Screen on Boot

1. Press `Ctrl+Alt+F1` to access console
2. Or SSH in from another machine
3. Run:
   ```bash
   cd /home/admin/CheckinSignage
   ./bin/upgrade_containers.sh
   ```

### Container Not Starting

```bash
# Check status
docker ps -a

# View logs for failed container
docker logs checkinsignage-<container-name>

# Restart all containers
docker compose down
docker compose up -d
```

### AirPlay Not Appearing

1. **Check container:**
   ```bash
   docker ps | grep airplay
   docker logs checkinsignage-checkin-airplay-1
   ```

2. **Check Avahi:**
   ```bash
   sudo systemctl status avahi-daemon
   avahi-browse -a  # List all mDNS services
   ```

3. **Check network:**
   - Ensure Pi and Apple device are on same network
   - Check mDNS is not blocked by network

### Display Issues

1. **Force HDMI output:**
   ```bash
   sudo nano /boot/firmware/config.txt
   ```
   Add:
   ```
   hdmi_force_hotplug=1
   hdmi_group=1
   hdmi_mode=16  # 1080p60
   ```

2. **Check DRM/KMS:**
   ```bash
   cat /sys/class/drm/card*/modes
   ```

### Web Interface Not Loading

1. **Check nginx:**
   ```bash
   docker logs checkinsignage-checkin-nginx-1
   ```

2. **Check server:**
   ```bash
   docker logs checkinsignage-checkin-server-1
   ```

3. **Restart services:**
   ```bash
   docker compose restart
   ```

### Redis Connection Issues

```bash
# Check Redis is running
docker exec checkinsignage-redis-1 redis-cli ping
# Should return: PONG

# Check Redis logs
docker logs checkinsignage-redis-1
```

---

## Quick Reference Commands

| Task | Command |
|------|---------|
| SSH into Pi | `ssh admin@<ip>` |
| View all containers | `docker ps` |
| View container logs | `docker logs -f <container>` |
| Restart containers | `docker compose restart` |
| Update CheckinSignage | `git pull && ./bin/upgrade_containers.sh` |
| Check AirPlay status | `curl http://localhost/api/v2/airplay` |
| Restart AirPlay | `docker restart checkinsignage-checkin-airplay-1` |
| System reboot | `sudo reboot` |

---

## Related Documentation

- [AirPlay Setup](AIRPLAY.md)
- [Developer Documentation](developer-documentation.md)
- [SSD Installation](raspberry-pi5-ssd-install-instructions.md)
- [Installation Options](installation-options.md)
- [WiFi Setup](wifi-setup.md)
