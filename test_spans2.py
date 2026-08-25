import os
import sqlite3

# Connect to both DBs
conn_events = sqlite3.connect('data/scanscribe_events.db')
conn_logs = sqlite3.connect('logs/scanscribe_logs.db')

cur_e = conn_events.cursor()
cur_l = conn_logs.cursor()

# Get spans for this specific event
cur_e.execute("""
    SELECT l.id, l.log_entry_id, l.llm_reason 
    FROM events e 
    JOIN event_transcript_links l ON e.id = l.event_id 
    WHERE e.event_id = '227c599cfdef4fc9'
    ORDER BY l.id ASC;
""")

rows = cur_e.fetchall()
print(f"Total spans attached: {len(rows)}")

for row in rows:
    link_id, log_entry_id, reason = row
    cur_l.execute("SELECT timestamp, transcript FROM log_entries WHERE id = ?", (log_entry_id,))
    res = cur_l.fetchone()
    if res:
        ts, transcript = res
    else:
        ts, transcript = "UNKNOWN", "NOT_FOUND"
    
    print(f"Time: {ts}")
    print(f"SPAN: {transcript}")
    print(f"REASON: {reason}")
    print("-" * 50)
