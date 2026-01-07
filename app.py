from flask import Flask, render_template, jsonify, request
import sqlite3
from datetime import datetime
import requests
import threading
import time
import os
import math

try:
	import serial
except Exception:
	serial = None

app = Flask(__name__)
DB_PATH = "../training_data.db"  # adjust if needed

# --- set this to your ESP32 DevKit IP (velocity sensor) if you use network mode
ESP32_URL = os.environ.get("ESP32_URL", "http://192.168.0.110")

# Serial settings - override with environment variables if needed
SERIAL_PORT = os.environ.get('ARDUINO_SERIAL_PORT', 'COM3')
SERIAL_BAUD = int(os.environ.get('ARDUINO_BAUD', '115200'))

# Global state populated by serial reader thread
last_velocity = None
last_velocity_time = 0
serial_error = None
_serial_thread = None


def _serial_reader_thread(port, baud):
	global last_velocity, last_velocity_time, serial_error
	if serial is None:
		serial_error = 'pyserial not installed'
		return

	try:
		ser = serial.Serial(port, baud, timeout=1)
		print(f"[serial] opened {port} @ {baud}")
	except Exception as e:
		serial_error = f'unable to open serial port {port}: {e}'
		print(serial_error)
		return

	serial_error = None
	while True:
		try:
			line = ser.readline()
			if not line:
				time.sleep(0.05)
				continue
			try:
				text = line.decode(errors='ignore').strip()
				if not text:
					continue
				v = float(text)
				last_velocity = v
				last_velocity_time = time.time()
				print(f"[serial] got velocity: {v}")
			except ValueError:
				# ignore non-numeric lines
				continue
		except Exception as e:
			serial_error = f'error reading serial: {e}'
			print(serial_error)
			time.sleep(1)


def start_serial_thread():
	global _serial_thread
	if _serial_thread is not None:
		return
	if serial is None:
		return
	t = threading.Thread(target=_serial_reader_thread, args=(SERIAL_PORT, SERIAL_BAUD), daemon=True)
	_serial_thread = t
	t.start()


@app.route('/')
def index():
	return render_template('index.html')


@app.route('/data')
def data():
	try:
		conn = sqlite3.connect(DB_PATH)
		cur = conn.cursor()
		cur.execute(
			"""
			SELECT timestamp, angle_type, angle_value
			FROM angles
			ORDER BY id DESC LIMIT 200
			"""
		)
		rows = cur.fetchall()
		conn.close()
		data = [{"timestamp": r[0], "type": r[1], "value": float(r[2])} for r in rows]
		return jsonify(data)
	except Exception as e:
		return jsonify({"error": str(e)}), 500


@app.route('/stats')
def stats():
	try:
		conn = sqlite3.connect(DB_PATH)
		cur = conn.cursor()
		stats = {}
		for angle_type in ["left_leg", "right_leg", "left_arm", "right_arm"]:
			cur.execute(
				"""
				SELECT COUNT(*), AVG(angle_value), MIN(angle_value), MAX(angle_value)
				FROM angles WHERE angle_type = ?
				""",
				(angle_type,),
			)
			result = cur.fetchone()
			if result and result[0] > 0:
				stats[angle_type] = {
					"count": result[0],
					"avg": float(result[1]) if result[1] is not None else 0.0,
					"min": float(result[2]) if result[2] is not None else 0.0,
					"max": float(result[3]) if result[3] is not None else 0.0,
				}
		conn.close()
		return jsonify(stats)
	except Exception as e:
		return jsonify({"error": str(e)}), 500


@app.route('/velocity')
def velocity():
	try:
		now = time.time()
		# prefer serial if recent
		if last_velocity is not None and (now - last_velocity_time) < 5:
			return jsonify({"velocity": float(last_velocity)})

		# fall back to ESP32 network endpoint
		try:
			r = requests.get(ESP32_URL + "/velocity", timeout=1)
			v = float(r.text.strip())
			return jsonify({"velocity": v})
		except Exception:
			if serial is None:
				return jsonify({"error": "pyserial not installed; set up SERIAL_PORT or install pyserial"}), 500
			if serial_error:
				return jsonify({"error": serial_error}), 500
			return jsonify({"error": "no recent velocity available"}), 500
	except Exception as e:
		return jsonify({"error": str(e)}), 500


@app.route('/set_velocity')
def set_velocity():
	global last_velocity, last_velocity_time
	try:
		v = request.args.get('value')
		if v is None:
			return jsonify({"error": "missing value parameter"}), 400
		last_velocity = float(v)
		last_velocity_time = time.time()
		return jsonify({"ok": True, "velocity": last_velocity})
	except Exception as e:
		return jsonify({"error": str(e)}), 400


@app.route('/velocity_test')
def velocity_test():
	v = 3.0 + math.sin(time.time()) * 1.5
	return jsonify({"velocity": float(v)})


if __name__ == '__main__':
	# start serial reader if pyserial present
	try:
		start_serial_thread()
	except Exception:
		pass
	app.run(debug=True, host='0.0.0.0', port=5000)