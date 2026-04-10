
import subprocess
import sys
import os
import threading
import time

def run_backend():
    """Run the backend server"""
    try:
        print("Starting backend server...")
        backend_process = subprocess.Popen([sys.executable, "app.py"], 
                                         stdout=subprocess.PIPE, 
                                         stderr=subprocess.PIPE)
        return backend_process
    except Exception as e:
        print(f"Error starting backend: {e}")
        return None

def main():
    """Main runner function to start both backend and frontend"""
    print("Starting application runner...")
    
    # Start backend in a separate thread
    backend_process = run_backend()
    
    # Wait a moment for backend to start
    time.sleep(2)
    
    # Start frontend    
    try:
        print("Both servers are running. Press Ctrl+C to stop.")
        print("Backend: http://localhost:5000")
        print("Frontend: http://localhost:3000")
        
        # Keep the main thread alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutting down servers...")
        
        if backend_process:
            backend_process.terminate()
            backend_process.wait()
            
        print("Servers stopped.")

if __name__ == "__main__":
    main()