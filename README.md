# SSD1306 OLED Display via CP2112 on Ubuntu 24.04

## Hardware

- SSD1306 128x64 OLED display (I2C address 0x3C)
- Silicon Labs CP2112 USB-to-I2C/SMBus bridge

---

## System Packages

```bash
sudo apt install python3 python3-pip python3-venv libhidapi-hidraw0 i2c-tools fonts-terminus fonts-unifont
```

Add your user to the required groups:

```bash
sudo usermod -aG i2c,plugdev $USER
```

Add a udev rule so the CP2112 hidraw device is accessible without sudo:

```bash
sudo tee /etc/udev/rules.d/99-cp2112.rules <<'EOF'
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea90", MODE="0660", GROUP="plugdev"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Log out and back in for group membership to take effect.

---

## Python Virtual Environment

```bash
python3 -m venv ~/oled-display
cd ~/oled-display
source bin/activate
```

## pip Packages

```bash
pip install luma.oled pillow smbus2 hid psutil
```

---

## Verify Hardware

```bash
# Confirm CP2112 shows as i2c-0
i2cdetect -l

# Confirm SSD1306 at 0x3C
sudo i2cdetect -y -r 0

# Confirm hidraw sees the CP2112
python3 -c "
import hid
for d in hid.enumerate():
    if d['vendor_id'] == 0x10C4:
        print(d)
"
```

---

## Critical Fix: CP2112 Block Size

The most important detail when using luma.oled with the CP2112 bridge is to pass a
pre-opened `SMBus` object to force luma into **unmanaged mode**.

Without this fix, luma defaults to 4096-byte `i2c_rdwr` transfers which exceed the
CP2112's 61-byte SMBus limit, resulting in a snow/garbage display with no readable output.

**Always use this boilerplate:**

```python
import smbus2
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306

bus = smbus2.SMBus(0)                  # 0 = i2c-0
serial = i2c(bus=bus, address=0x3C)   # forces _managed=False -> 32-byte chunks
device = ssd1306(serial)               # 128x64 default
```

---

## Full Stats Display Script

Save as `oled_stats.py` in your virtual environment directory:

```python
# oled_stats.py
import time
import socket
import psutil
import smbus2
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from luma.core.render import canvas
from PIL import ImageFont

# --- Font setup ---
UNIFONT   = "/usr/share/fonts/opentype/unifont/unifont.otf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

font_host = ImageFont.truetype(FONT_BOLD,  9)
font_sm   = ImageFont.truetype(UNIFONT,    8)
font_md   = ImageFont.truetype(UNIFONT,   10)

def get_hostname():
    return socket.gethostname()

def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "No IP"

def get_uptime():
    seconds = int(time.time() - psutil.boot_time())
    days    = seconds // 86400
    hours   = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    if days > 0:
        return f"Up: {days}d {hours:02d}h {minutes:02d}m"
    else:
        return f"Up: {hours:02d}h {minutes:02d}m"

def centered_x(draw, text, font, width):
    bbox = draw.textbbox((0, 0), text, font=font)
    return (width - (bbox[2] - bbox[0])) // 2

def draw_stats(device):
    hostname = get_hostname()
    ip       = get_ip()
    cpu      = psutil.cpu_percent(interval=1)
    ram      = psutil.virtual_memory().percent
    uptime   = get_uptime()
    w        = device.width

    with canvas(device) as draw:

        # Row 1: Hostname inverted
        draw.rectangle((0, 0, w - 1, 11), fill="white")
        x = centered_x(draw, hostname, font_host, w)
        draw.text((x, 1), hostname, font=font_host, fill="black")

        # Row 2: IP centered
        x = centered_x(draw, ip, font_sm, w)
        draw.text((x, 13), ip, font=font_sm, fill="white")

        # Row 3: Uptime centered
        x = centered_x(draw, uptime, font_sm, w)
        draw.text((x, 22), uptime, font=font_sm, fill="white")

        # Row 4: CPU + bar
        draw.text((0, 31), f"CPU:  {cpu:5.1f}%", font=font_md, fill="white")
        bar_w = int((w - 2) * cpu / 100)
        draw.rectangle((0, 41, w - 1, 44), outline="white", fill="black")
        draw.rectangle((0, 41, bar_w,  44), fill="white")

        # Row 5: RAM + bar
        draw.text((0, 47), f"RAM: {ram:5.1f}%", font=font_md, fill="white")
        bar_w = int((w - 2) * ram / 100)
        draw.rectangle((0, 57, w - 1, 60), outline="white", fill="black")
        draw.rectangle((0, 57, bar_w,  60), fill="white")

def main():
    bus    = smbus2.SMBus(0)
    serial = i2c(bus=bus, address=0x3C)
    device = ssd1306(serial)

    print("Running — Ctrl+C to exit")
    try:
        while True:
            draw_stats(device)
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        device.cleanup()
        bus.close()

if __name__ == "__main__":
    main()
```

Run it:

```bash
source ~/oled-display/bin/activate
python3 oled_stats.py
```

---

## Display Layout

```
+--------------------------------+
|            nebula              |  <- inverted bar, bold, centered
|       172.16.100.216           |  <- centered
|        Up: 02h 48m             |  <- centered, days shown only if > 0
|  CPU:    0.5%                  |  <- label + progress bar
|  RAM:   14.2%                  |  <- label + progress bar
+--------------------------------+
```

---

## Run on Boot with systemd

To have the display start automatically on boot, create a systemd service.
Adjust the username and paths if your venv is not in `/home/rwurttem/oled-display`:

```bash
sudo tee /etc/systemd/system/oled-stats.service <<'EOF'
[Unit]
Description=OLED Stats Display
After=network.target

[Service]
Type=simple
User=rwurttem
WorkingDirectory=/home/rwurttem/oled-display
ExecStart=/home/rwurttem/oled-display/bin/python3 /home/rwurttem/oled-display/oled_stats.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

Enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable oled-stats
sudo systemctl start oled-stats
sudo systemctl status oled-stats
```

Check logs if it fails to start:

```bash
journalctl -u oled-stats -f
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Snow/garbage on display | luma using 4096-byte transfers, CP2112 limit is 61 bytes | Pass `bus=smbus2.SMBus(0)` to `i2c()` |
| `ModuleNotFoundError: luma` with sudo | sudo uses system Python, not venv | Use `sudo ~/oled-display/bin/python3` |
| `ImportError: Unable to load libhidapi` | Missing system library | `sudo apt install libhidapi-hidraw0` |
| Permission denied on `/dev/hidraw0` | hidraw defaults to root:root | udev rule + plugdev group membership |
| Numbers/punctuation rendering badly | TTF font poor at small sizes | Use Unifont OTF at size 8/10 |
| Script not starting on boot | systemd service misconfigured | Check `journalctl -u oled-stats` |
