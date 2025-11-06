README.md
IP over Avian Carriers (IPoAC) via USB/SD - Avian.py
Overview
avian.py is a Python implementation of RFC 1149 ("A Standard for the Transmission of IP Datagrams on Avian Carriers"), adapted for modern sneakernet-style networking using USB drives or SD cards as the "avian carriers." It simulates high-latency, low-throughput networking between computers, treating physical media transport as the transmission medium. Key features include:

Packet Encapsulation: IP datagrams or custom packets (e.g., commands, data, SSH sessions) serialized to JSON files on the carrier.
Virtual Network Interface: Creates a TUN-based interface (ipoac0) for standard IP traffic (ping, SSH, etc.) over the carrier.
Mesh Networking: Configurable multi-host routing with static routes and hop limits for 2+ computers.
Command Execution: Remote Bash commands, updates, installs, and stateful SSH-like sessions.
Filesystem Ops: Simulated remote mounting and FS read/write/list.
Diagnostics: Ping/pong and traceroute simulations with latency/hop tracking.
Security: Checksums for integrity; extendable to encryption (e.g., via GPG).

Inspired by historical pigeon-based demos, this is perfect for offline environments, air-gapped systems, or just fun experiments. Latency: minutes to hours per "flight." Throughput: limited by carrier size/speed.
Features

Modes: send (write packets), receive (process packets), network (daemon with TUN interface).
Packet Types: data, command, update, install, ssh, mount, ping, traceroute, fs, ip (raw IP).
Configurable Mesh: Via avian_config.json for IPs, hosts, and routes.
Automation: Integrates with udev/systemd for auto-mount/process on insertion.

Quick Start

Install requirements (see REQUIREMENTS.md).
Mount USB/SD at /mnt/carrier.
For basic: sudo python3 avian.py network --mount /mnt/carrier.
Configure IPs: sudo ip addr add 192.168.42.1/24 dev ipoac0.
Test: ping 192.168.42.2 (carry media to remote host).

For full setup, see Installation Guide below.
Usage Examples

Simple Command: python3 avian.py send --type command --payload "ls -la" --dest /mnt/carrier.
SSH Session: python3 avian.py send --type ssh --payload "cd /tmp && ls" --session_id 123.
Mesh Ping: Run daemon on all hosts; ping remote IP—routes via config.
Daemon: sudo python3 avian.py network --config avian_config.json.

Configuration
Create avian_config.json:
json
