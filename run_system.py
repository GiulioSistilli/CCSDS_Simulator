# run_system.py
import subprocess
import sys
import time
import os

def start_mo_service():
    """Start the MO Service"""
    print("🚀 Starting CCSDS MO Service...")
    return subprocess.Popen(
        [sys.executable, "mo_service.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

def start_simulator():
    """Start the Simulator"""
    print("📡 Starting CCSDS Simulator...")
    # Wait a bit for MO service to start
    time.sleep(3)
    return subprocess.Popen(
        [sys.executable, "simulator.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

def print_output(process, label):
    """Print output from a process"""
    for line in iter(process.stdout.readline, ''):
        print(f"[{label}] {line}", end='')
    process.stdout.close()

def main():
    print("=" * 60)
    print("🚀 CCSDS MO Services Complete System")
    print("=" * 60)
    print("\nStarting all components...")
    
    # Start MO Service
    mo_process = start_mo_service()
    time.sleep(5)  # Give it time to start
    
    # Check if MO Service started
    if mo_process.poll() is not None:
        # Process terminated
        stdout, stderr = mo_process.communicate()
        print("❌ MO Service failed to start!")
        print("STDOUT:", stdout)
        print("STDERR:", stderr)
        return
    
    print("✅ MO Service started successfully")
    print("\n📊 You can now access:")
    print("   API Documentation: http://localhost:8000/docs")
    print("   Service Health: http://localhost:8000/health")
    
    print("\n📡 Starting simulator in 5 seconds...")
    print("   (Press Ctrl+C to stop the system)")
    print("-" * 60)
    
    try:
        # Start simulator
        simulator_process = start_simulator()
        
        # Keep running until interrupted
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping system...")
        
        # Terminate processes
        if 'simulator_process' in locals():
            simulator_process.terminate()
        
        mo_process.terminate()
        
        print("✅ System stopped")
    
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()