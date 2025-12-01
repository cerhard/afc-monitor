# AFC Schedule Monitor

Automated monitoring for Ambassadors FC soccer schedules with notifications via ntfy.sh.

## Overview

This GitHub Action automatically checks the Ambassadors FC schedule every 6 hours and sends push notifications to your phone when changes are detected.

## Features

- Runs automatically via GitHub Actions (every 6 hours)
- Detects schedule changes (new matches, updates, cancellations)
- Sends notifications to your phone via [ntfy.sh](https://ntfy.sh)
- No server required - runs entirely on GitHub infrastructure
- Manual trigger option for immediate checks

## Setup

### 1. Configure ntfy.sh Topic

Choose a unique topic name for your notifications. This will be your notification channel.

Example: `afc-ambassadors-2014-white-schedule`

### 2. Set GitHub Secret

1. Go to your repository **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `NTFY_TOPIC`
4. Value: Your chosen topic name (e.g., `afc-ambassadors-2014-white-schedule`)
5. Click **Add secret**

### 3. Subscribe to Notifications on Your Phone

1. Install the ntfy app:
   - [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
   - [iOS](https://apps.apple.com/us/app/ntfy/id1625396347)

2. Open the app and subscribe to your topic:
   - Tap the **+** button
   - Enter your topic name (the same one you used in the secret)
   - Tap **Subscribe**

3. You're done! You'll now receive notifications when the schedule updates.

### 4. Enable GitHub Actions

1. Go to the **Actions** tab in your repository
2. Enable workflows if prompted
3. The monitor will run automatically every 6 hours

## Usage

### Automatic Monitoring

The workflow runs automatically every 6 hours:
- 12:00 AM UTC
- 6:00 AM UTC
- 12:00 PM UTC
- 6:00 PM UTC

### Manual Check

To check for updates immediately:

1. Go to **Actions** tab
2. Select **Monitor AFC Schedule** workflow
3. Click **Run workflow** → **Run workflow**

### View Results

- Go to **Actions** tab to see all workflow runs
- Click on any run to see logs and details
- Check your phone for notifications when changes are detected

## Notification Examples

When a change is detected, you'll receive a notification like:

```
⚽ AFC Schedule Updated!

The Ambassadors FC schedule has been updated.

Changes detected:
• Added matches: 1

View schedule: https://system.gotsport.com/org_event/events/46853/schedules?team=3577069

Last checked: 2025-11-30 15:30:00
```

## Customization

### Change Check Frequency

Edit [.github/workflows/monitor-schedule.yml](.github/workflows/monitor-schedule.yml):

```yaml
schedule:
  - cron: '0 */6 * * *'  # Every 6 hours
```

Examples:
- Every 2 hours: `'0 */2 * * *'`
- Every hour: `'0 * * * *'`
- Every 30 minutes: `'*/30 * * * *'`
- Daily at 9 AM UTC: `'0 9 * * *'`

### Customize Notifications

Edit [monitor.py](monitor.py) to customize notification content, priority, or tags.

## How It Works

1. **Fetch**: Downloads the schedule page from GotSport
2. **Parse**: Extracts match and standings information
3. **Compare**: Compares with previous state (stored as GitHub artifact)
4. **Notify**: If changes detected, sends notification via ntfy.sh
5. **Store**: Saves current state for next comparison

## Troubleshooting

### Not receiving notifications?

1. Verify the `NTFY_TOPIC` secret is set correctly
2. Check that you're subscribed to the same topic in the ntfy app
3. Review workflow logs in the Actions tab for errors

### Want to test?

1. Run the workflow manually (see Manual Check above)
2. Check the workflow logs
3. Look for "Schedule has changed!" or "No changes detected" messages

## Local Testing

To test locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Set your ntfy topic
export NTFY_TOPIC="your-topic-name"

# Run the monitor
python monitor.py
```

## License

MIT
