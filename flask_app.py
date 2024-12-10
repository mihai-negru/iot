#!/bin/usr/python

from flask import Flask, request, render_template
from datetime import datetime

app = Flask(__name__)

@app.route('/')
def homepage():
    return render_template('index.html')

@app.route('/gas_sensor', methods=['POST'])
def post_value():
    value = request.json.get("value")
    if value is not None:
        
        
        return {"status": "success"}, 200
    return {"error": "Invalid value"}, 400

# @app.route('/sensor_data', methods=['GET'])

if __name__ == "__main__":
    app.run()