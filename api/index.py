import os
import json
import time
import requests
from flask import Flask, request, jsonify
from supabase import create_client, Client
import google.generativeai as genai

app = Flask(__name__)

# Mengambil Kunci dari Environment Variables Vercel
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Inisialisasi Supabase & Gemini
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# ENDPOINT UNTUK WEB DASHBOARD
# ==========================================

@app.route('/api/customers', methods=['GET'])
def get_customers():
    try:
        # Mengambil semua data customer beserta file dokumen yang terhubung
        res = supabase.table('customers').select('*, documents(*)').order('updated_at', desc=True).execute()
        return jsonify(res.data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/customers', methods=['POST'])
def add_customer():
    try:
        data = request.json
        res = supabase.table('customers').insert(data).execute()
        return jsonify(res.data), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/customers/<customer_id>', methods=['PUT', 'DELETE'])
def manage_customer(customer_id):
    try:
        if request.method == 'DELETE':
            supabase.table('customers').delete().eq('id', customer_id).execute()
            return jsonify({"status": "deleted"}), 200
        else:
            data = request.json
            data['updated_at'] = 'now()'
            res = supabase.table('customers').update(data).eq('id', customer_id).execute()
            return jsonify(res.data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_document():
    try:
        customer_id = request.form.get('customer_id')
        kategori = request.form.get('kategori_file', 'Dokumen')
        file = request.files.get('file')
        
        if not file or not customer_id:
            return jsonify({"error": "File dan Customer ID wajib diisi"}), 400

        file_bytes = file.read()
        file_path = f"{customer_id}/{int(time.time())}_{file.filename}"
        
        # Upload ke Supabase Storage bucket 'crm_files'
        supabase.storage.from_('crm_files').upload(
            path=file_path,
            file=file_bytes,
            file_options={"content-type": file.content_type}
        )
        
        public_url = supabase.storage.from_('crm_files').get_public_url(file_path)
        
        # Catat ke tabel documents
        doc_data = {
            "customer_id": customer_id,
            "nama_file": file.filename,
            "kategori_file": kategori,
            "file_url": public_url
        }
        res = supabase.table('documents').insert(doc_data).execute()
        return jsonify(res.data), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==========================================
# ENDPOINT UNTUK WEBHOOK TELEGRAM
# ==========================================

@app.route('/api/webhook', methods=['POST'])
def telegram_webhook():
    data = request.json
    if not data or 'message' not in data:
        return jsonify({"status": "ok"}), 200

    msg = data['message']
    chat_id = msg['chat']['id']

    try:
        # 1. JIKA VOICE NOTE
        if 'voice' in msg:
            send_telegram(chat_id, "🎙️ Menganalisis Voice Note...")
            file_bytes, _ = get_telegram_file(msg['voice']['file_id'])
            ai_res = analyze_with_gemini(audio_bytes=file_bytes, mime_type=msg['voice'].get('mime_type', 'audio/ogg'))
            reply = execute_crm_action(ai_res)
            send_telegram(chat_id, reply)

        # 2. JIKA DOKUMEN (PDF, WORD, DLL) ATAU FOTO
        elif 'document' in msg or 'photo' in msg:
            send_telegram(chat_id, "📁 Menyimpan file ke Cloud...")
            caption = msg.get('caption', '')
            
            if 'document' in msg:
                file_id = msg['document']['file_id']
                file_name = msg['document'].get('file_name', f"doc_{int(time.time())}")
                mime_type = msg['document'].get('mime_type', 'application/octet-stream')
            else:
                file_id = msg['photo'][-1]['file_id'] # Ambil resolusi tertinggi
                file_name = f"foto_{int(time.time())}.jpg"
                mime_type = 'image/jpeg'

            file_bytes, _ = get_telegram_file(file_id)
            
            # Analisis caption dengan Gemini untuk tahu milik PT apa & kategori apa
            ai_res = analyze_with_gemini(text=f"File diupload dengan caption: {caption}")
            reply = execute_crm_action(ai_res, file_bytes=file_bytes, file_name=file_name, mime_type=mime_type)
            send_telegram(chat_id, reply)

        # 3. JIKA TEKS BIASA
        elif 'text' in msg and not msg['text'].startswith('/'):
            send_telegram(chat_id, "🤖 Memproses instruksi...")
            ai_res = analyze_with_gemini(text=msg['text'])
            reply = execute_crm_action(ai_res)
            send_telegram(chat_id, reply)

    except Exception as e:
        send_telegram(chat_id, f"⚠️ Terjadi kesalahan: {str(e)}")

    return jsonify({"status": "ok"}), 200

# ==========================================
# FUNGSI PENDUKUNG AI & DATABASE
# ==========================================

def analyze_with_gemini(text=None, audio_bytes=None, mime_type=None):
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = """
    Kamu adalah AI CRM Manager. Analisis input teks atau suara ini.
    Keluarkan HANYA format JSON murni (tanpa ```json) dengan struktur berikut:
    {
      "action": "INSERT" atau "UPDATE" atau "DELETE",
      "target_perusahaan": "Nama PT/Perusahaan yang disebut",
      "kategori_file": "MOU" / "Adendum" / "Company Profile" / "Foto Pertemuan" / "Lainnya",
      "data": {
        "nama_customer": "Nama orang/PIC (jika ada)",
        "perusahaan": "Nama PT/Perusahaan",
        "jabatan": "Jabatan PIC (jika ada)",
        "alamat": "Alamat (jika ada)",
        "no_telepon": "Nomor telp (jika ada)",
        "status_kerjasama": "Prospect / Negosiasi / MOU Aktif / Selesai (jika disebut)",
        "notes": "Catatan tambahan dari pembicaraan"
      }
    }
    Aturan:
    - Jika user minta tambah data baru, action = INSERT.
    - Jika user minta ubah status, tambah catatan, atau melampirkan file ke PT yang sudah ada, action = UPDATE.
    - Kosongkan string "" jika informasi tidak disebutkan di input.
    """
    content = [prompt]
    if text:
        content.append(text)
    if audio_bytes:
        content.append({"mime_type": mime_type, "data": audio_bytes})

    response = model.generate_content(content)
    raw = response.text.strip().replace('```json', '').replace('```', '').strip()
    return json.loads(raw)

def execute_crm_action(ai_res, file_bytes=None, file_name=None, mime_type=None):
    action = ai_res.get('action', 'INSERT')
    target_pt = ai_res.get('target_perusahaan') or ai_res.get('data', {}).get('perusahaan')
    raw_data = ai_res.get('data', {})
    
    # Bersihkan field yang kosong agar tidak menimpa data lama dengan string kosong saat UPDATE
    clean_data = {k: v for k, v in raw_data.items() if v}

    if not target_pt:
        return "❌ Tolong sebutkan nama Perusahaan (PT) dengan jelas."

    # Cari apakah perusahaan sudah ada di database
    existing = supabase.table('customers').select('*').ilike('perusahaan', f"%{target_pt}%").execute()
    
    customer_id = None
    msg_status = ""

    if existing.data:
        # Jika PT ditemukan, kita UPDATE datanya
        customer_id = existing.data[0]['id']
        nama_pt_asli = existing.data[0]['perusahaan']
        if action == 'DELETE':
            supabase.table('customers').delete().eq('id', customer_id).execute()
            return f"🗑️ Data {nama_pt_asli} beserta seluruh dokumennya telah dihapus."
        
        if clean_data:
            clean_data['updated_at'] = 'now()'
            supabase.table('customers').update(clean_data).eq('id', customer_id).execute()
        msg_status = f"✅ Data *{nama_pt_asli}* berhasil diperbarui!"
    else:
        # Jika PT belum ada, kita INSERT baru
        if 'perusahaan' not in clean_data:
            clean_data['perusahaan'] = target_pt
        res = supabase.table('customers').insert(clean_data).execute()
        customer_id = res.data[0]['id']
        msg_status = f"✅ Perusahaan baru *{target_pt}* berhasil ditambahkan!"

    # Jika ada pengiriman file/foto bersama instruksi tersebut
    if file_bytes and customer_id:
        path = f"{customer_id}/{int(time.time())}_{file_name}"
        supabase.storage.from_('crm_files').upload(
            path=path, file=file_bytes, file_options={"content-type": mime_type}
        )
        public_url = supabase.storage.from_('crm_files').get_public_url(path)
        
        doc_entry = {
            "customer_id": customer_id,
            "nama_file": file_name,
            "kategori_file": ai_res.get('kategori_file', 'Dokumen'),
            "file_url": public_url
        }
        supabase.table('documents').insert(doc_entry).execute()
        msg_status += f"\n📎 File *{file_name}* ({doc_entry['kategori_file']}) berhasil disimpan!"

    return msg_status

def get_telegram_file(file_id):
    r = requests.get(f"[https://api.telegram.org/bot](https://api.telegram.org/bot){TELEGRAM_TOKEN}/getFile?file_id={file_id}").json()
    file_path = r['result']['file_path']
    file_bytes = requests.get(f"[https://api.telegram.org/file/bot](https://api.telegram.org/file/bot){TELEGRAM_TOKEN}/{file_path}").content
    return file_bytes, file_path

def send_telegram(chat_id, text):
    requests.post(f"[https://api.telegram.org/bot](https://api.telegram.org/bot){TELEGRAM_TOKEN}/sendMessage", json={
        "chat_id": chat_id, "text": text, "parse_mode": "Markdown"
    })

if __name__ == '__main__':
    app.run(debug=True)
