# README.md

## IP over Avian Carriers (IPoAC) via USB/SD - Avian.py

### Overview
`avian.py` is a Python implementation of RFC 1149 ("A Standard for the Transmission of IP Datagrams on Avian Carriers"), adapted for modern sneakernet-style networking using USB drives or SD cards as the "avian carriers." It simulates high-latency, low-throughput networking between computers, treating physical media transport as the transmission medium. Key features include:

- **Packet Encapsulation**: IP datagrams or custom packets (e.g., commands, data, SSH sessions) serialized to JSON files on the carrier.
- **Virtual Network Interface**: Creates a TUN-based interface (`ipoac0`) for standard IP traffic (ping, SSH, etc.) over the carrier.
- **Mesh Networking**: Configurable multi-host routing with static routes and hop limits for 2+ computers.
- **Command Execution**: Remote Bash commands, updates, installs, and stateful SSH-like sessions.
- **Filesystem Ops**: Simulated remote mounting and FS read/write/list.
- **Diagnostics**: Ping/pong and traceroute simulations with latency/hop tracking.
- **Security**: Checksums for integrity; extendable to encryption (e.g., via GPG).

Inspired by historical pigeon-based demos, this is perfect for offline environments, air-gapped systems, or just fun experiments. Latency: minutes to hours per "flight." Throughput: limited by carrier size/speed.

### Features
- **Modes**: `send` (write packets), `receive` (process packets), `network` (daemon with TUN interface).
- **Packet Types**: `data`, `command`, `update`, `install`, `ssh`, `mount`, `ping`, `traceroute`, `fs`, `ip` (raw IP).
- **Configurable Mesh**: Via `avian_config.json` for IPs, hosts, and routes.
- **Automation**: Integrates with udev/systemd for auto-mount/process on insertion.

### Quick Start
1. Install requirements (see [REQUIREMENTS.md](REQUIREMENTS.md)).
2. Mount USB/SD at `/mnt/carrier`.
3. For basic: `sudo python3 avian.py network --mount /mnt/carrier`.
4. Configure IPs: `sudo ip addr add 192.168.42.1/24 dev ipoac0`.
5. Test: `ping 192.168.42.2` (carry media to remote host).

For full setup, see [Installation Guide](#installation) below.

### Usage Examples
- **Simple Command**: `python3 avian.py send --type command --payload "ls -la" --dest /mnt/carrier`.
- **SSH Session**: `python3 avian.py send --type ssh --payload "cd /tmp && ls" --session_id 123`.
- **Mesh Ping**: Run daemon on all hosts; ping remote IP—routes via config.
- **Daemon**: `sudo python3 avian.py network --config avian_config.json`.

### Configuration
Create `avian_config.json`:
```json
{
  "local_id": "hostA",
  "hosts": {
    "hostA": "192.168.42.1",
    "hostB": "192.168.42.2"
  },
  "routes": {
    "hostB": ["hostA"]
  },
  "max_hops": 5
}
```

### Troubleshooting
- **Corrupted Packets**: Check mount permissions; ensure `sync`.
- **TUN Errors**: Run as sudo; ensure `/dev/net/tun` exists.
- **No Traffic**: Use `tcpdump -i ipoac0` to monitor.
- **High Latency**: Expected—carry the carrier!

### License
MIT License. See LICENSE for details.

### Contributing
Fork, PR, or report issues. Inspired by RFC 1149—may the pigeons fly true!

---

# REQUIREMENTS.md

## System Requirements

### Hardware
- **Computers**: 2+ Linux machines (e.g., Ubuntu 20.04+; macOS/WSL adaptable but TUN limited).
- **Carrier**: USB drive or SD card (≥1GB, FAT32/exFAT formatted for cross-compat).
- **Reader**: USB/SD slot or adapter.

### Software
- **OS**: Linux kernel ≥3.10 (for TUN/TAP). Tested on Ubuntu 22.04.
- **Python**: 3.6+ (stdlib only: json, hashlib, subprocess, os, argparse, time, base64, fcntl, struct, select, socket).
- **Bash**: 4.0+ (for command execution).
- **Networking Tools**: `ip` (iproute2), `tcpdump` (debug), `tar` (mounting), `sync` (flushing).
- **Optional**:
  - `udev` (auto-detection).
  - `systemd` (daemons).
  - `openssh-server` (for SSH tests).
  - `inotify-tools` (file watching).

No external Python libs needed—pure stdlib. No internet required.

### Dependencies
- Kernel module: `tun` (load with `modprobe tun` if missing).
- Mount point: Create `/mnt/carrier` (`sudo mkdir -p /mnt/carrier`).

---

## Installation and Setup Guide

### Step 1: Install Dependencies
On Ubuntu/Debian:
```bash
sudo apt update
sudo apt install python3 iproute2 tcpdump tar bash openssh-server udev
sudo modprobe tun
```

On other distros: Use equivalent package manager (e.g., `dnf` for Fedora).

### Step 2: Prepare the Carrier
- Format USB/SD: `sudo mkfs.vfat -F 32 /dev/sdX1` (replace `sdX1`; backup first!).
- Label optionally: `sudo e2label /dev/sdX1 IPOAC_CARRIER`.
- Mount: `sudo mount /dev/sdX1 /mnt/carrier` (or auto via fstab/udev).

### Step 3: Download and Configure
- Save `avian.py` to a dir (e.g., `~/avian/`).
- Make executable: `chmod +x avian.py`.
- Create `avian_config.json` (see README example; customize for your hosts).
- For mesh: Ensure all hosts share compatible config (IPs/routes).

### Step 4: Run the Program
- **Basic Send/Receive** (no TUN):
  ```bash
  # Send command
  python3 avian.py send --type command --payload "ls -la" --dest /mnt/carrier

  # Receive (mount carrier first)
  python3 avian.py receive --src /mnt/carrier
  ```
- **Network Daemon (TUN + Mesh)**:
  ```bash
  sudo python3 avian.py network --config avian_config.json --mount /mnt/carrier
  ```
  - Auto-creates `ipoac0` and assigns IP from config.
  - Daemon polls TUN and carrier; skips self-packets.

### Step 5: Configure Network
- On each host: Run daemon, then:
  ```bash
  sudo ip link set ipoac0 up  # If not auto
  # IP auto-assigned from config; verify: ip addr show ipoac0
  ```
- For mesh routes: Add to config and restart daemon.

### Step 6: Test
- **Ping**: `ping <remote_ip>` (e.g., 192.168.42.2). Carry USB to remote; process (daemon auto-handles).
- **SSH**: `ssh user@<remote_ip>` (high timeouts in `~/.ssh/config`: `ConnectTimeout 3600`).
- **Mesh Test**: Ping across hops; check logs for forwarding.
- **Automation**: Add udev rule (`/etc/udev/rules.d/99-ipoac.rules`):
  ```
  ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_LABEL}=="IPOAC_CARRIER", RUN+="/usr/bin/python3 /path/to/avian.py receive --src /mnt/carrier"
  ```
  Reload: `sudo udevadm control --reload-rules`.

### Step 7: Cleanup
- Stop daemon: Ctrl+C or `sudo pkill -f avian.py`.
- Remove interface: `sudo ip link delete ipoac0`.
- Unmount: `sudo umount /mnt/carrier`.

If issues: Check logs (`journalctl -f` for systemd), permissions, or kernel TUN. For non-Linux: Use user-space TUN libs (e.g., pytun).

---

### Updated Program Help (in `avian.py`)
To update the help text, replace the `description` and `epilog` in `main()` with this enhanced version (full script snippet for context):

```python
def main():
    global MOUNT_PATH, PACKET_DIR
    
    description = """
IP over Avian Carriers (IPoAC) via USB/SD Card - Mesh Network Edition

This script implements RFC 1149 for offline networking using USB/SD as 'avian carriers.' It creates a virtual TUN interface (ipoac0) for IP traffic, supports mesh routing via config, and enables data/commands/SSH over physical carries. For 2+ hosts: Assign IPs/routes in avian_config.json; packets hop via sequential carries.
"""
    
    epilog = """
Modes:
- send: Write packet to carrier.
  --type {data,command,update,install,ssh,mount,ping,traceroute,fs,ip} (req)
  --payload PAYLOAD (req; base64 for binary)
  --dest DEST (default: /mnt/carrier)
  --session_id ID (for ssh)
  --extra JSON (e.g., '{"encoding":"base64"}')

- receive: Process packets from carrier.
  --src SRC (default: /mnt/carrier)

- network: Daemon with TUN/mesh (sudo req).
  --mount MOUNT (default: /mnt/carrier)
  --config CONFIG (default: avian_config.json)

Config (avian_config.json):
{
  "local_id": "hostA",
  "hosts": {"hostA": "192.168.42.1", "hostB": "192.168.42.2"},
  "routes": {"hostB": ["hostA"]},
  "max_hops": 5
}

Examples:
1. Daemon: sudo python3 avian.py network --config avian_config.json
2. Ping mesh: ping 192.168.42.2 (carry to remote)
3. SSH: ssh user@192.168.42.2 (high timeouts)
4. Send data: python3 avian.py send --type data --payload "hello" --extra '{"filename":"test.txt"}'

Notes:
- Mount carrier before ops.
- Auto-IP on startup; use tcpdump -i ipoac0 for debug.
- Mesh: Forwarding via routes; carry along path.
- RFC 1149: High latency, low MTU—embrace the pigeon!
"""
    
    parser = argparse.ArgumentParser(
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    # ... rest of parser setup as before
```

Run `python3 avian.py -h` to see the updated help. This matches current features: TUN, mesh config, all packet types.
