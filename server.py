#!/usr/bin/env python3
"""Internship Pilot: a single-user, loopback-only application preparation service."""
import argparse
import base64
from pdf_resume import make_pdf
import hashlib
import html
import json
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('PILOT_DATA_DIR', ROOT / 'data'))
POLL_LOCK = threading.Lock()
STOP = threading.Event()
PORT = 8765
TOKEN = ''
SKILLS = ['python', 'java', 'javascript', 'typescript', 'react', 'node.js', 'sql', 'aws', 'numpy', 'pandas', 'machine learning', 'deep learning', 'data engineering', 'git', 'c++', 'c', 'matplotlib', 'seaborn', 'streamlit', 'quicksight', 'amazon q', 'fft', 'randomforest', 'feature engineering', 'hyperparameter tuning', 'agentic ai', 'cloud', 'backend', 'dashboard', 'classification']


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def db():
    con = sqlite3.connect(DATA / 'pilot.sqlite', timeout=30)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    try:
        yield con
        con.commit()
    finally:
        con.close()


def clean_html(value):
    value = html.unescape(str(value or ''))
    value = re.sub(r'<(?:script|style)\b[^>]*>.*?</(?:script|style)>', '', value, flags=re.S | re.I)
    value = re.sub(r'</(?:p|li|div|h\d)>|<br\s*/?>', '\n', value, flags=re.I)
    return re.sub(r'<[^>]+>', '', value).strip()


def seed_profile():
    """New checkouts start blank. Existing private profiles remain in the local database."""
    return dict(first_name='', last_name='', email='', phone='', location='', linkedin='', github='', website='', school='', graduation='', roles='software, data, machine learning, artificial intelligence, ai, engineer, developer, research, security, cloud, technical, technology, systems, analytics, quantitative', locations='', resume='', answers=[])


def initialize():
    global TOKEN
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(DATA, 0o700)
    token_path = DATA / 'extension-token'
    if not token_path.exists():
        token_path.write_text(secrets.token_urlsafe(32))
    os.chmod(token_path, 0o600)
    TOKEN = token_path.read_text().strip()
    with db() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sources (id INTEGER PRIMARY KEY, provider TEXT NOT NULL, slug TEXT NOT NULL, company TEXT NOT NULL, enabled INTEGER DEFAULT 1, checked_at TEXT, error TEXT, UNIQUE(provider, slug));
        CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL, external_id TEXT, title TEXT NOT NULL, company TEXT NOT NULL, location TEXT, url TEXT NOT NULL UNIQUE, description TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, open INTEGER DEFAULT 1, saved INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS applications (id INTEGER PRIMARY KEY, job_id TEXT UNIQUE NOT NULL REFERENCES jobs(id), status TEXT NOT NULL DEFAULT 'draft', resume TEXT NOT NULL, analysis TEXT NOT NULL, fields TEXT NOT NULL, profile_snapshot TEXT NOT NULL, approved_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL, read INTEGER DEFAULT 0);
        ''')
        con.execute('INSERT OR IGNORE INTO settings VALUES (?, ?)', ('profile', json.dumps(seed_profile())))
        con.execute('INSERT OR IGNORE INTO settings VALUES (?, ?)', ('monitor', json.dumps({'enabled': True, 'interval_minutes': 60, 'desktop_notifications': True, 'auto_prepare': True})))
        if not con.execute("SELECT 1 FROM settings WHERE key='watchlist_seeded'").fetchone():
            for slug, company in [('cloudflare','Cloudflare'),('databricks','Databricks'),('figma','Figma'),('scaleai','Scale AI'),('pinterest','Pinterest'),('roblox','Roblox')]:
                con.execute('INSERT OR IGNORE INTO sources(provider,slug,company) VALUES (?,?,?)', ('greenhouse',slug,company))
            con.execute('INSERT INTO settings VALUES (?,?)', ('watchlist_seeded','true'))
    os.chmod(DATA / 'pilot.sqlite', 0o600)


def get_setting(key):
    with db() as con:
        return json.loads(con.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()[0])


def event(con, kind, message):
    con.execute('INSERT INTO events(kind,message,created_at) VALUES (?,?,?)', (kind, message, now()))


def terms(text):
    return set(re.findall(r'[a-z][a-z0-9+#.]*', text.lower()))


def has_phrase(text, phrase):
    return bool(re.search(r'(?<![a-z0-9])' + re.escape(phrase) + r'(?![a-z0-9])', text.lower()))


def analyze(job, profile):
    required = [s for s in SKILLS if has_phrase(job['description'] + ' ' + job['title'], s)]
    matched = [s for s in required if has_phrase(profile['resume'], s)]
    gaps = [s for s in required if s not in matched]
    return {'matched': matched, 'gaps': gaps, 'coverage': round(100 * len(matched) / len(required)) if required else None, 'method': 'Keyword coverage of a fixed skills vocabulary; not a hiring probability.', 'changes': [], 'warnings': ['Verify graduation, dates, work authorization, location, and every claim before approving.']}


def tailor(job, profile):
    """Reorder verbatim bullets inside their original heading. Never move facts between roles."""
    analysis = analyze(job, profile)
    lines = profile['resume'].splitlines()
    result, i = [], 0
    while i < len(lines):
        if re.match(r'^\s*(?:[•*-]|\d+\.)\s', lines[i]):
            block = []
            while i < len(lines) and re.match(r'^\s*(?:[•*-]|\d+\.)\s', lines[i]):
                block.append(lines[i]); i += 1
            ordered = sorted(block, key=lambda line: -sum(has_phrase(line, s) for s in analysis['matched']))
            if block != ordered:
                analysis['changes'].append({'section': next((r for r in reversed(result) if r.strip()), 'Experience'), 'before': block, 'after': ordered})
            result.extend(ordered)
        else:
            result.append(lines[i]); i += 1
    return '\n'.join(result), analysis


def fields_for(profile):
    keys = ['first_name', 'last_name', 'email', 'phone', 'location', 'linkedin', 'github', 'website', 'school', 'graduation']
    fields = {k: profile.get(k, '') for k in keys}
    fields['full_name'] = (fields['first_name'] + ' ' + fields['last_name']).strip()
    fields['custom'] = profile.get('answers', [])
    return fields


def safe_url(value):
    parsed = urlparse(str(value))
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use a complete HTTPS application URL.')
    return str(value)


def download_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'InternshipPilot/1.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read(12_000_001)
        if len(raw) > 12_000_000:
            raise ValueError('Company feed exceeds the 12 MB response limit.')
        return json.loads(raw)


def fetch_source(source):
    slug = source['slug']
    if source['provider'] == 'greenhouse':
        data = download_json(f'https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true')
        if not isinstance(data, dict) or not isinstance(data.get('jobs'), list):
            raise ValueError('Unexpected Greenhouse response')
        return [dict(external_id=str(j['id']), title=j['title'], location=j.get('location', {}).get('name', ''), url=j['absolute_url'], description=clean_html(j.get('content', ''))) for j in data['jobs']]
    if source['provider'] == 'ashby':
        data = download_json(f'https://api.ashbyhq.com/posting-api/job-board/{slug}')
        if not isinstance(data, dict) or not isinstance(data.get('jobs'), list):
            raise ValueError('Unexpected Ashby response')
        return [dict(external_id=j['id'], title=j['title'], location=j.get('location','') + (' · Remote' if j.get('isRemote') else ''), url=j.get('applyUrl') or j['jobUrl'], description=j.get('descriptionPlain') or clean_html(j.get('descriptionHtml',''))) for j in data['jobs'] if j.get('isListed', True)]
    result, skip = [], 0
    host = 'api.eu.lever.co' if source['provider'] == 'lever-eu' else 'api.lever.co'
    while True:
        batch = download_json(f'https://{host}/v0/postings/{slug}?mode=json&limit=100&skip={skip}')
        if not isinstance(batch, list):
            raise ValueError('Unexpected Lever response')
        for j in batch:
            description = j.get('descriptionPlain') or clean_html(j.get('description', ''))
            for section in j.get('lists', []):
                description += '\n' + section.get('text', '') + '\n' + clean_html(section.get('content', ''))
            description += '\n' + (j.get('additionalPlain') or clean_html(j.get('additional', '')))
            result.append(dict(external_id=j['id'], title=j['text'], location=j.get('categories', {}).get('location', ''), url=j.get('applyUrl') or j['hostedUrl'], description=description.strip()))
        if len(batch) < 100:
            break
        skip += 100
        if skip > 20000:
            raise ValueError('Feed pagination limit reached; scan incomplete, no jobs changed.')
    return result


def relevant(job, profile):
    if not re.search(r'\b(interns?|internships?|co-?op|placement)\b', job['title'], re.I):
        return False
    roles = [t.strip().lower() for t in profile.get('roles', '').split(',') if t.strip()]
    locations = [t.strip().lower() for t in profile.get('locations', '').split(',') if t.strip()]
    return (not roles or any(has_phrase(job['title'], t) or (len(t)>3 and any(w.startswith(t) for w in terms(job['title']))) for t in roles)) and (not locations or any(t in job['location'].lower() for t in locations))


def prepare_packet(con, job, profile):
    existing = con.execute('SELECT id FROM applications WHERE job_id=?', (job['id'],)).fetchone()
    if existing:
        return existing['id']
    if not profile['resume'].strip():
        raise ValueError('Add your resume text in Profile first.')
    resume, analysis = tailor(dict(job), profile)
    cursor = con.execute('INSERT INTO applications(job_id,resume,analysis,fields,profile_snapshot,created_at,updated_at) VALUES (?,?,?,?,?,?,?)', (job['id'], resume, json.dumps(analysis), json.dumps(fields_for(profile)), json.dumps(profile), now(), now()))
    event(con, 'draft', f"Ready for review: {job['title']} at {job['company']}")
    return cursor.lastrowid


def poll_sources():
    if not POLL_LOCK.acquire(blocking=False):
        return {'busy': True, 'new': 0, 'errors': []}
    added, errors = 0, []
    try:
        profile = get_setting('profile')
        auto_prepare = get_setting('monitor').get('auto_prepare', True)
        with db() as con:
            sources = [dict(r) for r in con.execute('SELECT * FROM sources WHERE enabled=1')]
        for source in sources:
            try:
                jobs = fetch_source(source)
                # Validate the complete feed before closing missing roles.
                for j in jobs:
                    safe_url(j['url'])
                with db() as con:
                    previous = {r['external_id']: dict(r) for r in con.execute('SELECT * FROM jobs WHERE source_id=?', (source['id'],))}
                    seen = set()
                    for job in jobs:
                        seen.add(job['external_id'])
                        old = previous.get(job['external_id'])
                        if not old and not relevant(job, profile):
                            continue
                        stamp = now()
                        if old:
                            con.execute('UPDATE jobs SET title=?, location=?, description=?, url=?, last_seen=?, open=1 WHERE id=?', (job['title'], job['location'], job['description'], job['url'], stamp, old['id']))
                            if not old['open']:
                                event(con, 'reopened', f"{source['company']} reopened {job['title']}")
                        else:
                            jid = hashlib.sha256(job['url'].encode()).hexdigest()[:20]
                            cursor = con.execute('INSERT OR IGNORE INTO jobs(id,source_id,external_id,title,company,location,url,description,first_seen,last_seen) VALUES (?,?,?,?,?,?,?,?,?,?)', (jid, source['id'], job['external_id'], job['title'], source['company'], job['location'], job['url'], job['description'], stamp, stamp))
                            if cursor.rowcount:
                                added += 1
                                event(con, 'opening', f"Newly discovered: {job['title']} at {source['company']}")
                        if auto_prepare and profile['resume'].strip() and relevant(job, profile):
                            packet_job = con.execute('SELECT * FROM jobs WHERE url=?', (job['url'],)).fetchone()
                            if packet_job:
                                prepare_packet(con, packet_job, profile)
                        # Existing snapshots remain approved for editing in the dashboard, but cannot be filled after the job changes.
                        if old and (old['description'] != job['description'] or old['url'] != job['url']):
                            con.execute("UPDATE applications SET status='draft',approved_at=NULL,updated_at=? WHERE job_id=? AND status IN ('approved','filled')", (stamp, old['id']))
                    for ext, old in previous.items():
                        if ext not in seen and old['open']:
                            con.execute('UPDATE jobs SET open=0 WHERE id=?', (old['id'],))
                            event(con, 'closed', f"No longer on board: {old['title']} at {old['company']}")
                    con.execute('UPDATE sources SET checked_at=?,error=NULL WHERE id=?', (now(), source['id']))
            except Exception as exc:
                message = f"{source['company']}: {str(exc)[:200]}"
                errors.append(message)
                with db() as con:
                    con.execute('UPDATE sources SET checked_at=?,error=? WHERE id=?', (now(), str(exc)[:300], source['id']))
                    event(con, 'error', message)
        if added and get_setting('monitor').get('desktop_notifications', True):
            notify_desktop(added)
        return {'new': added, 'errors': errors}
    finally:
        POLL_LOCK.release()


def notify_desktop(count):
    if sys.platform == 'darwin':
        try:
            subprocess.run(['osascript', '-e', f'display notification "{count} newly discovered internships. Open your local dashboard to review." with title "Internship Pilot"'], capture_output=True, timeout=4)
        except (OSError, subprocess.TimeoutExpired):
            pass  # Activity is durable even if system notifications are unavailable.


def monitor_loop():
    next_poll = 0
    while not STOP.wait(10):
        cfg = get_setting('monitor')
        if cfg['enabled'] and time.monotonic() >= next_poll:
            poll_sources()
            next_poll = time.monotonic() + cfg['interval_minutes'] * 60
        if not cfg['enabled']:
            next_poll = 0


def application_dict(row):
    a = dict(row)
    for k in ['fields', 'analysis', 'profile_snapshot']:
        a[k] = json.loads(a[k])
    return a


def state():
    profile = get_setting('profile')
    with db() as con:
        jobs = [dict(r) for r in con.execute('SELECT * FROM jobs ORDER BY first_seen DESC')]
        apps = [application_dict(r) for r in con.execute('SELECT * FROM applications ORDER BY updated_at DESC')]
        sources = [dict(r) for r in con.execute('SELECT * FROM sources ORDER BY company')]
        events = [dict(r) for r in con.execute('SELECT * FROM events ORDER BY id DESC LIMIT 100')]
    app_jobs = {a['job_id'] for a in apps}
    jobs = [j for j in jobs if j['source_id'] is None or relevant(j, profile) or j['id'] in app_jobs]
    for j in jobs:
        j['analysis'] = analyze(j, profile)
    return dict(profile=profile, jobs=jobs, applications=apps, sources=sources, events=events, monitor=get_setting('monitor'))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Never log request bodies or pairing credentials.
        pass

    def json_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def guard(self, extension=False):
        host = self.headers.get('Host', '')
        if host not in [f'127.0.0.1:{PORT}', f'localhost:{PORT}']:
            raise PermissionError('Invalid host')
        origin = self.headers.get('Origin')
        if extension:
            if not secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + TOKEN):
                raise PermissionError('Pair the extension using the dashboard token.')
        elif origin and origin not in [f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}']:
            raise PermissionError('Cross-origin requests are blocked.')
        if not extension and self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise PermissionError('Cross-site requests are blocked.')

    def do_GET(self):
        try:
            path = urlparse(self.path).path
            extension = path.startswith('/api/extension/')
            self.guard(extension)
            if path == '/api/state':
                return self.json_response(state())
            if path == '/api/pairing':
                return self.json_response({'token': TOKEN})
            if path == '/api/extension/applications':
                with db() as con:
                    rows = con.execute("SELECT a.*,j.url,j.title,j.company FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.status IN ('approved','filled') AND j.open=1").fetchall()
                return self.json_response([dict(id=r['id'], url=r['url'], title=r['title'], company=r['company']) for r in rows])
            if path.startswith('/api/extension/application/'):
                aid = int(path.rsplit('/', 1)[-1])
                with db() as con:
                    row = con.execute("SELECT a.*, j.url,j.open FROM applications a JOIN jobs j ON a.job_id=j.id WHERE a.id=?", (aid,)).fetchone()
                if not row or row['status'] not in ('approved', 'filled') or not row['open']:
                    raise ValueError('Application is not approved, or the role has closed.')
                # Extension receives the exact reviewed snapshot, never the latest unreviewed profile.
                return self.json_response(dict(id=aid, url=row['url'], fields=json.loads(row['fields']), resume=row['resume'], pdf=base64.b64encode(make_pdf(row['resume'])).decode()))
            if path.startswith('/api/pdf/'):
                aid = int(path.rsplit('/', 1)[-1])
                with db() as con:
                    row = con.execute('SELECT resume FROM applications WHERE id=?', (aid,)).fetchone()
                if not row:
                    raise ValueError('Application not found')
                data = make_pdf(row['resume'])
                self.send_response(200)
                self.send_header('Content-Type', 'application/pdf')
                self.send_header('Content-Disposition', f'attachment; filename="resume-{aid}.pdf"')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(data)
                return
            if path.startswith('/api/resume/'):
                aid = int(path.rsplit('/', 1)[-1])
                with db() as con:
                    row = con.execute('SELECT resume FROM applications WHERE id=?', (aid,)).fetchone()
                if not row:
                    raise ValueError('Application not found')
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Content-Disposition', f'attachment; filename="resume-{aid}.txt"')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(row['resume'].encode())
                return
            files = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}
            if path not in files:
                return self.json_response({'error': 'Not found'}, 404)
            data = (ROOT / 'static' / files[path]).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', {'/': 'text/html; charset=utf-8', '/app.js': 'text/javascript', '/style.css': 'text/css'}[path])
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)
        except PermissionError as exc:
            self.json_response({'error': str(exc)}, 403)
        except (ValueError, KeyError) as exc:
            self.json_response({'error': str(exc)}, 400)
        except Exception:
            self.json_response({'error': 'Server error. Your previous data is preserved.'}, 500)

    def do_POST(self):
        try:
            path = urlparse(self.path).path
            self.guard(path.startswith('/api/extension/'))
            if 'application/json' not in self.headers.get('Content-Type', ''):
                raise ValueError('JSON body required')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1_000_000:
                raise ValueError('Body must be 1 byte–1 MB')
            body = json.loads(self.rfile.read(length))
            result = self.mutate(path, body)
            self.json_response(result or {'ok': True})
        except PermissionError as exc:
            self.json_response({'error': str(exc)}, 403)
        except (ValueError, KeyError, TypeError, sqlite3.IntegrityError) as exc:
            self.json_response({'error': str(exc)}, 400)
        except Exception:
            self.json_response({'error': 'Server error. Your previous data is preserved.'}, 500)

    def mutate(self, path, body):
        if path == '/api/profile':
            old = get_setting('profile')
            p = {k: str(body.get(k, old[k])).strip()[:100000 if k == 'resume' else 1000] for k in old if k != 'answers'}
            answers = body.get('answers', old.get('answers', []))
            if not isinstance(answers, list) or any(not isinstance(a, dict) or not isinstance(a.get('label'), str) or not isinstance(a.get('value'), str) or not a['label'].strip() for a in answers):
                raise ValueError('Each saved answer needs an exact question label and a text value.')
            p['answers'] = [{'label': a['label'].strip()[:500], 'value': a['value'].strip()[:10000]} for a in answers[:100]]
            with db() as con:
                con.execute('UPDATE settings SET value=? WHERE key=?', (json.dumps(p), 'profile'))
            return
        if path == '/api/source':
            provider, slug, company = body['provider'], body['slug'].strip(), body['company'].strip()
            if provider not in ['greenhouse', 'lever', 'lever-eu', 'ashby'] or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', slug) or not company:
                raise ValueError('Choose a provider, company name, and a valid board slug.')
            with db() as con:
                con.execute('INSERT INTO sources(provider,slug,company) VALUES (?,?,?)', (provider, slug, company[:150]))
            return
        if path == '/api/source/toggle':
            with db() as con:
                con.execute('UPDATE sources SET enabled=? WHERE id=?', (int(bool(body['enabled'])), int(body['id'])))
            return
        if path == '/api/poll':
            return poll_sources()
        if path == '/api/monitor':
            cfg = {'enabled': bool(body['enabled']), 'interval_minutes': max(15, min(1440, int(body['interval_minutes']))), 'desktop_notifications': bool(body.get('desktop_notifications', True)), 'auto_prepare': bool(body.get('auto_prepare', True))}
            with db() as con:
                con.execute('UPDATE settings SET value=? WHERE key=?', (json.dumps(cfg), 'monitor'))
            return
        if path == '/api/events/read':
            with db() as con:
                con.execute('UPDATE events SET read=1 WHERE id<=?', (int(body['through_id']),))
            return
        if path == '/api/job':
            url = safe_url(body['url'].strip())
            if not body.get('title', '').strip() or not body.get('company', '').strip() or not body.get('description', '').strip():
                raise ValueError('Title, company, and job description are required.')
            jid = hashlib.sha256(url.encode()).hexdigest()[:20]
            with db() as con:
                con.execute('INSERT INTO jobs(id,title,company,location,url,description,first_seen,last_seen) VALUES (?,?,?,?,?,?,?,?)', (jid, body['title'][:300], body['company'][:150], body.get('location', '')[:300], url, body['description'][:100000], now(), now()))
            return {'id': jid}
        if path == '/api/prepare':
            profile = get_setting('profile')
            if not profile['resume'].strip():
                raise ValueError('Add your resume text in Profile first.')
            with db() as con:
                job = con.execute('SELECT * FROM jobs WHERE id=?', (body['job_id'],)).fetchone()
                if not job or not job['open']:
                    raise ValueError('Open job not found.')
                return {'id': prepare_packet(con, job, profile)}
        if path == '/api/application':
            with db() as con:
                app = con.execute('SELECT * FROM applications WHERE id=?', (int(body['id']),)).fetchone()
                if not app:
                    raise ValueError('Application not found')
                action = body['action']
                if action == 'save':
                    if not body.get('resume', '').strip():
                        raise ValueError('Resume cannot be empty.')
                    fields = body.get('fields')
                    if not isinstance(fields, dict) or any(not isinstance(fields.get(k, ''), str) for k in fields_for(get_setting('profile')) if k != 'custom'):
                        raise ValueError('Invalid application fields.')
                    if not isinstance(fields.get('custom', []), list) or any(not isinstance(a, dict) or not isinstance(a.get('label'), str) or not isinstance(a.get('value'), str) or not a['label'].strip() for a in fields.get('custom', [])):
                        raise ValueError('Invalid custom answers.')
                    con.execute("UPDATE applications SET resume=?,fields=?,status='draft',approved_at=NULL,updated_at=? WHERE id=?", (body['resume'][:100000], json.dumps(fields), now(), app['id']))
                elif action == 'approve':
                    if body.get('reviewed') is not True:
                        raise ValueError('Confirm that you reviewed the resume and answers.')
                    job = con.execute('SELECT open FROM jobs WHERE id=?', (app['job_id'],)).fetchone()
                    if not job['open']:
                        raise ValueError('This role is no longer open.')
                    if not app['resume'].strip() or not json.loads(app['fields']).get('email'):
                        raise ValueError('Resume and email are required before approval.')
                    con.execute("UPDATE applications SET status='approved',approved_at=?,updated_at=? WHERE id=?", (now(), now(), app['id']))
                elif action == 'submitted':
                    if app['status'] not in ('approved', 'filled'):
                        raise ValueError('Approve this application before marking it submitted.')
                    con.execute("UPDATE applications SET status='submitted',updated_at=? WHERE id=?", (now(), app['id']))
                elif action == 'reopen':
                    con.execute("UPDATE applications SET status='draft',approved_at=NULL,updated_at=? WHERE id=?", (now(), app['id']))
                else:
                    raise ValueError('Unknown application action')
            return
        if path == '/api/extension/filled':
            with db() as con:
                row = con.execute("SELECT a.id FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.id=? AND a.status IN ('approved','filled') AND j.open=1", (int(body['id']),)).fetchone()
                if not row:
                    raise ValueError('Application no longer approved.')
                con.execute("UPDATE applications SET status='filled',updated_at=? WHERE id=?", (now(), row['id']))
                event(con, 'filled', 'Form fields filled. Final page review and submission still required.')
            return
        raise ValueError('Unknown action')


def main():
    global PORT
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    PORT = args.port
    initialize()
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    threading.Thread(target=monitor_loop, daemon=True).start()
    print(f'Internship Pilot is running at http://127.0.0.1:{PORT}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        STOP.set()
        server.server_close()


if __name__ == '__main__':
    main()
