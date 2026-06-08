import os
import json
import requests
import urllib3
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

EMAIL_TO = os.environ.get("EMAIL_TO")
EMAIL_FROM = os.environ.get("EMAIL_FROM")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

STATE_FILE = "cusat_status.json"
URL = "https://admissions.cusat.ac.in/?tag=archive"

KEYWORDS = ["rank list", "cat", "cat 2026", "msc", "502", "provisional rank list"]

def fetch_notifications():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://admissions.cusat.ac.in"
    }

    try:
        response = requests.get(URL, headers=headers, timeout=15, verify=False)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, "html.parser")
        # Find the table containing "ARCHIVED LATEST NEWS" or just the notification table
        # Since we don't have the exact HTML structure, we look for table rows.
        # Often it is in a table. Let's find all tables and check headers or just get the main news table.
        # Actually usually the news is in a scrollable div or table. We'll find a table where th says "Published Date"
        
        table = None
        for tbl in soup.find_all("table"):
            if "Published Date" in tbl.text and "News" in tbl.text:
                table = tbl
                break
        
        if not table:
            return None
            
        rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")
        
        notifications = []
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 2:
                date_td = cols[0]
                news_td = cols[1]
                link_tag = news_td.find("a")
                
                date_text = date_td.get_text(strip=True)
                news_text = news_td.get_text(strip=True)
                if not news_text and link_tag:
                    news_text = link_tag.get_text(strip=True)
                
                url = ""
                if link_tag and link_tag.has_attr("href"):
                    href = link_tag["href"]
                    # handle relative URLs
                    if href.startswith("http"):
                        url = href
                    else:
                        url = f"https://admissions.cusat.ac.in/{href.lstrip('/')}"
                
                if date_text and news_text:
                    notifications.append({
                        "date": date_text,
                        "text": news_text,
                        "url": url
                    })
        return notifications
    except Exception as e:
        print(f"Error fetching notifications: {e}")
        return None

def is_high_priority(text):
    text_lower = text.lower()
    for kw in KEYWORDS:
        if kw.lower() in text_lower:
            return True
    return False

def send_email(notification, is_hp):
    if not all([EMAIL_TO, EMAIL_FROM, EMAIL_APP_PASSWORD]):
        print("Missing Email configuration. Skipping email.")
        return

    prefix = "🚨 URGENT: " if is_hp else "📢 "
    subject = f"{prefix}New CUSAT Notification: {notification['date']}"
    
    note = "HIGH PRIORITY: Keywords matched for this notification.\n" if is_hp else ""
    
    body = f"""A new notification has been published on the CUSAT Admissions page.

{note}
Date: {notification['date']}
Text: {notification['text']}
Link: {notification['url']}
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

def send_telegram(notification, is_hp):
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        print("Missing Telegram configuration. Skipping Telegram.")
        return
        
    prefix = "🚨" if is_hp else "📢"
    note = "\n\n⚠️ *HIGH PRIORITY MATCH*" if is_hp else ""
    
    text = (f"{prefix} *New CUSAT Notification*\n\n"
            f"*Date:* {notification['date']}\n"
            f"*News:* [{notification['text']}]({notification['url']}){note}")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"Telegram API Error: {response.text}")
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def main():
    notifications = fetch_notifications()
    if not notifications:
        print("No notifications found or failed to parse.")
        return
        
    latest_notif = notifications[0]
    
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            old_notifications = json.load(f)
            
        old_latest = old_notifications[0] if old_notifications else {}
        
        if (latest_notif.get("date") != old_latest.get("date") or 
            latest_notif.get("text") != old_latest.get("text")):
            
            # Additional check: Make sure we don't alert twice if it somehow was in the list earlier
            # but usually topmost is sufficient as per requirements. We'll trigger on any NEW top notification.
            print("New notification detected! Sending alerts.")
            is_hp = is_high_priority(latest_notif["text"])
            send_email(latest_notif, is_hp)
            send_telegram(latest_notif, is_hp)
        else:
            print("No new notification.")
    else:
        print("First run. Saving state and sending initial alert for the topmost notification.")
        is_hp = is_high_priority(latest_notif["text"])
        send_email(latest_notif, is_hp)
        send_telegram(latest_notif, is_hp)
        
    with open(STATE_FILE, "w") as f:
        json.dump(notifications, f, indent=4)

if __name__ == "__main__":
    main()
