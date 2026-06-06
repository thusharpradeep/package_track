import os
import json
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

AWB_NUMBER = os.environ.get("AWB_NUMBER")
EMAIL_TO = os.environ.get("EMAIL_TO")
EMAIL_FROM = os.environ.get("EMAIL_FROM")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

STATE_FILE = "last_status.json"

def get_tracking_data():
    if not AWB_NUMBER:
        print("Missing AWB_NUMBER in environment")
        return None
        
    url = f"https://dlv-api.delhivery.com/v3/unified-tracking-new?wbn={AWB_NUMBER}"
    headers = {
        "Origin": "https://www.delhivery.com",
        "Referer": "https://www.delhivery.com/tracking",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return None
        
        data = response.json()
        if not data.get("data") or len(data["data"]) == 0:
            return None
            
        return data["data"][0]
    except Exception:
        return None

def extract_snapshot(data):
    status_info = data.get("status", {})
    tracking_states = data.get("trackingStates", [])
    
    # Typically latest scan is at index 0, or just extract the first available location
    latest_city = "Unknown"
    latest_hub = "Unknown"
    latest_remark = "Unknown"
    
    if tracking_states and len(tracking_states) > 0:
        latest_state = tracking_states[0]
        scans = latest_state.get("scans", [])
        if scans and len(scans) > 0:
            latest_scan = scans[0]
            latest_city = latest_scan.get("cityLocation", "Unknown")
            latest_hub = latest_scan.get("scannedLocation", "Unknown")
            latest_remark = latest_scan.get("scanNslRemark", "Unknown")
        
    return {
        "status": status_info.get("status"),
        "statusDateTime": status_info.get("statusDateTime"),
        "instructions": status_info.get("instructions"),
        "destination": data.get("destination"),
        "deliveryDate_v1": data.get("deliveryDate_v1"),
        "deliveryDate": data.get("deliveryDate"),
        "hqStatus": data.get("hqStatus"),
        "trackingStatesLength": len(tracking_states),
        "latestCity": latest_city,
        "latestHub": latest_hub,
        "latestRemark": latest_remark
    }

def detect_changes(old_state, new_state):
    changes = []
    if old_state.get("status") != new_state.get("status"):
        changes.append("Status updated")
    if old_state.get("instructions") != new_state.get("instructions"):
        changes.append("Instructions updated")
    if old_state.get("deliveryDate_v1") != new_state.get("deliveryDate_v1"):
        changes.append("Expected delivery range updated")
    if old_state.get("deliveryDate") != new_state.get("deliveryDate"):
        changes.append("Specific delivery date updated")
    if old_state.get("hqStatus") != new_state.get("hqStatus"):
        changes.append("High level status updated")
    if old_state.get("trackingStatesLength") != new_state.get("trackingStatesLength"):
        changes.append("New scan added")
    if old_state.get("latestRemark") != new_state.get("latestRemark"):
        changes.append("New remark (scanNslRemark) added")
        
    return changes

def send_email(changes, new_state):
    if not all([EMAIL_TO, EMAIL_FROM, EMAIL_APP_PASSWORD]):
        print("Missing email configuration, skipping email.")
        return

    subject = f"Delhivery Tracker: Package {AWB_NUMBER} Updated"
    body = f"""AWB Number: {AWB_NUMBER}

What changed:
- {chr(10) + '- '.join(changes)}

New Status: {new_state.get('status')}
Instructions: {new_state.get('instructions')}
Location: {new_state.get('latestCity')} ({new_state.get('latestHub')})
Remark: {new_state.get('latestRemark')}
Status Timestamp: {new_state.get('statusDateTime')}
Expected Delivery Range: {new_state.get('deliveryDate_v1')}
Specific Delivery Date: {new_state.get('deliveryDate')}
"""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(EMAIL_FROM, EMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Failed to send email: {e}")

def send_startup_email(new_state):
    if not all([EMAIL_TO, EMAIL_FROM, EMAIL_APP_PASSWORD]):
        print("Missing email configuration, skipping startup email.")
        return

    subject = f"Delhivery Tracker: Started for {AWB_NUMBER}"
    body = f"""The Delhivery package tracker is working, and currently at {new_state.get('latestCity')}!

AWB Number: {AWB_NUMBER}

Current Status: {new_state.get('status')}
Instructions: {new_state.get('instructions')}
Location: {new_state.get('latestCity')} ({new_state.get('latestHub')})
Remark: {new_state.get('latestRemark')}
Status Timestamp: {new_state.get('statusDateTime')}
Expected Delivery Range: {new_state.get('deliveryDate_v1')}
Specific Delivery Date: {new_state.get('deliveryDate')}
"""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(EMAIL_FROM, EMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Failed to send startup email: {e}")

def send_telegram(changes, new_state):
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        print("Missing Telegram configuration, skipping Telegram.")
        return
        
    changes_str = ", ".join(changes)
    msg = f"""📦 *Delhivery Update*
*AWB:* `{AWB_NUMBER}`

*Changes:* {changes_str}

*Status:* {new_state.get('status')}
*Instructions:* {new_state.get('instructions')}
*Location:* {new_state.get('latestCity')} ({new_state.get('latestHub')})
*Remark:* {new_state.get('latestRemark')}
*Timestamp:* {new_state.get('statusDateTime')}
*Expected Delivery:* {new_state.get('deliveryDate_v1') or new_state.get('deliveryDate')}
"""
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"Telegram API Error: {response.text}")
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def send_startup_telegram(new_state):
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        print("Missing Telegram configuration, skipping startup Telegram.")
        return
        
    msg = f"""🟢 *Delhivery Tracker Started*
*AWB:* `{AWB_NUMBER}`

The tracker is working, and currently at {new_state.get('latestCity')}.

*Status:* {new_state.get('status')}
*Instructions:* {new_state.get('instructions')}
*Location:* {new_state.get('latestCity')} ({new_state.get('latestHub')})
*Remark:* {new_state.get('latestRemark')}
*Timestamp:* {new_state.get('statusDateTime')}
*Expected Delivery:* {new_state.get('deliveryDate_v1') or new_state.get('deliveryDate')}
"""
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"Telegram API Error (Startup): {response.text}")
    except Exception as e:
        print(f"Failed to send startup Telegram message: {e}")

def main():
    data = get_tracking_data()
    if not data:
        return
        
    current_state = extract_snapshot(data)
    
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            old_state = json.load(f)
            
        changes = detect_changes(old_state, current_state)
        if changes:
            send_email(changes, current_state)
            send_telegram(changes, current_state)
    else:
        print("First run. Saving state, sending startup alerts (email + telegram).")
        send_startup_email(current_state)
        send_startup_telegram(current_state)
        
    with open(STATE_FILE, "w") as f:
        json.dump(current_state, f, indent=4)

if __name__ == "__main__":
    main()