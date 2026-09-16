# EventMate – College Event Management System 🎓

**EventMate** is a full-featured, modern, and user-friendly Web Application designed for managing college symposiums, hackathons, and technical events (such as **CodeCraft**, **CodeStorm**, **CodeVerse**, and **ByteBattle**).

Built using **Python (Flask)**, **MySQL**, **Vanilla HTML/CSS/JavaScript**, and **SMTP**, it provides automated workflows for participant registrations, duplicate prevention, attendance tracking, instant high-resolution certificate generation with verification QR codes, and automated email dispatch.

---

## 🌟 Key Features

1. **Authentication & Role-Based Access Control**:
   - Dedicated **Admin Login** (`admin` / `admin123`) for faculty/organizers.
   - **Student / Participant Portal** with registration and personal dashboard (`my_events`).
   - Secure hashed password storage (`werkzeug.security`).

2. **Real-time Admin Analytics Dashboard**:
   - Live metric cards: Total Events, Total Participants, Attendance Count, Certificates Generated, and Certificates Sent.
   - Recent registrations table and quick event overview.

3. **Event Management (CRUD)**:
   - Create, edit, view, and delete symposium events.
   - Pre-loaded with college tech events:
     - **CodeCraft** (Hackathon & Coding Sprint) &bull; *18-Sep-2026*
     - **CodeStorm** (Bug Debugging & DSA) &bull; *19-Sep-2026*
     - **CodeVerse** (Web & App Development Challenge) &bull; *19-Sep-2026*
     - **ByteBattle** (Speed Coding Duel) &bull; *20-Sep-2026*

4. **Participant Registration & Duplicate Prevention**:
   - Clean registration form capturing Participant Name, Email, Phone, College, Department, Semester, and Event selection.
   - Strict database-level uniqueness preventing duplicate registrations for the same event.

5. **Participant Directory**:
   - Search by student name, college, email, or department.
   - Event filter dropdown and edit/delete controls.

6. **Interactive Attendance Tracker**:
   - Single-click **Mark Present / Mark Absent** buttons with real-time AJAX updates (no full page reload).
   - Live calculation of attendance percentage and presence counters.

7. **Automatic High-Resolution Certificate Generation**:
   - Generates authentic diploma-grade certificates of participation with:
     - College Name & Department Branding
     - Event Name (**CodeCraft**, **CodeStorm**, **CodeVerse**, **ByteBattle**)
     - Participant Name
     - Event Dates (18-Sep-2026, 19-Sep-2026, 20-Sep-2026)
     - Unique Certificate ID (e.g. `EM-2026-CC-8742`)
     - Official Gold Seal Emblem & Authorized Signatures
     - Live Verification QR code pointing directly to the verification portal.
   - Single-click bulk generator for all verified attendees.
   - Instant high-res PNG download and preview modal.

8. **SMTP Email Certificate Dispatch**:
   - Sends the certificate as an attachment directly to the participant's registered email.
   - Includes fallback demo mode if SMTP credentials are not yet configured.

9. **Public Certificate Verification Portal (`/verify`)**:
   - Anyone can enter a Certificate ID or scan the QR code to verify participant authenticity.
   - Displays official validity badge and student/event credentials.

---

## 🛠️ Technology Stack

| Layer | Technology |
|---|---|
| **Backend Framework** | Python 3.x with Flask |
| **Database** | MySQL (with SQLite dual connector fallback) |
| **Frontend** | HTML5, Modern CSS3 (Variables, Flexbox, Grid), JavaScript (Vanilla ES6) |
| **Certificate Generator** | Pillow (PIL) + QRCode |
| **Email Protocol** | SMTP (`smtplib` + `email.mime`) |
| **IDE** | Visual Studio Code / Antigravity |

---

## 📁 Project Structure

```
EventMate/
│
├── app.py                      # Flask application main routes & server entry
├── config.py                   # Centralized configuration (MySQL, SMTP, College info)
├── database.py                 # Database connector, parameterized query runner & seeder
├── certificate_generator.py    # Pillow-based high-res Certificate & QR code generator
├── mailer.py                   # SMTP email dispatcher with certificate attachment
├── schema.sql                  # MySQL database schema and initial seed data
├── setup_db.py                 # Automatic DB initialization & directory setup script
├── requirements.txt            # Python dependencies
├── .env.example                # Sample environment variables template
├── README.md                   # Project documentation & viva explanation
│
├── templates/
│   ├── base.html               # Master layout with navigation, flash alerts, & footer
│   ├── login.html              # Admin & Student tabbed login & signup
│   ├── dashboard.html          # Admin analytics dashboard with metric cards
│   ├── events.html             # Event showcase cards & CRUD actions
│   ├── add_event.html          # New event creation form
│   ├── edit_event.html         # Event editing form
│   ├── register.html           # Participant registration form
│   ├── participants.html       # Participant directory & search
│   ├── edit_participant.html   # Participant edit form
│   ├── attendance.html         # Interactive attendance tracking sheet
│   ├── certificates.html       # Certificate management hub & bulk generator
│   ├── verify_certificate.html # Public certificate verification portal
│   └── my_events.html          # Student pass & certificate dashboard
│
├── static/
│   ├── css/
│   │   └── style.css           # Modern custom CSS stylesheet
│   ├── js/
│   │   └── script.js           # AJAX handlers, search/filter, & modal preview
│   └── images/                 # Static images and logos
│
└── certificates/               # Storage directory for generated certificate images
```

---

## 🚀 Step-by-Step Installation & Setup

### Step 1: Open the Project in Visual Studio Code
Open your terminal in the project directory:
```bash
cd c:\Users\varshitha.h\OneDrive\Desktop\Eventmanagement
```

### Step 2: Install Required Python Packages
Run the following command to install Flask, MySQL connector, Pillow, and other dependencies:
```bash
pip install -r requirements.txt
```

---

## 🗄️ MySQL Database Setup

### Option A: Automatic Setup (Recommended)
1. Ensure your MySQL service is running (e.g., via XAMPP, WampServer, or MySQL Server).
2. Configure your MySQL username and password in `.env` (or `config.py`):
   ```ini
   MYSQL_HOST=localhost
   MYSQL_USER=root
   MYSQL_PASSWORD=your_mysql_password
   MYSQL_DB=eventmate_db
   MYSQL_PORT=3306
   ```
3. Run the setup script:
   ```bash
   python setup_db.py
   ```
   *This will automatically create the database `eventmate_db`, all tables, and seed initial symposium events and default users.*

### Option B: Manual Import via phpMyAdmin / MySQL CLI
1. Open phpMyAdmin or MySQL Workbench.
2. Create a new database named `eventmate_db`.
3. Import the provided [`schema.sql`](file:///c:/Users/varshitha.h/OneDrive/Desktop/Eventmanagement/schema.sql) file.

> **Note on Standby Mode:** If MySQL is not running or credentials are empty, EventMate automatically initializes an embedded database file (`eventmate.db`) so you can test and demonstrate the entire project immediately without any setup errors.

---

## ✉️ SMTP Email Setup (Optional for Live Emails)

To send real emails to participants with the attached certificate:
1. In your `.env` file, configure your Gmail SMTP settings:
   ```ini
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=your_email@gmail.com
   SMTP_PASSWORD=your_gmail_app_password
   SMTP_SENDER_EMAIL=your_email@gmail.com
   SMTP_USE_TLS=True
   ```
   *(For Gmail, generate an 16-character **App Password** under Google Account -> Security -> 2-Step Verification -> App Passwords).*
2. If left blank, EventMate runs in **Safe Demo Mode**, simulating email delivery and notifying you via the UI.

---

## ▶️ Running the Application

Start the Flask development server:
```bash
python app.py
```

Open your web browser and navigate to:
```
http://127.0.0.1:5000
```

---

## 🔑 Admin Login Configuration

Set `ADMIN_PASSWORD` to a strong, private value before creating or provisioning the administrator account. Credentials are intentionally not documented in this repository.

> **Note on Student Registration**: Students and symposium attendees do not need to create accounts or log in. They simply navigate to the **Register** tab to sign up for any competition directly.

---

## 📖 Module Explanation (For BCA Mini Project Viva)

1. **User Authentication Module (`app.py`, `templates/login.html`)**:
   - Uses Flask session management with cryptographic signing.
   - Dedicated administrator authentication configured through environment variables.
   - Features an interactive **Login Credentials Sheet** on the login page for effortless evaluation and testing.
   - Decorators `@login_required` and `@admin_required` protect administrative endpoints.

2. **Event Management Module (`templates/events.html`, `add_event.html`)**:
   - Manages technical symposium events (CodeCraft, CodeStorm, CodeVerse, ByteBattle).
   - Allows administrators to schedule events, assign venues, and set participant limits.

3. **Direct Participant Registration & Duplicate Prevention Engine (`templates/register.html`)**:
   - Seamless public registration capturing Participant Name, Email, Phone, College, Department, Semester, and Event selection.
   - Enforces unique constraint `(participant_id, event_id)` to ensure no participant can register more than once for the same event.

4. **Attendance Tracking Module (`templates/attendance.html`, `static/js/script.js`)**:
   - Uses asynchronous `fetch()` API to update attendance status in the database without page refresh, providing instant UI feedback.

5. **Automated Certificate Generation Module (`certificate_generator.py`)**:
   - Utilizes Python Pillow (PIL) to draw a 1920x1080 high-resolution certificate.
   - Embeds a dynamic QR code generated using `qrcode` that links to the verification portal.

6. **Verification Module (`templates/verify_certificate.html`)**:
   - Public endpoint allowing universities or employers to enter a Certificate ID to verify participation authenticity.

7. **Email Dispatcher (`mailer.py`)**:
   - Constructs MIME multipart messages containing HTML styling and the certificate image attachment dispatched via secure SMTP.

---

## 🧪 Testing & Demonstration Procedure

1. **Test Admin Flow**:
   - Navigate to **Admin Login** (`/login`).
   - Enter the administrator credentials configured in the environment.
   - Click **Sign In** to access the **Admin Dashboard**.
   - View metric counters for Events, Participants, Attendance, and Certificates.
   - Go to **Events** -> Click **+ Add New Event** and add a test event.
   - Go to **Attendance** -> Toggle a student's status between Present and Absent.
   - Go to **Certificates** -> Click **⚡ Generate All for Present Attendees**.
   - Click **Preview** or **Download** to inspect the generated certificate.
   - Click **📧 Email** to test SMTP dispatch.

2. **Test Direct Participant Registration Flow**:
   - Go to **Register** (`/register`) -> Fill out details for a participant (Name, Email, Phone, College, Department, Event).
   - Submit registration and observe confirmation.
   - Attempt to re-register with the same email for the same event to observe duplicate prevention.

3. **Test Public Verification**:
   - Copy any generated Certificate ID (e.g., from the Certificates Hub).
   - Open **Verify Certificate** (`/verify`).
   - Paste the ID and click **Verify** to see the official verified credentials badge.
