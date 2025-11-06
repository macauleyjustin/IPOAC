import json
import hashlib
import subprocess
import os
import argparse
import time
import base64
import fcntl
import struct
import select
import socket

# TUN/TAP constants (Linux-specific)
TUNSETIFF = 0x400454ca
IFF_TUN = 0x0001
IFF_TAP = 0x0002
IFF_NO_PI = 0x1000
TUN_DEV = '/dev/net/tun'

MOUNT_PATH = '/mnt/carrier'
PACKET_DIR = os.path.join(MOUNT_PATH, 'ipoac_packets')
PACKET_FILE_PREFIX = 'packet_'
CHECKSUM_ALGO = 'sha256'
SESSION_STATE_DIR = os.path.join(os.path.expanduser('~'), '.ipoac_sessions')
INTERFACE_NAME = 'ipoac0'
CONFIG_PATH = 'avian_config.json'  # Default

def load_config(config_path):
    """Load configuration from JSON file."""
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    # Default config for single host
    default_config = {
        "local_id": socket.gethostname(),
        "hosts": {socket.gethostname(): "192.168.42.1"},
        "routes": {},
        "max_hops": 5
    }
    print("No config found; using defaults.")
    return default_config

def calculate_checksum(data):
    """Compute SHA256 checksum of data with sorted keys for consistency."""
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

def write_packet(packet_type, payload, packet_id=None, session_id=None, extra=None, source=None, destination=None, hops=None):
    """Write a packet to the carrier."""
    if not os.path.exists(PACKET_DIR):
        os.makedirs(PACKET_DIR)
    
    packet_id = packet_id or str(int(time.time()))
    packet = {
        'type': packet_type,
        'payload': payload,
        'id': packet_id,
        'session_id': session_id,
        'extra': extra or {},
        'source': source or socket.gethostname(),
        'destination': destination,
        'hops': hops or []
    }
    packet['checksum'] = calculate_checksum(packet)
    
    file_path = os.path.join(PACKET_DIR, f'{PACKET_FILE_PREFIX}{packet_id}.json')
    with open(file_path, 'w') as f:
        json.dump(packet, f, sort_keys=True)
    
    subprocess.run(['sync'], check=True)
    print(f"Packet {packet_id} (type: {packet_type}) written.")

def read_packets(local_id):
    """Read all packets from carrier, validate checksums, skip own."""
    if not os.path.exists(PACKET_DIR):
        return []
    
    packets = []
    for filename in os.listdir(PACKET_DIR):
        if filename.startswith(PACKET_FILE_PREFIX):
            file_path = os.path.join(PACKET_DIR, filename)
            with open(file_path, 'r') as f:
                packet = json.load(f)
            
            if packet.get('source') == local_id:
                print(f"Skipping own packet {packet['id']}.")
                os.remove(file_path)
                continue
            
            checksum = packet.pop('checksum')
            if calculate_checksum(packet) != checksum:
                print(f"Corrupted packet {packet['id']}.")
                os.remove(file_path)
                continue
            
            packets.append(packet)
            os.remove(file_path)
    
    return packets

def process_packet(packet, tun_fd=None, config=None):
    """Process based on type. Handle forwarding for mesh."""
    local_id = config['local_id']
    max_hops = config['max_hops']
    ptype = packet['type']
    payload = packet['payload']
    session_id = packet.get('session_id')
    extra = packet.get('extra', {})
    destination = packet.get('destination')
    hops = packet.get('hops', [])
    
    if len(hops) > max_hops:
        print(f"Dropped packet {packet['id']}: Hop limit exceeded.")
        return None
    
    hops.append(local_id)  # Record this hop
    
    # Check if for local host; else forward
    if destination and destination != local_id:
        # Find next hop from routes
        route = config['routes'].get(destination, [])
        next_hop = route[0] if route else None
        if next_hop:
            print(f"Forwarding packet {packet['id']} to {destination} via {next_hop}.")
            return {
                'type': ptype,
                'payload': payload,
                'extra': extra,
                'source': packet['source'],
                'destination': destination,
                'hops': hops,
                'ref_id': packet['id']  # Preserve for responses
            }
        else:
            print(f"No route to {destination} for packet {packet['id']}.")
            return None
    
    # Local processing
    if ptype == 'ip':
        if tun_fd:
            try:
                os.write(tun_fd, base64.b64decode(payload))
                print(f"Injected IP packet {packet['id']} into TUN.")
            except Exception as e:
                print(f"Error injecting packet: {e}")
        return None
    
    if ptype == 'data':
        filename = extra.get('filename', 'received_data.txt')
        try:
            if extra.get('encoding') == 'base64':
                data = base64.b64decode(payload)
                with open(filename, 'wb') as f:
                    f.write(data)
            else:
                with open(filename, 'w') as f:
                    f.write(payload)
            print("Data received and saved.")
            return None  # No response
        except Exception as e:
            print(f"Data write error: {e}")
            return {'type': 'response', 'payload': f'Data failed: {e}', 'ref_id': packet['id']}
    
    elif ptype == 'command':
        try:
            result = subprocess.run(['bash', '-c', payload], capture_output=True, text=True, check=True)
            output = result.stdout + result.stderr
            return {'type': 'response', 'payload': output, 'ref_id': packet['id']}
        except subprocess.CalledProcessError as e:
            return {'type': 'response', 'payload': str(e), 'ref_id': packet['id']}
    
    elif ptype == 'update':
        try:
            subprocess.run(['bash', '-c', f'patch < <(echo "{payload}")'], check=True)
            return {'type': 'response', 'payload': 'Update applied.', 'ref_id': packet['id']}
        except Exception as e:
            return {'type': 'response', 'payload': f'Update failed: {e}', 'ref_id': packet['id']}
    
    elif ptype == 'install':
        install_file = 'install.sh'
        with open(install_file, 'w') as f:
            f.write(payload)
        try:
            subprocess.run(['bash', install_file], check=True)
            os.remove(install_file)
            return {'type': 'response', 'payload': 'Install complete.', 'ref_id': packet['id']}
        except Exception as e:
            if os.path.exists(install_file):
                os.remove(install_file)
            return {'type': 'response', 'payload': f'Install failed: {e}', 'ref_id': packet['id']}
    
    elif ptype == 'ssh':
        if not os.path.exists(SESSION_STATE_DIR):
            os.makedirs(SESSION_STATE_DIR)
        state_file = os.path.join(SESSION_STATE_DIR, f'session_{session_id}.json')
        
        state = {'cwd': os.getcwd(), 'env': dict(os.environ)}
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                state = json.load(f)
        
        os.chdir(state['cwd'])
        os.environ.update(state['env'])
        
        try:
            result = subprocess.run(['bash', '-c', payload], capture_output=True, text=True, check=True)
            output = result.stdout + result.stderr
        except subprocess.CalledProcessError as e:
            output = str(e)
        
        state['cwd'] = os.getcwd()
        state['env'] = dict(os.environ)
        with open(state_file, 'w') as f:
            json.dump(state, f)
        
        return {'type': 'ssh_response', 'payload': output, 'ref_id': packet['id'], 'session_id': session_id}
    
    elif ptype == 'mount':
        remote_path = extra.get('remote_path', '/')
        local_mount = extra.get('local_mount', '/mnt/remote')
        if not os.path.exists(local_mount):
            os.makedirs(local_mount)
        try:
            tar_data = base64.b64decode(payload)
            with open('remote_fs.tar', 'wb') as f:
                f.write(tar_data)
            subprocess.run(['tar', '-xf', 'remote_fs.tar', '-C', local_mount], check=True)
            os.remove('remote_fs.tar')
            print(f"Remote fs mounted at {local_mount}.")
            return {'type': 'response', 'payload': 'Mount successful.', 'ref_id': packet['id']}
        except Exception as e:
            if os.path.exists('remote_fs.tar'):
                os.remove('remote_fs.tar')
            return {'type': 'response', 'payload': f'Mount failed: {e}', 'ref_id': packet['id']}
    
    elif ptype == 'ping':
        return {'type': 'pong', 'payload': '', 'ref_id': packet['id'], 'extra': {'timestamp': int(time.time())}}
    
    elif ptype == 'traceroute':
        hops = extra.get('hops', [])
        hops.append({'host': os.uname().nodename, 'time': int(time.time())})
        ttl = extra.get('ttl', 1)
        if ttl > 1:
            return {'type': 'traceroute', 'payload': payload, 'extra': {'hops': hops, 'ttl': ttl - 1}, 'ref_id': packet['id']}
        return {'type': 'traceroute_response', 'payload': 'Reached.', 'ref_id': packet['id'], 'extra': {'hops': hops}}
    
    elif ptype == 'fs':
        op = extra.get('op')
        path = extra.get('path')
        try:
            if op == 'write':
                with open(path, 'w') as f:
                    f.write(payload)
                return {'type': 'response', 'payload': 'Write complete.', 'ref_id': packet['id']}
            elif op == 'read':
                with open(path, 'r') as f:
                    content = f.read()
                return {'type': 'fs_response', 'payload': content, 'ref_id': packet['id']}
            elif op == 'list':
                content = os.listdir(path)
                return {'type': 'fs_response', 'payload': json.dumps(content), 'ref_id': packet['id']}
        except Exception as e:
            return {'type': 'response', 'payload': f'FS op failed: {e}', 'ref_id': packet['id']}
    
    else:
        print(f"Unknown packet type: {ptype}")
        return None

def create_tun_interface(local_ip):
    """Create and configure the TUN interface."""
    if os.path.exists(f'/sys/class/net/{INTERFACE_NAME}'):
        subprocess.run(['ip', 'link', 'delete', INTERFACE_NAME])
    tun_fd = os.open(TUN_DEV, os.O_RDWR)
    ifr = struct.pack('16sH', INTERFACE_NAME.encode(), IFF_TUN | IFF_NO_PI)
    fcntl.ioctl(tun_fd, TUNSETIFF, ifr)
    subprocess.run(['ip', 'link', 'set', INTERFACE_NAME, 'up'])
    if local_ip:
        subprocess.run(['ip', 'addr', 'add', f'{local_ip}/24', 'dev', INTERFACE_NAME])
    print(f"Created virtual interface: {INTERFACE_NAME} with IP {local_ip or 'none'}")
    return tun_fd

def network_daemon(tun_fd, config):
    """Daemon loop: Poll TUN for outbound, carrier for inbound."""
    local_id = config['local_id']
    
    while True:
        try:
            readable, _, _ = select.select([tun_fd], [], [], 1)
            if readable:
                ip_packet = os.read(tun_fd, 2048)
                # For simplicity, set destination to 'broadcast'; enhance with IP parsing for real dest
                write_packet('ip', base64.b64encode(ip_packet).decode(), extra={'protocol': 'ipv4'}, source=local_id, destination='broadcast', hops=[])
            
            if os.path.exists(PACKET_DIR):
                packets = read_packets(local_id)
                for packet in packets:
                    response = process_packet(packet, tun_fd=tun_fd, config=config)
                    if response:
                        # If response, write back (destination is original source for replies)
                        reply_dest = packet.get('source')
                        write_packet(
                            response.get('type', 'response'),
                            response.get('payload', ''),
                            packet_id=response.get('ref_id', None),
                            session_id=response.get('session_id'),
                            extra=response.get('extra', {}),
                            source=local_id,
                            destination=reply_dest,
                            hops=response.get('hops', [])
                        )
                        print("Response packet prepared for return flight.")
        except KeyboardInterrupt:
            print("Daemon interrupted. Cleaning up...")
            break
        except Exception as e:
            print(f"Daemon error: {e}")
        
        time.sleep(1)  # Polling interval

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
    subparsers = parser.add_subparsers(dest='mode', required=True)
    
    # Send subparser
    send_parser = subparsers.add_parser('send')
    send_parser.add_argument('--type', required=True, choices=['data', 'command', 'update', 'install', 'ssh', 'mount', 'ping', 'traceroute', 'fs', 'ip'])
    send_parser.add_argument('--payload', required=True, help="Data or command string")
    send_parser.add_argument('--dest', default=MOUNT_PATH, help="Mount path")
    send_parser.add_argument('--session_id', type=str, help="Session ID for ssh")
    send_parser.add_argument('--extra', type=json.loads, default={}, help="JSON extra dict")
    
    # Receive subparser
    receive_parser = subparsers.add_parser('receive')
    receive_parser.add_argument('--src', default=MOUNT_PATH, help="Mount path")
    
    # Network subparser
    network_parser = subparsers.add_parser('network')
    network_parser.add_argument('--mount', default=MOUNT_PATH, help="Mount path")
    network_parser.add_argument('--config', default=CONFIG_PATH, help="Config file path")
    
    args = parser.parse_args()
    
    # Set paths based on mode
    if args.mode == 'send':
        MOUNT_PATH = args.dest
    elif args.mode == 'receive':
        MOUNT_PATH = args.src
    elif args.mode == 'network':
        MOUNT_PATH = args.mount
    PACKET_DIR = os.path.join(MOUNT_PATH, 'ipoac_packets')
    
    if args.mode == 'send':
        write_packet(args.type, args.payload, session_id=args.session_id, extra=args.extra)
    
    elif args.mode == 'receive':
        config = load_config(CONFIG_PATH)  # Load for local_id
        packets = read_packets(config['local_id'])
        for packet in packets:
            response = process_packet(packet, config=config)
            if response:
                write_packet(
                    response.get('type', 'response'),
                    response.get('payload', ''),
                    packet_id=response.get('ref_id'),
                    session_id=response.get('session_id'),
                    extra=response.get('extra', {})
                )
                print("Response packet prepared.")
    
    elif args.mode == 'network':
        config = load_config(args.config)
        local_id = config['local_id']
        local_ip = config['hosts'].get(local_id)
        tun_fd = create_tun_interface(local_ip)
        network_daemon(tun_fd, config)

if __name__ == '__main__':
    main()
