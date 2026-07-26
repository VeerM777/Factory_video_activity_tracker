"""Root launcher script for Factory Video Analysis system.

Starts both the FastAPI backend server (port 8123) and Vite React frontend (port 5173).
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent

def main():
    print("=" * 60)
    print("  Factory Video Analysis System Launcher")
    print("=" * 60)
    
    backend_dir = ROOT / "backend"
    frontend_dir = ROOT / "frontend"
    
    print("\n[1/2] Starting Backend API Server (http://127.0.0.1:8123)...")
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8123", "--reload", "--reload-dir", "app"],
        cwd=str(backend_dir),
    )
    
    time.sleep(2)
    
    print("[2/2] Starting Frontend App (http://localhost:5173)...")
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    frontend_proc = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=str(frontend_dir),
    )
    
    print("\n" + "=" * 60)
    print("  ✅ BOTH SERVERS ARE RUNNING LIVE!")
    print("  👉 Web Studio UI : http://localhost:5173")
    print("  👉 Backend API   : http://127.0.0.1:8123/docs")
    print("  Press Ctrl+C in this terminal to stop both servers.")
    print("=" * 60 + "\n")
    
    try:
        backend_proc.wait()
        frontend_proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down servers...")
        backend_proc.terminate()
        frontend_proc.terminate()

if __name__ == "__main__":
    main()
