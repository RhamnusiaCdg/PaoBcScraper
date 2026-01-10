import os
import os.path
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Προαιρετικά: Φόρτωσε .env αρχείο για local development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # Δεν υπάρχει python-dotenv, χρησιμοποίησε system env vars

# ==========================================================
# ΡΥΘΜΙΣΕΙΣ
# ==========================================================
CALENDAR_ID = os.environ.get('CALENDAR_ID')
if not CALENDAR_ID:
    raise ValueError("❌ Το CALENDAR_ID δεν βρέθηκε στα environment variables!")

CALENDARS_TO_CLEAN = [CALENDAR_ID]
SCOPES = ['https://www.googleapis.com/auth/calendar']

def authenticate_google_calendar():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return build('calendar', 'v3', credentials=creds)

def surgical_clean():
    service = authenticate_google_calendar()
    
    # Από το 2024 έως το τέλος του 2026
    t_min = "2024-01-01T00:00:00Z"
    t_max = "2026-12-31T23:59:59Z"
    
    # Λέξεις κλειδιά για διαγραφή (πολύ συγκεκριμένες)
    keywords = ["PANATHINAIKOS BC AKTOR", "☘️", "PANATHINAIKOS AKTOR ATHENS"]
    
    for cal_id in CALENDARS_TO_CLEAN:
        print(f"\n🔍 Έλεγχος στο ημερολόγιο: {cal_id}")
        try:
            events_result = service.events().list(
                calendarId=cal_id, 
                timeMin=t_min, 
                timeMax=t_max, 
                singleEvents=True
            ).execute()
            
            events = events_result.get('items', [])
            deleted_count = 0
            
            for event in events:
                summary = event.get('summary', '')
                # Έλεγχος αν κάποιο από τα keywords είναι ΜΕΣΑ στον τίτλο
                if any(key.upper() in summary.upper() for key in keywords):
                    print(f"🗑️ Διαγραφή: {summary} ({event['start'].get('dateTime', 'All Day')})")
                    service.events().delete(calendarId=cal_id, eventId=event['id']).execute()
                    deleted_count += 1
            
            print(f"✅ Καθαρίστηκαν {deleted_count} εγγραφές.")
            
        except Exception as e:
            print(f"❌ Σφάλμα στο {cal_id}: {e}")

if __name__ == "__main__":
    surgical_clean()
    print("\nΤο καθάρισμα ολοκληρώθηκε.")