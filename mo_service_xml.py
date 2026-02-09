# mo_service_xml.py
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from contextlib import asynccontextmanager
import uvicorn
import xml.etree.ElementTree as ET
from xmlschema import XMLSchema
import json
import threading
import socket
import struct
import time

from xml_validator import CCSDSXMLValidator

app = FastAPI(
    title="CCSDS MO Services with XML Support",
    description="Full CCSDS MO Services implementation with XML schema validation",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Initialize validator
validator = CCSDSXMLValidator()

# Data stores
telemetry_store = {}
parameter_store = {}
command_queue = []
xml_requests = []
store_lock = threading.Lock()

# Models for JSON API
class JSONParameter(BaseModel):
    name: str
    value: Any
    timestamp: str
    validity: str = "VALID"
    units: Optional[str] = None

class JSONGetParameterValuesRequest(BaseModel):
    parameterIds: List[str]
    requestId: str

class JSONGetParameterValuesResponse(BaseModel):
    parameters: List[JSONParameter]
    requestId: str
    timestamp: str

# UDP Receiver (same as before)
class CCSDSReceiver(threading.Thread):
    def __init__(self, port=12345):
        super().__init__(daemon=True)
        self.port = port
        self.running = True
        
    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(('0.0.0.0', self.port))
        except OSError as e:
            print(f"[ERROR] Cannot bind to port {self.port}: {e}")
            return
            
        sock.settimeout(1.0)
        
        print(f"[INFO] CCSDS Receiver started on port {self.port}")
        
        while self.running:
            try:
                data, addr = sock.recvfrom(65535)
                # Process packet (simplified)
                with store_lock:
                    packet_id = len(telemetry_store)
                    telemetry_store[packet_id] = {
                        "source": addr[0],
                        "size": len(data),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[ERROR] Receiver error: {e}")
        
        sock.close()

receiver = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global receiver
    
    print("=" * 60)
    print("CCSDS MO Services with XML Support")
    print("=" * 60)
    print("XML Schema Validation: ENABLED")
    print("API Documentation: http://localhost:8001/docs")
    print("XML Endpoint: /xml/operations")
    print("=" * 60)
    
    receiver = CCSDSReceiver(port=12345)
    receiver.start()
    
    yield
    
    if receiver:
        receiver.stop()

app = FastAPI(
    title="CCSDS MO Services with XML Support",
    description="Full CCSDS MO Services implementation with XML schema validation",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# ===========================================
# JSON API Endpoints (Backward Compatible)
# ===========================================

@app.get("/")
async def root():
    return {
        "service": "CCSDS MO Services with XML Support",
        "version": "2.0.0",
        "xml_schema_version": "1.0",
        "endpoints": {
            "json_api": {
                "/json/parameters": "JSON GetParameterValues",
                "/json/telemetry": "JSON telemetry access"
            },
            "xml_api": {
                "/xml/operations": "XML CCSDS operations",
                "/xml/validate": "XML validation",
                "/xml/samples": "Sample XML documents"
            },
            "docs": {
                "/docs": "Swagger UI",
                "/redoc": "ReDoc documentation"
            }
        }
    }

@app.post("/json/parameters", response_model=JSONGetParameterValuesResponse)
async def json_get_parameter_values(request: JSONGetParameterValuesRequest):
    """JSON version of GetParameterValues"""
    parameters = []
    
    with store_lock:
        for param_id in request.parameterIds:
            param_id_upper = param_id.upper()
            
            if param_id_upper in parameter_store:
                param_data = parameter_store[param_id_upper]
                param = JSONParameter(
                    name=param_id_upper,
                    value=param_data["value"],
                    timestamp=param_data["timestamp"],
                    validity=param_data["validity"],
                    units=param_data.get("units")
                )
            else:
                param = JSONParameter(
                    name=param_id_upper,
                    value=None,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    validity="INVALID"
                )
            
            parameters.append(param)
    
    return JSONGetParameterValuesResponse(
        parameters=parameters,
        requestId=request.requestId,
        timestamp=datetime.now(timezone.utc).isoformat()
    )

# ===========================================
# XML API Endpoints
# ===========================================

@app.post("/xml/operations")
async def xml_operations(xml_content: str = Body(..., media_type="application/xml")):
    """
    Process CCSDS MO Service XML operations
    
    Supported operations:
    - GetParameterValuesRequest
    - SetParameterValuesRequest
    - GetServiceInfoRequest
    """
    
    # Validate XML
    validation_result = validator.validate_mo_xml(xml_content, "")
    
    if not validation_result["valid"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "XML validation failed",
                "errors": validation_result.get("errors", []),
                "operation": validation_result.get("operation", "unknown")
            }
        )
    
    # Parse XML to determine operation
    try:
        root = ET.fromstring(xml_content)
        
        # Extract request ID
        request_id_elem = root.find('.//{*}requestId')
        request_id = request_id_elem.text if request_id_elem is not None else "UNKNOWN"
        
        # Store request
        with store_lock:
            xml_requests.append({
                "request_id": request_id,
                "operation": validation_result["operation"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "xml": xml_content[:1000]  # Store first 1000 chars
            })
        
        # Process based on operation
        if "GetParameterValuesRequest" in validation_result["operation"]:
            return await _process_get_parameter_values_xml(root, request_id)
        
        elif "SetParameterValuesRequest" in validation_result["operation"]:
            return await _process_set_parameter_values_xml(root, request_id)
        
        elif "GetServiceInfoRequest" in validation_result["operation"]:
            return await _process_get_service_info_xml(root, request_id)
        
        else:
            raise HTTPException(
                status_code=501,
                detail=f"Operation not implemented: {validation_result['operation']}"
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"XML processing error: {str(e)}")

async def _process_get_parameter_values_xml(root: ET.Element, request_id: str) -> str:
    """Process GetParameterValuesRequest XML"""
    # Extract parameter IDs
    param_ids = []
    param_list = root.find('.//{*}parameterIdList')
    if param_list is not None:
        for param_elem in param_list.findall('.//{*}parameterId'):
            param_ids.append(param_elem.text)
    
    # Generate response XML
    response_dict = {
        "parameterList": {
            "parameter": []
        },
        "requestId": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": {
            "status": "SUCCESS"
        }
    }
    
    with store_lock:
        for param_id in param_ids:
            param_id_upper = param_id.upper() if param_id else ""
            
            if param_id_upper in parameter_store:
                param_data = parameter_store[param_id_upper]
                param_dict = {
                    "parameterId": param_id_upper,
                    "parameterValue": {
                        "floatValue": param_data["value"] if isinstance(param_data["value"], (int, float)) else 0.0
                    },
                    "validity": param_data["validity"],
                    "generationTime": param_data["timestamp"],
                    "qualityIndicator": "GOOD"
                }
            else:
                param_dict = {
                    "parameterId": param_id_upper,
                    "parameterValue": {
                        "stringValue": "NOT_FOUND"
                    },
                    "validity": "INVALID",
                    "generationTime": datetime.now(timezone.utc).isoformat(),
                    "qualityIndicator": "UNKNOWN"
                }
            
            response_dict["parameterList"]["parameter"].append(param_dict)
    
    # Convert to XML
    response_xml = validator.dict_to_xml(response_dict, "GetParameterValuesResponse")
    
    # Store response
    with store_lock:
        xml_requests.append({
            "request_id": request_id,
            "operation": "GetParameterValuesResponse",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "xml": response_xml[:1000]
        })
    
    return response_xml

async def _process_set_parameter_values_xml(root: ET.Element, request_id: str) -> str:
    """Process SetParameterValuesRequest XML"""
    # Extract parameter sets
    param_sets = []
    param_set_list = root.find('.//{*}parameterSetList')
    if param_set_list is not None:
        for param_set_elem in param_set_list.findall('.//{*}parameterSet'):
            param_id_elem = param_set_elem.find('.//{*}parameterId')
            param_value_elem = param_set_elem.find('.//{*}parameterValue')
            
            if param_id_elem is not None and param_value_elem is not None:
                param_sets.append({
                    "parameterId": param_id_elem.text,
                    "parameterValue": param_value_elem
                })
    
    # Generate response
    response_dict = {
        "parameterResultList": {
            "parameterResult": []
        },
        "requestId": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": {
            "status": "SUCCESS"
        }
    }
    
    for param_set in param_sets:
        result_dict = {
            "parameterId": param_set["parameterId"],
            "executionResult": {
                "status": "SUCCESS"
            },
            "completionTime": datetime.now(timezone.utc).isoformat()
        }
        response_dict["parameterResultList"]["parameterResult"].append(result_dict)
    
    response_xml = validator.dict_to_xml(response_dict, "SetParameterValuesResponse")
    
    # Store command
    with store_lock:
        command_queue.append({
            "request_id": request_id,
            "parameters": param_sets,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    return response_xml

async def _process_get_service_info_xml(root: ET.Element, request_id: str) -> str:
    """Process GetServiceInfoRequest XML"""
    service_info_dict = {
        "serviceInfo": {
            "serviceName": "CCSDS MO Services",
            "serviceType": "MONITOR_AND_CONTROL",
            "serviceVersion": "2.0.0",
            "description": "Full CCSDS MO Services implementation with XML support",
            "provider": "CCSDS Simulator Project",
            "supportedOperations": {
                "operation": [
                    {
                        "operationId": "GET_PARAMETER_VALUES",
                        "operationName": "GetParameterValues",
                        "description": "Retrieve parameter values from spacecraft"
                    },
                    {
                        "operationId": "SET_PARAMETER_VALUES",
                        "operationName": "SetParameterValues",
                        "description": "Set parameter values on spacecraft"
                    },
                    {
                        "operationId": "GET_SERVICE_INFO",
                        "operationName": "GetServiceInfo",
                        "description": "Retrieve service capabilities and information"
                    }
                ]
            }
        },
        "requestId": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": {
            "status": "SUCCESS"
        }
    }
    
    response_xml = validator.dict_to_xml(service_info_dict, "GetServiceInfoResponse")
    return response_xml

@app.post("/xml/validate")
async def validate_xml(xml_content: str = Body(..., media_type="application/xml")):
    """Validate XML against CCSDS schemas"""
    result = validator.validate_mo_xml(xml_content, "")
    
    if result["valid"]:
        # Convert to dictionary for display
        xml_dict = validator.xml_to_dict(xml_content)
        
        return {
            "valid": True,
            "operation": result.get("operation", "unknown"),
            "validation_warnings": result.get("validation_result", {}).get("warnings", []),
            "structure": xml_dict
        }
    else:
        return {
            "valid": False,
            "errors": result.get("errors", ["Unknown validation error"]),
            "operation": result.get("operation", "unknown")
        }

@app.get("/xml/samples/{operation}")
async def get_xml_sample(operation: str):
    """Get sample XML for a given operation"""
    sample = validator.generate_sample_xml(operation)
    
    if sample:
        return {
            "operation": operation,
            "xml": sample,
            "description": f"Sample {operation} XML document"
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"No sample available for operation: {operation}"
        )

@app.get("/xml/operations/history")
async def get_xml_operations_history(limit: int = 10):
    """Get history of XML operations"""
    with store_lock:
        history = xml_requests[-limit:] if len(xml_requests) > limit else xml_requests
    
    return {
        "count": len(history),
        "operations": history
    }

@app.get("/xml/schema/info")
async def get_schema_info():
    """Get information about loaded XML schemas"""
    return {
        "schemas_loaded": list(validator.schemas.keys()),
        "supported_operations": [
            "GetParameterValuesRequest",
            "GetParameterValuesResponse", 
            "SetParameterValuesRequest",
            "SetParameterValuesResponse",
            "GetServiceInfoRequest",
            "GetServiceInfoResponse"
        ],
        "schema_versions": {
            "ccsds_mo_services": "1.0",
            "ccsds_common_types": "1.0"
        }
    }

# ===========================================
# Health and Monitoring
# ===========================================

@app.get("/health")
async def health_check():
    """Comprehensive health check"""
    with store_lock:
        stats = {
            "telemetry_packets": len(telemetry_store),
            "parameters_monitored": len(parameter_store),
            "commands_pending": len(command_queue),
            "xml_requests_processed": len(xml_requests)
        }
    
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "statistics": stats,
        "xml_support": {
            "enabled": True,
            "validator_ready": len(validator.schemas) > 0,
            "schemas_loaded": len(validator.schemas)
        },
        "endpoints": {
            "xml_validation": "POST /xml/validate",
            "xml_operations": "POST /xml/operations",
            "xml_samples": "GET /xml/samples/{operation}",
            "json_api": "POST /json/parameters"
        }
    }

# Initialize with sample parameters
def initialize_sample_parameters():
    """Initialize with sample spacecraft parameters"""
    sample_params = {
        "TEMPERATURE_BUS": {
            "value": 25.5,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "validity": "VALID",
            "units": "C"
        },
        "VOLTAGE_BUS": {
            "value": 12.3,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "validity": "VALID",
            "units": "V"
        },
        "CURRENT_BUS": {
            "value": 2.5,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "validity": "VALID",
            "units": "A"
        },
        "MODE_SELECTION": {
            "value": "SAFE_MODE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "validity": "VALID",
            "units": ""
        },
        "BATTERY_CHARGE": {
            "value": 85,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "validity": "VALID",
            "units": "%"
        }
    }
    
    with store_lock:
        for name, data in sample_params.items():
            parameter_store[name.upper()] = data

# Initialize on import
initialize_sample_parameters()

if __name__ == "__main__":
    print("[INFO] Starting CCSDS MO Services with XML Support...")
    print("[INFO] Port: 8001 (to avoid conflict with JSON-only service)")
    print("[INFO] XML Schema Validation: ENABLED")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        reload=False
    )