# CHANGELOG.md

## IP over Avian Carriers (IPoAC) - avian.py Project Changelog

This file documents the evolution of `avian.py`, key changes, dependencies installed (system-level), and manual setup steps required to get the project running. The project started as a simple RFC 1149-inspired script for USB/SD-based "networking" and evolved into a full-featured mesh-capable virtual network simulator. All changes are tracked by version (semantic versioning: major.minor.patch).

### Version 1.0.0 (Initial Release - November 2025)
- **Overview**: Core implementation of IPoAC with manual send/receive modes, packet types (data, command, update, install, ssh), checksum validation, and Bash integration.
- **Key Features Added**:
  - JSON packet serialization/deserialization with SHA256 checksums.
  - Basic error handling for corrupted packets.
  - Stateful SSH simulation via session files in `~/.ipoac_sessions`.
- **Changes**:
  - No prior version; bootstrapped from RFC 1149 review.
- **Dependencies Installed**:
  - **Python Stdlib**: json, hashlib, subprocess, os, argparse, time (no pip installs needed).
  - **System (via apt on Ubuntu/Debian)**:
    - `bash` (for command execution; usually pre-installed).
    - `sync` (coreutils; pre-installed).
- **Manual Install Steps**:
  - Download `avian.py`.
  - `chmod +x avian.py`.
  - Mount USB/SD: `sudo mkdir -p /mnt/carrier && sudo mount /dev/sdX1 /mnt/carrier`.
  - Test: `python3 avian.py send --type command --payload "ls -la" --dest /mnt/carrier`.
- **Known Issues Fixed**: N/A.

### Version 1.1.0 (Auto-Mount & Network Simulation - November 2025)
- **Overview**: Added automation hooks and virtual network interface for Ethernet-like visibility.
- **Key Features Added**:
  - `network` mode with TUN/TAP interface (`ipoac0`) for IP traffic injection.
  - Daemon polling for TUN and carrier.
  - Packet types: mount, ping, traceroute, fs.
  - udev/systemd integration examples for auto-processing on USB insert.
- **Changes**:
  - Fixed SyntaxError in global declarations.
  - Fixed AttributeError for missing mode args (added `required=True` to subparsers).
  - Enhanced help (`-h`) with detailed descriptions, examples, and notes.
  - Added base64 support for binary data.
- **Dependencies Installed**:
  - **System**:
    - `iproute2` (for `ip` command; `sudo apt install iproute2`).
    - `tcpdump` (debug; optional, `sudo apt install tcpdump`).
    - `tar` (for mount; usually pre-installed).
    - Kernel module: `sudo modprobe tun` (if `/dev/net/tun` missing).
- **Manual Install Steps**:
  - Ensure TUN support: `lsmod | grep tun` (load if needed).
  - Create udev rule: Edit `/etc/udev/rules.d/99-ipoac.rules` with insert trigger, then `sudo udevadm control --reload-rules`.
  - Test: `sudo python3 avian.py network --mount /mnt/carrier`; verify `ip link show ipoac0`.
- **Known Issues Fixed**:
  - Checksum corruption (added `sort_keys=True` in json.dumps).
  - Self-packet loops (skip if `source == local_id`).
  - KeyboardInterrupt handling in daemon.

### Version 1.2.0 (Mesh Networking - November 2025)
- **Overview**: Extended to multi-host mesh with configurable routing.
- **Key Features Added**:
  - Config file (`avian_config.json`) for hosts, IPs, static routes, max_hops.
  - Multi-hop forwarding in packets (hops array).
  - Auto-IP assignment on TUN creation.
  - Broadcast destination fallback for IP packets.
- **Changes**:
  - Integrated config loading in all modes.
  - Enhanced `process_packet` for forwarding logic.
  - Added `source`, `destination`, `hops` fields to packets.
  - Improved error handling in data/install/mount (try/except blocks, cleanup files).
  - Updated help/epilog to reflect mesh, new types, and config examples.
- **Dependencies Installed**:
  - No new; reused existing (iproute2 for routing).
- **Manual Install Steps**:
  - Create `avian_config.json` (copy example from README).
  - For multi-host: Sync config across machines (e.g., via initial carry).
  - Add routes: Restart daemon after config changes.
  - Test mesh: Ping across hops; carry USB along route path.
- **Known Issues Fixed**:
  - Daemon crashes on interrupt (added try/except KeyboardInterrupt).
  - Incomplete process_packet implementations (added full try/except for all types).

### Version 1.3.0 (Documentation & Polish - November 2025)
- **Overview**: Added comprehensive docs and requirements files.
- **Key Features Added**: N/A (docs-focused).
- **Changes**:
  - Created README.md (overview, usage, config).
  - Created REQUIREMENTS.md (hardware/software/setup guide).
  - Created requirements.txt (stdlib note + system deps).
  - Minor: Default config fallback; better logging in forwarding.
- **Dependencies Installed**: N/A.
- **Manual Install Steps**:
  - Follow REQUIREMENTS.md for full setup.
  - For SSH tests: `sudo apt install openssh-server && sudo systemctl start ssh`.
- **Known Issues Fixed**: N/A.

### Overall Setup Summary
To get this working end-to-end:
1. **Automated Installs (One-Time)**:
   - `sudo apt update && sudo apt install python3 iproute2 tcpdump tar bash openssh-server udev`.
   - `sudo modprobe tun`.
2. **Manual Steps (Per-Host)**:
   - Download `avian.py` and docs.
   - Format/mount carrier: `sudo mkfs.vfat -F 32 /dev/sdX1 && sudo mount /dev/sdX1 /mnt/carrier`.
   - Create config: Edit `avian_config.json`.
   - Udev for auto: Add rule and reload.
3. **Runtime**:
   - Daemon: `sudo python3 avian.py network --config avian_config.json`.
   - Verify: `ip addr show ipoac0`, `tcpdump -i ipoac0`.
4. **Testing Workflow**:
   - Generate traffic: `ping <remote_ip>`.
   - Carry: Unmount, transport USB, remount on next host.
   - Process: Daemon auto-handles.

### Future Plans
- Dynamic routing (e.g., via carried route updates).
- Encryption (GPG integration).
- Cross-OS support (macOS/Windows TUN via pytun).
- GUI for config/mesh visualization.

Report issues or PRs welcome! Last updated: November 06, 2025.
