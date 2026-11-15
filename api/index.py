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

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST'])
@app.route('/<path:path>', methods=['GET', 'POST'])
def master_route(path):
    if not supabase: return jsonify({"error": "Database terputus"}), 500

    if request.method == 'GET':
        tipe = request.args.get('tipe', 'meeting')
        projek = request.args.get('projek')
        customer_id = request.args.get('customer_id') 
        
        if projek:
            if tipe == 'dokumen' and customer_id:
                try:
                    res = supabase.table('documents').select('*').eq('customer_id', customer_id).order('uploaded_at', desc=True).execute()
                    return jsonify(res.data), 200
                except Exception as e: return jsonify({"error": str(e)}), 500
            else:
                try:
                    res = supabase.table('meetings').select('*').eq('nama_projek', projek).order('tanggal', desc=True).order('jam', desc=True).execute()
                    return jsonify(res.data), 200
                except Exception as e: return jsonify({"error": str(e)}), 500
        else:
            try:
                res = supabase.table('customers').select('*').order('updated_at', desc=True).execute()
                return jsonify(res.data), 200
            except Exception as e: return jsonify({"error": str(e)}), 500

    elif request.method == 'POST':
        if request.is_json:
            data = request.get_json()
            if data and 'message' in data: return process_telegram_webhook(data)
            
            action = data.get('action')
            customer_id = data.get('id')
            
            # --- LOGIKA HAPUS CUSTOMER ---
            if action == 'delete':
                try:
                    supabase.table('customers').delete().eq('id', customer_id).execute()
                    return jsonify({"message": "Dihapus"}), 200
                except Exception as e: return jsonify({"error": str(e)}), 500

            # --- LOGIKA TAMBAH / EDIT CUSTOMER ---
            perusahaan = data.get("perusahaan", "").strip()
            
            # Validasi Anti-Duplikat Nama PT
            if perusahaan:
                existing = supabase.table('customers').select('id').ilike('perusahaan', perusahaan).execute()
                if existing.data:
                    # Tolak jika ini tambah baru, ATAU jika diedit tapi pakai nama PT lain yang sudah ada
                    if not customer_id or str(existing.data[0]['id']) != str(customer_id):
                        return jsonify({"error": f"Nama perusahaan '{perusahaan}' sudah terdaftar di sistem!"}), 400

            try:
                payload = {
                    "perusahaan": perusahaan, "nama_customer": data.get("nama_customer"),
                    "no_telepon": data.get("no_telepon"), "alamat": data.get("alamat"),
                    "posisi": data.get("posisi"), "nama_projek": data.get("nama_projek"),
                    "status_projek": data.get("status_projek"), "dibawa_oleh": data.get("dibawa_oleh"),
                    "status_kerjasama": "Aktif"
                }
                if customer_id:
                    supabase.table('customers').update(payload).eq('id', customer_id).execute()
                else:
                    supabase.table('customers').insert(payload).execute()
                return jsonify({"message": "Berhasil!"}), 201
            except Exception as e: return jsonify({"error": str(e)}), 500
        
        else:
            action = request.form.get('action', 'meeting')
            projek = request.form.get('nama_projek')
            customer_id = request.form.get('customer_id')
            
            # --- LOGIKA UPLOAD DOKUMEN ---
            if action == 'dokumen' and customer_id:
                doc_id = request.form.get('id')
                nama_file = request.form.get('nama_file')
                kategori_file = request.form.get('kategori_file')
                file = request.files.get('file')
                file_url = request.form.get('file_url_lama') 
                
                if file and file.filename:
                    file_name = f"doc_{customer_id}_{file.filename.replace(' ', '_')}"
                    file_bytes = file.read()
                    try:
                        supabase.storage.from_('documents').upload(file_name, file_bytes, {"content-type": file.content_type})
                        file_url = f"{SUPABASE_URL}/storage/v1/object/public/documents/{file_name}"
                    except Exception:
                        file_url = f"{SUPABASE_URL}/storage/v1/object/public/documents/{file_name}"
                
                try:
                    if doc_id:
                        supabase.table('documents').update({"nama_file": nama_file, "kategori_file": kategori_file, "file_url": file_url}).eq('id', doc_id).execute()
                    else:
                        supabase.table('documents').insert({"customer_id": customer_id, "nama_file": nama_file, "kategori_file": kategori_file, "file_url": file_url}).execute()
                    return jsonify({"status": "ok"}), 201
                except Exception as e: return jsonify({"error": str(e)}), 500
                
            # --- LOGIKA MEETING / PROGRESS ---
            elif projek:
                meeting_id = request.form.get('id')
                tanggal = request.form.get('tanggal')
                jam = request.form.get('jam')
                judul = request.form.get('judul')
                mom = request.form.get('mom')
                foto = request.files.get('foto')
                foto_url = None
                
                if foto and foto.filename:
                    file_name = f"{projek.replace(' ', '_')}_{foto.filename.replace(' ', '_')}"
                    file_bytes = foto.read()
                    try:
                        supabase.storage.from_('documents').upload(file_name, file_bytes, {"content-type": foto.content_type})
                        foto_url = f"{SUPABASE_URL}/storage/v1/object/public/documents/{file_name}"
                    except Exception:
                        foto_url = f"{SUPABASE_URL}/storage/v1/object/public/documents/{file_name}"
                
                try:
                    data_payload = {"nama_projek": projek, "tanggal": tanggal, "jam": jam, "judul": judul, "mom": mom}
                    if foto_url: data_payload["foto_url"] = foto_url
                        
                    if meeting_id: supabase.table('meetings').update(data_payload).eq('id', meeting_id).execute()
                    else: supabase.table('meetings').insert(data_payload).execute()
                    return jsonify({"status": "ok"}), 201
                except Exception as e: return jsonify({"error": str(e)}), 500

        return jsonify({"error": "Permintaan tidak valid"}), 400

def process_telegram_webhook(data):
    if not data or 'message' not in data: return jsonify({"status": "ok"}), 200
    chat_id = data['message']['chat']['id']
    text_message = data['message'].get('text', '')
    
    if text_message == '/start':
        send_telegram_message(chat_id, "Halo! Asisten CRM siap membantu. Tanyakan progres proyek Anda.")
        return jsonify({"status": "ok"}), 200
        
    if not ai_client: return jsonify({"status": "ok"}), 200
    try:
        cust_data = "Kosong"
        meet_data = "Kosong"
        if supabase:
            c_res = supabase.table('customers').select('perusahaan, nama_projek, status_projek').execute()
            m_res = supabase.table('meetings').select('nama_projek, tanggal, judul, mom').execute()
            if c_res.data: cust_data = json.dumps(c_res.data)
            if m_res.data: meet_data = json.dumps(m_res.data)
            
        prompt = f"Data Proyek: {cust_data}. Riwayat Meeting: {meet_data}. Pertanyaan pengguna: '{text_message}'. Jawab ringkas."
        response = ai_client.models.generate_content(model='gemini-3.8-flash', contents=prompt)
        send_telegram_message(chat_id, response.text)
    except Exception as e: pass
    return jsonify({"status": "ok"}), 200

def send_telegram_message(chat_id, text):
    if TELEGRAM_TOKEN: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": text})

if __name__ == '__main__':
    app.run(debug=True)
