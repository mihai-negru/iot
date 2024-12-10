#!/bin/usr/python

from flask import Flask, request, render_template, jsonify
import threading
import json
from datetime import datetime, timedelta
import os
import uuid
import shutil

app = Flask(__name__)

app.DATA_FILE = '/var/www/html/iot/data'

app.TOKENS = []
app.TOKENS_DATA_LOCKS = {}
app.TOKENS_SENSOR = {}

if os.path.exists(app.DATA_FILE):
    for filename in os.listdir(app.DATA_FILE):
        file_path = f'{app.DATA_FILE}/{filename}'
        try:
            if os.path.isdir(file_path):
                shutil.rmtree(file_path)
            else:
                os.remove(file_path)
        except Exception:
            pass

@app.route('/', methods = ['GET'])
def homepage():
    return render_template(template_name_or_list = 'index.html')

@app.route('/generate_token', methods = ['GET'])
def generate_token():
    new_token = uuid.uuid4()

    with app.TOKENS_LOCK:
        with open(app.TOKENS, 'a') as fout:
            fout.write(f'{new_token}\n')

    app.TOKENS_DATA_LOCKS[new_token] = threading.Lock()

    return render_template(
        template_name_or_list = 'generated_token.html',
        token = new_token
    )

def __validate_token(token):
    return token in app.TOKENS

def __validate_sensor(token, sensor):
    if token not in app.TOKENS_SENSOR:
        return False
    
    if sensor is not None and app.TOKENS_SENSOR[token][0] != sensor:
        return False

    current_time = datetime.now()
    if current_time >= app.TOKENS_SENSOR[token][1]:
        del app.TOKENS_SENSOR[token]
        return False
    
    return True

@app.route('/view', methods = ['GET'])
def view():
    token = request.args.get('token')

    if not __validate_token(token):
        return render_template(
            template_name_or_list = 'error.html',
            message = f'Token {token} is not registered'
        )
    
    if not __validate_token(token, None):
        return render_template(
            template_name_or_list = 'error.html',
            message = f'Token {token} has no sensor attached'
        )

    return render_template(
        template_name_or_list = 'view.html',
        token = token
    )

def __read__token_data(token):
    try:
        with app.TOKENS_DATA_LOCKS[token]:
            with open(f'{app.DATA_FILE}/{token}', 'r') as fin:
                data = json.load(fin)

        return data
    except Exception:
        return []
    
def __write_token_data(token, data):
    with app.TOKENS_DATA_LOCKS[token]:
        with open(f'{app.DATA_FILE}/{token}', 'w') as fout:
                json.dump(data, fout)

@app.route('/view_data/<token>', methods = ['GET'])
def view_data(token):
    if not __validate_token(token):
        return jsonify({'error': 'Bad token'}), 405
    
    if not __validate_token(token, None):
        return jsonify({'error': 'No sensor attached'}), 405
    
    data = __read__token_data(token)
    return jsonify(data), 200

@app.route('/update_data/<token>', methods = ['POST'])
def update_data(token):
    if not __validate_token(token):
        return jsonify({'error': 'Bad token'}), 405
    
    if not __validate_token(token, request.remote_addr):
        return jsonify({'error': 'Mismatch in sensors'}), 405
    
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
        return jsonify({'error': 'Bad token'}), 405
    
    app.TOKENS_SENSOR[token] = (request.remote_addr, datetime.now() + timedelta(minutes=10))

    return jsonify({'success': f'Registered sensor for token {token} for 10 min'}), 200

if __name__ == "__main__":
    app.run()