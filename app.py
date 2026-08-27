import os, sqlite3, secrets
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, abort

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-me-in-production')
DB_PATH = os.environ.get('DATABASE_PATH', os.path.join(os.path.dirname(__file__), 'availability.db'))
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin')

DAYS = ['Mon','Tue','Wed','Thu','Fri']
SLOTS = []
for h in range(11, 17):
    for m in (0,30):
        SLOTS.append(f'{h:02d}:{m:02d}')
SLOTS.append('17:00')


def db():
    os.makedirs(os.path.dirname(DB_PATH) or '.', exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            submitted_at TEXT
        );
        CREATE TABLE IF NOT EXISTS availability (
            participant_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            slot TEXT NOT NULL,
            PRIMARY KEY (participant_id, day, slot),
            FOREIGN KEY(participant_id) REFERENCES participants(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        ''')
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('meeting_duration','60')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('title','Find a Meeting Time')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('description','Select all times that work for you. We will combine everyone’s availability to find the best overlap.')")

init_db()


def get_settings():
    with db() as con:
        rows = con.execute('SELECT key,value FROM settings').fetchall()
    return {r['key']: r['value'] for r in rows}


def overlap_data():
    with db() as con:
        people = con.execute('SELECT id,name,submitted_at FROM participants ORDER BY name').fetchall()
        submitted = [p for p in people if p['submitted_at']]
        rows = con.execute('SELECT participant_id,day,slot FROM availability').fetchall()
    selected = {(r['participant_id'], r['day'], r['slot']) for r in rows}
    counts = {d:{s:0 for s in SLOTS} for d in DAYS}
    names = {d:{s:[] for s in SLOTS} for d in DAYS}
    for p in submitted:
        for d in DAYS:
            for s in SLOTS:
                if (p['id'], d, s) in selected:
                    counts[d][s]+=1
                    names[d][s].append(p['name'])
    return people, submitted, counts, names


def best_windows(duration):
    _, submitted, counts, names = overlap_data()
    nslots = max(1, duration // 30)
    out=[]
    for d in DAYS:
        for i in range(0, len(SLOTS)-nslots+1):
            window=SLOTS[i:i+nslots]
            # require consecutive half-hour slots; 17:00 can be a boundary/start only if duration allows but kept simple
            min_count=min(counts[d][s] for s in window)
            common=set(names[d][window[0]])
            for s in window[1:]: common &= set(names[d][s])
            out.append({'day':d,'start':window[0],'end':_add_minutes(window[0],duration),'count':len(common),'total':len(submitted),'names':sorted(common)})
    out.sort(key=lambda x:(x['count'], -DAYS.index(x['day']), -int(x['start'][:2])*60-int(x['start'][3:])), reverse=True)
    return out[:5]


def _add_minutes(t, mins):
    h,m=map(int,t.split(':')); total=h*60+m+mins
    return f'{total//60:02d}:{total%60:02d}'

@app.get('/')
def index():
    settings=get_settings()
    with db() as con:
        people=con.execute('SELECT name,submitted_at FROM participants ORDER BY name').fetchall()
    return render_template('index.html', days=DAYS, slots=SLOTS, settings=settings, people=people)

@app.get('/api/person/<path:name>')
def person(name):
    with db() as con:
        p=con.execute('SELECT id,submitted_at FROM participants WHERE name=?',(name.strip(),)).fetchone()
        if not p: return jsonify({'name':name,'selected':[],'submitted':False})
        rows=con.execute('SELECT day,slot FROM availability WHERE participant_id=?',(p['id'],)).fetchall()
    return jsonify({'name':name,'selected':[[r['day'],r['slot']] for r in rows],'submitted':bool(p['submitted_at'])})

@app.post('/api/save')
def save():
    data=request.get_json(force=True)
    name=(data.get('name') or '').strip()
    selected=data.get('selected') or []
    if not name or len(name)>80: return jsonify({'error':'Please enter your name.'}),400
    clean={(d,s) for d,s in selected if d in DAYS and s in SLOTS}
    with db() as con:
        con.execute('INSERT OR IGNORE INTO participants(name) VALUES(?)',(name,))
        p=con.execute('SELECT id FROM participants WHERE name=?',(name,)).fetchone()
        con.execute('DELETE FROM availability WHERE participant_id=?',(p['id'],))
        con.executemany('INSERT INTO availability(participant_id,day,slot) VALUES(?,?,?)',[(p['id'],d,s) for d,s in clean])
        con.execute('UPDATE participants SET submitted_at=? WHERE id=?',(datetime.utcnow().isoformat(),p['id']))
    return jsonify({'ok':True})

@app.get('/api/overlap')
def overlap():
    people, submitted, counts, names=overlap_data()
    duration=int(get_settings().get('meeting_duration','60'))
    return jsonify({
        'total_people':len(people), 'responses':len(submitted),
        'pending':[p['name'] for p in people if not p['submitted_at']],
        'counts':counts,'names':names,'best':best_windows(duration),'duration':duration
    })

@app.route('/admin', methods=['GET','POST'])
def admin():
    if request.method=='POST' and 'password' in request.form:
        if secrets.compare_digest(request.form['password'], ADMIN_PASSWORD):
            session['admin']=True
            return redirect(url_for('admin'))
        return render_template('admin_login.html', error='Incorrect password')
    if not session.get('admin'):
        return render_template('admin_login.html', error=None)
    with db() as con:
        people=con.execute('SELECT id,name,submitted_at FROM participants ORDER BY name').fetchall()
    return render_template('admin.html', people=people, settings=get_settings())

@app.post('/admin/settings')
def admin_settings():
    if not session.get('admin'): abort(403)
    allowed={'title','description','meeting_duration'}
    with db() as con:
        for k in allowed:
            if k in request.form:
                con.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,request.form[k]))
    return redirect(url_for('admin'))

@app.post('/admin/add')
def admin_add():
    if not session.get('admin'): abort(403)
    names=request.form.get('names','').replace(',', '\n').splitlines()
    with db() as con:
        for name in names:
            name=name.strip()
            if name: con.execute('INSERT OR IGNORE INTO participants(name) VALUES(?)',(name,))
    return redirect(url_for('admin'))

@app.post('/admin/delete/<int:pid>')
def admin_delete(pid):
    if not session.get('admin'): abort(403)
    with db() as con:
        con.execute('DELETE FROM availability WHERE participant_id=?',(pid,))
        con.execute('DELETE FROM participants WHERE id=?',(pid,))
    return redirect(url_for('admin'))

@app.post('/admin/reset')
def admin_reset():
    if not session.get('admin'): abort(403)
    with db() as con:
        con.execute('DELETE FROM availability')
        con.execute('UPDATE participants SET submitted_at=NULL')
    return redirect(url_for('admin'))

@app.get('/health')
def health(): return {'ok':True}

if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)), debug=True)
