# simulator.py
import socket
import time
import struct
from datetime import datetime, timezone
from typing import Dict, Any
import json
import random

class CCSDSSimulator:
    """CCSDS Space Packet Simulator"""
    
    def __init__(self, host='127.0.0.1', port=12345):
        self.host = host
        self.port = port
        self.packet_counter = 0
        self.apid = 100  # Application Process ID
        
    def create_ccsds_packet(self, data: Dict[str, Any]) -> bytes:
        """
        Create a CCSDS-compliant space packet
        """
        # CCSDS Primary Header
        packet_version = 0  # 3 bits
        packet_type = 0     # 0=Telemetry, 1=Telecommand
        sec_header_flag = 1 # Secondary header present
        
        # First word (16 bits)
        word1 = (packet_version << 13) | (packet_type << 12) | (sec_header_flag << 11) | self.apid
        
        # Sequence control
        sequence_flags = 3  # Unsegmented user data
        sequence_count = self.packet_counter % 16384
        
        # Second word (16 bits)
        word2 = (sequence_flags << 14) | sequence_count
        
        # Create data
        json_data = json.dumps(data).encode('utf-8')
        
        # Calculate total length: header(6) + sec_header(11) + data + crc(2)
        sec_header_length = 11
        crc_length = 2
        total_data_length = sec_header_length + len(json_data) + crc_length
        
        # CCSDS: data_length field = total_data_length - 7
        word3 = total_data_length - 7
        
        # Build header
        header = struct.pack('>HHH', word1, word2, word3)
        
        # Create secondary header (PUS-like)
        # Use smaller timestamp to avoid overflow
        timestamp_seconds = int(datetime.now(timezone.utc).timestamp()) % 86400  # Seconds in day
        
        # Secondary header (11 bytes)
        sec_header = struct.pack('>I', timestamp_seconds)  # 4 bytes: time
        sec_header += struct.pack('>BBB', 1, 3, 1)  # PUS version, service 3, subtype 1
        sec_header += struct.pack('>H', 1000)  # Destination ID
        sec_header += struct.pack('>H', 2000)  # Source ID
        
        # Combine everything
        packet = header + sec_header + json_data
        
        # Add simple CRC (for demo)
        crc = self._calculate_crc(packet)
        packet += struct.pack('>H', crc)
        
        self.packet_counter += 1
        return packet
    
    def _calculate_crc(self, data: bytes) -> int:
        """Simple CRC-16 calculation"""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte << 8
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc <<= 1
                crc &= 0xFFFF
        return crc
    
    def generate_telemetry(self) -> Dict[str, Any]:
        """Generate realistic spacecraft telemetry"""
        current_time = datetime.now(timezone.utc)
        
        return {
            "timestamp": current_time.isoformat(),
            "packet_id": self.packet_counter,
            "subsystem": random.choice(["ADCS", "EPS", "OBC", "COMMS"]),
            "health": {
                "status": random.choice(["NOMINAL", "DEGRADED", "SAFE"]),
                "mode": random.choice(["SUN_POINT", "NADIR", "INERTIAL"]),
                "errors": random.randint(0, 3)
            },
            "measurements": {
                "temperature_bus": round(25 + random.uniform(-5, 10), 2),
                "temperature_battery": round(15 + random.uniform(-5, 15), 2),
                "voltage_bus": round(12.0 + random.uniform(-1.5, 1.5), 3),
                "current_bus": round(2.5 + random.uniform(-0.5, 0.5), 2),
                "battery_charge": random.randint(20, 100),
                "solar_current": round(3.0 + random.uniform(-1.0, 2.0), 2),
                "gyro_x": round(random.uniform(-0.1, 0.1), 4),
                "gyro_y": round(random.uniform(-0.1, 0.1), 4),
                "gyro_z": round(random.uniform(-0.1, 0.1), 4)
            },
            "payload": {
                "data_volume": random.randint(0, 1000),
                "compression_rate": round(random.uniform(0.5, 0.9), 2),
                "active_instruments": random.randint(1, 3)
            }
        }
    
    def send_packets(self, interval: float = 2.0, count: int = None):
        """Send packets to the MO Service"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        print(f"🚀 CCSDS Simulator starting...")
        print(f"📡 Sending to {self.host}:{self.port}")
        print("⏸️  Press Ctrl+C to stop")
        print("-" * 50)
        
        sent = 0
        try:
            while count is None or sent < count:
                # Generate telemetry
                telemetry = self.generate_telemetry()
                
                # Create CCSDS packet
                packet = self.create_ccsds_packet(telemetry)
                
                # Send packet
                sock.sendto(packet, (self.host, self.port))
                
                # Print status
                print(f"📤 Packet {self.packet_counter-1}:")
                print(f"   Size: {len(packet)} bytes")
                print(f"   APID: {self.apid}")
                print(f"   Subsystem: {telemetry['subsystem']}")
                print(f"   Temp: {telemetry['measurements']['temperature_bus']}°C")
                print(f"   Voltage: {telemetry['measurements']['voltage_bus']}V")
                print("-" * 40)
                
                time.sleep(interval)
                sent += 1
                
        except KeyboardInterrupt:
            print("\n🛑 Simulator stopped by user")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            sock.close()

if __name__ == "__main__":
    simulator = CCSDSSimulator()
    simulator.send_packets(interval=2.0)