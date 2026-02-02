from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import json

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(50), nullable=False) # admin, referee, judge, viewer

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    scores = db.relationship('Score', backref='team', lazy=True)

class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey('fll_table.id'), nullable=True)
    total_score = db.Column(db.Integer, nullable=False)
    details = db.Column(db.Text, nullable=False) # JSON string of specific mission scores
    round = db.Column(db.String(20), default='1') # Practice, 1, 2, 3
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    judge_name = db.Column(db.String(100))

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team1_id = db.Column(db.Integer, db.ForeignKey('team.id'))
    team2_id = db.Column(db.Integer, db.ForeignKey('team.id'))
    time = db.Column(db.String(20))
    table = db.Column(db.String(20))
    completed = db.Column(db.Boolean, default=False)

class Table(db.Model):
    __tablename__ = 'fll_table'  # Avoid SQLite reserved word conflict
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)

class Timesheet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey('fll_table.id'), nullable=True)
    round = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    duration_seconds = db.Column(db.Integer, nullable=True)
    judge_name = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)