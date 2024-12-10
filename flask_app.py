#!/bin/usr/python

from flask import Flask, request, render_template, jsonify
import threading
import json
from datetime import datetime
import os

app = Flask(__name__)

DATA_FILE = '/var/www/html/iot/data/pico.json'
data_lock = threading.Lock()

@app.route('/', methods = ['GET'])
def homepage():
    return render_template('index.html')


def read_data():
    try:
        with open(DATA_FILE, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return []
    
def write_data(data):
    with open(DATA_FILE, "w") as file:
        return json.dump(data, file)

@app.route('/sensor_data', methods = ['GET'])
def sensor_data():
    with data_lock:
        data = read_data()

    return jsonify(data)

@app.route('/gas_sensor', methods=['POST'])
def post_value():
    content = request.json

    if 'values' not in content:
        jsonify({"error": "Invalid payload"}), 400

    with data_lock:
        data = read_data()

    for item in content['values']:
        data.append({
            'x': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'y': item
        })

    if len(data) > 1000:
        data = data[-1000:]

    with data_lock:
        write_data(data)

    return jsonify({"status": "success"}), 200


if __name__ == "__main__":
    os.remove(DATA_FILE)
    app.run()