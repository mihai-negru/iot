#!/bin/usr/python

from flask import Flask, request, render_template, jsonify, redirect
from flask_caching import Cache
import threading
import requests
import json
from datetime import datetime, timedelta
import uuid
import smtplib
from email.mime.text import MIMEText

MAX_SENSOR_LIMIT = 2 ** 16
DEFAULT_SENSOR_LIMIT = 45000

DATA_FILE = '/var/www/html/iot/data'
TOKEN_KEY = 'TOKENS'
TOKEN_SENSOR_KEY = 'TOKEN_SENSOR'
TOKEN_DATA_KEY = 'TOKEN_DATA'
TOKEN_LIMIT_KEY = 'TOKEN_LIMIT'
TOKEN_LIMIT_MODIFIED_KEY = 'TOKEN_LIMIT_MODIFIED'
TOKEN_EMAIL_KEY = 'TOKEN_EMAIL'
TOKEN_NOTIFIED_KEY = 'TOKEN_NOTIFIED'

config = {
    'CACHE_TYPE': 'FileSystemCache',
    'CACHE_DIR': DATA_FILE,
    'CACHE_DEFAULT_TIMEOUT': 300
}

app = Flask(__name__)
app.config.from_mapping(config)
cache = Cache(app)

def __cache_get(key):
    value = cache.get(key)
    if value is None:
        return None
    
    return json.loads(value)

def __cache_set(key, value, timeout=0):
    value = json.dumps(value)
    cache.set(key, value, timeout = timeout)

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

def __read__token_data(token):
    content = __cache_get(f'{TOKEN_DATA_KEY}_{token}')
    if content is None:
        return []
    
    return content
    
def __write_token_data(token, data):
    __cache_set(f'{TOKEN_DATA_KEY}_{token}', data)

def __update_token_sensor_time(token, sensor_ip):
    __cache_set(f'{TOKEN_SENSOR_KEY}_{token}', sensor_ip, timeout=600)

def __send_email(token, limit):
    notified = __cache_get(f'{TOKEN_NOTIFIED_KEY}_{token}')
    if notified is not None:
        notified_date = datetime.strptime(notified, '%Y-%m-%d %H:%M:%S')
        if notified_date + timedelta(minutes=10) >= datetime.now():
            return
        
        __cache_set(f'{TOKEN_NOTIFIED_KEY}_{token}', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    content = __cache_get(f'{TOKEN_EMAIL_KEY}_{token}')
    if content is None:
        return
    
    email = content['email']
    password = content['password']

    msg = MIMEText(f'Sensor attached to token {token} has reached its limit: {limit}')
    msg['Subject'] = 'Sensor Limit Reached'
    msg['From'] = email
    msg['To'] = email

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(email, password)
        server.sendmail(email, email, msg.as_string())


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
    __cache_set(f'{TOKEN_LIMIT_KEY}_{new_token}', DEFAULT_SENSOR_LIMIT)

    return render_template(
        template_name_or_list = 'generated_token.html',
        token = new_token
    )

@app.route('/notify/email', methods = ['POST'])
def notify_email():
    token = request.args.get('token')

    if not __validate_token(token):
        return render_template(
            template_name_or_list = 'error.html',
            message = f'Token {token} is not registered',
            back = '/'
        )
    
    email = request.args.get('email')
    password = request.args.get('password')

    __cache_set(f'{TOKEN_EMAIL_KEY}_{token}', {'email': email, 'password': password})

    return render_template(
        template_name_or_list = 'ok.html',
        message = f'Email {email} successfully registered',
        back = '/'
    )

@app.route('/view', methods = ['GET'])
def view():
    token = request.args.get('token')

    if not __validate_token(token):
        return render_template(
            template_name_or_list = 'error.html',
            message = f'Token {token} is not registered',
            back = '/'
        )
    
    if not __validate_sensor(token, None):
        return render_template(
            template_name_or_list = 'error.html',
            message = f'Token {token} has no sensor attached',
            back = '/'
        )

    return render_template(
        template_name_or_list = 'view.html',
        token = token
    )

@app.route('/view_data/<token>', methods = ['GET'])
def view_data(token):
    if not __validate_token(token):
        return jsonify({'error': f'Bad token {token}'}), 405
    
    if not __validate_sensor(token, None):
        return jsonify({'error': 'No sensor attached'}), 405
    
    data = __read__token_data(token)
    return jsonify(data), 200

@app.route('/update_data/<token>', methods = ['POST'])
def update_data(token):
    if not __validate_token(token):
        return jsonify({'error': f'Bad token {token}'}), 405
    
    if not __validate_sensor(token, request.remote_addr):
        return jsonify({'error': 'Mismatch in sensors'}), 405
    
    __update_token_sensor_time(token, request.remote_addr)
    
    body = request.json
    if 'value' not in body:
        return jsonify({'error': 'Expected a value'}), 405
    
    data = __read__token_data(token)
    data.append({
            'x': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'y': body['value']
        })

    if len(data) > 100:
        data = data[-100:]

    __write_token_data(token, data)

    response = {'success': 'Data successfully updated'}
    limit = __cache_get(f'{TOKEN_LIMIT_MODIFIED_KEY}_{token}')
    if limit is not None:
        response['update'] = limit
        cache.delete(f'{TOKEN_LIMIT_MODIFIED_KEY}_{token}')
    else:
        limit = __cache_get(f'{TOKEN_LIMIT_KEY}_{token}')

    try:
        if float(body['value']) >= limit:
            threading.Thread(target = __send_email, args = (token, limit)).start()
    except:
        pass

    return jsonify(response), 200

@app.route('/alive/<token>', methods = ['POST'])
def alive(token):
    if not __validate_token(token):
        return jsonify({'error': f'Bad token {token}'}), 405
    
    __update_token_sensor_time(token, request.remote_addr)

    return jsonify({'success': f'Registered sensor for token {token} for 10 min'}), 200

@app.route('/sensor_limit/<token>', methods = ['GET'])
def sensor_limit(token):
    if not __validate_token(token):
        return render_template(
            template_name_or_list = 'error.html',
            message = f'Token {token} is not registered',
            back = f'/view?token={token}'
        )
    
    if not __validate_token(token):
        return render_template(
            template_name_or_list = 'error.html',
            message = f'Token {token} is not registered',
            back = f'/view?token={token}'
        )
    
    return render_template(
        template_name_or_list = 'change_limit.html',
        token = token
    )

@app.route('/update_sensor_limit/<token>', methods = ['GET'])
def update_sensor_limit(token):
    if not __validate_token(token):
        return render_template(
            template_name_or_list = 'error.html',
            message = f'Token {token} is not registered',
            back = f'/sensor_limit/{token}'
        )
    
    if not __validate_token(token):
        return render_template(
            template_name_or_list = 'error.html',
            message = f'Token {token} is not registered',
            back = f'/sensor_limit/{token}'
        )
    
    limit = request.args.get('limit')

    if not limit.isnumeric():
        return render_template(
                    template_name_or_list = 'error.html',
                    message = f'Limit {limit} cannot be converted to int',
                    back = f'/sensor_limit/{token}'
                )
            
    limit = int(limit)
    if limit >= MAX_SENSOR_LIMIT or limit <= 0:
        return render_template(
            template_name_or_list = 'error.html',
            message = f'Choose a limit between (0: {MAX_SENSOR_LIMIT}]',
            back = f'/sensor_limit/{token}'
        )

    __cache_set(f'{TOKEN_LIMIT_KEY}_{token}', limit)
    __cache_set(f'{TOKEN_LIMIT_MODIFIED_KEY}_{token}', limit)

    return redirect(f'/view?token={token}')

if __name__ == "__main__":
    app.run()
