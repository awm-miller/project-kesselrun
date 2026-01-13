#!/usr/bin/env python3
"""
Instagram Monitor Dashboard
Flask dashboard for managing multiple account lists and subscribers.
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
        return age_seconds / 86400
    return -1


def get_file_mtime(filename: str) -> str:
    """Get the last modified time of a file as a formatted string"""
    filepath = BASE_DIR / filename
    if filepath.exists():
        mtime = filepath.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
    return "File not found"


# ============================================================
# LIST HELPERS
# ============================================================

def get_all_lists() -> dict:
    """Get all lists from accounts.json"""
    data = load_json_file(ACCOUNTS_FILE)
    return data.get('lists', {})


def get_list(list_id: str) -> dict:
    """Get a specific list by ID"""
    lists = get_all_lists()
    return lists.get(list_id, {})


def get_current_list_id() -> str:
    """Get the currently selected list ID from session, default to 'master'"""
    return session.get('current_list', 'master')


def set_current_list_id(list_id: str):
    """Set the currently selected list ID in session"""
    session['current_list'] = list_id


def get_current_list() -> tuple:
    """Get (list_id, list_data) for the current list"""
    list_id = get_current_list_id()
    list_data = get_list(list_id)
    if not list_data:
        # Fallback to master if current list doesn't exist
        list_id = 'master'
        list_data = get_list(list_id)
        set_current_list_id(list_id)
    return list_id, list_data


def save_list(list_id: str, list_data: dict):
    """Save a list back to accounts.json"""
    data = load_json_file(ACCOUNTS_FILE)
    if 'lists' not in data:
        data['lists'] = {}
    data['lists'][list_id] = list_data
    save_json_file(ACCOUNTS_FILE, data)


def delete_list(list_id: str):
    """Delete a list from accounts.json"""
    data = load_json_file(ACCOUNTS_FILE)
    if 'lists' in data and list_id in data['lists']:
        del data['lists'][list_id]
        save_json_file(ACCOUNTS_FILE, data)


def generate_list_id(name: str) -> str:
    """Generate a URL-safe list ID from a name"""
    import re
    # Lowercase, replace spaces with hyphens, remove non-alphanumeric
    list_id = name.lower().strip()
    list_id = re.sub(r'\s+', '-', list_id)
    list_id = re.sub(r'[^a-z0-9-]', '', list_id)
    return list_id or 'list'


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
    state = load_json_file(STATE_FILE)
    all_lists = get_all_lists()
    
    # Calculate stats across all lists
    total_accounts = 0
    total_posts = 0
    total_stories = 0
    
    list_stats = []
    for list_id, list_data in all_lists.items():
        accounts = list_data.get('accounts', [])
        list_posts = 0
        list_stories = 0
        
        for account in accounts:
            username = account['username']
            if username in state:
                list_posts += len(state[username].get('posts', []))
                list_stories += len(state[username].get('stories', []))
        
        total_accounts += len(accounts)
        total_posts += list_posts
        total_stories += list_stories
        
        list_stats.append({
            'id': list_id,
            'name': list_data.get('name', list_id),
            'account_count': len(accounts),
            'subscriber_count': len(list_data.get('subscribers', [])),
            'posts': list_posts,
            'stories': list_stories,
        })
    
    # Cookie status
    cookie_age = get_file_age_days(COOKIES_FILE)
    cookie_mtime = get_file_mtime(COOKIES_FILE)
    cookie_stale = cookie_age > 7 if cookie_age >= 0 else True
    
    return render_template('index.html',
        list_stats=list_stats,
        total_lists=len(all_lists),
        total_accounts=total_accounts,
        total_posts=total_posts,
        total_stories=total_stories,
        cookie_age=cookie_age,
        cookie_mtime=cookie_mtime,
        cookie_stale=cookie_stale
    )


@app.route('/cookies', methods=['GET', 'POST'])
@login_required
def cookies():
    """Cookie management page"""
    if request.method == 'POST':
        cookie_content = request.form.get('cookies', '')
        if cookie_content.strip():
            filepath = BASE_DIR / COOKIES_FILE
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(cookie_content)
            flash('Cookies updated successfully', 'success')
        else:
            flash('No cookie content provided', 'error')
        return redirect(url_for('cookies'))
    
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


# ============================================================
# LIST MANAGEMENT ROUTES
# ============================================================

@app.route('/lists')
@login_required
def lists():
    """List management page with inline account/subscriber management"""
    all_lists = get_all_lists()
    state = load_json_file(STATE_FILE)
    
    list_items = []
    for list_id, list_data in all_lists.items():
        accounts = list_data.get('accounts', [])
        
        # Enrich accounts with stats
        for account in accounts:
            username = account['username']
            if username in state:
                account['posts_analyzed'] = len(state[username].get('posts', []))
                account['stories_analyzed'] = len(state[username].get('stories', []))
            else:
                account['posts_analyzed'] = 0
                account['stories_analyzed'] = 0
        
        list_items.append({
            'id': list_id,
            'name': list_data.get('name', list_id),
            'accounts': accounts,
            'subscribers': list_data.get('subscribers', []),
        })
    
    return render_template('lists.html', lists=list_items)


@app.route('/lists/select/<list_id>')
@login_required
def select_list(list_id):
    """Select a list as the current working list"""
    if get_list(list_id):
        set_current_list_id(list_id)
        flash(f'Switched to list: {get_list(list_id).get("name", list_id)}', 'success')
    else:
        flash('List not found', 'error')
    return redirect(request.referrer or url_for('lists'))


@app.route('/lists/create', methods=['POST'])
@login_required
def create_list():
    """Create a new list"""
    name = request.form.get('name', '').strip()
    if not name:
        flash('List name is required', 'error')
        return redirect(url_for('lists'))
    
    list_id = generate_list_id(name)
    
    # Ensure unique ID
    existing_lists = get_all_lists()
    base_id = list_id
    counter = 1
    while list_id in existing_lists:
        list_id = f"{base_id}-{counter}"
        counter += 1
    
    # Create new list
    save_list(list_id, {
        'name': name,
        'accounts': [],
        'subscribers': []
    })
    
    set_current_list_id(list_id)
    flash(f'List "{name}" created', 'success')
    return redirect(url_for('lists'))


@app.route('/lists/rename/<list_id>', methods=['POST'])
@login_required
def rename_list(list_id):
    """Rename a list"""
    new_name = request.form.get('name', '').strip()
    if not new_name:
        flash('List name is required', 'error')
        return redirect(url_for('lists'))
    
    list_data = get_list(list_id)
    if not list_data:
        flash('List not found', 'error')
        return redirect(url_for('lists'))
    
    list_data['name'] = new_name
    save_list(list_id, list_data)
    
    flash(f'List renamed to "{new_name}"', 'success')
    return redirect(url_for('lists'))


@app.route('/lists/delete/<list_id>', methods=['POST'])
@login_required
def delete_list_route(list_id):
    """Delete a list"""
    if list_id == 'master':
        flash('Cannot delete the Master List', 'error')
        return redirect(url_for('lists'))
    
    list_data = get_list(list_id)
    if not list_data:
        flash('List not found', 'error')
        return redirect(url_for('lists'))
    
    delete_list(list_id)
    
    # Switch to master if we deleted the current list
    if get_current_list_id() == list_id:
        set_current_list_id('master')
    
    flash(f'List "{list_data.get("name", list_id)}" deleted', 'success')
    return redirect(url_for('lists'))


# ============================================================
# ACCOUNT MANAGEMENT ROUTES (per-list)
# ============================================================

@app.route('/lists/<list_id>/accounts/add', methods=['POST'])
@login_required
def add_account_to_list(list_id):
    """Add account to a specific list"""
    username = request.form.get('username', '').strip().lower().lstrip('@')
    include_stories = request.form.get('include_stories') == 'on'
    
    if not username:
        flash('Username is required', 'error')
        return redirect(url_for('lists'))
    
    list_data = get_list(list_id)
    if not list_data:
        flash('List not found', 'error')
        return redirect(url_for('lists'))
    
    accounts_list = list_data.get('accounts', [])
    
    if any(a['username'] == username for a in accounts_list):
        flash(f'@{username} already in this list', 'error')
        return redirect(url_for('lists'))
    
    accounts_list.append({'username': username, 'include_stories': include_stories})
    list_data['accounts'] = accounts_list
    save_list(list_id, list_data)
    
    flash(f'@{username} added', 'success')
    return redirect(url_for('lists'))


@app.route('/lists/<list_id>/accounts/remove/<username>', methods=['POST'])
@login_required
def remove_account_from_list(list_id, username):
    """Remove account from a specific list"""
    list_data = get_list(list_id)
    if not list_data:
        flash('List not found', 'error')
        return redirect(url_for('lists'))
    
    accounts_list = list_data.get('accounts', [])
    accounts_list = [a for a in accounts_list if a['username'] != username]
    list_data['accounts'] = accounts_list
    save_list(list_id, list_data)
    
    flash(f'@{username} removed', 'success')
    return redirect(url_for('lists'))


@app.route('/lists/<list_id>/accounts/toggle/<username>', methods=['POST'])
@login_required
def toggle_stories_in_list(list_id, username):
    """Toggle stories for account in a specific list"""
    list_data = get_list(list_id)
    if not list_data:
        flash('List not found', 'error')
        return redirect(url_for('lists'))
    
    accounts_list = list_data.get('accounts', [])
    for account in accounts_list:
        if account['username'] == username:
            account['include_stories'] = not account.get('include_stories', False)
            break
    
    list_data['accounts'] = accounts_list
    save_list(list_id, list_data)
    
    flash(f'Stories toggled for @{username}', 'success')
    return redirect(url_for('lists'))


# ============================================================
# SUBSCRIBER MANAGEMENT ROUTES (per-list)
# ============================================================

@app.route('/lists/<list_id>/subscribers/add', methods=['POST'])
@login_required
def add_subscriber_to_list(list_id):
    """Add subscriber to a specific list"""
    email = request.form.get('email', '').strip()
    
    if not email:
        flash('Email is required', 'error')
        return redirect(url_for('lists'))
    
    list_data = get_list(list_id)
    if not list_data:
        flash('List not found', 'error')
        return redirect(url_for('lists'))
    
    subs = list_data.get('subscribers', [])
    if email in subs:
        flash(f'{email} already subscribed', 'error')
        return redirect(url_for('lists'))
    
    subs.append(email)
    list_data['subscribers'] = subs
    save_list(list_id, list_data)
    
    flash(f'{email} added', 'success')
    return redirect(url_for('lists'))


@app.route('/lists/<list_id>/subscribers/remove', methods=['POST'])
@login_required
def remove_subscriber_from_list(list_id):
    """Remove subscriber from a specific list"""
    email = request.form.get('email', '').strip()
    
    list_data = get_list(list_id)
    if not list_data:
        flash('List not found', 'error')
        return redirect(url_for('lists'))
    
    subs = list_data.get('subscribers', [])
    if email in subs:
        subs.remove(email)
        list_data['subscribers'] = subs
        save_list(list_id, list_data)
        flash(f'{email} removed', 'success')
    
    return redirect(url_for('lists'))


# ============================================================
# API ENDPOINTS
# ============================================================

@app.route('/api/lists')
@login_required
def api_lists():
    """API endpoint for all lists"""
    return jsonify(get_all_lists())


@app.route('/api/lists/<list_id>')
@login_required
def api_list(list_id):
    """API endpoint for a specific list"""
    return jsonify(get_list(list_id))


@app.route('/api/accounts')
@login_required
def api_accounts():
    """API endpoint for accounts in current list"""
    _, list_data = get_current_list()
    return jsonify(list_data.get('accounts', []))


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=DASHBOARD_PORT, debug=False)
