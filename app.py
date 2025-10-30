import sqlite3
from flask import Flask, render_template, session, redirect, url_for, request, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
import os
import requests

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "users.db")

app = Flask(__name__)
app.secret_key = "çok-gizli-bir-anahtar-değiştir"

# ---------- Veritabanı yardımcıları ----------
def get_db():
    if "db" not in g:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DATABASE)
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    db.commit()
    db.close()

# ---------- Kütüphane tablosu ----------
def init_library_db():
    db = sqlite3.connect(DATABASE)
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            content TEXT
        )
    """)
    db.commit()
    db.close()

init_db()
init_library_db()

# ---------- Auth rotaları ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not username or not password:
            flash("Kullanıcı adı ve şifre boş olamaz.")
            return render_template('register.html')

        db = get_db()
        try:
            hashed = generate_password_hash(password)
            db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed))
            db.commit()
        except sqlite3.IntegrityError:
            flash("Bu kullanıcı adı zaten alınmış.")
            return render_template('register.html')

        session['user'] = username
        flash("Kayıt başarılı! Hoşgeldiniz.")
        return redirect(url_for('home'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not username or not password:
            flash("Kullanıcı adı ve şifre girin.")
            return render_template('login.html')

        db = get_db()
        cur = db.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        if row and check_password_hash(row['password'], password):
            session['user'] = username
            next_page = request.args.get('next') or url_for('home')
            if not next_page.startswith('/'):
                next_page = url_for('home')
            return redirect(next_page)
        else:
            flash("Kullanıcı adı veya şifre yanlış.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash("Çıkış yapıldı.")
    return redirect(url_for('login'))

# ---------- Oturum kontrolü ----------
@app.before_request
def require_login():
    allowed = {'login', 'register', 'static'}
    if request.endpoint is None:
        return
    if request.endpoint in allowed:
        return
    if 'user' in session:
        return
    return redirect(url_for('login', next=request.path))

# ---------- Sayfa rotaları ----------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/search', methods=['GET', 'POST'])
def search():
    results = []
    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        if query:
            results = [
                {"title": f"{query} hakkında bilgi 1", "link": "#", "snippet": "Burada özet bilgi 1 yer alacak."},
                {"title": f"{query} hakkında bilgi 2", "link": "#", "snippet": "Burada özet bilgi 2 yer alacak."},
                {"title": f"{query} hakkında bilgi 3", "link": "#", "snippet": "Burada özet bilgi 3 yer alacak."},
            ]
    return render_template('search.html', results=results)

# ---------- Ask rotası (SerpAPI ile Google) ----------
SERPAPI_KEY = "d3b44d1d90069fc87916c42e632795790dbb221bb00bb85e7a398967f494d88b"

@app.route('/ask', methods=['GET', 'POST'])
def ask():
    answers = []
    if request.method == 'POST':
        question = request.form.get('question', '').strip()
        if question:
            try:
                url = "https://serpapi.com/search.json"
                params = {
                    "q": question,
                    "hl": "tr",
                    "gl": "tr",
                    "api_key": SERPAPI_KEY
                }
                response = requests.get(url, params=params, timeout=10)
                data = response.json()

                if "organic_results" in data:
                    for result in data["organic_results"][:3]:
                        answers.append({
                            "title": result.get("title", question),
                            "snippet": result.get("snippet", "Cevap bulunamadı."),
                            "link": result.get("link", "#")
                        })
                else:
                    answers.append({
                        "title": question,
                        "snippet": "Cevap bulunamadı.",
                        "link": "#"
                    })
            except Exception as e:
                answers.append({
                    "title": question,
                    "snippet": f"Cevap alınamadı. Hata: {str(e)}",
                    "link": "#"
                })
    return render_template('ask.html', answers=answers)

# ---------- Kütüphane ----------
@app.route('/save', methods=['POST'])
def save():
    title = request.form['title']
    content = request.form['content']
    link = request.form.get('link', '#')  # Link yoksa '#' kullan
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id FROM users WHERE username = ?", (session['user'],))
    user_row = cur.fetchone()
    if user_row:
        user_id = user_row['id']
        cur.execute("INSERT INTO library (user_id, title, content, link) VALUES (?, ?, ?, ?)",
                    (user_id, title, content, link))
        db.commit()
    return redirect('/library')


@app.route('/library')
def library():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id FROM users WHERE username = ?", (session['user'],))
    user_row = cur.fetchone()
    entries = []
    if user_row:
        user_id = user_row['id']
        cur.execute("SELECT id, title, content FROM library WHERE user_id=? ORDER BY title ASC", (user_id,))
        entries = cur.fetchall()
    return render_template('library.html', entries=entries)

@app.route('/delete/<int:entry_id>', methods=['POST'])
def delete(entry_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id FROM users WHERE username = ?", (session['user'],))
    user_row = cur.fetchone()
    if user_row:
        user_id = user_row['id']
        cur.execute("DELETE FROM library WHERE id=? AND user_id=?", (entry_id, user_id))
        db.commit()
    return redirect('/library')

# ---------- Debug ----------
@app.route('/_debug_users')
def debug_users():
    db = get_db()
    rows = db.execute("SELECT username FROM users").fetchall()
    users = [r['username'] for r in rows]
    return "<br>".join(users) or "Kayıtlı kullanıcı yok."

# ---------- Ana program ----------
if __name__ == '__main__':
    app.run(debug=True)
