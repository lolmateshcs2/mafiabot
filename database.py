import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'mafia_ratings.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS ratings (
            user_id INTEGER PRIMARY KEY,
            rating INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS players_stats (
            user_id INTEGER PRIMARY KEY,
            role TEXT DEFAULT 'Новичок',
            мирный_побед INTEGER DEFAULT 0,
            мирный_игр INTEGER DEFAULT 0,
            шериф_побед INTEGER DEFAULT 0,
            шериф_игр INTEGER DEFAULT 0,
            доктор_побед INTEGER DEFAULT 0,
            доктор_игр INTEGER DEFAULT 0,
            мафия_побед INTEGER DEFAULT 0,
            мафия_игр INTEGER DEFAULT 0,
            дон_побед INTEGER DEFAULT 0,
            дон_игр INTEGER DEFAULT 0,
            first_game TEXT,
            total_wins INTEGER DEFAULT 0,
            coins INTEGER DEFAULT 0,
            total_games INTEGER DEFAULT 0,
            top INTEGER DEFAULT 0,
            rating REAL DEFAULT 0.0
        )
    ''')
    conn.commit()
    conn.close()

def get_player_data(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM players_stats WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "role": row[1],
            "roles": {
                "Мирный": {"wins": row[2], "games": row[3]},
                "Шериф":  {"wins": row[4], "games": row[5]},
                "Доктор": {"wins": row[6], "games": row[7]},
                "Мафия":  {"wins": row[8], "games": row[9]},
                "Дон":    {"wins": row[10], "games": row[11]},
            },
            "first_game": row[12],
            "total_wins": row[13],
            "coins": row[14],
            "total_games": row[15],
            "top": row[16],
            "rating": row[17],
        }
    else:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('INSERT INTO players_stats (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()
        return {
            "role": "Новичок",
            "roles": {
                "Мирный": {"wins": 0, "games": 0},
                "Шериф":  {"wins": 0, "games": 0},
                "Доктор": {"wins": 0, "games": 0},
                "Мафия":  {"wins": 0, "games": 0},
                "Дон":    {"wins": 0, "games": 0},
            },
            "first_game": None,
            "total_wins": 0,
            "coins": 0,
            "total_games": 0,
            "top": 0,
            "rating": 0.0,
        }

def update_first_game(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT first_game FROM players_stats WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    if row and row[0] is None:
        c.execute('UPDATE players_stats SET first_game = ? WHERE user_id = ?', (datetime.now().strftime("%d/%m/%Y"), user_id))
        conn.commit()
    conn.close()

def update_role_stats(user_id, role, win=False):
    role_map = {
        "мирный": "Мирный",
        "шериф": "Шериф",
        "доктор": "Доктор",
        "мафия": "Мафия",
        "дон": "Дон"
    }
    role = role_map.get(role, role)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT 1 FROM players_stats WHERE user_id = ?', (user_id,))
    if not c.fetchone():
        c.execute('INSERT INTO players_stats (user_id) VALUES (?)', (user_id,))
        conn.commit()
    role_cols = {
        "Мирный": ("мирный_игр", "мирный_побед"),
        "Шериф": ("шериф_игр", "шериф_побед"),
        "Доктор": ("доктор_игр", "доктор_побед"),
        "Мафия": ("мафия_игр", "мафия_побед"),
        "Дон": ("дон_игр", "дон_побед"),
    }
    if role not in role_cols:
        conn.close()
        return
    games_col, wins_col = role_cols[role]
    if win:
        query = f"UPDATE players_stats SET {games_col} = {games_col} + 1, {wins_col} = {wins_col} + 1, total_games = total_games + 1, total_wins = total_wins + 1 WHERE user_id = ?"
    else:
        query = f"UPDATE players_stats SET {games_col} = {games_col} + 1, total_games = total_games + 1 WHERE user_id = ?"
    c.execute(query, (user_id,))
    conn.commit()
    conn.close()
    update_player_role(user_id)

def update_coins(user_id, coins):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE players_stats SET coins = coins + ? WHERE user_id = ?', (coins, user_id))
    conn.commit()
    conn.close()

def update_rating(user_id, rating_delta):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE players_stats SET rating = rating + ? WHERE user_id = ?', (rating_delta, user_id))
    conn.commit()
    conn.close()

def update_player_role(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT total_games FROM players_stats WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    if row:
        total = row[0]
        if total >= 100:
            role = "Мафиози"
        elif total >= 50:
            role = "Опытный"
        elif total >= 20:
            role = "Игрок"
        else:
            role = "Новичок"
        c.execute('UPDATE players_stats SET role = ? WHERE user_id = ?', (role, user_id))
        conn.commit()
    conn.close()

def get_top_players(limit=10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT user_id, rating FROM players_stats
        ORDER BY rating DESC
        LIMIT ?
    ''', (limit,))
    rows = c.fetchall()
    conn.close()
    return rows