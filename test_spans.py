import os
import sqlite3

# Connect to both DBs
conn_events = sqlite3.connect('data/scanscribe_events.db')
conn_logs = sqlite3.connect('logs/scanscribe_logs.db')

cur_e = conn_events.cursor()
cur_l = conn_logs.cursor()

# Get recent events with ATTACH links
cur_e.execute("""
    SELECT e.id, e.event_id, e.event_type, l.log_entry_id, l.llm_reason 
    FROM events e 
    JOIN event_transcript_links l ON e.id = l.event_id 
    WHERE e.status = 'open' 
    ORDER BY l.id DESC LIMIT 5;
""")

for row in cur_e.fetchall():
    eid, event_uuid, etype, log_entry_id, reason = row
    cur_l.execute("SELECT transcript FROM log_entries WHERE id = ?", (log_entry_id,))
    res = cur_l.fetchone()
    transcript = res[0] if res else "NOT_FOUND"
    
    print(f"EVENT: {etype} ({event_uuid})")
    print(f"SPAN: {transcript}")
    print(f"REASON: {reason}")
    print("-" * 50)
