"""
Instagram Monitor Admin Dashboard

Flask-based admin interface with:
- Account management (add/remove monitored accounts)
- Subscriber management (add/remove email subscribers)
- Real-time log streaming via WebSocket
- Password-protected access
"""
import os
import sys
import json
import time
import threading
from pathlib import Path
from functools import wraps
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_socketio import SocketIO, emit

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    ACCOUNTS_FILE,
    SUBSCRIBERS_FILE,
    DASHBOARD_PASSWORD,
    DASHBOARD_PORT,
    DASHBOARD_SECRET_KEY,
    LOG_FILE,
)

# Resolve log file path
LOG_FILE_PATH = Path(__file__).parent.parent / LOG_FILE

# Initialize Flask app
app = Flask(__name__)
app.secret_key = DASHBOARD_SECRET_KEY
app.config['SESSION_COOKIE_SECURE'] = False  # Set True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Log streaming state
log_stream_active = False
log_stream_thread = None


# =============================================================================
# Authentication
# =============================================================================

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == DASHBOARD_PASSWORD:
            session['authenticated'] = True
            session.permanent = True
            return redirect(url_for('accounts'))
        else:
            flash('Invalid password', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    return redirect(url_for('login'))


# =============================================================================
# Page Routes
# =============================================================================

@app.route('/')
def index():
    """Redirect to accounts page"""
    return redirect(url_for('accounts'))


@app.route('/accounts')
@login_required
def accounts():
    """Account management page"""
    return render_template('accounts.html', active_page='accounts')


@app.route('/subscribers')
@login_required
def subscribers():
    """Subscriber management page"""
    return render_template('subscribers.html', active_page='subscribers')


@app.route('/logs')
@login_required
def logs():
    """Real-time logs page"""
    return render_template('logs.html', active_page='logs')


# =============================================================================
# API: Accounts Management
# =============================================================================

def load_accounts():
    """Load accounts from JSON file"""
    accounts_path = Path(ACCOUNTS_FILE)
    if accounts_path.exists():
        with open(accounts_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('accounts', [])
    return []


def save_accounts(accounts):
    """Save accounts to JSON file"""
    accounts_path = Path(ACCOUNTS_FILE)
    with open(accounts_path, 'w', encoding='utf-8') as f:
        json.dump({'accounts': accounts}, f, indent=2)


@app.route('/api/accounts', methods=['GET'])
@login_required
def api_get_accounts():
    """Get all monitored accounts"""
    try:
        accounts = load_accounts()
        return jsonify({'success': True, 'accounts': accounts})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/accounts', methods=['POST'])
@login_required
def api_add_account():
    """Add a new account to monitor"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip().lstrip('@')
        include_stories = data.get('include_stories', False)
        
        if not username:
            return jsonify({'success': False, 'error': 'Username is required'}), 400
        
        accounts = load_accounts()
        
        # Check if account already exists
        if any(acc['username'] == username for acc in accounts):
            return jsonify({'success': False, 'error': 'Account already exists'}), 400
        
        # Add new account
        new_account = {
            'username': username,
            'include_stories': include_stories,
            'added_date': datetime.now().isoformat()
        }
        accounts.append(new_account)
        save_accounts(accounts)
        
        return jsonify({'success': True, 'account': new_account})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/accounts/<username>', methods=['DELETE'])
@login_required
def api_delete_account(username):
    """Remove an account from monitoring"""
    try:
        accounts = load_accounts()
        original_count = len(accounts)
        accounts = [acc for acc in accounts if acc['username'] != username]
        
        if len(accounts) == original_count:
            return jsonify({'success': False, 'error': 'Account not found'}), 404
        
        save_accounts(accounts)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/accounts/<username>', methods=['PUT'])
@login_required
def api_update_account(username):
    """Update account settings"""
    try:
        data = request.get_json()
        accounts = load_accounts()
        
        for acc in accounts:
            if acc['username'] == username:
                if 'include_stories' in data:
                    acc['include_stories'] = data['include_stories']
                save_accounts(accounts)
                return jsonify({'success': True, 'account': acc})
        
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# API: Subscribers Management
# =============================================================================

def load_subscribers():
    """Load subscribers from JSON file"""
    subscribers_path = Path(SUBSCRIBERS_FILE)
    if subscribers_path.exists():
        with open(subscribers_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('subscribers', [])
    return []


def save_subscribers(subscribers):
    """Save subscribers to JSON file"""
    subscribers_path = Path(SUBSCRIBERS_FILE)
    with open(subscribers_path, 'w', encoding='utf-8') as f:
        json.dump({'subscribers': subscribers}, f, indent=2)


@app.route('/api/subscribers', methods=['GET'])
@login_required
def api_get_subscribers():
    """Get all subscribers"""
    try:
        subscribers = load_subscribers()
        return jsonify({'success': True, 'subscribers': subscribers})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/subscribers', methods=['POST'])
@login_required
def api_add_subscriber():
    """Add a new subscriber"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        
        if not email or '@' not in email:
            return jsonify({'success': False, 'error': 'Valid email is required'}), 400
        
        subscribers = load_subscribers()
        
        # Check if subscriber already exists
        if any(sub['email'] == email for sub in subscribers):
            return jsonify({'success': False, 'error': 'Subscriber already exists'}), 400
        
        # Add new subscriber
        new_subscriber = {
            'email': email,
            'added_date': datetime.now().isoformat()
        }
        subscribers.append(new_subscriber)
        save_subscribers(subscribers)
        
        return jsonify({'success': True, 'subscriber': new_subscriber})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/subscribers/<email>', methods=['DELETE'])
@login_required
def api_delete_subscriber(email):
    """Remove a subscriber"""
    try:
        subscribers = load_subscribers()
        original_count = len(subscribers)
        subscribers = [sub for sub in subscribers if sub['email'] != email]
        
        if len(subscribers) == original_count:
            return jsonify({'success': False, 'error': 'Subscriber not found'}), 404
        
        save_subscribers(subscribers)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# WebSocket: Real-time Log Streaming
# =============================================================================

def tail_log_file(socketio_instance):
    """Background thread to tail the log file and emit new lines"""
    global log_stream_active
    
    log_path = LOG_FILE_PATH
    last_position = 0
    
    # Start from end of file if it exists
    if log_path.exists():
        last_position = log_path.stat().st_size
    
    while log_stream_active:
        try:
            if log_path.exists():
                current_size = log_path.stat().st_size
                
                # File was truncated or rotated
                if current_size < last_position:
                    last_position = 0
                
                if current_size > last_position:
                    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                        f.seek(last_position)
                        new_lines = f.read()
                        last_position = f.tell()
                        
                        if new_lines.strip():
                            for line in new_lines.strip().split('\n'):
                                if line.strip():
                                    socketio_instance.emit('log_line', {
                                        'line': line,
                                        'timestamp': datetime.now().isoformat()
                                    }, namespace='/')
            
            time.sleep(0.5)  # Check every 500ms
            
        except Exception as e:
            socketio_instance.emit('log_error', {'error': str(e)}, namespace='/')
            time.sleep(1)


@socketio.on('connect')
def handle_connect():
    """Handle new WebSocket connection"""
    if not session.get('authenticated'):
        return False  # Reject unauthenticated connections
    
    emit('connected', {'status': 'Connected to log stream'})


@socketio.on('start_log_stream')
def handle_start_stream():
    """Start streaming logs"""
    global log_stream_active, log_stream_thread
    
    if not session.get('authenticated'):
        return
    
    if not log_stream_active:
        log_stream_active = True
        log_stream_thread = threading.Thread(target=tail_log_file, args=(socketio,), daemon=True)
        log_stream_thread.start()
        emit('stream_status', {'status': 'started'})
    
    # Send recent log history
    try:
        if LOG_FILE_PATH.exists():
            with open(LOG_FILE_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                # Send last 100 lines
                for line in lines[-100:]:
                    if line.strip():
                        emit('log_line', {
                            'line': line.strip(),
                            'timestamp': datetime.now().isoformat(),
                            'historical': True
                        })
    except Exception as e:
        emit('log_error', {'error': str(e)})


@socketio.on('stop_log_stream')
def handle_stop_stream():
    """Stop streaming logs"""
    global log_stream_active
    log_stream_active = False
    emit('stream_status', {'status': 'stopped'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection"""
    pass  # Log stream continues for other clients


# =============================================================================
# API: Log Management
# =============================================================================

@app.route('/api/logs/download')
@login_required
def api_download_logs():
    """Download the full log file"""
    try:
        if LOG_FILE_PATH.exists():
            with open(LOG_FILE_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            return content, 200, {
                'Content-Type': 'text/plain',
                'Content-Disposition': f'attachment; filename=monitor_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
            }
        return 'Log file not found', 404
    except Exception as e:
        return str(e), 500


@app.route('/api/logs/clear', methods=['POST'])
@login_required
def api_clear_logs():
    """Clear the log file"""
    try:
        with open(LOG_FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(f"[{datetime.now().isoformat()}] Log cleared by admin\n")
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == '__main__':
    print(f"\n{'='*60}")
    print("Instagram Monitor Dashboard")
    print(f"{'='*60}")
    print(f"Running on: http://localhost:{DASHBOARD_PORT}")
    print(f"Password: {'*' * len(DASHBOARD_PASSWORD)} (set via DASHBOARD_PASSWORD env var)")
    print(f"{'='*60}\n")
    
    socketio.run(app, host='0.0.0.0', port=DASHBOARD_PORT, debug=False, allow_unsafe_werkzeug=True)

