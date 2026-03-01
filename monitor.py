#!/usr/bin/env python3
"""
AFC Schedule Monitor
Monitors one or more GotSport schedule URLs for changes and sends notifications via ntfy.sh
"""

import requests
import json
import hashlib
import os
import sys
import re
from datetime import datetime
from bs4 import BeautifulSoup


# Each entry: (label, url, state_file)
SCHEDULES = [
    (
        "AFC 2014 Boys White",
        "https://system.gotsport.com/org_event/events/46853/schedules?team=3577069",
        "schedule_state_46853_3577069.json",
    ),
    (
        "AFC 2014 Boys GLA",
        "https://system.gotsport.com/org_event/events/43157/schedules?team=3151579",
        "schedule_state_43157_3151579.json",
    ),
]

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "afc-schedule-updates")


def fetch_schedule(url):
    """Fetch the schedule page content"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def parse_match_text(match_text):
    """Parse match text to extract structured data"""
    match_info = {
        'raw': match_text,
        'opponent': None,
        'date': None,
        'time': None,
        'score': None,
        'location': None
    }

    # Extract date (e.g., "Nov 08, 2025")
    date_match = re.search(r'([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})', match_text)
    if date_match:
        match_info['date'] = date_match.group(1)

    # Extract time (e.g., "2:00 PM EST")
    time_match = re.search(r'(\d{1,2}:\d{2}\s+[AP]M\s+[A-Z]{3})', match_text)
    if time_match:
        match_info['time'] = time_match.group(1)

    # Extract score (e.g., "2 - 2")
    score_match = re.search(r'(\d+\s*-\s*\d+)', match_text)
    if score_match:
        match_info['score'] = score_match.group(1)

    # Extract opponent (team name before date/time, excluding "Ambassadors FC")
    if '(H)' in match_text and '(A)' in match_text:
        parts = match_text.split(match_info['date']) if match_info['date'] else [match_text]
        if len(parts) >= 1:
            home_part = parts[0]
            if match_info['time']:
                home_part = home_part.replace(match_info['time'], '')
            if match_info['score']:
                home_part = home_part.replace(match_info['score'], '')
            home_team_match = re.search(r'([A-Z][^()]+?)\s*\([HA]\)', home_part)
            if home_team_match:
                home_team = home_team_match.group(1).strip()
                if 'Ambassadors FC' not in home_team:
                    match_info['opponent'] = home_team
                    match_info['location'] = 'Away'
                else:
                    if len(parts) > 1:
                        away_part = parts[1]
                        away_team_match = re.search(r'([A-Z][^()]+?)\s*\([HA]\)', away_part)
                        if away_team_match:
                            match_info['opponent'] = away_team_match.group(1).strip()
                            match_info['location'] = 'Home'

    return match_info


def parse_schedule(html_content):
    """Parse the schedule HTML and extract relevant information"""
    soup = BeautifulSoup(html_content, 'html.parser')

    schedule_data = {'matches': []}

    matches = soup.find_all(['div', 'tr'], class_=lambda x: x and any(
        keyword in str(x).lower() for keyword in ['game', 'match', 'schedule-row']
    ))

    for match in matches:
        text = match.get_text(strip=True)
        if text and ('Ambassadors FC' in text or 'Nov' in text or 'Dec' in text):
            match_info = parse_match_text(text)
            schedule_data['matches'].append(match_info)

    return schedule_data


def calculate_hash(data):
    """Calculate hash of the schedule data"""
    json_str = json.dumps(data, sort_keys=True)
    return hashlib.sha256(json_str.encode()).hexdigest()


def load_previous_state(state_file):
    """Load the previous schedule state"""
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            return json.load(f)
    return None


def save_state(state_file, data, data_hash):
    """Save the current schedule state"""
    state = {
        'hash': data_hash,
        'data': data,
        'timestamp': datetime.now().isoformat()
    }
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)


def send_notification(title, message, priority="default", tags=None):
    """Send notification via ntfy.sh"""
    url = f"https://ntfy.sh/{NTFY_TOPIC}"

    headers = {"Priority": priority}
    if tags:
        headers["Tags"] = ",".join(tags)

    full_message = f"{title}\n\n{message}"
    response = requests.post(url, data=full_message.encode('utf-8'), headers=headers)
    response.raise_for_status()
    print(f"Notification sent: {title}")


def format_match(match_info):
    """Format match info for display"""
    parts = []
    if match_info.get('opponent'):
        parts.append(f"vs {match_info['opponent']}")
    if match_info.get('date'):
        parts.append(f"on {match_info['date']}")
    if match_info.get('time'):
        parts.append(f"at {match_info['time']}")
    if match_info.get('location'):
        parts.append(f"({match_info['location']})")
    if match_info.get('score'):
        parts.append(f"[Score: {match_info['score']}]")
    return ' '.join(parts) if parts else match_info.get('raw', 'Unknown match')


def detect_changes(old_data, new_data):
    """Detect what changed between old and new schedule data"""
    changes = []
    detailed_changes = []

    if old_data is None:
        new_matches = new_data.get('matches', [])
        detailed_changes.append(f"Initial schedule loaded with {len(new_matches)} match(es)")
        for match in new_matches:
            detailed_changes.append(f"  • {format_match(match)}")
        return changes, detailed_changes

    old_matches = old_data.get('matches', [])
    new_matches = new_data.get('matches', [])

    old_lookup = {(m.get('date'), m.get('opponent')): m for m in old_matches}
    new_lookup = {(m.get('date'), m.get('opponent')): m for m in new_matches}

    old_keys = set(old_lookup.keys())
    new_keys = set(new_lookup.keys())

    added_keys = new_keys - old_keys
    if added_keys:
        changes.append(f"Added: {len(added_keys)} match(es)")
        for key in sorted(added_keys):
            detailed_changes.append(f"✅ NEW MATCH: {format_match(new_lookup[key])}")

    removed_keys = old_keys - new_keys
    if removed_keys:
        changes.append(f"Removed: {len(removed_keys)} match(es)")
        for key in sorted(removed_keys):
            detailed_changes.append(f"❌ REMOVED: {format_match(old_lookup[key])}")

    for key in sorted(old_keys & new_keys):
        old_match = old_lookup[key]
        new_match = new_lookup[key]
        match_changes = []

        if old_match.get('time') != new_match.get('time'):
            match_changes.append(f"Time: {old_match.get('time', 'TBD')} → {new_match.get('time', 'TBD')}")
        if old_match.get('score') != new_match.get('score'):
            match_changes.append(f"Score: {old_match.get('score', 'TBD')} → {new_match.get('score', 'TBD')}")
        if old_match.get('location') != new_match.get('location'):
            match_changes.append(f"Location: {old_match.get('location', 'TBD')} → {new_match.get('location', 'TBD')}")

        if match_changes:
            changes.append(f"Modified: {format_match(new_match)}")
            detailed_changes.append(f"🔄 UPDATED: {format_match(new_match)}")
            for change in match_changes:
                detailed_changes.append(f"    - {change}")

    if not changes:
        return ["No significant changes"], []

    return changes, detailed_changes


def check_schedule(label, url, state_file):
    """Check a single schedule URL for changes and notify if needed. Returns 0 on success, 1 on error."""
    print(f"\n--- Checking: {label} ---")
    try:
        html_content = fetch_schedule(url)
        schedule_data = parse_schedule(html_content)
        current_hash = calculate_hash(schedule_data)

        previous_state = load_previous_state(state_file)
        previous_hash = previous_state['hash'] if previous_state else None

        if current_hash != previous_hash:
            print("Schedule has changed!")

            changes, detailed_changes = detect_changes(
                previous_state['data'] if previous_state else None,
                schedule_data
            )

            title = f"⚽ AFC Schedule Updated — {label}"

            if detailed_changes:
                changes_text = '\n'.join(detailed_changes)
            else:
                changes_text = '\n'.join(f'• {change}' for change in changes)

            message = f"""The schedule has been updated.

{changes_text}

View schedule: {url}

Last checked: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

            send_notification(
                title=title,
                message=message,
                priority="high",
                tags=["soccer", "warning"]
            )

            save_state(state_file, schedule_data, current_hash)
            print("State updated and notification sent")
        else:
            print("No changes detected")

        return 0

    except Exception as e:
        print(f"Error checking {label}: {e}", file=sys.stderr)
        try:
            send_notification(
                title=f"❌ AFC Monitor Error — {label}",
                message=f"Failed to check schedule: {str(e)}",
                priority="low",
                tags=["warning", "error"]
            )
        except Exception:
            pass
        return 1


def main():
    print(f"Checking schedules at {datetime.now().isoformat()}")

    exit_code = 0
    for label, url, state_file in SCHEDULES:
        result = check_schedule(label, url, state_file)
        if result != 0:
            exit_code = result

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
