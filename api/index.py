import os
import json
import requests
from flask import Flask, request, jsonify
from supabase import create_client, Client
from google import genai

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
SUPABASE_URL = os.environ.get('SUPABASE_URL', '').strip()
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '').strip()
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '').strip()
ALLOWED_TELEGRAM_IDS = str(os.environ.get('ALLOWED_TELEGRAM_IDS', ''))

if SUPABASE_URL.endswith('/'): SUPABASE_URL = SUPABASE_URL[:-1]
if SUPABASE_URL.endswith('/rest/v1'): SUPABASE_URL = SUPABASE_URL.replace('/rest/v1', '')

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try: supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e: print(f"Error Supabase: {e}")

ai_client = None
if GEMINI_API_KEY:
    try: ai_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e: print(f"Error Gemini: {e}")

@app.route('/api/customers', methods=['GET', 'POST'])
@app.route('/api/index.py', methods=['GET', 'POST']) 
def manage_customers():
    if not supabase: return jsonify({"error": "Database tidak terhubung"}), 500
    if request.method == 'GET':
        try:
            res = supabase.table('customers').select('*').order('updated_at', desc=True).execute()
            return jsonify(res.data), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    elif request.method == 'POST':
        data = request.get_json()
        if data and 'message' in data: return process_telegram_webhook(data)
        try:
            supabase.table('customers').insert({
                "perusahaan": data.get("perusahaan"), "nama_customer": data.get("nama_customer"),
                "no_telepon": data.get("no_telepon"), "alamat": data.get("alamat"),
                "posisi": data.get("posisi"), "nama_projek": data.get("nama_projek"),
                "status_projek": data.get("status_projek"), "dibawa_oleh": data.get("dibawa_oleh"),
                "status_kerjasama": "Aktif"
            }).execute()
            return jsonify({"message": "Berhasil!"}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 500

@app.route('/api/meetings', methods=['GET', 'POST'])
def manage_meetings():
    if not supabase: return jsonify({"error": "Database terputus"}), 500
    if request.method == 'GET':
        projek = request.args.get('projek')
        try:
            res = supabase.table('meetings').select('*').eq('nama_projek', projek).order('tanggal', desc=True).execute()
            return jsonify(res.data), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    if request.method == 'POST':
        projek = request.form.get('nama_projek')
        tanggal = request.form.get('tanggal')
        judul = request.form.get('judul')
        mom = request.form.get('mom')
        foto = request.files.get('foto')
        foto_url = ""
        if foto:
            file_name = f"{projek.replace(' ', '_')}_{foto.filename}"
            file_bytes = foto.read()
            try:
                supabase.storage.from_('documents').upload(file_name, file_bytes, {"content-type": foto.content_type})
                foto_url = f"{SUPABASE_URL}/storage/v1/object/public/documents/{file_name}"
            except: pass 
                
        try:
            supabase.table('meetings').insert({
                "nama_projek": projek, "tanggal": tanggal, "judul": judul, "mom": mom, "foto_url": foto_url
            }).execute()
            return jsonify({"status": "ok"}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 500

@app.route('/api/webhook', methods=['POST'])
def webhook_route():
    return process_telegram_webhook(request.get_json())

def process_telegram_webhook(data):
    if not data or 'message' not in data: return jsonify({"status": "ok"}), 200
    chat_id = data['message']['chat']['id']
    text_message = data['message'].get('text', '')
    if text_message == '/start':
        send_telegram_message(chat_id, "Halo! Asisten CRM siap membantu.")
        return jsonify({"status": "ok"}), 200
    if not ai_client: return jsonify({"status": "ok"}), 200
    try:
        cust_data = "Kosong."
        if supabase:
            res = supabase.table('customers').select('perusahaan, nama_customer, nama_projek, status_projek').execute()
            if res.data: cust_data = json.dumps(res.data)
        prompt = f"Data pelanggan: {cust_data}. Pertanyaan: '{text_message}'. Jawab ringkas dan sopan."
        response = ai_client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
        send_telegram_message(chat_id, response.text)
    except Exception as e:
        send_telegram_message(chat_id, f"Error: {e}")
    return jsonify({"status": "ok"}), 200

def send_telegram_message(chat_id, text):
    if TELEGRAM_TOKEN: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": text})

if __name__ == '__main__':
    app.run(debug=True)
