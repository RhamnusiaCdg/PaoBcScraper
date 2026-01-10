import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pickle
import os
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import re

# Προαιρετικά: Φόρτωσε .env αρχείο για local development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # Δεν υπάρχει python-dotenv, χρησιμοποίησε system env vars

# ==========================================================
# ΡΥΘΜΙΣΕΙΣ
# ==========================================================
# Βάλε εδώ το δικό σου Calendar ID (ή χρησιμοποίησε environment variable)
CALENDAR_ID = os.environ.get('CALENDAR_ID', 'primary')
SCOPES = ['https://www.googleapis.com/auth/calendar']
BASE_URL = "https://www.paobc.gr/schedule/page/"

def authenticate_google_calendar():
    """Authenticate and return Google Calendar service"""
    creds = None
    
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    service = build('calendar', 'v3', credentials=creds)
    return service

def scrape_pao_schedule():
    """Scrape Panathinaikos BC schedule from all pages"""
    all_matches = []
    seen_matches = set()  # Track unique matches
    page = 1
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    while True:
        if page == 1:
            url = "https://www.paobc.gr/schedule/"
        else:
            url = f"{BASE_URL}{page}/"
        
        print(f"Σάρωση σελίδας {page}: {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all game divs
            matches = soup.find_all('div', class_='game')
            
            if not matches:
                print(f"Δεν βρέθηκαν αγώνες στη σελίδα {page}")
                break
            
            for match in matches:
                try:
                    # Extract match details
                    data_div = match.find('div', class_='game__data')
                    header_div = match.find('div', class_='game__header')
                    
                    # Get competition
                    competition = data_div.find('div', class_='game__data__league').text.strip()
                    
                    # Get date and time
                    date_div = data_div.find('div', class_='game__data__date')
                    date_spans = date_div.find_all('span')
                    date_text = date_spans[0].text.strip() if len(date_spans) > 0 else ''
                    time_text = date_spans[1].text.strip() if len(date_spans) > 1 else ''
                    
                    # Get venue
                    venue_div = data_div.find('div', class_='game__data__stadium')
                    venue = venue_div.text.strip() if venue_div else 'ΟΑΚΑ'
                    
                    # Get teams
                    name_div = header_div.find('div', class_='game__header__name')
                    team_spans = name_div.find_all('span')
                    home_team = team_spans[0].text.strip() if len(team_spans) > 0 else ''
                    away_team = team_spans[1].text.strip() if len(team_spans) > 1 else ''
                    
                    # Create unique identifier to detect duplicates
                    match_id = f"{home_team}|{away_team}|{date_text}"
                    
                    # Skip if we've already seen this exact match
                    if match_id in seen_matches:
                        print(f"⏭️ Παράλειψη διπλότυπου: {home_team} vs {away_team} στις {date_text}")
                        continue
                    
                    seen_matches.add(match_id)
                    
                    match_data = {
                        'date': date_text,
                        'time': time_text,
                        'home_team': home_team,
                        'away_team': away_team,
                        'competition': competition,
                        'venue': venue
                    }
                    
                    all_matches.append(match_data)
                    print(f"Βρέθηκε: {home_team} vs {away_team} στις {date_text}")
                    
                except AttributeError as e:
                    print(f"Σφάλμα ανάλυσης αγώνα: {e}")
                    continue
            
            page += 1
            
            # Stop after 5 pages to avoid too many requests
            if page > 5:
                break
            
        except requests.RequestException as e:
            print(f"Σφάλημα φόρτωσης σελίδας {page}: {e}")
            break
    
    return all_matches

def parse_match_datetime(date_text, time_text):
    """Parse date/time to datetime object"""
    try:
        # Greek day names to remove
        greek_days = ['Δευτέρα', 'Τρίτη', 'Τετάρτη', 'Πέμπτη', 'Παρασκευή', 'Σάββατο', 'Κυριακή']
        
        # Remove Greek day names
        for day in greek_days:
            date_text = date_text.replace(day + ',', '').replace(day, '')
        
        # Greek month mapping
        greek_months = {
            'Ιανουαρίου': 'January', 'Ιαν': 'January',
            'Φεβρουαρίου': 'February', 'Φεβ': 'February',
            'Μαρτίου': 'March', 'Μαρ': 'March',
            'Απριλίου': 'April', 'Απρ': 'April',
            'Μαΐου': 'May', 'Μάι': 'May',
            'Ιουνίου': 'June', 'Ιουν': 'June',
            'Ιουλίου': 'July', 'Ιουλ': 'July',
            'Αυγούστου': 'August', 'Αυγ': 'August',
            'Σεπτεμβρίου': 'September', 'Σεπ': 'September',
            'Οκτωβρίου': 'October', 'Οκτ': 'October',
            'Νοεμβρίου': 'November', 'Νοε': 'November',
            'Δεκεμβρίου': 'December', 'Δεκ': 'December'
        }
        
        # English month mapping
        english_months = {
            'January': '01', 'February': '02', 'March': '03', 'April': '04',
            'May': '05', 'June': '06', 'July': '07', 'August': '08',
            'September': '09', 'October': '10', 'November': '11', 'December': '12',
            'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
            'Jun': '06', 'Jul': '07', 'Aug': '08', 'Sep': '09',
            'Oct': '10', 'Nov': '11', 'Dec': '12'
        }
        
        # Replace Greek months with English
        for greek, english in greek_months.items():
            date_text = date_text.replace(greek, english)
        
        # Remove English day names too
        english_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        for day in english_days:
            date_text = date_text.replace(day + ',', '').replace(day, '')
        
        # Clean up the date text
        date_text = date_text.strip().replace(',', '')
        
        # Parse different date formats
        parts = date_text.split()
        if len(parts) >= 3:
            day = parts[0]
            month = parts[1]
            year = parts[2]
            
            # Convert month name to number
            month_num = english_months.get(month, month)
            
            # Parse time - Default ώρα 21:15 αν δεν υπάρχει ή είναι σκορ
            time = time_text.strip()
            if not time or ':' not in time or len(time) > 5:
                time = "21:15"
            
            # Parse datetime
            datetime_str = f"{day}/{month_num}/{year} {time}"
            match_datetime = datetime.strptime(datetime_str, "%d/%m/%Y %H:%M")
            
            return match_datetime
        
        return None
        
    except Exception as e:
        print(f"Σφάλμα ανάλυσης ημερομηνίας '{date_text} {time_text}': {e}")
        return None

def create_match_key(match_data, match_datetime):
    """Create unique key for a match: teams + date"""
    date_str = match_datetime.strftime('%Y-%m-%d')
    return f"{match_data['home_team']}|{match_data['away_team']}|{date_str}"

def add_or_update_match(service, match_data, existing_calendar_events):
    """Add match to calendar if it doesn't exist, or update if time changed"""
    try:
        match_datetime = parse_match_datetime(match_data['date'], match_data['time'])
        
        if not match_datetime:
            print(f"Παράλειψη αγώνα λόγω σφάλματος ημερομηνίας: {match_data}")
            return None
        
        # Create unique key for this match
        match_key = create_match_key(match_data, match_datetime)
        
        # Διάρκεια 2 ώρες (ώστε να μην ξεπερνά την ημέρα)
        end_datetime = match_datetime + timedelta(hours=2)
        
        # Emoji ☘️🏀 στον τίτλο + ημερομηνία για μοναδικότητα
        date_str = match_datetime.strftime('%d/%m')
        summary = f"☘️🏀 {match_data['home_team']} - {match_data['away_team']} [{date_str}]"
        
        # Check if this exact match already exists in calendar
        event_to_update = None
        for existing in existing_calendar_events:
            existing_summary = existing.get('summary', '')
            existing_start = existing.get('start', {}).get('dateTime', '')
            
            if existing_start and (match_data['home_team'] in existing_summary and 
                                   match_data['away_team'] in existing_summary):
                existing_dt = datetime.fromisoformat(existing_start.replace('Z', '+00:00'))
                existing_dt = existing_dt.replace(tzinfo=None)
                
                # Same date? Then it's the same match
                if existing_dt.date() == match_datetime.date():
                    # Check if time changed
                    if existing_dt.time() == match_datetime.time():
                        # Same time - no update needed
                        print(f"ℹ️ ΥΠΑΡΧΕΙ ΗΔΗ: {summary} ({match_datetime.strftime('%d/%m/%Y %H:%M')})")
                        return match_key
                    else:
                        # Time changed - need to update
                        event_to_update = existing
                        break
        
        # Create event data
        event = {
            'summary': summary,
            'location': match_data['venue'],
            'description': f"Διοργάνωση: {match_data['competition']}",
            'start': {
                'dateTime': match_datetime.isoformat(),
                'timeZone': 'Europe/Athens',
            },
            'end': {
                'dateTime': end_datetime.isoformat(),
                'timeZone': 'Europe/Athens',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 60},
                ],
            },
        }
        
        if event_to_update:
            # Update existing event
            existing_time = datetime.fromisoformat(event_to_update['start']['dateTime'].replace('Z', '+00:00')).strftime('%H:%M')
            service.events().update(
                calendarId=CALENDAR_ID, 
                eventId=event_to_update['id'], 
                body=event
            ).execute()
            print(f"🔄 ΕΝΗΜΕΡΩΣΗ ΩΡΑ: {summary} ({existing_time} → {match_datetime.strftime('%H:%M')})")
        else:
            # Insert new event
            service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
            print(f"✅ ΠΡΟΣΤΕΘΗΚΕ: {summary} ({match_datetime.strftime('%d/%m/%Y %H:%M')})")
        
        return match_key
        
    except Exception as e:
        print(f"Σφάλμα προσθήκης αγώνα στο ημερολόγιο: {e}")
        return None

def get_all_pao_events(service):
    """Get all PAO basketball events from calendar"""
    try:
        # Get events from 6 months ago to 18 months in the future
        # This covers the entire basketball season
        time_min = (datetime.now() - timedelta(days=180)).isoformat() + 'Z'
        time_max = (datetime.now() + timedelta(days=540)).isoformat() + 'Z'
        
        print(f"   Αναζήτηση από {(datetime.now() - timedelta(days=180)).strftime('%d/%m/%Y')} έως {(datetime.now() + timedelta(days=540)).strftime('%d/%m/%Y')}")
        
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=2500,  # Αυξάνουμε το όριο
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        all_events = events_result.get('items', [])
        
        # Filter only PAO basketball events (with ☘️🏀 or basketball teams)
        pao_events = []
        for event in all_events:
            summary = event.get('summary', '')
            # Check if it's a basketball event (has emoji or team names)
            if '🏀' in summary or 'ΠΑΟ' in summary.upper() or 'PANATHINAIKOS' in summary.upper():
                pao_events.append(event)
        
        return pao_events
        
    except Exception as e:
        print(f"Σφάλμα ανάκτησης events από ημερολόγιο: {e}")
        return []

def delete_obsolete_events(service, valid_match_keys, calendar_events):
    """Delete events that are no longer in the website schedule"""
    deleted_count = 0
    
    for event in calendar_events:
        try:
            summary = event.get('summary', '')
            existing_start = event.get('start', {}).get('dateTime', '')
            
            if not existing_start:
                continue
            
            # Parse teams from summary
            # Format: "☘️🏀 TEAM1 - TEAM2 [dd/mm]"
            if ' - ' in summary:
                teams_part = summary.replace('☘️', '').replace('🏀', '').strip()
                
                # Remove date part [dd/mm] if exists
                if '[' in teams_part:
                    teams_part = teams_part.split('[')[0].strip()
                
                parts = teams_part.split(' - ')
                if len(parts) == 2:
                    home_team = parts[0].strip()
                    away_team = parts[1].strip()
                    
                    # Get date
                    existing_dt = datetime.fromisoformat(existing_start.replace('Z', '+00:00'))
                    existing_dt = existing_dt.replace(tzinfo=None)
                    date_str = existing_dt.strftime('%Y-%m-%d')
                    
                    # Create key
                    event_key = f"{home_team}|{away_team}|{date_str}"
                    
                    # Check if this event is in valid matches
                    if event_key not in valid_match_keys:
                        # Delete this event
                        service.events().delete(calendarId=CALENDAR_ID, eventId=event['id']).execute()
                        print(f"🗑️ ΔΙΑΓΡΑΦΗ (δεν υπάρχει πια): {summary} ({existing_dt.strftime('%d/%m/%Y %H:%M')})")
                        deleted_count += 1
        
        except Exception as e:
            print(f"⚠️ Σφάλμα διαγραφής event: {e}")
            continue
    
    return deleted_count

def main():
    """Main function with 2-phase sync"""
    print("🏀 Έναρξη Panathinaikos BC Schedule Scraper...")
    print("=" * 60)
    
    # Authenticate Google Calendar
    print("🔐 Έλεγχος ταυτότητας Google Calendar...")
    service = authenticate_google_calendar()
    
    # PHASE 0: Get existing calendar events
    print("📅 Ανάκτηση υπαρχόντων events από ημερολόγιο...")
    existing_calendar_events = get_all_pao_events(service)
    print(f"   Βρέθηκαν {len(existing_calendar_events)} υπάρχοντα events")
    
    # PHASE 1: Scrape schedule from website
    print(f"\n🌐 Σάρωση προγράμματος από {BASE_URL}...")
    matches = scrape_pao_schedule()
    
    print("=" * 60)
    print(f"📊 Βρέθηκαν {len(matches)} αγώνες στο site\n")
    
    # PHASE 2: Add/update matches from website
    print("🔄 ΦΑΣΗ 1: Συγχρονισμός αγώνων από το site...")
    print("-" * 60)
    
    processed_count = 0
    valid_match_keys = set()
    
    for match in matches:
        match_key = add_or_update_match(service, match, existing_calendar_events)
        if match_key:
            valid_match_keys.add(match_key)
            processed_count += 1
    
    # PHASE 3: Delete events that no longer exist on website
    print("\n🗑️ ΦΑΣΗ 2: Διαγραφή αγώνων που δεν υπάρχουν πια στο site...")
    print("-" * 60)
    
    deleted_count = delete_obsolete_events(service, valid_match_keys, existing_calendar_events)
    
    print("\n" + "=" * 60)
    print(f"✅ Ολοκληρώθηκε!")
    print(f"   • Επεξεργάστηκαν: {processed_count} αγώνες")
    print(f"   • Διαγράφηκαν: {deleted_count} (ακυρώθηκαν/μετακινήθηκαν)")
    print("=" * 60)

if __name__ == "__main__":
    main()