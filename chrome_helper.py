import os
import sys
import time
import subprocess
import urllib.request

PORT = 9444
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA = r"d:\temp\Classroom\.chrome_isolated"

def ensure_chrome():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
        return
    except Exception:
        pass

    print("[*] Launching Chrome on port", PORT)
    cmd = [
        CHROME_EXE,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={USER_DATA}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://classroom.google.com"
    ]
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    subprocess.Popen(cmd, creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)
    for _ in range(15):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
            print("[+] Chrome ready on port", PORT)
            return
        except Exception:
            pass
    raise RuntimeError(f"Could not connect to Chrome on port {PORT}")
