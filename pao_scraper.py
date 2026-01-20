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
    """Κανονικοποίηση ονομάτων ομάδων"""
    if not name:
        return ""
    # Αφαίρεση emojis και ειδικών χαρακτήρων
    name = re.sub(r'[^\w\s-]', '', str(name), flags=re.UNICODE)
    # Αφαίρεση suffixes
    for suffix in [" BC", " AKTOR", " ATHENS", " OPAP"]:
        name = name.replace(suffix, "")
    # Uppercase και καθαρισμός
    name = name.strip().upper()
    name = re.sub(r'\s+', ' ', name)
    return name


def authenticate_google_calendar():
    """Ταυτοποίηση με Google Calendar"""
    logger.info("Έλεγχος ταυτότητας Google Calendar...")
    
    try:
        if os.getenv('SERVICE_ACCOUNT_KEY'):
            logger.info("Φόρτωση credentials από environment variable")
            service_account_info = json.loads(
                base64.b64decode(os.getenv('SERVICE_ACCOUNT_KEY'))
            )
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info, scopes=SCOPES
            )
        elif os.path.exists('service-account-key.json'):
            logger.info("Φόρτωση credentials από αρχείο")
            credentials = service_account.Credentials.from_service_account_file(
                'service-account-key.json', scopes=SCOPES
            )
        else:
            raise FileNotFoundError("Δεν βρέθηκαν service account credentials!")
        
        service = build("calendar", "v3", credentials=credentials)
        logger.info("✓ Επιτυχής ταυτοποίηση")
        return service
        
    except Exception as e:
        logger.error(f"❌ Σφάλμα ταυτοποίησης: {e}")
        sys.exit(1)


def scrape_pao_schedule():
    """Σάρωση προγράμματος από paobc.gr"""
    all_matches = []
    seen_matches = set()
    page = 1
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    consecutive_empty_pages = 0

    logger.info(f"Έναρξη σάρωσης από {BASE_URL}")

    while page <= MAX_PAGES:
        url = "https://www.paobc.gr/schedule/" if page == 1 else f"{BASE_URL}{page}/"
        
        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            matches = soup.find_all("div", class_="game")

            if not matches:
                consecutive_empty_pages += 1
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
                        continue

                    seen_matches.add(match_id)
                    all_matches.append({
                        "date": date_text,
                        "time": time_text,
                        "home_team": home_team,
                        "away_team": away_team,
                        "competition": competition,
                        "venue": venue,
                    })
                    matches_on_page += 1

                except AttributeError as e:
                    logger.warning(f"Σφάλμα ανάλυσης αγώνα: {e}")
                    continue

            logger.info(f"✓ Σελίδα {page}: {matches_on_page} αγώνες")
            page += 1

        except requests.RequestException as e:
            logger.error(f"Σφάλμα δικτύου στη σελίδα {page}: {e}")
            if all_matches:
                break
            sys.exit(1)

    logger.info(f"📊 Σύνολο: {len(all_matches)} μοναδικοί αγώνες")
    return all_matches


def parse_match_datetime(date_text, time_text):
    """Μετατροπή ημερομηνίας σε datetime object"""
    try:
        # Αφαίρεση ημερών εβδομάδας (ελληνικά)
        greek_days = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"]
        for day in greek_days:
            date_text = date_text.replace(day + ",", "").replace(day, "")
        
        # Αφαίρεση ημερών εβδομάδας (αγγλικά - Ευρωλίγκα)
        english_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for day in english_days:
            date_text = date_text.replace(day + ",", "").replace(day, "")

        # Μετατροπή ελληνικών μηνών σε αριθμούς
        greek_to_month = {
            "Ιανουαρίου": "01", "Ιαν": "01", "Φεβρουαρίου": "02", "Φεβ": "02",
            "Μαρτίου": "03", "Μαρ": "03", "Απριλίου": "04", "Απρ": "04",
            "Μαΐου": "05", "Μάι": "05", "Ιουνίου": "06", "Ιουν": "06",
            "Ιουλίου": "07", "Ιουλ": "07", "Αυγούστου": "08", "Αυγ": "08",
            "Σεπτεμβρίου": "09", "Σεπ": "09", "Οκτωβρίου": "10", "Οκτ": "10",
            "Νοεμβρίου": "11", "Νοε": "11", "Δεκεμβρίου": "12", "Δεκ": "12",
        }
        
        # Μετατροπή αγγλικών μηνών σε αριθμούς (Ευρωλίγκα)
        english_to_month = {
            "January": "01", "Jan": "01", "February": "02", "Feb": "02",
            "March": "03", "Mar": "03", "April": "04", "Apr": "04",
            "May": "05", "June": "06", "Jun": "06",
            "July": "07", "Jul": "07", "August": "08", "Aug": "08",
            "September": "09", "Sep": "09", "October": "10", "Oct": "10",
            "November": "11", "Nov": "11", "December": "12", "Dec": "12",
        }

        # Αντικατάσταση ελληνικών μηνών
        for greek, month_num in greek_to_month.items():
            date_text = date_text.replace(greek, month_num)
        
        # Αντικατάσταση αγγλικών μηνών
        for english, month_num in english_to_month.items():
            date_text = date_text.replace(english, month_num)

        date_text = date_text.strip().replace(",", "")
        parts = date_text.split()
        
        if len(parts) >= 3:
            day, month, year = parts[0], parts[1], parts[2]
            time = time_text.strip() if time_text and ":" in time_text else "21:15"
            
            datetime_str = f"{day}/{month}/{year} {time}"
            return datetime.strptime(datetime_str, "%d/%m/%Y %H:%M")

        return None

    except Exception as e:
        logger.warning(f"Σφάλμα ανάλυσης ημερομηνίας '{date_text} {time_text}': {e}")
        return None


def get_all_pao_events(service):
    """Ανάκτηση όλων των PAO events από το ημερολόγιο"""
    try:
        time_min = (datetime.now() - timedelta(days=180)).isoformat() + "Z"
        time_max = (datetime.now() + timedelta(days=540)).isoformat() + "Z"

        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=2500,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        all_events = events_result.get("items", [])
        
        # Φιλτράρισμα μόνο PAO events
        pao_events = []
        for event in all_events:
            summary = event.get("summary", "")
            if "🏀" in summary or "ΠΑΟ" in summary.upper() or "PANATHINAIKOS" in summary.upper():
                pao_events.append(event)

        logger.info(f"✓ Βρέθηκαν {len(pao_events)} PAO basketball events στο ημερολόγιο")
        return pao_events

    except Exception as e:
        logger.error(f"Σφάλμα ανάκτησης events: {e}")
        return []


def extract_teams_from_summary(summary):
    """Εξαγωγή ομάδων από summary"""
    if not summary or " - " not in summary:
        return None, None
    
    # Αφαίρεση emojis και brackets
    clean = re.sub(r'[^\w\s\-\[\]]', ' ', summary, flags=re.UNICODE)
    clean = re.sub(r'\s+', ' ', clean).strip()
    
    # Αφαίρεση [dd/mm] bracket
    if "[" in clean:
        clean = clean.split("[")[0].strip()
    
    # Split με " - "
    parts = clean.split(" - ")
    if len(parts) >= 2:
        return parts[0].strip(), parts[1].strip()
    
    return None, None


def create_match_key(home_team, away_team, match_datetime):
    """Δημιουργία unique key: normalized_teams|date"""
    home_norm = normalize_team_name(home_team)
    away_norm = normalize_team_name(away_team)
    teams_sorted = sorted([home_norm, away_norm])
    date_str = match_datetime.strftime("%Y-%m-%d")
    return f"{teams_sorted[0]}|{teams_sorted[1]}|{date_str}"


def sync_calendar_with_website(service, website_matches):
    """
    Κύριος αλγόριθμος συγχρονισμού
    """
    
    # =========================================================================
    # ΒΗΜΑ 1: Φόρτωση όλων των δεδομένων στη μνήμη
    # =========================================================================
    logger.info("\n" + "="*70)
    logger.info("ΒΗΜΑ 1: Φόρτωση δεδομένων στη μνήμη")
    logger.info("="*70)
    
    # Φόρτωση calendar events
    calendar_events = get_all_pao_events(service)
    
    # Δημιουργία map: key -> calendar event
    calendar_map = {}
    for event in calendar_events:
        home, away = extract_teams_from_summary(event.get("summary", ""))
        if not home or not away:
            continue
            
        event_start = event.get("start", {}).get("dateTime", "")
        if not event_start:
            continue
            
        event_dt = datetime.fromisoformat(event_start.replace("Z", "+00:00")).replace(tzinfo=None)
        event_key = create_match_key(home, away, event_dt)
        
        calendar_map[event_key] = {
            "event_id": event["id"],
            "datetime": event_dt,
            "home": home,
            "away": away
        }
    
    logger.info(f"  • Calendar events: {len(calendar_map)}")
    
    # Δημιουργία map: key -> site match
    site_map = {}
    for match in website_matches:
        match_dt = parse_match_datetime(match["date"], match["time"])
        if not match_dt:
            continue
        
        match_key = create_match_key(match["home_team"], match["away_team"], match_dt)
        site_map[match_key] = {
            "datetime": match_dt,
            "home": match["home_team"],
            "away": match["away_team"],
            "venue": match.get("venue", "ΟΑΚΑ"),
            "competition": match.get("competition", "")
        }
    
    logger.info(f"  • Site matches: {len(site_map)}")
    
    # =========================================================================
    # ΒΗΜΑ 2: Επεξεργασία calendar events
    # =========================================================================
    logger.info("\n" + "="*70)
    logger.info("ΒΗΜΑ 2: Έλεγχος calendar events")
    logger.info("="*70)
    
    updated_count = 0
    deleted_count = 0
    processed_site_keys = set()
    
    for cal_key, cal_info in list(calendar_map.items()):
        if cal_key in site_map:
            # Βρέθηκε στο site
            site_info = site_map[cal_key]
            
            # Έλεγχος αν άλλαξε η ώρα
            time_diff = abs((cal_info["datetime"] - site_info["datetime"]).total_seconds())
            
            if time_diff >= 60:  # Διαφορά > 1 λεπτό
                # UPDATE - Αλλαγή ώρας
                date_str = site_info["datetime"].strftime("%d/%m")
                end_dt = site_info["datetime"] + timedelta(hours=2)
                
                event_data = {
                    "summary": f"☘️🏀 {site_info['home']} - {site_info['away']} [{date_str}]",
                    "location": site_info["venue"],
                    "description": f"Διοργάνωση: {site_info['competition']}",
                    "start": {
                        "dateTime": site_info["datetime"].isoformat(),
                        "timeZone": "Europe/Athens",
                    },
                    "end": {
                        "dateTime": end_dt.isoformat(),
                        "timeZone": "Europe/Athens",
                    },
                    "reminders": {
                        "useDefault": False,
                        "overrides": [{"method": "popup", "minutes": 60}],
                    },
                }
                
                service.events().update(
                    calendarId=CALENDAR_ID,
                    eventId=cal_info["event_id"],
                    body=event_data
                ).execute()
                
                logger.info(f"🔄 ΕΝΗΜΕΡΩΣΗ: {cal_info['home']} vs {cal_info['away']} "
                           f"({cal_info['datetime'].strftime('%H:%M')} → {site_info['datetime'].strftime('%H:%M')})")
                updated_count += 1
            
            # Μάρκαρε ως processed
            processed_site_keys.add(cal_key)
        else:
            # ΔΕΝ βρέθηκε στο site - DELETE
            service.events().delete(
                calendarId=CALENDAR_ID,
                eventId=cal_info["event_id"]
            ).execute()
            
            logger.info(f"🗑️ ΔΙΑΓΡΑΦΗ: {cal_info['home']} vs {cal_info['away']} "
                       f"({cal_info['datetime'].strftime('%d/%m/%Y')}) - δεν υπάρχει πια στο site")
            deleted_count += 1
    
    # =========================================================================
    # ΒΗΜΑ 3: Προσθήκη νέων matches από το site
    # =========================================================================
    logger.info("\n" + "="*70)
    logger.info("ΒΗΜΑ 3: Προσθήκη νέων matches")
    logger.info("="*70)
    
    added_count = 0
    
    for site_key, site_info in site_map.items():
        if site_key not in processed_site_keys:
            # Νέος αγώνας - INSERT
            date_str = site_info["datetime"].strftime("%d/%m")
            end_dt = site_info["datetime"] + timedelta(hours=2)
            
            event_data = {
                "summary": f"☘️🏀 {site_info['home']} - {site_info['away']} [{date_str}]",
                "location": site_info["venue"],
                "description": f"Διοργάνωση: {site_info['competition']}",
                "start": {
                    "dateTime": site_info["datetime"].isoformat(),
                    "timeZone": "Europe/Athens",
                },
                "end": {
                    "dateTime": end_dt.isoformat(),
                    "timeZone": "Europe/Athens",
                },
                "reminders": {
                    "useDefault": False,
                    "overrides": [{"method": "popup", "minutes": 60}],
                },
            }
            
            service.events().insert(calendarId=CALENDAR_ID, body=event_data).execute()
            
            logger.info(f"✅ ΠΡΟΣΘΗΚΗ: {site_info['home']} vs {site_info['away']} "
                       f"({site_info['datetime'].strftime('%d/%m/%Y %H:%M')})")
            added_count += 1
    
    # =========================================================================
    # ΣΥΝΟΨΗ
    # =========================================================================
    logger.info("\n" + "="*70)
    logger.info("✅ ΟΛΟΚΛΗΡΩΘΗΚΕ ΕΠΙΤΥΧΩΣ!")
    logger.info(f"  • Αγώνες στο site: {len(site_map)}")
    logger.info(f"  • Ενημερώθηκαν: {updated_count}")
    logger.info(f"  • Διαγράφηκαν: {deleted_count}")
    logger.info(f"  • Προστέθηκαν: {added_count}")
    logger.info(f"  • Τελικά events: {len(calendar_map) - deleted_count + added_count}")
    logger.info("="*70)


def main():
    """Κύρια συνάρτηση"""
    logger.info("="*70)
    logger.info("🏀 Panathinaikos BC Schedule Scraper")
    logger.info("="*70)
    
    # Ταυτοποίηση
    service = authenticate_google_calendar()
    
    # Σάρωση website
    logger.info("\n" + "="*70)
    logger.info("Σάρωση προγράμματος από paobc.gr")
    logger.info("="*70)
    
    website_matches = scrape_pao_schedule()
    
    if not website_matches:
        logger.error("❌ Δεν βρέθηκαν αγώνες - τερματισμός")
        sys.exit(1)
    
    # Συγχρονισμός
    sync_calendar_with_website(service, website_matches)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("\n⚠️ Διακόπηκε από τον χρήστη")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n❌ Κρίσιμο σφάλμα: {e}", exc_info=True)
        sys.exit(1)