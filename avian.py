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

# TUN/TAP constants
TUNSETIFF = 0x400454ca
IFF_TUN = 0x0001
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
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    return {"local_id": socket.gethostname(), "hosts": {}, "routes": {}, "max_hops": 5}

def calculate_checksum(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

def write_packet(packet_type, payload, packet_id=None, session_id=None, extra=None, source=None, destination=None, hops=None):
    if not os.path.exists(PACKET_DIR):
        os.makedirs(PACKET_DIR)
    
    packet_id = packet_id or str(int(time.time()))
    packet = {
        'type': packet_type,
        'payload': payload,
        'id': packet_id,
        'session_id': session_id,
        'extra': extra or {},
        'source': source,
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
    local_id = config['local_id']
    max_hops = config['max_hops']
    ptype = packet['type']
    payload = packet['payload']
    destination = packet.get('destination')
    hops = packet.get('hops', [])
    
    if len(hops) > max_hops:
        print(f"Dropped packet {packet['id']}: Hop limit exceeded.")
        return None
    
    hops.append(local_id)  # Add current hop
    
    if destination and destination != local_id:
        # Forward to next hop
        next_hop = config['routes'].get(destination, [])[0] if config['routes'].get(destination) else None
        if next_hop:
            print(f"Forwarding packet {packet['id']} to {destination} via {next_hop}.")
            return {'type': ptype, 'payload': payload, 'extra': packet['extra'], 'source': packet['source'], 'destination': destination, 'hops': hops}
        else:
            print(f"No route to {destination} for packet {packet['id']}.")
            return None
    
    # Local processing
    if ptype == 'ip':
        if tun_fd:
            os.write(tun_fd, base64.b64decode(payload))
            print(f"Injected IP packet {packet['id']} into TUN.")
        return None
    
    # Other types (command, ssh, etc.) as before...
    # (Omit full code for brevity; integrate from previous versions)
    
    return None  # Or response dict with updated hops if needed

def create_tun_interface(local_ip):
    tun_fd = os.open(TUN_DEV, os.O_RDWR)
    ifr = struct.pack('16sH', INTERFACE_NAME.encode(), IFF_TUN | IFF_NO_PI)
    fcntl.ioctl(tun_fd, TUNSETIFF, ifr)
    subprocess.run(['ip', 'link', 'set', INTERFACE_NAME, 'up'])
    if local_ip:
        subprocess.run(['ip', 'addr', 'add', f'{local_ip}/24', 'dev', INTERFACE_NAME])
    print(f"Created virtual interface: {INTERFACE_NAME} with IP {local_ip}")
    return tun_fd

def network_daemon(tun_fd, config):
    local_id = config['local_id']
    while True:
        readable, _, _ = select.select([tun_fd], [], [], 1)
        if readable:
            ip_packet = os.read(tun_fd, 2048)
            # Assume destination from IP header or config; for simplicity, prompt or use broadcast
            write_packet('ip', base64.b64encode(ip_packet).decode(), extra={'protocol': 'ipv4'}, source=local_id, destination='broadcast', hops=[])
        
        if os.path.exists(PACKET_DIR):
            packets = read_packets(local_id)
            for packet in packets:
                response = process_packet(packet, tun_fd, config)
                if response:
                    write_packet(response['type'], response.get('payload', ''), extra=response.get('extra', {}), source=local_id, destination=response.get('destination'), hops=response.get('hops', []))

        time.sleep(1)

def main():
    global MOUNT_PATH, PACKET_DIR
    
    parser = argparse.ArgumentParser(description="IPoAC Mesh Network")
    subparsers = parser.add_subparsers(dest='mode', required=True)
    
    network_parser = subparsers.add_parser('network')
    network_parser.add_argument('--mount', default=MOUNT_PATH)
    network_parser.add_argument('--config', default=CONFIG_PATH)
    
    # Add send/receive parsers as before...
    
    args = parser.parse_args()
    
    if args.mode == 'network':
        config = load_config(args.config)
        local_id = config['local_id']
        local_ip = config['hosts'].get(local_id)
        MOUNT_PATH = args.mount
        PACKET_DIR = os.path.join(MOUNT_PATH, 'ipoac_packets')
        tun_fd = create_tun_interface(local_ip)
        network_daemon(tun_fd, config)
    
    # Handle other modes...

if __name__ == '__main__':
    main()
