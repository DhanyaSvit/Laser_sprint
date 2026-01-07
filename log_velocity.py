import serial
import sqlite3
from datetime import datetime
import re

PORT = "COM5"          # change to your ESP32 port
BAUD = 115200
DB_PATH = "training_data.db"

line_re = re.compile(r"Velocity of person:\s*([0-9.]+)\s*m/s")

def insert_velocity(v):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO velocities (timestamp, velocity) VALUES (?, ?)",
        (datetime.now().isoformat(timespec="seconds"), float(v))
    )
    conn.commit()
    conn.close()

ser = serial.Serial(PORT, BAUD, timeout=1)

print("Listening for velocity lines...")

while True:
    raw = ser.readline().decode(errors="ignore").strip()
    if not raw:
        continue
    m = line_re.search(raw)
    if m:
        v = m.group(1)
        print("LOG:", v, "m/s")
        insert_velocity(v)
