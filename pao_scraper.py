import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import json
import base64
import os
import sys
from google.oauth2 import service_account
from googleapiclient.discovery import build
import logging
import re

# ==========================================================
# DEBUG SETTINGS
# ==========================================================
DEBUG_MODE = True

# ==========================================================
# LOGGING SETUP
# ==========================================================
logging.basicConfig(
    level=logging.DEBUG if DEBUG_MODE else logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ==========================================================
# ENVIRONMENT SETUP
# ==========================================================
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==========================================================
# ΡΥΘΜΙΣΕΙΣ
# ==========================================================
CALENDAR_ID = os.environ.get("CALENDAR_ID", "primary")
SCOPES = ["https://www.googleapis.com/auth/calendar"]
BASE_URL = "https://www.paobc.gr/schedule/page/"
MAX_PAGES = 10
REQUEST_TIMEOUT = 15


def normalize_team_name(name):
    if not name:
        return ""
    name = re.sub(r'[^\w\s-]', '', str(name), flags=re.UNICODE)
    suffixes = [" BC", " AKTOR", " ATHENS", " OPAP"]
    for suffix in suffixes:
        name = name.replace(suffix, "")
    name = name.strip().upper()
    name = re.sub(r'\s+', ' ', name)
    return name


def authenticate_google_calendar():
    logger.info("Έλεγχος ταυτότητας Google Calendar...")
    try:
        if os.getenv('SERVICE_ACCOUNT_KEY'):
            logger.info("Φόρτωση credentials από environment variable")
            service_account_info = json.loads(
                base64.b64decode(os.getenv('SERVICE_ACCOUNT_KEY'))
            )
            logger.info(f"Service Account Email: {service_account_info.get('client_email')}")
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=SCOPES
            )
        elif os.path.exists('service-account-key.json'):
            logger.info("Φόρτωση credentials από αρχείο")
            with open('service-account-key.json', 'r') as f:
                service_account_info = json.load(f)
            logger.info(f"Service Account Email: {service_account_info.get('client_email')}")
            credentials = service_account.Credentials.from_service_account_file(
                'service-account-key.json',
                scopes=SCOPES
            )
        else:
            raise FileNotFoundError("Δεν βρέθηκαν service account credentials!")
        
        service = build("calendar", "v3", credentials=credentials)
        
        try:
            calendar_list = service.calendarList().list().execute()
            logger.debug("Calendars που έχει πρόσβαση:")
            for calendar in calendar_list.get('items', []):
                logger.debug(f"   • {calendar.get('summary')} (ID: {calendar.get('id')})")
        except Exception as e:
            logger.warning(f"Δεν μπόρεσα να πάρω τη λίστα των calendars: {e}")
        
        logger.info("✓ Επιτυχής ταυτοποίηση")
        return service
        
    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Σφάλμα ταυτοποίησης: {e}")
        sys.exit(1)


def scrape_pao_schedule():
    all_matches = []
    seen_matches = set()
    page = 1
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    consecutive_empty_pages = 0

    logger.info(f"Έναρξη σάρωσης από {BASE_URL}")

    while page <= MAX_PAGES:
        if page == 1:
            url = "https://www.paobc.gr/schedule/"
        else:
            url = f"{BASE_URL}{page}/"

        logger.debug(f"Σάρωση σελίδας {page}: {url}")

        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            matches = soup.find_all("div", class_="game")

            if not matches:
                consecutive_empty_pages += 1
                logger.warning(f"Δεν βρέθηκαν αγώνες στη σελίδα {page}")
                if consecutive_empty_pages >= 2:
                    logger.info(f"Τερματισμός: {consecutive_empty_pages} συνεχόμενες κενές σελίδες")
                    break
                page += 1
                continue
            
            consecutive_empty_pages = 0
            matches_on_page = 0

            for match in matches:
                try:
                    data_div = match.find("div", class_="game__data")
                    header_div = match.find("div", class_="game__header")

                    if not data_div or not header_div:
                        continue

                    competition = data_div.find("div", class_="game__data__league").text.strip()

                    date_div = data_div.find("div", class_="game__data__date")
                    date_spans = date_div.find_all("span")
                    date_text = date_spans[0].text.strip() if len(date_spans) > 0 else ""
                    time_text = date_spans[1].text.strip() if len(date_spans) > 1 else ""

                    venue_div = data_div.find("div", class_="game__data__stadium")
                    venue = venue_div.text.strip() if venue_div else "ΟΑΚΑ"

                    name_div = header_div.find("div", class_="game__header__name")
                    team_spans = name_div.find_all("span")
                    home_team = team_spans[0].text.strip() if len(team_spans) > 0 else ""
                    away_team = team_spans[1].text.strip() if len(team_spans) > 1 else ""

                    match_id = f"{home_team}|{away_team}|{date_text}"

                    if match_id in seen_matches:
                        logger.debug(f"⏭️ Παράλειψη διπλότυπου: {home_team} vs {away_team}")
                        continue

                    seen_matches.add(match_id)

                    match_data = {
                        "date": date_text,
                        "time": time_text,
                        "home_team": home_team,
                        "away_team": away_team,
                        "competition": competition,
                        "venue": venue,
                    }

                    all_matches.append(match_data)
                    matches_on_page += 1
                    logger.debug(f"Βρέθηκε: {home_team} vs {away_team} στις {date_text}")

                except AttributeError as e:
                    logger.warning(f"Σφάλμα ανάλυσης αγώνα: {e}")
                    continue

            logger.info(f"✓ Σελίδα {page}: {matches_on_page} αγώνες")
            page += 1

        except requests.Timeout:
            logger.error(f"Timeout στη σελίδα {page} - Προσπαθούμε την επόμενη...")
            page += 1
            continue
        except requests.RequestException as e:
            logger.error(f"Σφάλμα δικτύου στη σελίδα {page}: {e}")
            if all_matches:
                logger.warning(f"Συνέχεια με {len(all_matches)} αγώνες που βρέθηκαν μέχρι τώρα")
                break
            else:
                logger.error("Κρίσιμο σφάλμα: Δεν βρέθηκαν αγώνες")
                sys.exit(1)

    logger.info(f"📊 Σύνολο: {len(all_matches)} μοναδικοί αγώνες από {page-1} σελίδες")
    return all_matches


def parse_match_datetime(date_text, time_text):
    try:
        greek_days = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"]
        for day in greek_days:
            date_text = date_text.replace(day + ",", "").replace(day, "")

        greek_months = {
            "Ιανουαρίου": "January", "Ιαν": "January",
            "Φεβρουαρίου": "February", "Φεβ": "February",
            "Μαρτίου": "March", "Μαρ": "March",
            "Απριλίου": "April", "Απρ": "April",
            "Μαΐου": "May", "Μάι": "May",
            "Ιουνίου": "June", "Ιουν": "June",
            "Ιουλίου": "July", "Ιουλ": "July",
            "Αυγούστου": "August", "Αυγ": "August",
            "Σεπτεμβρίου": "September", "Σεπ": "September",
            "Οκτωβρίου": "October", "Οκτ": "October",
            "Νοεμβρίου": "November", "Νοε": "November",
            "Δεκεμβρίου": "December", "Δεκ": "December",
        }

        english_months = {
            "January": "01", "February": "02", "March": "03",
            "April": "04", "May": "05", "June": "06",
            "July": "07", "August": "08", "September": "09",
            "October": "10", "November": "11", "December": "12",
            "Jan": "01", "Feb": "02", "Mar": "03",
            "Apr": "04", "Jun": "06", "Jul": "07",
            "Aug": "08", "Sep": "09", "Oct": "10",
            "Nov": "11", "Dec": "12",
        }

        for greek, english in greek_months.items():
            date_text = date_text.replace(greek, english)

        english_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for day in english_days:
            date_text = date_text.replace(day + ",", "").replace(day, "")

        date_text = date_text.strip().replace(",", "")

        parts = date_text.split()
        if len(parts) >= 3:
            day = parts[0]
            month = parts[1]
            year = parts[2]

            month_num = english_months.get(month, month)

            time = time_text.strip()
            if not time or ":" not in time or len(time) > 5:
                time = "21:15"

            datetime_str = f"{day}/{month_num}/{year} {time}"
            match_datetime = datetime.strptime(datetime_str, "%d/%m/%Y %H:%M")

            return match_datetime

        return None

    except Exception as e:
        logger.warning(f"Σφάλμα ανάλυσης ημερομηνίας '{date_text} {time_text}': {e}")
        return None


def create_match_identifier(match_data, match_datetime):
    home_normalized = normalize_team_name(match_data['home_team'])
    away_normalized = normalize_team_name(match_data['away_team'])
    teams_sorted = sorted([home_normalized, away_normalized])
    
    if match_datetime:
        date_part = match_datetime.strftime("%Y-%m-%d")
        return f"{teams_sorted[0]}|{teams_sorted[1]}|{date_part}"
    
    return f"{teams_sorted[0]}|{teams_sorted[1]}"


def extract_teams_from_event(event):
    summary = event.get("summary", "")
    
    logger.debug(f"📝 EXTRACTING FROM SUMMARY: '{summary}'")
    
    clean_summary = re.sub(r'[^\w\s\-\[\]]', ' ', summary, flags=re.UNICODE)
    clean_summary = re.sub(r'\s+', ' ', clean_summary).strip()
    
    logger.debug(f"📝 CLEANED SUMMARY: '{clean_summary}'")
    
    if " - " in clean_summary:
        if "[" in clean_summary:
            clean_summary = clean_summary.split("[")[0].strip()
        
        parts = clean_summary.split(" - ")
        if len(parts) >= 2:
            home_team = parts[0].strip()
            away_team = parts[1].strip()
            
            logger.debug(f"📝 EXTRACTED: '{home_team}' vs '{away_team}'")
            return home_team, away_team
    
    logger.debug(f"📝 FAILED TO EXTRACT from: '{summary}'")
    return None, None


def get_existing_events_map(calendar_events):
    events_map = {}
    
    logger.info(f"🔍 Processing {len(calendar_events)} calendar events...")
    
    for i, event in enumerate(calendar_events, 1):
        try:
            event_start = event.get("start", {}).get("dateTime", "")
            summary = event.get("summary", "")
            
            logger.debug(f"  [{i}] Event: '{summary}' at {event_start}")
            
            if not event_start:
                logger.debug(f"     ⚠️ No start time, skipping")
                continue
                
            home_team, away_team = extract_teams_from_event(event)
            if not home_team or not away_team:
                logger.debug(f"     ⚠️ Could not extract teams, skipping")
                continue
            
            home_normalized = normalize_team_name(home_team)
            away_normalized = normalize_team_name(away_team)
            teams_sorted = sorted([home_normalized, away_normalized])
            
            event_datetime = datetime.fromisoformat(
                event_start.replace("Z", "+00:00")
            ).replace(tzinfo=None)
            
            date_key = event_datetime.strftime("%Y-%m-%d")
            event_key = f"{teams_sorted[0]}|{teams_sorted[1]}|{date_key}"
            
            events_map[event_key] = {
                "event": event,
                "datetime": event_datetime,
                "original_home": home_team,
                "original_away": away_team
            }
            
            logger.debug(f"     ✅ Mapped as: {event_key}")
            
        except Exception as e:
            logger.warning(f"Σφάλμα επεξεργασίας event: {e}")
            continue
    
    logger.info(f"📊 Created events map with {len(events_map)} entries")
    
    logger.debug("📋 All event keys in map:")
    for key in sorted(events_map.keys()):
        logger.debug(f"   - {key}")
    
    return events_map


def create_event_data(match_data, match_datetime):
    date_str = match_datetime.strftime("%d/%m")
    summary = f"☘️🏀 {match_data['home_team']} - {match_data['away_team']} [{date_str}]"
    end_datetime = match_datetime + timedelta(hours=2)
    
    return {
        "summary": summary,
        "location": match_data.get("venue", "ΟΑΚΑ"),
        "description": f"Διοργάνωση: {match_data.get('competition', 'Ελληνικό Πρωτάθλημα')}",
        "start": {
            "dateTime": match_datetime.isoformat(),
            "timeZone": "Europe/Athens",
        },
        "end": {
            "dateTime": end_datetime.isoformat(),
            "timeZone": "Europe/Athens",
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 60},
            ],
        },
    }


def sync_match_with_calendar(service, match_data, existing_events_map):
    try:
        match_datetime = parse_match_datetime(match_data["date"], match_data["time"])
        if not match_datetime:
            logger.warning(f"Παράλειψη αγώνα: {match_data['home_team']} vs {match_data['away_team']}")
            return False, None

        home_normalized = normalize_team_name(match_data['home_team'])
        away_normalized = normalize_team_name(match_data['away_team'])
        teams_sorted = sorted([home_normalized, away_normalized])
        date_key = match_datetime.strftime("%Y-%m-%d")
        match_key = f"{teams_sorted[0]}|{teams_sorted[1]}|{date_key}"
        
        logger.debug(f"🔑 Match key: {match_key}")
        
        event_data = create_event_data(match_data, match_datetime)
        
        if match_key in existing_events_map:
            existing_info = existing_events_map[match_key]
            existing_event = existing_info["event"]
            existing_datetime = existing_info["datetime"]
            
            time_diff = abs((existing_datetime - match_datetime).total_seconds())
            
            if time_diff < 60:
                logger.debug(f"ℹ️ Υπάρχει ήδη: {match_data['home_team']} vs {match_data['away_team']}")
                return True, match_key
            else:
                existing_time_str = existing_datetime.strftime("%H:%M")
                new_time_str = match_datetime.strftime("%H:%M")
                
                service.events().update(
                    calendarId=CALENDAR_ID, 
                    eventId=existing_event["id"], 
                    body=event_data
                ).execute()
                
                logger.info(f"🔄 ΕΝΗΜΕΡΩΣΗ: {match_data['home_team']} vs {match_data['away_team']} ({existing_time_str} → {new_time_str})")
                return True, match_key
        else:
            service.events().insert(
                calendarId=CALENDAR_ID, 
                body=event_data
            ).execute()
            
            logger.info(f"✅ ΠΡΟΣΘΗΚΗ: {match_data['home_team']} vs {match_data['away_team']} ({match_datetime.strftime('%d/%m/%Y %H:%M')})")
            return True, match_key
            
    except Exception as e:
        logger.error(f"Σφάλμα συγχρονισμού αγώνα: {e}")
        return False, None


def get_all_pao_events(service):
    try:
        time_min = (datetime.now() - timedelta(days=180)).isoformat() + "Z"
        time_max = (datetime.now() + timedelta(days=540)).isoformat() + "Z"

        logger.info(f"Αναζήτηση events από {(datetime.now() - timedelta(days=180)).strftime('%d/%m/%Y')} έως {(datetime.now() + timedelta(days=540)).strftime('%d/%m/%Y')}")

        events_result = (
            service.events()
            .list(
                calendarId=CALENDAR_ID,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=2500,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        all_events = events_result.get("items", [])

        pao_events = []
        for event in all_events:
            summary = event.get("summary", "")
            if ("🏀" in summary or "☘️" in summary or "ΠΑΟ" in summary.upper() or 
                "PANATHINAIKOS" in summary.upper() or 
                (" - " in summary and any(x in summary.upper() for x in ["VS", "VS.", "ΑΓΩΝΑΣ", "ΑΓΩΝΑ"]))):
                pao_events.append(event)

        logger.info(f"✓ Βρέθηκαν {len(pao_events)} PAO basketball events")
        return pao_events

    except Exception as e:
        logger.error(f"Σφάλμα ανάκτησης events: {e}")
        return []


def delete_obsolete_events(service, website_match_keys, existing_events_map):
    deleted_count = 0
    
    logger.info(f"🔍 Έλεγχος {len(existing_events_map)} events για διαγραφή...")
    logger.info(f"📋 Keys από website: {len(website_match_keys)}")
    
    logger.debug("=== Website Match Keys ===")
    for key in sorted(website_match_keys):
        logger.debug(f"  - {key}")
    
    logger.debug("\n=== Calendar Event Keys ===")
    for key in sorted(existing_events_map.keys()):
        logger.debug(f"  - {key}")
    
    for event_key, event_info in list(existing_events_map.items()):
        if event_key not in website_match_keys:
            try:
                event = event_info["event"]
                event_datetime = event_info["datetime"]
                home_team = event_info.get("original_home", "Unknown")
                away_team = event_info.get("original_away", "Unknown")
                
                logger.info(f"🎯 Θα διαγραφεί: {event_key}")
                logger.info(f"   Teams: {home_team} vs {away_team}")
                logger.info(f"   Time: {event_datetime.strftime('%d/%m/%Y %H:%M')}")
                
                service.events().delete(
                    calendarId=CALENDAR_ID, 
                    eventId=event["id"]
                ).execute()
                
                logger.info(f"🗑️ ΔΙΑΓΡΑΦΗ: {home_team} vs {away_team} ({event_datetime.strftime('%d/%m/%Y %H:%M')})")
                deleted_count += 1
                
                del existing_events_map[event_key]
                
            except Exception as e:
                logger.warning(f"Σφάλμα διαγραφής: {e}")
                continue
        else:
            logger.debug(f"✅ Κρατάμε: {event_key}")
    
    return deleted_count


def main():
    logger.info("=" * 70)
    logger.info("🏀 Panathinaikos BC Schedule Scraper - Έναρξη")
    logger.info(f"📅 CALENDAR_ID: {CALENDAR_ID}")
    
    if os.getenv('SERVICE_ACCOUNT_KEY'):
        logger.info("🔑 Χρήση: GitHub Secrets")
    elif os.path.exists('service-account-key.json'):
        with open('service-account-key.json', 'r') as f:
            sa_info = json.load(f)
        logger.info(f"🔑 Χρήση: Local File - {sa_info.get('client_email')}")
    else:
        logger.warning("⚠️ Δεν βρέθηκαν credentials!")
    
    logger.info("=" * 70)

    service = authenticate_google_calendar()

    logger.info("\n📅 ΦΑΣΗ 0: Ανάκτηση υπαρχόντων events...")
    logger.info("-" * 70)
    existing_calendar_events = get_all_pao_events(service)
    existing_events_map = get_existing_events_map(existing_calendar_events)

    logger.info(f"\n🌐 ΦΑΣΗ 1: Σάρωση προγράμματος από paobc.gr...")
    logger.info("-" * 70)
    website_matches = scrape_pao_schedule()

    if not website_matches:
        logger.error("❌ Δεν βρέθηκαν αγώνες - τερματισμός")
        sys.exit(1)

    logger.info(f"\n🔄 ΦΑΣΗ 2: Συγχρονισμός {len(website_matches)} αγώνων...")
    logger.info("-" * 70)

    synced_count = 0
    website_match_keys = set()
    
    for match in website_matches:
        synced, match_key = sync_match_with_calendar(service, match, existing_events_map)
        if synced and match_key:
            synced_count += 1
            website_match_keys.add(match_key)
    
    logger.info(f"Συγχρονίστηκαν {synced_count} από {len(website_matches)} αγώνες")
    logger.info(f"Μοναδικά keys: {len(website_match_keys)}")

    logger.info(f"\n🗑️ ΦΑΣΗ 3: Έλεγχος για διαγραφές...")
    logger.info("-" * 70)

    deleted_count = delete_obsolete_events(service, website_match_keys, existing_events_map)

    logger.info("\n" + "=" * 70)
    logger.info("✅ ΟΛΟΚΛΗΡΩΘΗΚΕ!")
    logger.info(f"   • Αγώνες στο site: {len(website_matches)}")
    logger.info(f"   • Συγχρονίστηκαν: {synced_count}")
    logger.info(f"   • Διαγράφηκαν: {deleted_count}")
    logger.info(f"   • Υπόλοιπα events: {len(existing_events_map)}")
    logger.info("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("\n⚠️ Διακόπηκε από τον χρήστη")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n❌ Κρίσιμο σφάλμα: {e}", exc_info=True)
        sys.exit(1)