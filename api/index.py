import os
import json
import requests
from flask import Flask, request, jsonify
from supabase import create_client, Client
from google import genai

app = Flask(__name__)

# ==========================================
# 1. KONFIGURASI ENVIRONMENT VARIABLES
# ==========================================
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
SUPABASE_URL = os.environ.get('SUPABASE_URL', '').strip()
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '').strip()
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '').strip()
ALLOWED_TELEGRAM_IDS = str(os.environ.get('ALLOWED_TELEGRAM_IDS', ''))

if SUPABASE_URL.endswith('/'):
    SUPABASE_URL = SUPABASE_URL[:-1]
if SUPABASE_URL.endswith('/rest/v1'):
    SUPABASE_URL = SUPABASE_URL.replace('/rest/v1', '')

# ==========================================
# 2. INISIALISASI SUPABASE & GEMINI
# ==========================================
try:
    if SUPABASE_URL and SUPABASE_KEY:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    else:
        supabase = None
except Exception as e:
    print(f"Error Supabase: {e}")
    supabase = None

# ==========================================
# 3. RUTE API WEB: AMBIL & TAMBAH CUSTOMER
# ==========================================
@app.route('/api/customers', methods=['GET', 'POST'])
@app.route('/api/index.py', methods=['GET', 'POST']) 
def manage_customers():
    if not supabase:
        return jsonify({"error": "Database tidak terhubung"}), 500

    if request.method == 'GET':
        try:
            response = supabase.table('customers').select('*').order('updated_at', desc=True).execute()
            return jsonify(response.data), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    elif request.method == 'POST':
        data = request.get_json()
        if data and 'message' in data:
            return process_telegram_webhook(data)

        try:
            new_customer = {
                "perusahaan": data.get("perusahaan"),
                "nama_customer": data.get("nama_customer"),
                "no_telepon": data.get("no_telepon"),
                "alamat": data.get("alamat"),
                "status_kerjasama": "Aktif"
            }
            response = supabase.table('customers').insert(new_customer).execute()
            return jsonify({"message": "Data berhasil ditambahkan!"}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 500

# ==========================================
# 4. RUTE WEBHOOK TELEGRAM
# ==========================================
@app.route('/api/webhook', methods=['POST'])
def webhook_route():
    data = request.get_json()
    return process_telegram_webhook(data)

def process_telegram_webhook(data):
    if not data or 'message' not in data:
        return jsonify({"status": "ok"}), 200
        
    chat_id = data['message']['chat']['id']
    user_id = str(data['message']['from']['id'])
    text_message = data['message'].get('text', '')

    allowed_ids = [id.strip() for id in ALLOWED_TELEGRAM_IDS.split(',')]
    
    if user_id not in allowed_ids:
        send_telegram_message(chat_id, "🔒 Maaf, Anda tidak memiliki akses ke sistem CRM ini.")
        return jsonify({"status": "forbidden"}), 200

    if text_message == '/start':
        send_telegram_message(chat_id, "Halo! Sistem Cloud CRM aktif.")
        return jsonify({"status": "ok"}), 200

    send_telegram_message(chat_id, f"Pesan diterima: '{text_message}'.")
    return jsonify({"status": "ok"}), 200

def send_telegram_message(chat_id, text):
    if TELEGRAM_TOKEN:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text})

if __name__ == '__main__':
    app.run(debug=True)
