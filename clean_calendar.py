# clean_calendar_secure.py - SECURE VERSION
import os
import json
import base64
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ==========================================================
# Φόρτωσε το .env αρχείο
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

def authenticate_google_calendar():
    """Authenticate με Service Account"""
    print("🔑 Ταυτοποίηση με Google Calendar...")
    
    try:
        if os.getenv('SERVICE_ACCOUNT_KEY'):
            service_account_info = json.loads(
                base64.b64decode(os.getenv('SERVICE_ACCOUNT_KEY'))
            )
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=SCOPES
            )
        
        elif os.path.exists('service-account-key.json'):
            credentials = service_account.Credentials.from_service_account_file(
                'service-account-key.json',
                scopes=SCOPES
            )
        
        else:
            raise FileNotFoundError("Δεν βρέθηκαν service account credentials!")
        
        service = build("calendar", "v3", credentials=credentials)
        
        # Ασφαλής έλεγχος - μόνο τα 8 πρώτα και τελευταία χαρακτήρες
        cal_id_display = CALENDAR_ID[:8] + "..." + CALENDAR_ID[-8:] if len(CALENDAR_ID) > 20 else "***"
        print(f"   ✅ Επιτυχής ταυτοποίηση")
        print(f"   📅 Calendar: {cal_id_display}")
        
        return service
        
    except Exception as e:
        print(f"❌ Σφάλμα ταυτοποίησης: {e}")
        raise

def list_events(service):
    """Εμφάνιση όλων των events (ΧΩΡΙΣ ευαίσθητα δεδομένα)"""
    print(f"\n📋 Λίστα όλων των events:")
    print("=" * 60)
    
    events = []
    page_token = None
    total_count = 0
    
    while True:
        try:
            events_result = service.events().list(
                calendarId=CALENDAR_ID,
                pageToken=page_token,
                singleEvents=True,
                orderBy="startTime",
                maxResults=2500
            ).execute()
            
            batch = events_result.get('items', [])
            events.extend(batch)
            
            for event in batch:
                total_count += 1
                summary = event.get('summary', 'ΧΩΡΙΣ ΤΙΤΛΟ')
                # Αφαίρεση ευαίσθητων πληροφοριών από το summary
                safe_summary = summary[:60].replace(CALENDAR_ID, "***") if CALENDAR_ID in summary else summary[:60]
                start = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', 'ΧΩΡΙΣ ΗΜΕΡΟΜΗΝΙΑ'))
                
                # Ασφαλής εκτύπωση - μόνο ημερομηνία, όχι πλήρης timestamp
                if 'T' in start:
                    date_part = start.split('T')[0]
                    print(f"{total_count:3d}. {safe_summary:60} | {date_part}")
                else:
                    print(f"{total_count:3d}. {safe_summary:60} | {start}")
            
            page_token = events_result.get('nextPageToken')
            if not page_token:
                break
                
        except Exception as e:
            print(f"⚠️ Σφάλμα: {e}")
            break
    
    print(f"\n📊 Σύνολο events: {len(events)}")
    return events

def secure_confirmation(action_description, item_count):
    """Ασφαλής διαδικασία επιβεβαίωσης"""
    print(f"\n⚠️  ΠΡΟΣΟΧΗ  ⚠️")
    print(f"Θα εκτελεστεί: {action_description}")
    print(f"Αριθμός items: {item_count}")
    print("Αυτή η ενέργεια ΔΕΝ μπορεί να αναιρεθεί!")
    
    # Διπλή επιβεβαίωση
    confirm1 = input("\nΓράψτε 'ΣΥΝΕΧΕΙΑ' για να προχωρήσετε: ")
    if confirm1.upper() != 'ΣΥΝΕΧΕΙΑ':
        print("❌ Ακύρωση")
        return False
    
    confirm2 = input("Γράψτε 'ΕΠΙΒΕΒΑΙΩΝΩ' για τελική επιβεβαίωση: ")
    if confirm2.upper() != 'ΕΠΙΒΕΒΑΙΩΝΩ':
        print("❌ Ακύρωση")
        return False
    
    return True

def delete_all_events(service, events):
    """Διαγραφή ΟΛΩΝ των events με ασφάλεια"""
    if not events:
        print("ℹ️ Το calendar είναι ήδη κενό!")
        return
    
    if not secure_confirmation("Διαγραφή ΟΛΩΝ των events", len(events)):
        return
    
    deleted_count = 0
    print("\n🗑️  Διαγραφή events...")
    
    for i, event in enumerate(events, 1):
        try:
            summary = event.get('summary', 'ΧΩΡΙΣ ΤΙΤΛΟ')
            safe_summary = summary.replace(CALENDAR_ID, "***") if CALENDAR_ID in summary else summary[:50]
            
            service.events().delete(
                calendarId=CALENDAR_ID,
                eventId=event['id']
            ).execute()
            
            deleted_count += 1
            print(f"{i:3d}/{len(events)} Διαγράφηκε: {safe_summary}...")
            
        except Exception as e:
            print(f"⚠️ Σφάλμα: {e}")
    
    print(f"\n✅ Διαγράφηκαν {deleted_count} από {len(events)} events")

def main():
    """Κύριο μενού"""
    print("=" * 60)
    print("🗑️  GOOGLE CALENDAR CLEANER (SECURE)")
    print("=" * 60)
    
    try:
        service = authenticate_google_calendar()
    except Exception:
        return
    
    while True:
        print("\n" + "=" * 40)
        print("🔧 ΕΠΙΛΟΓΕΣ:")
        print("1. Εμφάνιση events")
        print("2. Διαγραφή ΟΛΩΝ")
        print("3. Έξοδος")
        print("=" * 40)
        
        choice = input("\n👉 Επίλεξε (1-3): ").strip()
        
        if choice == '1':
            events = list_events(service)
            input("\n👆 Πάτησε Enter...")
            
        elif choice == '2':
            events = list_events(service)
            delete_all_events(service, events)
            input("\n👆 Πάτησε Enter...")
            
        elif choice == '3':
            print("👋 Έξοδος...")
            break
            
        else:
            print("❌ Μη έγκυρη")

if __name__ == "__main__":
    main()