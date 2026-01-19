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
# LOGGING SETUP
# ==========================================================
logging.basicConfig(
    level=logging.INFO,
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
    """
    Normalize team names for comparison
    Αφαιρεί emojis, suffixes (BC, AKTOR), και κάνει uppercase
    """
    if not name:
        return ""
    # Αφαίρεση όλων των emojis
    name = re.sub(r'[^\w\s-]', '', str(name), flags=re.UNICODE)
    
    # Αφαίρεση κοινών suffixes
    suffixes = [" BC", " AKTOR", " ATHENS", " OPAP", " BC", " AKTOR"]
    for suffix in suffixes:
        name = name.replace(suffix, "")
    
    # Uppercase και trim
    name = name.strip().upper()
    
    # Αντικατάσταση πολλαπλών κενών με ένα
    name = re.sub(r'\s+', ' ', name)
    
    return name


def authenticate_google_calendar():
    """
    Authenticate with Google Calendar using Service Account
    Δεν χρειάζεται ΠΟΤΕ ανανέωση token!
    """
    logger.info("Έλεγχος ταυτότητας Google Calendar (Service Account)...")
    
    try:
        # Προσπάθεια φόρτωσης από environment variable (GitHub Actions)
        if os.getenv('SERVICE_ACCOUNT_KEY'):
            logger.info("Φόρτωση credentials από environment variable")
            service_account_info = json.loads(
                base64.b64decode(os.getenv('SERVICE_ACCOUNT_KEY'))
            )
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=SCOPES
            )
        
        # Προσπάθεια φόρτωσης από αρχείο (local development)
        elif os.path.exists('service-account-key.json'):
            logger.info("Φόρτωση credentials από αρχείο")
            credentials = service_account.Credentials.from_service_account_file(
                'service-account-key.json',
                scopes=SCOPES
            )
        
        else:
            raise FileNotFoundError(
                "Δεν βρέθηκαν service account credentials! "
                "Βάλε το service-account-key.json στο directory ή "
                "όρισε το SERVICE_ACCOUNT_KEY environment variable"
            )
        
        service = build("calendar", "v3", credentials=credentials)
        logger.info("✓ Επιτυχής ταυτοποίηση με Service Account")
        return service
        
    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Σφάλμα ταυτοποίησης: {e}")
        sys.exit(1)


def scrape_pao_schedule():
    """Scrape Panathinaikos BC schedule from all pages"""
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

        logger.info(f"Σάρωση σελίδας {page}: {url}")

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
    """Parse date/time to datetime object"""
    try:
        greek_days = [
            "Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", 
            "Παρασκευή", "Σάββατο", "Κυριακή"
        ]

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

        english_days = [
            "Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday"
        ]
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
    """
    Create unique identifier for a match
    """
    home_normalized = normalize_team_name(match_data['home_team'])
    away_normalized = normalize_team_name(match_data['away_team'])
    
    # Ταξινόμηση για να μην έχει σημασία η σειρά
    teams_sorted = sorted([home_normalized, away_normalized])
    
    if match_datetime:
        date_part = match_datetime.strftime("%Y-%m-%d")
        return f"{teams_sorted[0]}|{teams_sorted[1]}|{date_part}"
    
    return f"{teams_sorted[0]}|{teams_sorted[1]}"


def extract_teams_from_event(event):
    """Εξάγει τα ονόματα των ομάδων από το event"""
    summary = event.get("summary", "")
    
    # Καθαρισμός emojis και άλλων χαρακτήρων
    clean_summary = re.sub(r'[^\w\s\-\[\]]', ' ', summary, flags=re.UNICODE)
    clean_summary = re.sub(r'\s+', ' ', clean_summary).strip()
    
    # Αναζήτηση για pattern "TeamA - TeamB"
    if " - " in clean_summary:
        # Αφαίρεση του [dd/mm] αν υπάρχει
        if "[" in clean_summary:
            clean_summary = clean_summary.split("[")[0].strip()
        
        parts = clean_summary.split(" - ")
        if len(parts) >= 2:
            home_team = parts[0].strip()
            away_team = parts[1].strip()
            
            return home_team, away_team
    
    return None, None


def get_existing_events_map(calendar_events):
    """
    Δημιουργεί ένα map με τα υπάρχοντα events για γρήγορη αναζήτηση
    """
    events_map = {}
    
    for event in calendar_events:
        try:
            event_start = event.get("start", {}).get("dateTime", "")
            if not event_start:
                continue
                
            home_team, away_team = extract_teams_from_event(event)
            if not home_team or not away_team:
                continue
            
            # Normalize τα ονόματα
            home_normalized = normalize_team_name(home_team)
            away_normalized = normalize_team_name(away_team)
            teams_sorted = sorted([home_normalized, away_normalized])
            
            # Δημιουργία datetime
            event_datetime = datetime.fromisoformat(
                event_start.replace("Z", "+00:00")
            ).replace(tzinfo=None)
            
            # Δημιουργία key για το map
            date_key = event_datetime.strftime("%Y-%m-%d")
            event_key = f"{teams_sorted[0]}|{teams_sorted[1]}|{date_key}"
            
            events_map[event_key] = {
                "event": event,
                "datetime": event_datetime,
                "original_home": home_team,
                "original_away": away_team
            }
            
        except Exception as e:
            logger.warning(f"Σφάλμα επεξεργασίας event: {e}")
            continue
    
    logger.info(f"Δημιουργήθηκε events map με {len(events_map)} entries")
    return events_map


def create_event_data(match_data, match_datetime):
    """Δημιουργεί τα δεδομένα για ένα event"""
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
    """
    Συγχρονίζει έναν αγώνα με το ημερολόγιο:
    1. Αν υπάρχει με ίδιες ώρες: δεν κάνει τίποτα
    2. Αν υπάρχει με διαφορετικές ώρες: ενημερώνει
    3. Αν δεν υπάρχει: προσθέτει νέο
    """
    try:
        match_datetime = parse_match_datetime(match_data["date"], match_data["time"])
        if not match_datetime:
            logger.warning(f"Παράλειψη αγώνα λόγω σφάλματος ημερομηνίας: {match_data['home_team']} vs {match_data['away_team']}")
            return False, None

        # Δημιουργία key για αναζήτηση
        home_normalized = normalize_team_name(match_data['home_team'])
        away_normalized = normalize_team_name(match_data['away_team'])
        teams_sorted = sorted([home_normalized, away_normalized])
        date_key = match_datetime.strftime("%Y-%m-%d")
        match_key = f"{teams_sorted[0]}|{teams_sorted[1]}|{date_key}"
        
        # Δημιουργία event data
        event_data = create_event_data(match_data, match_datetime)
        
        # Έλεγχος αν υπάρχει ήδη
        if match_key in existing_events_map:
            existing_info = existing_events_map[match_key]
            existing_event = existing_info["event"]
            existing_datetime = existing_info["datetime"]
            
            # Έλεγχος αν έχουν αλλάξει οι ώρες
            time_diff = abs((existing_datetime - match_datetime).total_seconds())
            
            if time_diff < 60:  # Μικρότερο από 1 λεπτό διαφορά
                logger.debug(f"ℹ️ Υπάρχει ήδη με ίδιες ώρες: {match_data['home_team']} vs {match_data['away_team']} "
                           f"({match_datetime.strftime('%H:%M')})")
                return True, match_key
            else:
                # Ενημέρωση ώρας
                existing_time_str = existing_datetime.strftime("%H:%M")
                new_time_str = match_datetime.strftime("%H:%M")
                
                service.events().update(
                    calendarId=CALENDAR_ID, 
                    eventId=existing_event["id"], 
                    body=event_data
                ).execute()
                
                logger.info(f"🔄 ΕΝΗΜΕΡΩΣΗ ΩΡΑΣ: {match_data['home_team']} vs {match_data['away_team']} "
                          f"({existing_time_str} → {new_time_str})")
                return True, match_key
        else:
            # Νέος αγώνας - προσθήκη
            service.events().insert(
                calendarId=CALENDAR_ID, 
                body=event_data
            ).execute()
            
            logger.info(f"✅ ΠΡΟΣΘΗΚΗ: {match_data['home_team']} vs {match_data['away_team']} "
                      f"({match_datetime.strftime('%d/%m/%Y %H:%M')})")
            return True, match_key
            
    except Exception as e:
        logger.error(f"Σφάλμα συγχρονισμού αγώνα: {e}")
        return False, None


def get_all_pao_events(service):
    """Get all PAO basketball events from calendar"""
    try:
        time_min = (datetime.now() - timedelta(days=180)).isoformat() + "Z"
        time_max = (datetime.now() + timedelta(days=540)).isoformat() + "Z"

        logger.info(
            f"Αναζήτηση events από {(datetime.now() - timedelta(days=180)).strftime('%d/%m/%Y')} "
            f"έως {(datetime.now() + timedelta(days=540)).strftime('%d/%m/%Y')}"
        )

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
            if (
                "🏀" in summary
                or "☘️" in summary
                or "ΠΑΟ" in summary.upper()
                or "PANATHINAIKOS" in summary.upper()
                or (" - " in summary and any(x in summary.upper() for x in ["VS", "VS.", "ΑΓΩΝΑΣ", "ΑΓΩΝΑ"]))
            ):
                pao_events.append(event)

        logger.info(f"✓ Βρέθηκαν {len(pao_events)} PAO basketball events στο ημερολόγιο")
        return pao_events

    except Exception as e:
        logger.error(f"Σφάλμα ανάκτησης events από ημερολόγιο: {e}")
        return []


def delete_obsolete_events(service, website_match_keys, existing_events_map):
    """
    Διαγράφει events που υπάρχουν στο ημερολόγιο μας αλλά δεν υπάρχουν στο website
    """
    deleted_count = 0
    
    logger.info(f"Έλεγχος {len(existing_events_map)} events για πιθανή διαγραφή...")
    logger.info(f"Έγκυρα keys από website: {len(website_match_keys)}")
    
    for event_key, event_info in list(existing_events_map.items()):
        if event_key not in website_match_keys:
            try:
                event = event_info["event"]
                event_datetime = event_info["datetime"]
                home_team = event_info.get("original_home", "Unknown")
                away_team = event_info.get("original_away", "Unknown")
                
                # Διαγραφή event
                service.events().delete(
                    calendarId=CALENDAR_ID, 
                    eventId=event["id"]
                ).execute()
                
                logger.info(f"🗑️ ΔΙΑΓΡΑΦΗ: {home_team} vs {away_team} "
                          f"({event_datetime.strftime('%d/%m/%Y %H:%M')})")
                deleted_count += 1
                
                # Αφαίρεση από το map
                del existing_events_map[event_key]
                
            except Exception as e:
                logger.warning(f"Σφάλμα διαγραφής event {event_key}: {e}")
                continue
    
    return deleted_count


def main():
    """Main function with improved sync logic"""
    logger.info("=" * 70)
    logger.info("🏀 Panathinaikos BC Schedule Scraper - Έναρξη")
    logger.info("=" * 70)

    # Authenticate Google Calendar with Service Account
    service = authenticate_google_calendar()

    # PHASE 0: Get existing calendar events
    logger.info("\n📅 ΦΑΣΗ 0: Ανάκτηση υπαρχόντων events...")
    logger.info("-" * 70)
    existing_calendar_events = get_all_pao_events(service)
    
    # Δημιουργία map για γρήγορη αναζήτηση
    existing_events_map = get_existing_events_map(existing_calendar_events)

    # PHASE 1: Scrape schedule from website
    logger.info(f"\n🌐 ΦΑΣΗ 1: Σάρωση προγράμματος από paobc.gr...")
    logger.info("-" * 70)
    website_matches = scrape_pao_schedule()

    if not website_matches:
        logger.error("❌ Δεν βρέθηκαν αγώνες - τερματισμός")
        sys.exit(1)

    # PHASE 2: Sync matches from website to calendar
    logger.info(f"\n🔄 ΦΑΣΗ 2: Συγχρονισμός {len(website_matches)} αγώνων με το ημερολόγιο...")
    logger.info("-" * 70)

    synced_count = 0
    website_match_keys = set()
    
    for match in website_matches:
        synced, match_key = sync_match_with_calendar(service, match, existing_events_map)
        if synced and match_key:
            synced_count += 1
            website_match_keys.add(match_key)
    
    logger.info(f"Συγχρονίστηκαν {synced_count} από {len(website_matches)} αγώνες")
    logger.info(f"Μοναδικά keys από website: {len(website_match_keys)}")

    # PHASE 3: Delete events that no longer exist on website
    logger.info(f"\n🗑️ ΦΑΣΗ 3: Έλεγχος για αγώνες προς διαγραφή...")
    logger.info("-" * 70)

    deleted_count = delete_obsolete_events(service, website_match_keys, existing_events_map)

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("✅ ΟΛΟΚΛΗΡΩΘΗΚΕ ΕΠΙΤΥΧΩΣ!")
    logger.info(f"   • Αγώνες στο site: {len(website_matches)}")
    logger.info(f"   • Συγχρονίστηκαν: {synced_count}")
    logger.info(f"   • Διαγράφηκαν: {deleted_count}")
    logger.info(f"   • Υπόλοιπα events στο ημερολόγιο: {len(existing_events_map)}")
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