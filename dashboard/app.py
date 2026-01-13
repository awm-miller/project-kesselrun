#!/usr/bin/env python3
"""
Instagram Monitor Dashboard
Simple Flask dashboard for managing the Instagram monitor remotely.
"""
import os
import sys
import json
from datetime import datetime
from pathlib import Path
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    DASHBOARD_PASSWORD,
    DASHBOARD_PORT,
    DASHBOARD_SECRET_KEY,
    ACCOUNTS_FILE,
    COOKIES_FILE,
    STATE_FILE,
    STATS_FILE,
    SUBSCRIBERS_FILE,
)

app = Flask(__name__)
app.secret_key = DASHBOARD_SECRET_KEY

# Base directory for all files (parent of dashboard)
BASE_DIR = Path(__file__).parent.parent


def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def load_json_file(filename: str) -> dict:
    """Load a JSON file from the base directory"""
    filepath = BASE_DIR / filename
    if filepath.exists():
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_json_file(filename: str, data: dict):
    """Save data to a JSON file in the base directory"""
    filepath = BASE_DIR / filename
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_file_age_days(filename: str) -> float:
    """Get the age of a file in days"""
    filepath = BASE_DIR / filename
    if filepath.exists():
        mtime = filepath.stat().st_mtime
        age_seconds = datetime.now().timestamp() - mtime
        return age_seconds / 86400  # Convert to days
    return -1


def get_file_mtime(filename: str) -> str:
    """Get the last modified time of a file as a formatted string"""
    filepath = BASE_DIR / filename
    if filepath.exists():
        mtime = filepath.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
    return "File not found"


# ============================================================
# ROUTES
# ============================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == DASHBOARD_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            flash('Invalid password', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Logout"""
    session.pop('logged_in', None)
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    """Main dashboard - shows stats overview"""
    # Load stats
    stats = load_json_file(STATS_FILE)
    state = load_json_file(STATE_FILE)
    accounts = load_json_file(ACCOUNTS_FILE).get('accounts', [])
    
    # Calculate per-account stats from state
    account_stats = []
    for account in accounts:
        username = account['username']
        if username in state:
            acc_state = state[username]
            account_stats.append({
                'username': username,
                'include_stories': account.get('include_stories', False),
                'posts_analyzed': len(acc_state.get('posts', [])),
                'stories_analyzed': len(acc_state.get('stories', [])),
                'last_run': acc_state.get('last_run', 'Never'),
                'flagged': stats.get('flagged_by_account', {}).get(username, 0)
            })
        else:
            account_stats.append({
                'username': username,
                'include_stories': account.get('include_stories', False),
                'posts_analyzed': 0,
                'stories_analyzed': 0,
                'last_run': 'Never',
                'flagged': 0
            })
    
    # Cookie status
    cookie_age = get_file_age_days(COOKIES_FILE)
    cookie_mtime = get_file_mtime(COOKIES_FILE)
    cookie_stale = cookie_age > 7 if cookie_age >= 0 else True
    
    return render_template('index.html',
        stats=stats,
        account_stats=account_stats,
        total_accounts=len(accounts),
        cookie_age=cookie_age,
        cookie_mtime=cookie_mtime,
        cookie_stale=cookie_stale
    )


@app.route('/cookies', methods=['GET', 'POST'])
@login_required
def cookies():
    """Cookie management page"""
    if request.method == 'POST':
        # Handle cookie update
        cookie_content = request.form.get('cookies', '')
        if cookie_content.strip():
            filepath = BASE_DIR / COOKIES_FILE
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(cookie_content)
            flash('Cookies updated successfully', 'success')
        else:
            flash('No cookie content provided', 'error')
        return redirect(url_for('cookies'))
    
    # Load current cookies
    filepath = BASE_DIR / COOKIES_FILE
    current_cookies = ""
    if filepath.exists():
        with open(filepath, 'r', encoding='utf-8') as f:
            current_cookies = f.read()
    
    cookie_age = get_file_age_days(COOKIES_FILE)
    cookie_mtime = get_file_mtime(COOKIES_FILE)
    cookie_stale = cookie_age > 7 if cookie_age >= 0 else True
    
    return render_template('cookies.html',
        current_cookies=current_cookies,
        cookie_age=cookie_age,
        cookie_mtime=cookie_mtime,
        cookie_stale=cookie_stale
    )


@app.route('/accounts', methods=['GET'])
@login_required
def accounts():
    """Account management page"""
    data = load_json_file(ACCOUNTS_FILE)
    accounts_list = data.get('accounts', [])
    state = load_json_file(STATE_FILE)
    
    # Enrich accounts with stats
    for account in accounts_list:
        username = account['username']
        if username in state:
            account['posts_analyzed'] = len(state[username].get('posts', []))
            account['stories_analyzed'] = len(state[username].get('stories', []))
        else:
            account['posts_analyzed'] = 0
            account['stories_analyzed'] = 0
    
    return render_template('accounts.html', accounts=accounts_list)


@app.route('/accounts/add', methods=['POST'])
@login_required
def add_account():
    """Add a new account"""
    username = request.form.get('username', '').strip().lower()
    include_stories = request.form.get('include_stories') == 'on'
    
    if not username:
        flash('Username is required', 'error')
        return redirect(url_for('accounts'))
    
    # Remove @ if present
    username = username.lstrip('@')
    
    data = load_json_file(ACCOUNTS_FILE)
    accounts_list = data.get('accounts', [])
    
    # Check if already exists
    if any(a['username'] == username for a in accounts_list):
        flash(f'Account @{username} already exists', 'error')
        return redirect(url_for('accounts'))
    
    accounts_list.append({
        'username': username,
        'include_stories': include_stories
    })
    
    data['accounts'] = accounts_list
    save_json_file(ACCOUNTS_FILE, data)
    
    flash(f'Account @{username} added successfully', 'success')
    return redirect(url_for('accounts'))


@app.route('/accounts/remove/<username>', methods=['POST'])
@login_required
def remove_account(username):
    """Remove an account"""
    data = load_json_file(ACCOUNTS_FILE)
    accounts_list = data.get('accounts', [])
    
    accounts_list = [a for a in accounts_list if a['username'] != username]
    data['accounts'] = accounts_list
    save_json_file(ACCOUNTS_FILE, data)
    
    flash(f'Account @{username} removed', 'success')
    return redirect(url_for('accounts'))


@app.route('/accounts/toggle-stories/<username>', methods=['POST'])
@login_required
def toggle_stories(username):
    """Toggle stories tracking for an account"""
    data = load_json_file(ACCOUNTS_FILE)
    accounts_list = data.get('accounts', [])
    
    for account in accounts_list:
        if account['username'] == username:
            account['include_stories'] = not account.get('include_stories', False)
            break
    
    data['accounts'] = accounts_list
    save_json_file(ACCOUNTS_FILE, data)
    
    flash(f'Stories toggled for @{username}', 'success')
    return redirect(url_for('accounts'))


@app.route('/subscribers', methods=['GET', 'POST'])
@login_required
def subscribers():
    """Subscriber management page"""
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            email = request.form.get('email', '').strip()
            if email:
                data = load_json_file(SUBSCRIBERS_FILE)
                subs = data.get('subscribers', [])
                if email not in subs:
                    subs.append(email)
                    data['subscribers'] = subs
                    save_json_file(SUBSCRIBERS_FILE, data)
                    flash(f'Subscriber {email} added', 'success')
                else:
                    flash(f'Subscriber {email} already exists', 'error')
        
        elif action == 'remove':
            email = request.form.get('email', '').strip()
            data = load_json_file(SUBSCRIBERS_FILE)
            subs = data.get('subscribers', [])
            if email in subs:
                subs.remove(email)
                data['subscribers'] = subs
                save_json_file(SUBSCRIBERS_FILE, data)
                flash(f'Subscriber {email} removed', 'success')
        
        return redirect(url_for('subscribers'))
    
    data = load_json_file(SUBSCRIBERS_FILE)
    subs = data.get('subscribers', [])
    
    return render_template('subscribers.html', subscribers=subs)


# ============================================================
# API ENDPOINTS (for potential future use)
# ============================================================

@app.route('/api/stats')
@login_required
def api_stats():
    """API endpoint for stats"""
    stats = load_json_file(STATS_FILE)
    return jsonify(stats)


@app.route('/api/accounts')
@login_required
def api_accounts():
    """API endpoint for accounts list"""
    data = load_json_file(ACCOUNTS_FILE)
    return jsonify(data.get('accounts', []))


if __name__ == '__main__':
    # Bind to localhost only - use Nginx to expose externally
    app.run(host='127.0.0.1', port=DASHBOARD_PORT, debug=False)


