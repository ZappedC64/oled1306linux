# =============================================================================
# oled_stats_proxmox.py
#
# Displays live system stats for Proxmox on a 128x64 SSD1306 OLED display via I²C.
# Shows hostname (inverted banner), IP address, uptime, and CPU/RAM
# utilization with progress bars. Designed for use with a CP2112 USB-to-I²C
# bridge or any Linux system with an I²C bus.
#
# Author:       Raj Wurttemberg
# Contributions: Claude AI (Anthropic)
# Created:      2026-03-15
# Version:      1.0
#
# Dependencies:
#   pip install luma.oled smbus2 psutil pillow
#
# Usage:
#   python3 oled_stats_proxmox.py
# =============================================================================

import time
import signal
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

    def shutdown(signum, frame):
        device.cleanup()
        bus.close()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, shutdown)   # systemctl stop
    signal.signal(signal.SIGINT, shutdown)    # Ctrl+C for manual testing

    print("Running — send SIGTERM or SIGINT to exit")
    while True:
        draw_stats(device)
        time.sleep(2)

if __name__ == "__main__":
    main()
