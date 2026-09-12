#!/usr/bin/env python3

import os
import sys
import subprocess
import socket
import urllib.request
import json

def print_step(msg):
    print(f"[\033[94mINFO\033[0m] {msg}")

def print_pass(msg):
    print(f"[\033[92mPASS\033[0m] {msg}")

def print_fail(msg, critical=True):
    print(f"[\033[91mFAIL\033[0m] {msg}")
    if critical:
        sys.exit(1)

def print_warn(msg):
    print(f"[\033[93mWARN\033[0m] {msg}")

def check_command(cmd, name):
    try:
        subprocess.run([cmd, "--version"], capture_output=True, text=True, check=True)
        print_pass(f"{name} is installed.")
    except FileNotFoundError:
        print_fail(f"{name} is not installed or not in PATH.")

def check_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.bind(("0.0.0.0", port))
            print_pass(f"Port {port} is available.")
        except OSError:
            print_fail(f"Port {port} is already in use. Please free this port before starting CIRA.")

def check_env():
    if not os.path.exists("Backend/.env") and not os.getenv("OPENROUTER_API_KEY"):
        print_warn("No OPENROUTER_API_KEY found in environment or Backend/.env. The agent will run in deterministic mode (fallback mode).")
    else:
        print_pass("API key configuration found.")

def check_docker():
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
        print_pass("Docker is running.")
    except Exception:
        print_warn("Docker daemon is not running or accessible. You will need it if you want to deploy via docker-compose.")

def main():
    print("="*50)
    print("  CIRA Doctor - Environment Validation Tool")
    print("="*50)
    print("")
    
    print_step("Checking prerequisites...")
    check_command("python3", "Python 3")
    check_command("npm", "Node.js (npm)")
    
    print_step("Checking Docker...")
    check_docker()
    
    print_step("Checking ports...")
    check_port(8000)
    check_port(3000)
    check_port(5432)
    
    print_step("Checking environment configuration...")
    check_env()
    
    print("")
    print("="*50)
    print("\033[92mAll critical checks passed! CIRA is ready to be installed.\033[0m")
    print("Run \033[96mdocker-compose up -d\033[0m to deploy the application.")
    print("="*50)

if __name__ == "__main__":
    main()
