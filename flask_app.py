#!/bin/usr/python

from flask import Flask, request, render_template, jsonify
from flask_caching import Cache
import threading
import json
from datetime import datetime, timedelta
import os
import uuid
import shutil

DATA_FILE = '/var/www/html/iot/data'
TOKEN_KEY = 'TOKENS'
TOKEN_SENSOR_KEY = 'TOKEN_SENSOR'
TOKEN_DATA_KEY = 'TOKEN_DATA'

config = {
    'CACHE_TYPE': 'FileSystemCache',
    'CACHE_DIR': DATA_FILE,
    'CACHE_DEFAULT_TIMEOUT': 300
}

app = Flask(__name__)
app.config.from_mapping(config)
cache = Cache(app)

app.DATA_FILE = '/var/www/html/iot/data'

if os.path.exists(DATA_FILE):
    for filename in os.listdir(DATA_FILE):
        file_path = f'{DATA_FILE}/{filename}'
        try:
            if os.path.isdir(file_path):
                shutil.rmtree(file_path)
            else:
                os.remove(file_path)
        except Exception:
            pass

def __cache_get(key):
    value = cache.get(key)
    if value is None:
        return None
    
    return json.loads(value)

def __cache_set(key, value, timeout=0):
    value = json.dumps(value)
    cache.set(key, value, timeout = timeout)

@app.route('/', methods = ['GET'])
def homepage():
    return render_template(template_name_or_list = 'index.html')

@app.route('/generate_token', methods = ['GET'])
def generate_token():
    new_token = str(uuid.uuid4())

    tokens = __cache_get(TOKEN_KEY)
    if tokens is None:
        tokens = [new_token]
    else:
        tokens.append(new_token)

    __cache_set(TOKEN_KEY, tokens)

    return render_template(
        template_name_or_list = 'generated_token.html',
        token = new_token
    )

def __validate_token(token):
    tokens = __cache_get(TOKEN_KEY)
    if tokens is None:
        return False
    
    return token in tokens

def __validate_sensor(token, sensor):
    sensor_ip = __cache_get(f'{TOKEN_SENSOR_KEY}_{token}')
    if sensor_ip is None:
        return False

    return sensor is None or sensor == sensor_ip

@app.route('/view', methods = ['GET'])
def view():
    token = request.args.get('token')

    if not __validate_token(token):
        return render_template(
            template_name_or_list = 'error.html',
            message = f'Token {token} is not registered'
        )
    
    if not __validate_sensor(token, None):
        return render_template(
            template_name_or_list = 'error.html',
            message = f'Token {token} has no sensor attached'
        )

    return render_template(
        template_name_or_list = 'view.html',
        token = token
    )

def __read__token_data(token):
    content = __cache_get(f'{TOKEN_DATA_KEY}_{token}')
    if content is None:
        return []
    
    return content
    
def __write_token_data(token, data):
    __cache_set(f'{TOKEN_DATA_KEY}_{token}', data)

@app.route('/view_data/<token>', methods = ['GET'])
def view_data(token):
    if not __validate_token(token):
        return jsonify({'error': f'Bad token {token}'}), 405
    
    if not __validate_sensor(token, None):
        return jsonify({'error': 'No sensor attached'}), 405
    
    data = __read__token_data(token)
    return jsonify(data), 200

def __update_token_sensor_time(token, sensor_ip):
    __cache_set(f'{TOKEN_SENSOR_KEY}_{token}', sensor_ip, timeout=600)

@app.route('/update_data/<token>', methods = ['POST'])
def update_data(token):
    if not __validate_token(token):
        return jsonify({'error': f'Bad token {token}'}), 405
    
    if not __validate_sensor(token, request.remote_addr):
        return jsonify({'error': 'Mismatch in sensors'}), 405
    
    __update_token_sensor_time(token, request.remote_addr)
    
    body = request.json
    if 'values' not in body:
        return jsonify({'error': 'Expected values list'}), 405
    
    data = __read__token_data(token)
    for item in body['values']:
        data.append({
            'x': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'y': item
        })

    if len(data) > 100:
        data = data[-100:]

    __write_token_data(token, data)

    return jsonify({'success': 'Data successfully updated'}), 200

@app.route('/alive/<token>', methods=['POST'])
def alive(token):
    if not __validate_token(token):
        return jsonify({'error': f'Bad token {token}'}), 405
    
    __update_token_sensor_time(token, request.remote_addr)

    return jsonify({'success': f'Registered sensor for token {token} for 10 min'}), 200

if __name__ == "__main__":
    app.run()