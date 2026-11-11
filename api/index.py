import os
import json
import requests
from flask import Flask, request, jsonify
from supabase import create_client, Client
from google import genai

# Inisialisasi Aplikasi Flask
app = Flask(__name__)

# ==========================================
# 1. KONFIGURASI ENVIRONMENT VARIABLES
# ==========================================
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
ALLOWED_TELEGRAM_IDS = str(os.environ.get('ALLOWED_TELEGRAM_IDS', ''))

# ==========================================
# 2. INISIALISASI SUPABASE & GEMINI
# ==========================================
# Coba hubungkan ke Supabase (Jika env vars tersedia)
try:
    if SUPABASE_URL and SUPABASE_KEY:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    else:
        supabase = None
except Exception as e:
    print(f"Error Supabase: {e}")
    supabase = None

# Coba hubungkan ke Gemini (Paket baru: google-genai)
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
# 4. RUTE WEBHOOK UNTUK TELEGRAM BOT
# ==========================================
@app.route('/api/webhook', methods=['POST'])
def telegram_webhook():
    # Ambil data yang dikirim oleh Telegram
    data = request.get_json()
    
    # Pastikan data berupa pesan (message)
    if not data or 'message' not in data:
        return jsonify({"status": "ok"}), 200
        
    chat_id = data['message']['chat']['id']
    user_id = str(data['message']['from']['id'])
    text_message = data['message'].get('text', '')

    # --- PROTEKSI KEAMANAN ---
    # Pecah daftar ID yang diizinkan (misal dari "123456,987654" menjadi list)
    allowed_ids = [id.strip() for id in ALLOWED_TELEGRAM_IDS.split(',')]
    
    if user_id not in allowed_ids:
        # Jika ada orang asing mengirim pesan ke bot Anda
        send_telegram_message(chat_id, "🔒 Maaf, Anda tidak memiliki akses ke sistem CRM ini.")
        return jsonify({"status": "forbidden"}), 200

    # --- LOGIKA RESPON BOT ---
    if text_message == '/start':
        welcome_text = "Halo! Sistem Cloud CRM aktif.\n\nAnda dapat mengirimkan instruksi untuk menambah, mengubah, atau mencari data customer."
        send_telegram_message(chat_id, welcome_text)
        return jsonify({"status": "ok"}), 200

    # Respon default sementara (Sebelum Gemini dan Supabase dirakit penuh)
    reply_text = f"Pesan diterima: '{text_message}'.\nBot sedang dalam tahap penyelesaian konfigurasi dasar."
    send_telegram_message(chat_id, reply_text)

    return jsonify({"status": "ok"}), 200

# ==========================================
# 5. TITIK JALAN SERVER
# ==========================================
# Bagian ini wajib ada agar Vercel dapat menjalankan aplikasi Python
if __name__ == '__main__':
    app.run(debug=True)
