import os
import json
import requests
import uuid
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

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Error Supabase: {e}")

ai_client = None
if GEMINI_API_KEY:
    try:
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Error Gemini: {e}")

# ==========================================
# 2. RUTE CUSTOMER
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
                "posisi": data.get("posisi"),
                "nama_projek": data.get("nama_projek"),
                "status_projek": data.get("status_projek"),
                "dibawa_oleh": data.get("dibawa_oleh"),
                "status_kerjasama": "Aktif"
            }
            supabase.table('customers').insert(new_customer).execute()
            return jsonify({"message": "Data berhasil ditambahkan!"}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 500

# ==========================================
# 3. RUTE MEETING & DOKUMEN (BARU)
# ==========================================
@app.route('/api/meetings', methods=['GET', 'POST'])
def manage_meetings():
    if not supabase:
        return jsonify({"error": "Database tidak terhubung"}), 500

    if request.method == 'GET':
        projek = request.args.get('projek')
        try:
            if projek:
                res = supabase.table('meetings').select('*').eq('nama_projek', projek).order('tanggal', desc=True).execute()
            else:
                res = supabase.table('meetings').select('*').execute()
            return jsonify(res.data), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    elif request.method == 'POST':
        try:
            nama_projek = request.form.get('nama_projek')
            tanggal = request.form.get('tanggal')
            judul = request.form.get('judul')
            mom = request.form.get('mom')
            file = request.files.get('file')

            foto_url = ""
            if file and file.filename:
                # Ambil ekstensi asli (misal: .jpg, .png, .pdf)
                ext = file.filename.split('.')[-1]
                filename = f"{uuid.uuid4().hex}.{ext}"
                file_bytes = file.read()
                
                # Upload ke Supabase Bucket 'documents'
                supabase.storage.from_('documents').upload(
                    path=filename, 
                    file=file_bytes, 
                    file_options={"content-type": file.content_type}
                )
                foto_url = f"{SUPABASE_URL}/storage/v1/object/public/documents/{filename}"

            new_meeting = {
                "nama_projek": nama_projek,
                "tanggal": tanggal,
                "judul": judul,
                "mom": mom,
                "foto_url": foto_url
            }
            supabase.table('meetings').insert(new_meeting).execute()
            return jsonify({"message": "Meeting berhasil disimpan!"}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 500

# ==========================================
# 4. RUTE WEBHOOK TELEGRAM AI
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
    
    if user_id not in allowed_ids and ALLOWED_TELEGRAM_IDS:
        send_telegram_message(chat_id, "🔒 Maaf, Anda tidak memiliki akses ke sistem CRM ini.")
        return jsonify({"status": "forbidden"}), 200
    if text_message == '/start':
        send_telegram_message(chat_id, "Halo! Asisten AI CRM aktif. Anda bisa bertanya tentang data pelanggan.")
        return jsonify({"status": "ok"}), 200

    if not ai_client:
        send_telegram_message(chat_id, "Sistem AI belum siap.")
        return jsonify({"status": "ok"}), 200
    try:
        cust_data_text = "Saat ini belum ada data pelanggan."
        if supabase:
            res = supabase.table('customers').select('perusahaan, nama_customer, nama_projek, status_projek').execute()
            if res.data:
                cust_data_text = json.dumps(res.data)

        prompt = f"Berikut data pelanggan & proyek saat ini: {cust_data_text}. Pertanyaan: '{text_message}'. Jawab santai, sopan, dan singkat."
        response = ai_client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
        send_telegram_message(chat_id, response.text)
    except Exception as e:
        send_telegram_message(chat_id, f"Maaf, AI terkendala teknis: {str(e)}")
    return jsonify({"status": "ok"}), 200

def send_telegram_message(chat_id, text):
    if TELEGRAM_TOKEN:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": text})

if __name__ == '__main__':
    app.run(debug=True)
