# Team Availability

A deliberately small meeting-availability web app for a shared team link.

## Stack

- Flask
- PostgreSQL
- Vanilla HTML/CSS/JavaScript
- Gunicorn
- Render-compatible deployment

The public Render service can remain on the **Free** compute plan because the app no longer stores data on Render's local filesystem. Availability is stored in an external PostgreSQL database through `DATABASE_URL`.

## Features

- Monday–Friday availability grid
- 11:00 am–5:00 pm Melbourne time
- 30-minute blocks
- Click and drag selection
- Shared team overlap heatmap
- Automatic best-time ranking for 30/60/90/120-minute meetings
- Expected-participant list and pending-response status
- Password-protected admin page
- Reset/delete participant controls

## Deploy on Render

1. Push this repository to GitHub.
2. Create a PostgreSQL database with a provider of your choice (for example Neon).
3. Copy the provider's PostgreSQL connection string. It normally starts with `postgresql://`.
4. In Render, create a **Web Service** from this GitHub repository and select the **Free** compute plan.
5. Use:

   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`

6. Add these environment variables in Render:

   - `DATABASE_URL` = your PostgreSQL connection string
   - `ADMIN_PASSWORD` = a private password chosen by you
   - `SECRET_KEY` = a long random value (Render can generate it)

7. Deploy.

The database tables are created automatically on first startup.

## URLs

- Public page: `/`
- Admin: `/admin`
- Health check: `/health`

## Updating an existing GitHub repository

If you already uploaded the earlier SQLite version, replace the repository files with this version and commit/push. Render can then redeploy automatically from `main`.

## Security note

Do not commit `DATABASE_URL`, `ADMIN_PASSWORD`, or `SECRET_KEY` to GitHub. Store them only as Render environment variables (and in a local `.env` file if needed for development).
