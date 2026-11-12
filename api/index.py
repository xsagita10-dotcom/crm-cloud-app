import os
import json
import requests
from flask import Flask, request, jsonify
from supabase import create_client, Client
from google import genai

app = Flask(__name__)

# ==========================================
# 1. KONFIGURASI ENVIRONMENT VARIABLES (ANTI-ERROR)
# ==========================================
# .strip() akan otomatis menghapus spasi yang tidak sengaja ikut tersalin
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
SUPABASE_URL = os.environ.get('SUPABASE_URL', '').strip()
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '').strip()
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '').strip()
ALLOWED_TELEGRAM_IDS = str(os.environ.get('ALLOWED_TELEGRAM_IDS', ''))

# Bersihkan URL Supabase dari garis miring ekstra atau rute yang salah
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

try:
    if GEMINI_API_KEY:
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
    else:
        ai_client = None
except Exception as e:
    print(f"Error Gemini: {e}")
    ai_client = None

# ==========================================
# 3. FUNGSI BANTUAN (KIRIM PESAN TELEGRAM)
# ==========================================
def send_telegram_message(chat_id, text):
    if not TELEGRAM_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Gagal mengirim pesan Telegram: {e}")

# ==========================================
# 4 & 5. RUTE API & WEBHOOK
# ==========================================
@app.route('/api/index.py', methods=['GET', 'POST'])
@app.route('/api/customers', methods=['GET', 'POST'])
@app.route('/api/webhook', methods=['GET', 'POST'])
def api_handler():
    if request.method == 'GET':
        if not supabase:
            return jsonify({"error": "Database tidak terhubung (Cek URL & Key)"}), 500
        try:
            response = supabase.table('customers').select('*').order('updated_at', desc=True).execute()
            return jsonify(response.data), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    elif request.method == 'POST':
        data = request.get_json()
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
            welcome_text = "Halo! Sistem Cloud CRM aktif.\n\nAnda dapat mengirimkan instruksi untuk menambah, mengubah, atau mencari data customer."
            send_telegram_message(chat_id, welcome_text)
            return jsonify({"status": "ok"}), 200

        reply_text = f"Pesan diterima: '{text_message}'.\nBot sedang dalam tahap penyelesaian konfigurasi dasar."
        send_telegram_message(chat_id, reply_text)

        return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(debug=True)
