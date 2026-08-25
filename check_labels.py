import os
import sqlite3

conn = sqlite3.connect('data/scanscribe_events.db')
cur = conn.cursor()
cur.execute("SELECT DISTINCT label FROM entity_observations")
print("Labels:", cur.fetchall())

