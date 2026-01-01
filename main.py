"""
Valorant Match Notifier
-----------------------
A lightweight utility that monitors the local Riot Client API to detect
Valorant queue states and sends Discord notifications via Webhook.

Author: [Your Name/GitHub Username]
License: MIT
"""

import os
import json
import base64
import time
import sys
import requests
import urllib3

# Disable insecure request warnings for local API polling
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURATION ---
CONFIG_FILE = "config.json"
POLL_INTERVAL = 2.0  
GITHUB_LINK = "https://github.com/37xWy/Valorant-Match-Notifier" 

# --- TRANSLATION TABLES ---
MAP_NAMES = {
    # Standard Maps
    "/Game/Maps/Infinity/Infinity": "Abyss",     
    "/Game/Maps/Ascent/Ascent": "Ascent",
    "/Game/Maps/Duality/Duality": "Bind",
    "/Game/Maps/Foxtrot/Foxtrot": "Breeze",
    "/Game/Maps/Rook/Rook": "Corrode",           
    "/Game/Maps/Canyon/Canyon": "Fracture",
    "/Game/Maps/Triad/Triad": "Haven",
    "/Game/Maps/Port/Port": "Icebox",
    "/Game/Maps/Jam/Jam": "Lotus",
    "/Game/Maps/Pitt/Pitt": "Pearl",
    "/Game/Maps/Bonsai/Bonsai": "Split",
    "/Game/Maps/Juliett/Juliett": "Sunset",

    # Team Deathmatch (TDM)
    "/Game/Maps/HURM/HURM_Alley/HURM_Alley": "District",
    "/Game/Maps/HURM/HURM_Helix/HURM_Helix": "Drift",
    "/Game/Maps/HURM/HURM_HighTide/HURM_HighTide": "Glitch",
    "/Game/Maps/HURM/HURM_Bowl/HURM_Bowl": "Kasbah",
    "/Game/Maps/HURM/HURM_Yard/HURM_Yard": "Piazza",

    # Training
    "/Game/Maps/PovegliaV2/RangeV2": "Range"
}

QUEUE_NAMES = {
    "hurm": "Team Deathmatch",
    "deathmatch": "Deathmatch",
    "spikerush": "Spike Rush",
    "competitive": "Competitive",
    "unrated": "Unrated",
    "swiftplay": "Swiftplay",
    "ggteam": "Escalation",
    "onefa": "Replication",
    "snowball": "Snowball Fight"
}

def load_or_create_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                if "webhook_url" in config:
                    return config
        except: pass

    print("\n" + "="*40)
    print("      VALORANT MATCH NOTIFIER")
    print("="*40)
    print("\n[!] Setup Required")
    print("1. Go to your Discord Server settings.")
    print("2. Integrations -> Webhooks -> New Webhook.")
    print("3. Copy the Webhook URL.")
    
    while True:
        url = input("\n👉 Paste Webhook URL: ").strip()
        if url.startswith("http"): break
        print("❌ Invalid URL. Must start with 'http'.")

    config = {"webhook_url": url}
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    return config

def get_lockfile_credentials():
    path = os.path.join(os.getenv('LOCALAPPDATA'), R'Riot Games\Riot Client\Config\lockfile')
    if not os.path.exists(path): return None
    try:
        with open(path, 'r') as f:
            data = f.read().split(':')
        return {
            'base_url': f"https://127.0.0.1:{data[2]}",
            'auth': base64.b64encode(f"riot:{data[3]}".encode()).decode()
        }
    except: return None

def send_notification(webhook_url, message):
    try:
        payload = {"content": message, "username": "ValoNotifier"}
        requests.post(webhook_url, json=payload)
    except: pass

def resolve_map_name(decoded):
    raw_map = decoded.get("matchMap", "")
    if not raw_map and "matchPresenceData" in decoded:
        raw_map = decoded["matchPresenceData"].get("matchMap", "")
    return MAP_NAMES.get(raw_map, raw_map) 

# --- HELPER TO FETCH LATEST DATA ---
def fetch_presence_data(session, creds, puuid):
    try:
        resp = session.get(f"{creds['base_url']}/chat/v4/presences", headers={"Authorization": f"Basic {creds['auth']}"}, timeout=2)
        if resp.status_code != 200: return None
        
        data = resp.json()
        my_presence = next((p for p in data['presences'] if p['puuid'] == puuid), None)
        
        if my_presence and 'private' in my_presence:
            blob = my_presence['private']
            blob += '=' * (-len(blob) % 4)
            return json.loads(base64.b64decode(blob).decode('utf-8'))
    except: pass
    return None

def main():
    config = load_or_create_config()
    webhook_url = config['webhook_url']
    
    print("\n✅ Watching for Valorant match...")
    print(f"🔗 Check for updates at: {GITHUB_LINK}")

    last_loop_state = "Unknown"
    last_party_state = "Unknown"
    
    session = requests.Session()
    session.verify = False 

    while True:
        try:
            creds = get_lockfile_credentials()
            if not creds:
                sys.stdout.write(f"\r💤 Waiting for Valorant...{' '*20}")
                sys.stdout.flush()
                time.sleep(5)
                continue

            # 1. Get PUUID
            try:
                resp = session.get(f"{creds['base_url']}/chat/v1/session", headers={"Authorization": f"Basic {creds['auth']}"}, timeout=2)
                if resp.status_code == 200: my_puuid = resp.json().get('puuid')
                else: raise Exception()
            except: 
                time.sleep(POLL_INTERVAL); continue

            # 2. Get Presence
            decoded = fetch_presence_data(session, creds, my_puuid)
            if not decoded:
                time.sleep(POLL_INTERVAL); continue

            # --- PARSE STATE ---
            loop_state = decoded.get("sessionLoopState", "MENUS")
            if "matchPresenceData" in decoded:
                deep_state = decoded["matchPresenceData"].get("sessionLoopState")
                if deep_state: loop_state = deep_state

            party_state = "DEFAULT"
            if "partyPresenceData" in decoded:
                party_state = decoded["partyPresenceData"].get("partyState", "DEFAULT")

            current_map = resolve_map_name(decoded)
            
            # --- UI LOGIC ---
            status_text = f"[Active] State: {loop_state} | Party: {party_state}"
            if loop_state != "MENUS":
                map_display = current_map if current_map else "Loading..."
                status_text += f" | Map: {map_display}"
            
            sys.stdout.write(f"\r{status_text.ljust(80)}")
            sys.stdout.flush()

            # --- NOTIFICATION TRIGGERS ---

            # 1. Queue Started
            if party_state == "MATCHMAKING" and last_party_state != "MATCHMAKING":
                raw_q_id = decoded.get("queueId", "Unknown")
                if "matchPresenceData" in decoded and raw_q_id == "Unknown":
                    raw_q_id = decoded["matchPresenceData"].get("queueId", "Unknown")
                friendly_q_id = QUEUE_NAMES.get(raw_q_id, raw_q_id)
                
                print(f"\n[Event] Queue Started: {friendly_q_id}")
                send_notification(webhook_url, f"⏳ **Queue Started!**\nMode: `{friendly_q_id}`")

            # 2. Queue Cancelled (Dequeue)
            elif last_party_state == "MATCHMAKING" and party_state == "DEFAULT" and loop_state == "MENUS":
                print(f"\n[Event] Queue Cancelled")
                send_notification(webhook_url, "🛑 **Queue Cancelled**")

            # 3. Match Found (Agent Select)
            elif loop_state == "PREGAME" and last_loop_state != "PREGAME":
                # INCREASED RETRY LIMIT (4 -> 12)
                retries = 0
                while not current_map and retries < 12:
                    time.sleep(1)
                    new_decoded = fetch_presence_data(session, creds, my_puuid)
                    if new_decoded:
                        current_map = resolve_map_name(new_decoded)
                    retries += 1
                
                map_label = current_map if current_map else "Unknown Map"
                print(f"\n[Event] Match Found: {map_label}")
                
                future_time = int(time.time() + 80)
                send_notification(webhook_url, f"🚨 **MATCH FOUND!**\n🗺️ Map: **{map_label}**\n⏳ Lock in <t:{future_time}:R>!")

            # 4. Match Started (Instant)
            elif loop_state == "INGAME" and last_loop_state != "INGAME":
                 print(f"\n[Event] Match Started: {current_map}")
                 send_notification(webhook_url, f"✅ **Match Started!**\n🗺️ Map: **{current_map}**\n*Glhf!*")

            # 5. Returned to Menus
            elif loop_state == "MENUS" and last_loop_state == "INGAME":
                print("\n[Event] Returned to Menus")
                send_notification(webhook_url, "🏠 Welcome back to Lobby.")

            last_loop_state = loop_state
            last_party_state = party_state

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt: sys.exit()
        except: time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()