#!/usr/bin/env python3
"""
AFC Schedule Monitor
Monitors the Ambassadors FC schedule for changes and sends notifications via ntfy.sh
"""

import requests
import json
import hashlib
import os
import sys
import re
from datetime import datetime
from bs4 import BeautifulSoup


SCHEDULE_URL = "https://system.gotsport.com/org_event/events/46853/schedules?team=3577069"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "afc-schedule-updates")
STATE_FILE = "schedule_state.json"


def fetch_schedule():
    """Fetch the schedule page content"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    response = requests.get(SCHEDULE_URL, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def parse_match_text(match_text):
    """Parse match text to extract structured data"""
    # Example format: "Manta United Soccer Club Manta 2014 Boys GLA (H)2:00 PM ESTNov 08, 2025Ambassadors FC (OH) Ambassadors FC 2014 Boys White (A)"

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
    # Look for team name that's not Ambassadors FC
    if '(H)' in match_text and '(A)' in match_text:
        # Split by date to get teams
        parts = match_text.split(match_info['date']) if match_info['date'] else [match_text]
        if len(parts) >= 1:
            # The home team is before the date
            home_part = parts[0]
            # Remove time if present
            if match_info['time']:
                home_part = home_part.replace(match_info['time'], '')
            # Remove score if present
            if match_info['score']:
                home_part = home_part.replace(match_info['score'], '')
            # Extract team name (ends with (H) or (A))
            home_team_match = re.search(r'([A-Z][^()]+?)\s*\([HA]\)', home_part)
            if home_team_match:
                home_team = home_team_match.group(1).strip()
                if 'Ambassadors FC' not in home_team:
                    match_info['opponent'] = home_team
                    match_info['location'] = 'Away'
                else:
                    # If home team is Ambassadors, opponent is away team
                    if len(parts) > 1:
                        away_part = parts[1] if len(parts) > 1 else ''
                        away_team_match = re.search(r'([A-Z][^()]+?)\s*\([HA]\)', away_part)
                        if away_team_match:
                            match_info['opponent'] = away_team_match.group(1).strip()
                            match_info['location'] = 'Home'

    return match_info


def parse_schedule(html_content):
    """Parse the schedule HTML and extract relevant information"""
    soup = BeautifulSoup(html_content, 'html.parser')

    schedule_data = {
        'matches': []
    }

    # Extract match information
    # Look for match/game containers (structure may vary)
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


def load_previous_state():
    """Load the previous schedule state"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return None


def save_state(data, data_hash):
    """Save the current schedule state"""
    state = {
        'hash': data_hash,
        'data': data,
        'timestamp': datetime.now().isoformat()
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def send_notification(title, message, priority="default", tags=None):
    """Send notification via ntfy.sh"""
    url = f"https://ntfy.sh/{NTFY_TOPIC}"

    headers = {
        "Priority": priority,
    }

    if tags:
        headers["Tags"] = ",".join(tags)

    # Send title and message in the body
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


def matches_equal(m1, m2):
    """Check if two matches are the same (ignoring score changes)"""
    return (m1.get('date') == m2.get('date') and
            m1.get('opponent') == m2.get('opponent'))


def detect_changes(old_data, new_data):
    """Detect what changed between old and new schedule data"""
    changes = []
    detailed_changes = []

    if old_data is None:
        # First run - list all matches
        new_matches = new_data.get('matches', [])
        detailed_changes.append(f"Initial schedule loaded with {len(new_matches)} match(es)")
        for match in new_matches:
            detailed_changes.append(f"  • {format_match(match)}")
        return changes, detailed_changes

    old_matches = old_data.get('matches', [])
    new_matches = new_data.get('matches', [])

    # Create lookup by date+opponent
    old_lookup = {(m.get('date'), m.get('opponent')): m for m in old_matches}
    new_lookup = {(m.get('date'), m.get('opponent')): m for m in new_matches}

    old_keys = set(old_lookup.keys())
    new_keys = set(new_lookup.keys())

    # Find added matches
    added_keys = new_keys - old_keys
    if added_keys:
        changes.append(f"Added: {len(added_keys)} match(es)")
        for key in sorted(added_keys):
            match = new_lookup[key]
            detailed_changes.append(f"✅ NEW MATCH: {format_match(match)}")

    # Find removed matches
    removed_keys = old_keys - new_keys
    if removed_keys:
        changes.append(f"Removed: {len(removed_keys)} match(es)")
        for key in sorted(removed_keys):
            match = old_lookup[key]
            detailed_changes.append(f"❌ REMOVED: {format_match(match)}")

    # Find modified matches (same date+opponent, but other details changed)
    common_keys = old_keys & new_keys
    for key in sorted(common_keys):
        old_match = old_lookup[key]
        new_match = new_lookup[key]

        match_changes = []

        # Check time change
        if old_match.get('time') != new_match.get('time'):
            match_changes.append(f"Time: {old_match.get('time', 'TBD')} → {new_match.get('time', 'TBD')}")

        # Check score change
        if old_match.get('score') != new_match.get('score'):
            match_changes.append(f"Score: {old_match.get('score', 'TBD')} → {new_match.get('score', 'TBD')}")

        # Check location change
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


def main():
    print(f"Checking schedule at {datetime.now().isoformat()}")

    try:
        # Fetch and parse schedule
        html_content = fetch_schedule()
        schedule_data = parse_schedule(html_content)
        current_hash = calculate_hash(schedule_data)

        # Load previous state
        previous_state = load_previous_state()
        previous_hash = previous_state['hash'] if previous_state else None

        # Check for changes
        if current_hash != previous_hash:
            print("Schedule has changed!")

            changes, detailed_changes = detect_changes(
                previous_state['data'] if previous_state else None,
                schedule_data
            )

            # Send notification
            title = "⚽ AFC Schedule Updated!"

            # Build message with detailed changes
            if detailed_changes:
                changes_text = '\n'.join(detailed_changes)
            else:
                changes_text = '\n'.join(f'• {change}' for change in changes)

            message = f"""The Ambassadors FC schedule has been updated.

{changes_text}

View schedule: {SCHEDULE_URL}

Last checked: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

            send_notification(
                title=title,
                message=message,
                priority="high",
                tags=["soccer", "warning"]
            )

            # Save new state
            save_state(schedule_data, current_hash)
            print("State updated and notification sent")
        else:
            print("No changes detected")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

        # Send error notification
        try:
            send_notification(
                title="❌ AFC Monitor Error",
                message=f"Failed to check schedule: {str(e)}",
                priority="low",
                tags=["warning", "error"]
            )
        except:
            pass

        return 1


if __name__ == "__main__":
    sys.exit(main())
