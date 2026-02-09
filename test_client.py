# test_client.py
import requests
import json
import time
from datetime import datetime, timezone
import random

class CCSDSClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
    
    def check_service(self):
        """Check if service is running"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.json()
        except Exception as e:
            print(f"❌ Cannot connect to service: {e}")
            return None
    
    def display_dashboard(self):
        """Display a simple dashboard"""
        health = self.check_service()
        if not health:
            return False
        
        print("=" * 70)
        print("🚀 CCSDS MISSION OPERATIONS CLIENT")
        print("=" * 70)
        print(f"📡 Service: {health.get('status', 'unknown')}")
        print(f"📊 Packets: {health['statistics']['telemetry_packets_received']}")
        print(f"📈 Parameters: {health['statistics']['parameters_monitored']}")
        print(f"⚡ Receiver: {'ACTIVE' if health['receiver']['active'] else 'INACTIVE'}")
        print("=" * 70)
        return True
    
    def get_parameters_ccsds(self, parameter_names=None):
        """Get parameters using CCSDS standard interface"""
        if parameter_names is None:
            parameter_names = [
                "MEAS_TEMPERATURE_BUS",
                "MEAS_VOLTAGE_BUS",
                "MEAS_CURRENT_BUS",
                "HEALTH_STATUS",
                "SUBSYSTEM"
            ]
        
        request = {
            "parameterIds": parameter_names,
            "requestId": f"REQ_{int(datetime.now(timezone.utc).timestamp())}"
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/ccsds/parameters",
                json=request,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Error {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Request failed: {e}")
            return None
    
    def send_telecommand(self):
        """Send a sample telecommand"""
        command = {
            "commandId": f"TC_{int(datetime.now(timezone.utc).timestamp())}",
            "serviceType": 17,  # PUS Service 17: Test
            "serviceSubtype": 1,
            "parameters": {
                "test_mode": "DIAGNOSTIC",
                "duration": 60,
                "intensity": 75
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/commands/send",
                json=command
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Command failed: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Command error: {e}")
            return None
    
    def real_time_monitor(self, interval=5):
        """Monitor parameters in real-time"""
        print("\n📊 REAL-TIME PARAMETER MONITOR")
        print("   (Press Ctrl+C to stop)")
        print("-" * 70)
        
        try:
            while True:
                result = self.get_parameters_ccsds()
                
                if result:
                    print(f"\n🕒 {datetime.now().strftime('%H:%M:%S')}")
                    print(f"📋 Request ID: {result['requestId']}")
                    print("-" * 40)
                    
                    for param in result['parameters']:
                        status = "✅" if param['validity'] == "VALID" else "❌"
                        value_display = f"{param['value']} {param.get('units', '')}".strip()
                        print(f"{status} {param['name']:25} = {value_display:15} ({param['validity']})")
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n🛑 Monitoring stopped")
        except Exception as e:
            print(f"\n❌ Monitor error: {e}")
    
    def interactive_menu(self):
        """Interactive menu for testing"""
        while True:
            print("\n" + "=" * 50)
            print("CCSDS MO CLIENT - MAIN MENU")
            print("=" * 50)
            print("1. 📊 Display Service Dashboard")
            print("2. 📈 Get Parameters (CCSDS Standard)")
            print("3. 🚀 Send Telecommand")
            print("4. 📡 View Telemetry Packets")
            print("5. 🔄 Real-time Monitor")
            print("6. 📊 View Statistics")
            print("7. ❌ Exit")
            print("-" * 50)
            
            choice = input("Select option (1-7): ").strip()
            
            if choice == "1":
                self.display_dashboard()
                
            elif choice == "2":
                param_names_input = input("Enter parameter names (comma separated, or press Enter for default): ")
                if param_names_input.strip():
                    param_names = [p.strip() for p in param_names_input.split(",")]
                else:
                    param_names = None
                
                result = self.get_parameters_ccsds(param_names)
                if result:
                    print("\n📋 CCSDS GetParameterValues Response:")
                    print(json.dumps(result, indent=2))
            
            elif choice == "3":
                result = self.send_telecommand()
                if result:
                    print(f"\n✅ Command {result['commandId']}: {result['status']}")
                    print(f"   Message: {result.get('message', '')}")
            
            elif choice == "4":
                try:
                    response = requests.get(f"{self.base_url}/telemetry?limit=5")
                    if response.status_code == 200:
                        data = response.json()
                        print(f"\n📡 Latest {data['count']} telemetry packets:")
                        for pid, packet in data['packets'].items():
                            print(f"\nPacket {pid}:")
                            print(f"  APID: {packet['header']['apid']}")
                            print(f"  Type: {packet['header']['type']}")
                            print(f"  Time: {packet['timestamp']}")
                    else:
                        print(f"❌ Error: {response.status_code}")
                except Exception as e:
                    print(f"❌ Error: {e}")
            
            elif choice == "5":
                interval = input("Update interval in seconds (default 5): ").strip()
                try:
                    interval = float(interval) if interval else 5
                    self.real_time_monitor(interval=interval)
                except ValueError:
                    print("❌ Invalid interval, using default 5 seconds")
                    self.real_time_monitor()
            
            elif choice == "6":
                try:
                    response = requests.get(f"{self.base_url}/statistics")
                    if response.status_code == 200:
                        print("\n📊 Service Statistics:")
                        print(json.dumps(response.json(), indent=2))
                    else:
                        print(f"❌ Error: {response.status_code}")
                except Exception as e:
                    print(f"❌ Error: {e}")
            
            elif choice == "7":
                print("\n👋 Goodbye!")
                break
            
            else:
                print("❌ Invalid choice, please try again")
            
            input("\nPress Enter to continue...")

if __name__ == "__main__":
    client = CCSDSClient()
    
    # First check if service is running
    if client.check_service():
        client.interactive_menu()
    else:
        print("\n" + "=" * 60)
        print("⚠️  CCSDS MO Service not found!")
        print("=" * 60)
        print("Please start the MO Service first:")
        print("1. Open a new PowerShell window")
        print("2. Navigate to your project folder")
        print("3. Activate virtual environment:")
        print("   .\\venv\\Scripts\\activate")
        print("4. Run the MO Service:")
        print("   python mo_service.py")
        print("\nThen run this client again.")
        print("=" * 60)