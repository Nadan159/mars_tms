import eventlet
eventlet.monkey_patch()
import json
import uuid
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from datetime import datetime
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from models import db, User, Team, Score, Match, Table, Timesheet
import threading
import time
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key_change_me_in_prod'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///fll.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize Extensions
db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
socketio = SocketIO(app, async_mode='eventlet')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Timer Logic (same as before) ---
# --- Timer Logic (Precise) ---
timer_state = {
    "running": False,
    "start_time": None,  # Monotonic timestamp when current run started
    "time_left": 150,    # Time left at moment of pause/init
    "duration": 150
}

def timer_loop():
    while True:
        if timer_state['running']:
            elapsed = time.monotonic() - timer_state['start_time']
            current_remaining = timer_state['time_left'] - elapsed
            
            if current_remaining <= 0:
                timer_state['running'] = False
                timer_state['time_left'] = 0
                socketio.emit('timer_update', timer_state)
                socketio.emit('timer_end', {})
            else:
                # We send the display integer but calculation is float high precision
                display_state = timer_state.copy()
                display_state['time_left'] = int(current_remaining)
                socketio.emit('timer_update', display_state)
        time.sleep(0.1) # Higher update rate for smooth feel if needed, but display updates on change

timer_thread = threading.Thread(target=timer_loop, daemon=True)
timer_thread.start()

# --- Setup DB ---
def migrate_database():
    """Add missing columns to existing database"""
    with app.app_context():
        from sqlalchemy import inspect, text
        try:
            inspector = inspect(db.engine)
            
            # Check if score table exists and add table_id column if missing
            if 'score' in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns('score')]
                if 'table_id' not in columns:
                    try:
                        db.session.execute(text('ALTER TABLE score ADD COLUMN table_id INTEGER'))
                        db.session.commit()
                        print("✓ Added table_id column to score table")
                    except Exception as e:
                        print(f"Note: Could not add table_id (may already exist): {e}")
                        db.session.rollback()
            
            # Check if fll_table and timesheet tables exist
            tables = inspector.get_table_names()
            if 'fll_table' not in tables:
                try:
                    Table.__table__.create(db.engine)
                    print("✓ Created fll_table table")
                except Exception as e:
                    print(f"Note creating fll_table: {e}")
            if 'timesheet' not in tables:
                try:
                    Timesheet.__table__.create(db.engine)
                    print("✓ Created timesheet table")
                except Exception as e:
                    print(f"Note creating timesheet: {e}")
        except Exception as e:
            print(f"Migration warning: {e}")
            # Continue anyway - db.create_all() will handle it

def setup_database():
    with app.app_context():
        migrate_database()  # Run migration first
        db.create_all()  # Create any missing tables
        
        # Read admin password from file
        admin_pass = 'admin'
        password_file = 'admin_password.txt'
        print(f"Checking password file: {os.path.abspath(password_file)}")
        if os.path.exists(password_file):
             with open(password_file, 'r') as f:
                 content = f.read().strip()
                 if content:
                     admin_pass = content
        else:
             with open(password_file, 'w') as f:
                 f.write(admin_pass)
        
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            hashed_pw = bcrypt.generate_password_hash(admin_pass).decode('utf-8')
            admin = User(username='admin', password=hashed_pw, role='admin')
            db.session.add(admin)
            db.session.commit()
            print(f"Admin user created (pass from file)")
        else:
            # Update password if it doesn't match the file
            if not bcrypt.check_password_hash(admin_user.password, admin_pass):
                hashed_pw = bcrypt.generate_password_hash(admin_pass).decode('utf-8')
                admin_user.password = hashed_pw
                db.session.commit()
                print("Admin password updated from file")

setup_database()


# --- Helpers ---
def get_local_ip():
    """Get the actual local network IP address (not 127.0.0.1)"""
    import socket
    try:
        # Method 1: Connect to external address to determine local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith('127.'):
                return ip
        except:
            s.close()
        
        # Method 2: Parse Windows ipconfig output
        import platform
        if platform.system() == 'Windows':
            try:
                import subprocess
                result = subprocess.run(['ipconfig'], capture_output=True, text=True, timeout=5)
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if 'IPv4' in line or ('IP Address' in line and 'IPv4' not in line):
                        parts = line.split(':')
                        if len(parts) > 1:
                            potential_ip = parts[-1].strip().split()[0]
                            if potential_ip and not potential_ip.startswith('127.') and potential_ip.count('.') == 3:
                                try:
                                    socket.inet_aton(potential_ip)
                                    return potential_ip
                                except:
                                    pass
            except Exception as e:
                print(f"Error parsing ipconfig: {e}")
        
        # Method 3: Try hostname resolution
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and not ip.startswith('127.'):
            return ip
            
        return '127.0.0.1'
    except Exception as e:
        print(f"Error getting IP: {e}")
        return request.remote_addr if request.remote_addr else '127.0.0.1'

# --- Routes ---

@app.route('/')
@login_required
def index():
    return render_template('index.html', user=current_user)

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Sync admin password on login attempt too, just in case file changed while running
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == 'admin':
            admin_pass = 'admin'
            if os.path.exists('admin_password.txt'):
                 with open('admin_password.txt', 'r') as f:
                     content = f.read().strip()
                     if content:
                         admin_pass = content
                         
            user = User.query.filter_by(username='admin').first()
            if user and not bcrypt.check_password_hash(user.password, admin_pass):
                 hashed_pw = bcrypt.generate_password_hash(admin_pass).decode('utf-8')
                 user.password = hashed_pw
                 db.session.commit()
                 
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Login Unsuccessful. Please check username and password', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/timer')
@login_required
def timer():
    ip_address = get_local_ip()
    return render_template('timer.html', ip_address=ip_address)

# Removed /scorer route - use /web_scorer instead

@app.route('/scoreboard')
@login_required # protecting this too as requested
def scoreboard():
    return render_template('scoreboard.html')



@app.route('/timer_view')
def timer_view():
    return render_template('timer_view.html')

@app.route('/score/view/<int:score_id>')
@login_required
def view_score(score_id):
    score = Score.query.get_or_404(score_id)
    team = Team.query.get(score.team_id)
    # Parse details JSON safely
    try:
        details = json.loads(score.details)
    except:
        details = {}
    return render_template('score_sheet.html', score=score, team=team, details=details)

@app.route('/scoreboard_view')
def scoreboard_view():
    return render_template('scoreboard_view.html')

@app.route('/web_scorer')
@login_required
def web_scorer():
    teams = Team.query.all()
    tables = Table.query.filter_by(is_active=True).all()
    return render_template('web_scorer.html', teams=teams, tables=tables)

@app.route('/api/user-info')
@login_required
def user_info():
    return jsonify({"role": current_user.role, "username": current_user.username})

@app.route('/admin')
@login_required
def admin():
    if current_user.role != 'admin':
        flash('Access Denied', 'danger')
        return redirect(url_for('index'))
    import socket
    teams = Team.query.all()
    users = User.query.all()
    tables = Table.query.all()
    timesheets = Timesheet.query.order_by(Timesheet.timestamp.desc()).limit(50).all()
    matches = Match.query.all()
    scores = Score.query.order_by(Score.timestamp.desc()).all()
    

    
    hostname = socket.gethostname()
    ip_address = get_local_ip()
    
    # Resolve team names for matches
    enriched_matches = []
    for m in matches:
        t1 = Team.query.get(m.team1_id)
        t2 = Team.query.get(m.team2_id)
        enriched_matches.append({
            "time": m.time,
            "team1": t1.name if t1 else '?',
            "team2": t2.name if t2 else '?'
        })
    
    enriched_scores = []
    try:
        if scores:
            for s in scores:
                t = Team.query.get(s.team_id)
                table = Table.query.get(s.table_id) if s.table_id else None
                enriched_scores.append({
                    "id": s.id,
                    "team_name": t.name if t else 'Unknown',
                    "team_number": t.number if t else '?',
                    "round": s.round,
                    "total": s.total_score,
                    "judge": s.judge_name,
                    "table": table.name if table else 'N/A'
                })
    except Exception as e:
        print(f"Error enriching scores: {e}")
    
    # Enrich timesheets
    enriched_timesheets = []
    for ts in timesheets:
        team = Team.query.get(ts.team_id)
        table = Table.query.get(ts.table_id) if ts.table_id else None
        enriched_timesheets.append({
            "id": ts.id,
            "team_name": team.name if team else 'Unknown',
            "team_number": team.number if team else '?',
            "table_name": table.name if table else 'N/A',
            "round": ts.round,
            "start_time": ts.start_time.strftime('%Y-%m-%d %H:%M:%S') if ts.start_time else 'N/A',
            "end_time": ts.end_time.strftime('%Y-%m-%d %H:%M:%S') if ts.end_time else 'N/A',
            "duration": ts.duration_seconds,
            "judge": ts.judge_name
        })
        
    return render_template('admin.html', teams=teams, users=users, tables=tables, 
                         matches=enriched_matches, scores=enriched_scores, 
                         timesheets=enriched_timesheets, ip_address=ip_address, 
                         hostname=hostname)

# --- API ---

@app.route('/api/users', methods=['POST'])
@login_required
def create_user():
    if current_user.role != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.json
    if User.query.filter_by(username=data['username']).first():
        return jsonify({"error": "User exists"}), 400
        
    hashed_pw = bcrypt.generate_password_hash(data['password']).decode('utf-8')
    new_user = User(username=data['username'], password=hashed_pw, role=data['role'])
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"message": "User created"})

@app.route('/api/teams', methods=['GET', 'POST'])
@login_required
def handle_teams():
    if request.method == 'POST':
        data = request.json
        if Team.query.filter_by(number=data['number']).first():
            return jsonify({"error": "Team number already exists"}), 400
        new_team = Team(number=data['number'], name=data['name'])
        db.session.add(new_team)
        db.session.commit()
        return jsonify({"message": "Success", "id": new_team.id})
    
    teams = Team.query.all()
    return jsonify([{"id": t.id, "number": t.number, "name": t.name} for t in teams])

@app.route('/api/scores', methods=['GET', 'POST'])
@login_required
def handle_scores():
    if request.method == 'POST':
        # Prevent viewers from submitting scores
        if current_user.role == 'viewer':
            return jsonify({"error": "Viewers cannot submit scores"}), 403
        
        data = request.json
        # Delete existing score for this team and round to prevent duplicates
        Score.query.filter_by(team_id=int(data['team_id']), round=data.get('round', '1')).delete()
        
        # Require table_id for judges
        table_id = data.get('table_id')
        if current_user.role == 'judge' and not table_id:
            return jsonify({"error": "Table number is required for judges"}), 400
        
        new_score = Score(
            team_id=int(data['team_id']),
            table_id=int(table_id) if table_id else None,
            total_score=data['total'],
            details=data.get('details', '{}'),
            round=data.get('round', '1'),
            judge_name=current_user.username
        )
        db.session.add(new_score)
        db.session.commit()
        socketio.emit('score_update', {"team_id": new_score.team_id, "total": new_score.total_score, "round": new_score.round})
        return jsonify({"message": "Success", "total": new_score.total_score})
    
    # Get scores structured for scoreboard
    teams = Team.query.all()
    results = []
    for t in teams:
        scores = Score.query.filter_by(team_id=t.id).all()
        # Find highest official score (exclude practice)
        official_scores = [s.total_score for s in scores if s.round in ['1', '2', '3']]
        high_score = max(official_scores) if official_scores else 0
        
        team_data = {
            "id": t.id,
            "number": t.number,
            "name": t.name,
            "high_score": high_score,
            "practice": next((s.total_score for s in scores if s.round == 'Practice'), '-'),
            "round1": next((s.total_score for s in scores if s.round == '1'), '-'),
            "round2": next((s.total_score for s in scores if s.round == '2'), '-'),
            "round3": next((s.total_score for s in scores if s.round == '3'), '-')
        }
        results.append(team_data)
        
    return jsonify(results)

@app.route('/api/schedule', methods=['POST'])
@login_required
def generate_schedule():
    teams = Team.query.all()
    if len(teams) < 2:
        return jsonify({"error": "Not enough teams"}), 400
    
    Match.query.delete() # Clear old schedule for demo
    matches_data = []
    
    for i in range(0, len(teams), 2):
        if i + 1 < len(teams):
            m = Match(
                team1_id=teams[i].id,
                team2_id=teams[i+1].id,
                time="10:00",
                table="A"
            )
            db.session.add(m)
            matches_data.append(m)
            
    db.session.commit()
    return jsonify({"message": "Generated"})

@app.route('/api/tables', methods=['GET', 'POST', 'DELETE'])
@login_required
def handle_tables():
    if current_user.role != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    if request.method == 'POST':
        data = request.json
        if Table.query.filter_by(name=data['name']).first():
            return jsonify({"error": "Table already exists"}), 400
        new_table = Table(name=data['name'], is_active=data.get('is_active', True))
        db.session.add(new_table)
        db.session.commit()
        return jsonify({"message": "Table created", "id": new_table.id})
    
    if request.method == 'DELETE':
        table_id = request.json.get('id')
        table = Table.query.get(table_id)
        if table:
            db.session.delete(table)
            db.session.commit()
            return jsonify({"message": "Table deleted"})
        return jsonify({"error": "Table not found"}), 404
    
    tables = Table.query.all()
    return jsonify([{"id": t.id, "name": t.name, "is_active": t.is_active} for t in tables])

@app.route('/api/timesheets', methods=['GET', 'POST'])
@login_required
def handle_timesheets():
    if request.method == 'POST':
        data = request.json
        start_time = None
        end_time = None
        
        if data.get('start_time'):
            try:
                start_time = datetime.strptime(data['start_time'], '%Y-%m-%d %H:%M:%S')
            except:
                try:
                    start_time = datetime.fromisoformat(data['start_time'].replace('T', ' ').split('.')[0])
                except:
                    pass
        
        if data.get('end_time'):
            try:
                end_time = datetime.strptime(data['end_time'], '%Y-%m-%d %H:%M:%S')
            except:
                try:
                    end_time = datetime.fromisoformat(data['end_time'].replace('T', ' ').split('.')[0])
                except:
                    pass
        
        new_timesheet = Timesheet(
            team_id=int(data['team_id']),
            table_id=int(data['table_id']) if data.get('table_id') else None,
            round=data.get('round', '1'),
            start_time=start_time,
            end_time=end_time,
            duration_seconds=data.get('duration_seconds'),
            judge_name=current_user.username,
            notes=data.get('notes')
        )
        db.session.add(new_timesheet)
        db.session.commit()
        return jsonify({"message": "Timesheet created", "id": new_timesheet.id})
    
    timesheets = Timesheet.query.order_by(Timesheet.timestamp.desc()).limit(100).all()
    results = []
    for ts in timesheets:
        team = Team.query.get(ts.team_id)
        table = Table.query.get(ts.table_id) if ts.table_id else None
        results.append({
            "id": ts.id,
            "team_name": team.name if team else 'Unknown',
            "table_name": table.name if table else 'N/A',
            "round": ts.round,
            "start_time": ts.start_time.isoformat() if ts.start_time else None,
            "end_time": ts.end_time.isoformat() if ts.end_time else None,
            "duration": ts.duration_seconds,
            "judge": ts.judge_name
        })
    return jsonify(results)

@app.route('/api/remote/timer', methods=['GET', 'POST'])
def remote_timer_control():
    # Auth via query params
    username = request.args.get('username')
    password = request.args.get('password')
    
    if not username or not password:
        return jsonify({"error": "Missing username or password"}), 401
        
    user = User.query.filter_by(username=username).first()
    if not user or not bcrypt.check_password_hash(user.password, password):
        return jsonify({"error": "Invalid credentials"}), 401
    
    # Check for action in args
    action = request.args.get('action')
    # Also support JSON/Form data if sent
    if not action and request.json:
        action = request.json.get('action')
        
    if not action:
        return jsonify({"error": "Missing action"}), 400
    
    if action == 'start':
        if not timer_state['running'] and timer_state['time_left'] > 0:
            timer_state['running'] = True
            timer_state['start_time'] = time.monotonic()
            socketio.emit('timer_update', timer_state)
            return "Timer Started"
    
    elif action == 'stop':
        if timer_state['running']:
            timer_state['running'] = False
            elapsed = time.monotonic() - timer_state['start_time']
            timer_state['time_left'] -= elapsed
            socketio.emit('timer_update', timer_state)
            return "Timer Stopped"
            
    elif action == 'reset':
        timer_state['running'] = False
        timer_state['time_left'] = 150
        timer_state['start_time'] = None
        socketio.emit('timer_update', timer_state)
        return "Timer Reset"
            
    return "Action Ignored (Timer running or invalid state)", 200

@app.route('/api/erase_all', methods=['POST'])
@login_required
def erase_all():
    if current_user.role != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    # Keep admin user
    admin_user = User.query.filter_by(role='admin').first()
    admin_id = admin_user.id if admin_user else None
    
    # Delete all except admin
    User.query.filter(User.id != admin_id).delete()
    Team.query.delete()
    Score.query.delete()
    Match.query.delete()
    Table.query.delete()
    Timesheet.query.delete()
    
    db.session.commit()
    return jsonify({"message": "All data erased except admin user"})

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    if current_user.role != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    if user.role == 'admin':
        return jsonify({"error": "Cannot delete admin user"}), 400
    
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "User deleted"})

@app.route('/api/teams/<int:team_id>', methods=['DELETE'])
@login_required
def delete_team(team_id):
    if current_user.role != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    
    team = Team.query.get(team_id)
    if not team:
        return jsonify({"error": "Team not found"}), 404
    
    # Manually cascade delete to avoid foreign key errors
    try:
        Score.query.filter_by(team_id=team_id).delete()
        Match.query.filter((Match.team1_id == team_id) | (Match.team2_id == team_id)).delete()
        Timesheet.query.filter_by(team_id=team_id).delete()
        
        db.session.delete(team)
        db.session.commit()
        return jsonify({"message": "Team deleted"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# --- SocketIO Events ---

# Ready tracking
ready_count = 0

@socketio.on('table_ready')
def handle_ready(data):
    global ready_count
    if data['ready']:
        ready_count += 1
    else:
        ready_count = max(0, ready_count - 1)
    emit('ready_update', {"count": ready_count}, broadcast=True)

@socketio.on('start_timer')
def handle_start_timer():
    if current_user.is_authenticated:
        if not timer_state['running'] and timer_state['time_left'] > 0:
            timer_state['running'] = True
            timer_state['start_time'] = time.monotonic()
            broadcast=True

@socketio.on('stop_timer')
def handle_stop_timer():
    if current_user.is_authenticated:
        if timer_state['running']:
            timer_state['running'] = False
            # Consolidate elapsed time into time_left
            elapsed = time.monotonic() - timer_state['start_time']
            timer_state['time_left'] -= elapsed
            broadcast=True

@socketio.on('reset_timer')
def handle_reset_timer():
    if current_user.is_authenticated:
        timer_state['running'] = False
        timer_state['time_left'] = 150
        timer_state['start_time'] = None
        emit('timer_update', timer_state, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
