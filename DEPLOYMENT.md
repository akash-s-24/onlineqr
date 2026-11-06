# Production Deployment & Architecture Guide
## Shree Daksha Academy – College Event Management System

This document outlines the deployment strategy, database configuration (Supabase PostgreSQL), cloud hosting (Render vs Vercel), environment variables, and on-site gate check-in workflows.

---

## 1. Database Architecture: Is Supabase Enough?

### The Short Answer: **Yes, Supabase is more than enough.**
Supabase provides an enterprise-grade, fully managed **PostgreSQL** instance with:
- **Connection pooling** (`PgBouncer` / Supavisor) handling high concurrent registrations without dropping connections.
- **Automated SSL encryption** (`sslmode=require`) out of the box.
- **Automated daily backups** and high availability.
- **Transaction safety**: Our atomic registration pipeline (`create_registration`) uses row-level locks (`FOR UPDATE`) to prevent over-subscription of event caps and duplicate UTR submissions.

### How to Connect Supabase to This Application:
1. In your Supabase Project Dashboard, go to **Project Settings** &rsaquo; **Database**.
2. Find the **Connection string** section and select **URI**.
3. Copy the URI. It looks like:
   ```env
   DATABASE_URL=postgresql://postgres.[project-ref]:[YOUR-PASSWORD]@aws-0-[region].pooler.supabase.com:6543/postgres?sslmode=require
   ```
4. If using Supabase Connection Pooler (recommended for web services), use **Port 6543 (Transaction mode)** or Port 5432 (Session mode).
5. Paste this `DATABASE_URL` into your Render / Hosting Environment Variables.
6. The app's `database.init_db()` automatically detects PostgreSQL mode, executes table creations, runs column auto-migrations (including `payment_proof`), and provisions default administrative accounts seamlessly on first boot.

---

## 2. Hosting Platform: Render vs. Vercel?

| Feature | Render (Web Service) 🏆 **Recommended** | Vercel (Serverless Function) |
| :--- | :--- | :--- |
| **Execution Model** | Persistent long-running WSGI process | Ephemeral serverless lambdas (10–15s ceiling) |
| **Email Dispatching** | Background threading with persistent SMTP connections works reliably without timeouts | Serverless execution freezing can cut off background emails mid-flight |
| **File Storage** | Standard filesystem with persistent disk or upload mounts | Read-only ephemeral filesystem (`/tmp` cleared between invocations) |
| **Cold Starts** | Zero cold starts on standard/starter plans | Cold start delays on incoming requests |
| **Health Checks** | Native HTTP health check monitoring (`/healthz`) | Basic routing only |

> **Recommendation**: Deploy on **Render** using the provided `render.yaml` or Docker/Python runtime. We also include a `vercel.json` if you wish to run a serverless mirror.

---

## 3. Step-by-Step Render Deployment

### Option A: 1-Click Blueprint Deploy (Easiest)
1. Push your repository to **GitHub** (private or public).
2. Log into [Render.com](https://render.com).
3. Click **New +** &rsaquo; **Blueprint**.
4. Connect your GitHub repository.
5. Render will detect `render.yaml` and configure the Web Service, health checks, build commands, and environment variables automatically.
6. Under **Environment Variables**, fill in:
   - `DATABASE_URL`: Your Supabase connection string.
   - `ADMIN_PASSWORD`: A strong master admin password.
   - `BASE_URL`: Your Render service URL (e.g. `https://your-fest-app.onrender.com`).
7. Click **Apply**. Render will install dependencies and start the app using Gunicorn.

### Option B: Manual Web Service Setup
1. On Render, click **New +** &rsaquo; **Web Service**.
2. Connect your Git repository.
3. Configure the settings:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 app:app`
   - **Health Check Path**: `/healthz`
4. Add the required Environment Variables (see Section 4 below).
5. Click **Create Web Service**.

---

## 4. Environment Variables Reference

| Variable Name | Required | Default / Example | Purpose |
| :--- | :---: | :--- | :--- |
| `DATABASE_URL` | **Yes (Prod)** | `postgresql://...` | Connection URI for Supabase PostgreSQL. Falls back to SQLite if omitted in local dev. |
| `SECRET_KEY` | **Yes (Prod)** | `secrets.token_hex(32)` | Flask session encryption key. |
| `ADMIN_PASSWORD` | **Yes (Prod)** | `ChangeMe123!` | Password for default admin account (`admin`). |
| `BASE_URL` | **Yes (Prod)** | `https://fest.yourcollege.edu` | Canonical URL used for CSRF origin matching & email links. |
| `APP_ENV` | Optional | `production` | Set to `production` to enforce secure cookies and strict origin policies. |
| `SESSION_COOKIE_SECURE` | Optional | `True` | Transmit session cookies only over HTTPS. |
| `SMTP_MODE` | Optional | `live` or `demo` | `demo` simulates email dispatch instantly; `live` sends real emails. |
| `SMTP_HOST` | If live | `smtp.gmail.com` | SMTP host. |
| `SMTP_PORT` | If live | `587` | SMTP port (STARTTLS). |
| `SMTP_USER` | If live | `fest@gmail.com` | Gmail address. |
| `SMTP_PASSWORD` | If live | `abcd efgh ijkl mnop` | 16-character Google App Password (not your Gmail login password). |
| `COLLEGE_NAME` | Optional | `Shree Daksha Academy` | Branding title across headers, receipts, and certificates. |
| `EVENT_TITLE` | Optional | `Daksha Infinitx` | Official fest/symposium title across banners, headers, particle text, and payment notes. |

---

## 5. On-Site Gate Check-In & Mobile QR Scanner Operations

### How Team Members & Coordinators Scan Passes:
1. **Login from Mobile**:
   - Any authorized coordinator can open the website on their mobile browser (`Safari`, `Chrome`).
   - Tap the mobile navigation menu &rsaquo; tap **"🔐 Desk / Member Login"**.
   - Log in using coordinator or admin credentials.
2. **Access Scanner**:
   - Tap **"📱 QR Scanner"** directly in the top navigation bar or go to `/scanner`.
3. **Scan Attendee Gate Pass**:
   - Tap **"Start Camera Scanner"** and grant camera permissions.
   - Point at the attendee's phone screen showing their **Official Gate Pass QR**.
   - If an attendee's camera/screen is damaged, simply type their `REG-XXXXXX` into the **Manual Lookup** bar and tap **Lookup Pass**.
4. **Collect Cash & Settle Payment On Spot**:
   - If the participant selected **Pay on Spot (Cash Desk)**:
     - The scanner will clearly highlight: `💵 Cash Due at Desk: ₹100`.
     - Tap the prominent emerald button: **"💵 Collect ₹100 Cash & Mark Present"**.
     - In one click, the system:
       1. Records payment of ₹100 in the database under `Cash`.
       2. Sets `payment_status = 'paid'`, `payment_verified_by = current_user`.
       3. Moves registration to `approved`.
       4. Marks attendance as `present`.
       5. Immediately updates the central Admin Dashboard in real time.
5. **Continuous Scanning**:
   - The scanner displays a confirmation toast and automatically resets so the coordinator can scan the next attendee immediately without page reloads.

---

## 6. Certificate Generation Policy

- **Direct Generation & Dispatch**: Certificate validation gates have been removed. Certificates can be generated individually or bulk-generated and dispatched to participants without waiting for attendance or manual hurdles.
- Download PDF certificates directly from the **Certificates** panel (`/admin/certificates`).

---

## 7. Pre-Launch Verification Checklist

- [ ] Supabase PostgreSQL database connection tested (`/healthz` returns `{"database": "healthy", "status": "ok"}`).
- [ ] HTTPS enabled on custom domain or Render URL.
- [ ] Default `admin` password changed in production.
- [ ] At least one event created with fee and team configurations.
- [ ] Test registration submitted via Online UPI (with screenshot upload) and verified in Admin Dashboard.
- [ ] Test registration submitted via Cash Desk, scanned with mobile QR scanner, and settled with cash collection.
- [ ] PDF Certificate generation and download verified.

