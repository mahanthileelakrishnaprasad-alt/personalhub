# PersonalHub: Backend API

The REST API behind **PersonalHub**, a personal productivity app with three modules: **Tasks**, **Daily Routines**, and **Money Tracker**. Built with Django and Django REST Framework, backed by MySQL, and deployed on Render.

- **Live app:** <https://krishnahub.dpdns.org/>
- **Frontend repo:** [personalhub_frontend](https://github.com/mahanthileelakrishnaprasad-alt/personalhub_frontend) (React + Vite)
- **Earlier version:** [Task_manager_project](https://github.com/mahanthileelakrishnaprasad-alt/Task_manager_project) (Django templates only)

### Demo login

Recruiters and reviewers can explore the full app with this demo account:

| Username | Password |
|---|---|
| `sham` | `Myth@333` |

---

## Features

- **JWT authentication** so every user sees only their own data
- **Daily task manager** with full CRUD
- **Daily routine tracking** with per-day entries and summaries
- **Money tracker** for managing income and expenses
- **File uploads** stored in Cloudinary, so files work across devices
- **Email reminders** sent through the Brevo transactional API
- **Keep-alive ping** via cron-job.org so the free-tier Render instance stays awake

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Django, Django REST Framework |
| Auth | JWT |
| Database | MySQL on Aiven (SSL) |
| File storage | Cloudinary |
| Email | Brevo (transactional API) |
| Server | Gunicorn |
| Hosting | Render |
| Version control | Git, GitHub |

## Project Structure

```
personalhub/
├── taskmaster/        # Django project: settings, urls, wsgi
├── tasks/             # Main app: models, serializers, viewsets
├── manage.py
├── requirements.txt
├── runtime.txt        # Pins the Python version for Render
├── Procfile           # Start command for the web process
├── build.sh           # Render build script
└── .gitignore
```

## Design Notes

- **ViewSets and routers:** each module is a `ModelViewSet` registered through DRF's `DefaultRouter`, which keeps the URLs consistent and the views short.
- **One entry per day:** `RoutineEntry` uses `unique_together` so a routine can only have one entry per date.
- **Idempotent saves:** `update_or_create` is used for upserts, so saving the same day twice updates the entry instead of creating a duplicate.
- **Summaries:** custom `@action` endpoints on the viewsets return aggregated data (for example, routine and spending summaries).
- **Non-image uploads:** Cloudinary uploads for PDFs and other non-image files use `resource_type='raw'`.

## Getting Started

### Prerequisites

- Python 3.12 (see `runtime.txt`)
- A MySQL database (Aiven or local)
- A Cloudinary account and a Brevo account (only needed for uploads and email reminders)

### 1. Clone and install

```bash
git clone https://github.com/mahanthileelakrishnaprasad-alt/personalhub.git
cd personalhub

python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file next to `manage.py`. Match the names to the ones read in `taskmaster/settings.py`:

```env
SECRET_KEY=your-django-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173

# Database (Aiven MySQL, SSL required)
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=
DB_PORT=

# Cloudinary
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=

# Brevo (email reminders)
BREVO_API_KEY=
```

> **Security:** never commit `.env` or real credentials, and keep `.env` in `.gitignore`. If a credential was ever committed, removing the file is not enough because it stays in git history, so rotate it.

### 3. Migrate and run

```bash
python manage.py migrate
python manage.py createsuperuser   # optional
python manage.py runserver
```

The API is now available at <http://127.0.0.1:8000/>. Run the [frontend](https://github.com/mahanthileelakrishnaprasad-alt/personalhub_frontend) alongside it for the full app.

## Deployment (Render)

1. Create a Render web service from this repository.
2. **Build command:** `./build.sh` (installs dependencies, runs `collectstatic` and `migrate`).
3. **Start command:** `gunicorn taskmaster.wsgi` (also defined in the `Procfile`).
4. Add all environment variables from above in the Render dashboard, with `DEBUG=False`, and set `CORS_ALLOWED_ORIGINS` to your frontend URL.
5. Add a [cron-job.org](https://cron-job.org) job that pings the service every few minutes to prevent free-tier spin-down.

## Author

**Krishna (Mahanthi Leela Krishna Prasad)**
Python / Django backend developer, Hyderabad, India

- GitHub: [mahanthileelakrishnaprasad-alt](https://github.com/mahanthileelakrishnaprasad-alt)
- LinkedIn: [mahanthi-leela-krishna-prasad](https://www.linkedin.com/in/mahanthi-leela-krishna-prasad-b52699300)
