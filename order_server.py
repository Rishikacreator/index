from flask import Flask, request, jsonify, send_from_directory
from pathlib import Path
from datetime import datetime
import json
import os

import pymysql
from flask_cors import CORS

BASE = Path(__file__).resolve().parent

app = Flask(__name__, static_folder=str(BASE), static_url_path='')
CORS(app, resources={r"/api/*": {"origins": "*"}})

DB_HOST = os.getenv('MYSQL_HOST', '127.0.0.1')
DB_PORT = int(os.getenv('MYSQL_PORT', '3306'))
DB_USER = os.getenv('MYSQL_USER', 'root')
DB_PASSWORD = os.getenv('MYSQL_PASSWORD', '')
DB_NAME = os.getenv('MYSQL_DATABASE', 'suvidha_bazar')


def db_conn(database: bool = True):
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME if database else None,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def init_db():
    conn = db_conn(database=False)
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    finally:
        conn.close()

    conn = db_conn(database=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    customer_name VARCHAR(120) NOT NULL,
                    customer_phone VARCHAR(40) NULL,
                    items_json LONGTEXT NULL,
                    custom_request TEXT NULL,
                    custom_request_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
                    total DECIMAL(10,2) NOT NULL DEFAULT 0,
                    payment_mode VARCHAR(30) NOT NULL DEFAULT 'QR',
                    payment_status VARCHAR(80) NOT NULL DEFAULT 'Pending Screenshot'
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    name VARCHAR(120) NOT NULL,
                    rating TINYINT NOT NULL,
                    message TEXT NOT NULL
                )
                """
            )
    finally:
        conn.close()


def parse_items(items_json: str):
    if not items_json:
        return []
    try:
        return json.loads(items_json)
    except Exception:
        return []


def fmt_dt(value):
    if hasattr(value, 'isoformat'):
        return value.isoformat(timespec='seconds')
    return str(value)


@app.get('/')
def home():
    return send_from_directory(BASE, 'index.html')


@app.get('/api/orders')
def get_orders():
    try:
        conn = db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, created_at, customer_name, customer_phone,
                           items_json, custom_request, custom_request_amount,
                           total, payment_mode, payment_status
                    FROM orders
                    ORDER BY id DESC
                    LIMIT 200
                    """
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        out = []
        for r in rows:
            out.append({
                'id': r['id'],
                'created_at': fmt_dt(r['created_at']),
                'customer_name': r.get('customer_name') or 'Customer',
                'customer_phone': r.get('customer_phone') or '',
                'items': parse_items(r.get('items_json')),
                'custom_request': r.get('custom_request') or '',
                'custom_request_amount': float(r.get('custom_request_amount') or 0),
                'total': float(r.get('total') or 0),
                'payment_mode': r.get('payment_mode') or 'QR',
                'payment_status': r.get('payment_status') or 'Pending Screenshot',
            })
        return jsonify(out)
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Database error: {e}'}), 500


@app.post('/api/orders')
def create_order():
    payload = request.get_json(silent=True) or {}
    items = payload.get('items', [])
    custom_request = (payload.get('custom_request') or '').strip()
    if not items and not custom_request:
        return jsonify({'ok': False, 'error': 'No items'}), 400

    customer_name = (payload.get('customer_name') or 'Customer').strip() or 'Customer'
    customer_phone = (payload.get('customer_phone') or '').strip()
    custom_request_amount = float(payload.get('custom_request_amount') or 0)
    total = float(payload.get('total') or 0)
    payment_mode = (payload.get('payment_mode') or 'QR').strip() or 'QR'
    payment_status = (payload.get('payment_status') or 'Pending Screenshot').strip() or 'Pending Screenshot'

    try:
        conn = db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO orders
                    (customer_name, customer_phone, items_json, custom_request,
                     custom_request_amount, total, payment_mode, payment_status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        customer_name,
                        customer_phone,
                        json.dumps(items, ensure_ascii=False),
                        custom_request,
                        custom_request_amount,
                        total,
                        payment_mode,
                        payment_status,
                    ),
                )
                order_id = cur.lastrowid
                cur.execute(
                    """
                    SELECT id, created_at FROM orders WHERE id=%s
                    """,
                    (order_id,),
                )
                created = cur.fetchone()
        finally:
            conn.close()

        order = {
            'id': order_id,
            'created_at': fmt_dt(created['created_at']) if created else datetime.now().isoformat(timespec='seconds'),
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'items': items,
            'custom_request': custom_request,
            'custom_request_amount': custom_request_amount,
            'total': total,
            'payment_mode': payment_mode,
            'payment_status': payment_status,
        }
        return jsonify({'ok': True, 'order': order})
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Database error: {e}'}), 500


@app.get('/api/feedback')
def get_feedback():
    try:
        conn = db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, created_at, name, rating, message
                    FROM feedback
                    ORDER BY id DESC
                    LIMIT 300
                    """
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        data = [
            {
                'id': r['id'],
                'created_at': fmt_dt(r['created_at']),
                'name': r.get('name') or 'Customer',
                'rating': int(r.get('rating') or 0),
                'message': r.get('message') or '',
            }
            for r in rows
        ]
        return jsonify(data)
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Database error: {e}'}), 500


@app.post('/api/feedback')
def create_feedback():
    payload = request.get_json(silent=True) or {}
    name = (payload.get('name') or '').strip()
    message = (payload.get('message') or '').strip()
    rating = int(payload.get('rating') or 0)

    if not name or not message or rating < 1 or rating > 5:
        return jsonify({'ok': False, 'error': 'Invalid feedback'}), 400

    try:
        conn = db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO feedback (name, rating, message)
                    VALUES (%s,%s,%s)
                    """,
                    (name, rating, message),
                )
                feedback_id = cur.lastrowid
                cur.execute(
                    """
                    SELECT id, created_at FROM feedback WHERE id=%s
                    """,
                    (feedback_id,),
                )
                created = cur.fetchone()
        finally:
            conn.close()

        return jsonify(
            {
                'ok': True,
                'feedback': {
                    'id': feedback_id,
                    'created_at': fmt_dt(created['created_at']) if created else datetime.now().isoformat(timespec='seconds'),
                    'name': name,
                    'rating': rating,
                    'message': message,
                },
            }
        )
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Database error: {e}'}), 500


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
