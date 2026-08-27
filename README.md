# Team Availability

A lightweight shared meeting-time poll for Monday-Friday, 11:00 am-5:00 pm in Melbourne time, using 30-minute slots.

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ADMIN_PASSWORD='choose-a-password'
export SECRET_KEY='choose-a-random-secret'
python app.py
```

Open `http://localhost:5000`. Admin is at `http://localhost:5000/admin`.

## Deploy on Render

1. Push this folder to a GitHub repository.
2. In Render, choose **New > Blueprint** and connect the repository containing `render.yaml`.
3. Set `ADMIN_PASSWORD` when Render asks for it.
4. Deploy.
5. Share the generated `https://...onrender.com` URL with the team. Keep `/admin` for yourself.

### Data persistence

The included `render.yaml` mounts `/var/data` and stores SQLite at `/var/data/availability.db`. Render persistent disks are attached to paid web services. Without a persistent disk, SQLite data on Render's default filesystem can be lost on restart/redeploy.

## Main features

- Name entry with optional expected-participant list
- Click and drag to select availability
- Monday-Friday, 11:00-17:00, 30-minute slots
- Team overlap heatmap
- Best continuous meeting windows for 30/60/90/120 minutes
- Pending-response tracking
- Password-protected admin page
- Add/delete participants and reset all responses
