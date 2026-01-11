# 🏀 PAO BC Calendar Scraper

Αυτόματο scraping του προγράμματος του Panathinaikos BC από το [paobc.gr](https://www.paobc.gr/schedule/) και συγχρονισμός με Google Calendar.

## ✨ Features

- 🔄 Αυτόματη συγχρονισμός αγώνων με Google Calendar
- 📅 Υποστήριξη pagination (πολλές σελίδες)
- 🕒 Έλεγχος και ενημέρωση ωρών αγώνων
- 🗑️ Διαγραφή ακυρωμένων/μετακινημένων αγώνων
- ⏰ Υπενθύμιση 1 ώρα πριν τον αγώνα
- 🌍 Υποστήριξη timezone (Europe/Athens)

## 🚀 Εγκατάσταση

### Για χρήστες που θέλουν το δικό τους ημερολόγιο

**Σημαντικό**: Κάνοντας fork αυτό το repository, θα δημιουργήσεις το **δικό σου ξεχωριστό ημερολόγιο**. Δεν θα έχεις πρόσβαση στο δικό μου ημερολόγιο και δεν θα μπορείς να το τροποποιήσεις.

#### Βήματα:
1. Κάνε **Fork** αυτό το repository στο δικό σου GitHub account
2. Ακολούθησε τα παρακάτω βήματα για να στήσεις το δικό σου Google Calendar API
3. Πρόσθεσε τα **δικά σου** GitHub Secrets

### Προαπαιτούμενα

- Python 3.11+
- Google Calendar API credentials (τα δικά σου!)

### 1. Clone το repository (ή το fork σου)
```bash
git clone https://github.com/YOUR_USERNAME/pao-scraper.git
cd pao-scraper
```

### 2. Εγκατάσταση dependencies
```bash
pip install requests beautifulsoup4 google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

### 3. Google Calendar API Setup

1. Πήγαινε στο [Google Cloud Console](https://console.cloud.google.com/)
2. Δημιούργησε νέο project
3. Ενεργοποίησε το **Google Calendar API**
4. Δημιούργησε **OAuth 2.0 credentials** (Desktop app)
5. Κατέβασε το `credentials.json` και βάλτο στον root φάκελο

### 4. Ρύθμιση Calendar ID (προαιρετικό)

Αν θες να χρησιμοποιήσεις συγκεκριμένο calendar:
```bash
# Δημιούργησε το .env αρχείο
cp .env.example .env

# Επεξεργάσου το .env και βάλε το δικό σου Calendar ID
CALENDAR_ID=your_calendar_id@group.calendar.google.com
```

Αν δεν ορίσεις `CALENDAR_ID`, θα χρησιμοποιηθεί το **primary** calendar σου.

## 💻 Χρήση

### Τοπική εκτέλεση
```bash
python pao_scraper.py
```

Στην πρώτη εκτέλεση θα ανοίξει browser για authentication.

### Αυτόματη εκτέλεση με GitHub Actions

Το scraper τρέχει αυτόματα κάθε μέρα στις **10:00 πρωί** (ώρα Ελλάδας).

#### Ρύθμιση GitHub Secrets:

1. Στο **fork σου**, πήγαινε στο: `Settings` → `Secrets and variables` → `Actions`
2. Πρόσθεσε τα **δικά σου** secrets:
   - `GOOGLE_CREDENTIALS`: Το περιεχόμενο του **δικού σου** `credentials.json` (encoded σε base64)
   - `CALENDAR_ID`: (προαιρετικό) Το **δικό σου** Calendar ID

**Σημείωση**: Κάθε fork χρησιμοποιεί τα δικά του credentials και δημιουργεί ξεχωριστό ημερολόγιο. Δεν υπάρχει τρόπος να επηρεάσεις το ημερολόγιο κάποιου άλλου.

#### Πώς να κάνω encode το credentials.json σε base64:

**Windows (PowerShell):**
```powershell
[Convert]::ToBase64String([System.IO.File]::ReadAllBytes("credentials.json"))
```

**Linux/Mac:**
```bash
base64 -w 0 credentials.json
```

## 📁 Δομή Αρχείων
```
pao-scraper/
├── pao_scraper.py          # Main script
├── .github/
│   └── workflows/
│       └── scraper.yml     # GitHub Actions workflow
├── .gitignore              # Ignored files
├── .env.example            # Template για environment variables
└── README.md
```

## 🔒 Ασφάλεια

Τα παρακάτω αρχεία **ΔΕΝ** ανεβαίνουν στο GitHub (προστατεύονται από .gitignore):
- `credentials.json` - Google OAuth credentials
- `token.json` / `token.pickle` - Access tokens
- `.env` - Local configuration

**Προσοχή**: Μην κάνεις ποτέ commit αυτά τα αρχεία! Περιέχουν ευαίσθητα δεδομένα.

## 📝 License

MIT License - Ελεύθερο για προσωπική χρήση

## 🤝 Contributing

Pull requests are welcome! Για μεγάλες αλλαγές, άνοιξε πρώτα ένα issue.

## ⚠️ Disclaimer

Αυτό το project είναι ανεπίσημο και δεν έχει καμία σχέση με τον Παναθηναϊκό BC. Χρησιμοποιεί δημόσια διαθέσιμες πληροφορίες από το επίσημο website.

---

**Φτιαγμένο με 💚 για τον Παναθηναϊκό!**