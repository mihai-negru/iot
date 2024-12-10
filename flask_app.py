#!/bin/usr/python

from flask import Flask, request, render_template, jsonify
from datetime import datetime
import threading
import json

app = Flask(__name__)

DATA_FILE = 'data/pico.json'
data_lock = threading.Lock()

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

@app.route('/')
def homepage():
    return render_template('index.html')

@app.route('/gas_sensor', methods=['POST'])
def post_value():
    content = request.json
    if 'value' in content:
        data_entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "value": content['value']
        }

        with data_lock:
            data = read_data()
            
        data.append(data_entry)
        if len(data) > 1000:
            data = data[-1000:]
        
        with data_lock:
            write_data(data)
        return jsonify({"status": "success"}), 200
    return jsonify({"error": "Invalid payload"}), 400

if __name__ == "__main__":
    app.run()