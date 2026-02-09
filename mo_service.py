# mo_service.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from contextlib import asynccontextmanager
import uvicorn
import struct
import json
import threading
import socket

app = FastAPI(
    title="CCSDS Mission Operations Service",
    description="CCSDS-compliant MO Services",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Data stores
telemetry_store = {}
parameter_store = {}
command_queue = []
store_lock = threading.Lock()

# Models
class Parameter(BaseModel):
    name: str
    value: Any
    timestamp: str
    validity: str = "VALID"
    units: Optional[str] = None
    quality: Optional[str] = "GOOD"

class GetParameterValuesRequest(BaseModel):
    parameterIds: List[str]
    requestId: str

class GetParameterValuesResponse(BaseModel):
    parameters: List[Parameter]
    requestId: str
    timestamp: str

class Telecommand(BaseModel):
    commandId: str
    serviceType: int
    serviceSubtype: int
    parameters: Dict[str, Any]
    timestamp: str

class TelecommandResponse(BaseModel):
    commandId: str
    status: str
    timestamp: str
    message: Optional[str] = None

# CCSDS Packet Parser
class CCSDSParser:
    """Parse CCSDS Space Packets"""
    
    @staticmethod
    def parse_packet(data: bytes) -> Dict[str, Any]:
        """Parse CCSDS Space Packet"""
        if len(data) < 6:
            return {"error": "Packet too short"}
        
        try:
            # Parse primary header (6 bytes)
            word1, word2, word3 = struct.unpack('>HHH', data[:6])
            
            # Extract fields
            packet_version = (word1 >> 13) & 0x07
            packet_type = (word1 >> 12) & 0x01
            sec_header_flag = (word1 >> 11) & 0x01
            apid = word1 & 0x07FF
            
            sequence_flags = (word2 >> 14) & 0x03
            sequence_count = word2 & 0x3FFF
            
            data_length = word3  # Actually length - 1 per CCSDS
            
            # Parse secondary header if present
            json_data = None
            if sec_header_flag and len(data) >= 17:  # 6 + 11 bytes min
                # Skip secondary header (assuming 11 bytes for demo)
                json_start = 17
                if json_start < len(data) - 2:  # Account for CRC
                    json_data = data[json_start:-2]  # Exclude CRC
                    
                    try:
                        telemetry = json.loads(json_data.decode('utf-8', errors='ignore'))
                    except:
                        telemetry = {"raw": json_data.hex()}
                else:
                    telemetry = {"raw": data[6:].hex()}
            else:
                telemetry = {"raw": data[6:].hex()}
            
            return {
                "header": {
                    "version": packet_version,
                    "type": "TM" if packet_type == 0 else "TC",
                    "apid": apid,
                    "sequence_flags": sequence_flags,
                    "sequence_count": sequence_count,
                    "data_length": data_length
                },
                "telemetry": telemetry,
                "raw_size": len(data),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            return {"error": f"Parse error: {str(e)}"}

# UDP Receiver
class CCSDSReceiver(threading.Thread):
    def __init__(self, port=12345):
        super().__init__(daemon=True)
        self.port = port
        self.running = True
        self.parser = CCSDSParser()
        
    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', self.port))
        sock.settimeout(1.0)
        
        print(f"📡 CCSDS Receiver started on port {self.port}")
        print("   Waiting for space packets...")
        
        while self.running:
            try:
                data, addr = sock.recvfrom(65535)
                
                # Parse packet
                parsed = self.parser.parse_packet(data)
                
                if "error" not in parsed:
                    # Store telemetry
                    packet_id = parsed["header"]["sequence_count"]
                    
                    with store_lock:
                        telemetry_store[packet_id] = parsed
                        
                        # Extract parameters from telemetry
                        if "telemetry" in parsed and isinstance(parsed["telemetry"], dict):
                            self._extract_parameters(parsed, packet_id)
                    
                    # Log reception
                    print(f"📥 Packet {packet_id} from {addr[0]}: "
                          f"APID={parsed['header']['apid']}, "
                          f"Size={parsed['raw_size']} bytes")
                    
                else:
                    print(f"⚠️ Parse error: {parsed['error']}")
                    
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"❌ Receiver error: {e}")
        
        sock.close()
        print("📡 Receiver stopped")
    
    def _extract_parameters(self, parsed: Dict, packet_id: int):
        """Extract parameters from telemetry and store them"""
        telemetry = parsed["telemetry"]
        
        # Check if telemetry is a dict (not hex string)
        if isinstance(telemetry, dict):
            # Extract measurements
            if "measurements" in telemetry:
                for key, value in telemetry["measurements"].items():
                    param_name = f"MEAS_{key.upper()}"
                    parameter_store[param_name] = {
                        "value": value,
                        "timestamp": parsed["timestamp"],
                        "validity": "VALID",
                        "units": self._get_units(key),
                        "source": f"Packet_{packet_id}"
                    }
            
            # Extract health status
            if "health" in telemetry:
                for key, value in telemetry["health"].items():
                    param_name = f"HEALTH_{key.upper()}"
                    parameter_store[param_name] = {
                        "value": value,
                        "timestamp": parsed["timestamp"],
                        "validity": "VALID",
                        "units": "",
                        "source": f"Packet_{packet_id}"
                    }
            
            # Store subsystem
            if "subsystem" in telemetry:
                parameter_store["SUBSYSTEM"] = {
                    "value": telemetry["subsystem"],
                    "timestamp": parsed["timestamp"],
                    "validity": "VALID",
                    "units": "",
                    "source": f"Packet_{packet_id}"
                }
    
    def _get_units(self, param_name: str) -> str:
        """Get units for parameter based on name"""
        param_lower = param_name.lower()
        
        if any(x in param_lower for x in ['temp', 'temperature']):
            return '°C'
        elif 'voltage' in param_lower:
            return 'V'
        elif 'current' in param_lower:
            return 'A'
        elif 'gyro' in param_lower:
            return 'rad/s'
        elif 'charge' in param_lower:
            return '%'
        else:
            return ''
    
    def stop(self):
        self.running = False

# Global receiver instance
receiver = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup/shutdown"""
    global receiver
    
    # Startup
    receiver = CCSDSReceiver(port=12345)
    receiver.start()
    
    print("=" * 60)
    print("🚀 CCSDS Mission Operations Service")
    print("=" * 60)
    print("📊 API Documentation: http://localhost:8000/docs")
    print("📡 Listening for CCSDS packets on UDP port 12345")
    print("=" * 60)
    
    yield  # App runs here
    
    # Shutdown
    if receiver:
        receiver.stop()
        receiver.join(timeout=2.0)
    print("\n🛑 MO Service stopped")

# Create app with lifespan
app = FastAPI(
    title="CCSDS Mission Operations Service",
    description="CCSDS-compliant MO Services",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# REST API Endpoints
@app.get("/")
async def root():
    return {
        "service": "CCSDS Mission Operations Service",
        "standard": "CCSDS MO Services",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": [
            "/docs - Interactive API documentation",
            "/health - Service health check",
            "/telemetry - Get telemetry data",
            "/parameters - Get parameter values",
            "/ccsds/parameters - CCSDS GetParameterValues",
            "/commands - Send telecommands"
        ]
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    with store_lock:
        packet_count = len(telemetry_store)
        param_count = len(parameter_store)
    
    receiver_status = "ACTIVE" if receiver and receiver.running else "INACTIVE"
    
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "statistics": {
            "telemetry_packets_received": packet_count,
            "parameters_monitored": param_count,
            "commands_queued": len(command_queue)
        },
        "receiver": {
            "active": receiver.running if receiver else False,
            "port": 12345,
            "status": receiver_status
        }
    }

@app.get("/telemetry/latest")
async def get_latest_telemetry():
    """Get latest telemetry packet"""
    with store_lock:
        if not telemetry_store:
            raise HTTPException(status_code=404, detail="No telemetry received")
        
        latest_id = max(telemetry_store.keys())
        return telemetry_store[latest_id]

@app.get("/telemetry/{packet_id}")
async def get_telemetry(packet_id: int):
    """Get specific telemetry packet"""
    with store_lock:
        if packet_id not in telemetry_store:
            raise HTTPException(status_code=404, detail=f"Packet {packet_id} not found")
        
        return telemetry_store[packet_id]

@app.get("/telemetry")
async def get_all_telemetry(limit: int = 10):
    """Get recent telemetry packets"""
    with store_lock:
        packet_ids = sorted(telemetry_store.keys(), reverse=True)[:limit]
        return {
            "count": len(packet_ids),
            "packets": {pid: telemetry_store[pid] for pid in packet_ids}
        }

@app.get("/parameters")
async def get_all_parameters():
    """Get all monitored parameters"""
    with store_lock:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(parameter_store),
            "parameters": parameter_store
        }

@app.get("/parameter/{param_name}")
async def get_parameter(param_name: str):
    """Get specific parameter"""
    param_name_upper = param_name.upper()
    
    with store_lock:
        if param_name_upper not in parameter_store:
            raise HTTPException(status_code=404, detail=f"Parameter '{param_name}' not found")
        
        return {
            "parameter": {
                "name": param_name_upper,
                **parameter_store[param_name_upper]
            }
        }

@app.post("/ccsds/parameters", response_model=GetParameterValuesResponse)
async def get_ccsds_parameters(request: GetParameterValuesRequest):
    """
    CCSDS MO Service: GetParameterValues
    """
    parameters = []
    
    with store_lock:
        for param_id in request.parameterIds:
            param_id_upper = param_id.upper()
            
            if param_id_upper in parameter_store:
                param_data = parameter_store[param_id_upper]
                param = Parameter(
                    name=param_id_upper,
                    value=param_data["value"],
                    timestamp=param_data["timestamp"],
                    validity=param_data["validity"],
                    units=param_data.get("units"),
                    quality=param_data.get("quality", "GOOD")
                )
            else:
                # Parameter not found
                param = Parameter(
                    name=param_id_upper,
                    value=None,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    validity="INVALID",
                    quality="UNKNOWN"
                )
            
            parameters.append(param)
    
    return GetParameterValuesResponse(
        parameters=parameters,
        requestId=request.requestId,
        timestamp=datetime.now(timezone.utc).isoformat()
    )

@app.post("/commands/send", response_model=TelecommandResponse)
async def send_telecommand(command: Telecommand):
    """Send a telecommand"""
    with store_lock:
        command_queue.append(command.dict())
    
    return TelecommandResponse(
        commandId=command.commandId,
        status="ACKNOWLEDGED",
        timestamp=datetime.now(timezone.utc).isoformat(),
        message=f"Telecommand {command.commandId} queued for transmission"
    )

@app.get("/commands/pending")
async def get_pending_commands():
    """Get pending telecommands"""
    with store_lock:
        return {
            "count": len(command_queue),
            "commands": command_queue[-10:]  # Last 10 commands
        }

@app.get("/statistics")
async def get_statistics():
    """Get service statistics"""
    with store_lock:
        packet_count = len(telemetry_store)
        param_count = len(parameter_store)
        
        if telemetry_store:
            apids = set()
            for packet in telemetry_store.values():
                apids.add(packet["header"]["apid"])
            
            return {
                "telemetry": {
                    "total_packets": packet_count,
                    "unique_apids": len(apids),
                    "latest_packet": max(telemetry_store.keys()),
                    "oldest_packet": min(telemetry_store.keys())
                },
                "parameters": {
                    "total_monitored": param_count,
                    "valid_parameters": sum(1 for p in parameter_store.values() if p["validity"] == "VALID")
                },
                "commands": {
                    "pending": len(command_queue)
                }
            }
        else:
            return {"message": "No telemetry received yet"}

if __name__ == "__main__":
    # Run without reload to avoid the warning
    uvicorn.run("mo_service:app", host="0.0.0.0", port=8000, reload=False)