import os
import json
import urllib.parse
from datetime import datetime, timedelta, timezone
import requests
from flask import Flask, request, jsonify
from supabase import create_client, Client
from google import genai
from google.genai import types

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
        tipe = request.args.get('tipe', 'customer')
        projek = request.args.get('projek')
        customer_id = request.args.get('customer_id') 
        
        try:
            if tipe == 'all_dokumen':
                res = supabase.table('documents').select('*').order('uploaded_at', desc=True).execute()
                return jsonify(res.data), 200
            elif tipe == 'all_meetings':
                res = supabase.table('meetings').select('*').order('tanggal', desc=True).order('jam', desc=True).execute()
                return jsonify(res.data), 200
            elif tipe == 'dokumen' and customer_id:
                res = supabase.table('documents').select('*').eq('customer_id', customer_id).order('uploaded_at', desc=True).execute()
                return jsonify(res.data), 200
            elif tipe == 'meeting':
                if projek == '__ALL__' and customer_id:
                    c_res = supabase.table('customers').select('nama_projek').eq('id', customer_id).execute()
                    if c_res.data and c_res.data[0].get('nama_projek'):
                        projs = [p.strip() for p in c_res.data[0]['nama_projek'].split('||') if p.strip()]
                        if projs:
                            res = supabase.table('meetings').select('*').in_('nama_projek', projs).order('tanggal', desc=True).order('jam', desc=True).execute()
                            return jsonify(res.data), 200
                    return jsonify([]), 200
                elif projek:
                    res = supabase.table('meetings').select('*').eq('nama_projek', projek).order('tanggal', desc=True).order('jam', desc=True).execute()
                    return jsonify(res.data), 200
                return jsonify([]), 200
            else:
                res = supabase.table('customers').select('*').order('updated_at', desc=True).execute()
                return jsonify(res.data), 200
        except Exception as e: 
            return jsonify({"error": str(e)}), 500

    elif request.method == 'POST':
        if request.is_json:
            data = request.get_json()
            if data and 'message' in data: return process_telegram_webhook(data)
            
            action = data.get('action')
            customer_id = data.get('id')
            
            # --- HAPUS CUSTOMER ---
            if action == 'delete':
                try:
                    supabase.table('customers').delete().eq('id', customer_id).execute()
                    return jsonify({"message": "Dihapus"}), 200
                except Exception as e: return jsonify({"error": str(e)}), 500

            # --- HAPUS FILE DOKUMEN (DATABASE + STORAGE) ---
            if action == 'delete_dokumen':
                doc_id = data.get('id')
                file_url = data.get('file_url', '')
                try:
                    if file_url and '/storage/v1/object/public/documents/' in file_url:
                        file_name = file_url.split('/storage/v1/object/public/documents/')[-1]
                        try:
                            supabase.storage.from_('documents').remove([file_name])
                        except Exception:
                            pass
                    supabase.table('documents').delete().eq('id', doc_id).execute()
                    return jsonify({"message": "Dokumen dihapus"}), 200
                except Exception as e: return jsonify({"error": str(e)}), 500

            # --- MINTA TIKET DIRECT UPLOAD KE SUPABASE (BYPASS LIMIT VERCEL) ---
            if action == 'get_upload_url':
                file_name = data.get('file_name', '').strip()
                if not file_name:
                    return jsonify({"error": "Nama file kosong"}), 400
                try:
                    res = supabase.storage.from_('documents').create_signed_upload_url(file_name)
                    signed_url = res.get('signed_url') or res.get('signedURL')
                    if signed_url and signed_url.startswith('/'):
                        signed_url = f"{SUPABASE_URL}/storage/v1{signed_url}"
                    public_url = f"{SUPABASE_URL}/storage/v1/object/public/documents/{file_name}"
                    return jsonify({"signed_url": signed_url, "public_url": public_url}), 200
                except Exception as e:
                    return jsonify({"error": str(e)}), 500

            perusahaan = data.get("perusahaan", "").strip()
            if perusahaan:
                existing = supabase.table('customers').select('id').ilike('perusahaan', perusahaan).execute()
                if existing.data:
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
                if customer_id: supabase.table('customers').update(payload).eq('id', customer_id).execute()
                else: supabase.table('customers').insert(payload).execute()
                return jsonify({"message": "Berhasil!"}), 201
            except Exception as e: return jsonify({"error": str(e)}), 500
        
        else:
            action = request.form.get('action', 'meeting')
            projek = request.form.get('nama_projek', 'Umum')
            customer_id = request.form.get('customer_id')
            timestamp = int(datetime.now().timestamp())
            
            if action == 'dokumen' and customer_id:
                doc_id = request.form.get('id')
                nama_file = request.form.get('nama_file')
                kategori_raw = request.form.get('kategori_file', 'Umum')
                
                if projek and not kategori_raw.startswith('['):
                    kategori_file = f"[{projek}] {kategori_raw}"
                else:
                    kategori_file = kategori_raw

                file = request.files.get('file')
                file_url = request.form.get('file_url_lama') 
                
                if file and file.filename:
                    safe_name = file.filename.replace(' ', '_')
                    file_name = f"doc_{customer_id}_{timestamp}_{safe_name}"
                    file_bytes = file.read()
                    try:
                        supabase.storage.from_('documents').upload(file_name, file_bytes, {"content-type": file.content_type})
                        file_url = f"{SUPABASE_URL}/storage/v1/object/public/documents/{file_name}"
                    except Exception:
                        file_url = f"{SUPABASE_URL}/storage/v1/object/public/documents/{file_name}"
                
                try:
                    if doc_id: supabase.table('documents').update({"nama_file": nama_file, "kategori_file": kategori_file, "file_url": file_url}).eq('id', doc_id).execute()
                    else: supabase.table('documents').insert({"customer_id": customer_id, "nama_file": nama_file, "kategori_file": kategori_file, "file_url": file_url}).execute()
                    return jsonify({"status": "ok"}), 201
                except Exception as e: return jsonify({"error": str(e)}), 500
                
            elif projek:
                meeting_id = request.form.get('id')
                tanggal = request.form.get('tanggal')
                jam = request.form.get('jam')
                judul = request.form.get('judul')
                mom = request.form.get('mom')
                foto = request.files.get('foto')
                foto_url = request.form.get('foto_url_direct') or None
                
                if foto and foto.filename:
                    safe_proj = projek.replace(' ', '_')
                    safe_foto = foto.filename.replace(' ', '_')
                    file_name = f"{safe_proj}_{timestamp}_{safe_foto}"
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

def get_telegram_file_bytes(file_id):
    try:
        res = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}").json()
        if res.get("ok"):
            file_path = res["result"]["file_path"]
            return requests.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}").content
    except Exception as e: print(f"Gagal unduh suara: {e}")
    return None

def process_telegram_webhook(data):
    if not data or 'message' not in data: return jsonify({"status": "ok"}), 200
    msg = data['message']
    chat_id = msg['chat']['id']
    text_message = msg.get('text', '')
    voice = msg.get('voice')
    
    if text_message == '/start':
        send_telegram_message(chat_id, "Halo! Asisten Pintar CRM siap membantu.")
        return jsonify({"status": "ok"}), 200
        
    if not ai_client: return jsonify({"status": "ok"}), 200

    try:
        wib_now = datetime.now(timezone(timedelta(hours=7)))
        waktu_sekarang = wib_now.strftime("%Y-%m-%d %H:%M (%A)")

        cust_data, meet_data, doc_data = "[]", "[]", "[]"
        if supabase:
            c_res = supabase.table('customers').select('id, perusahaan, nama_customer, posisi, no_telepon, nama_projek, status_projek').execute()
            m_res = supabase.table('meetings').select('nama_projek, tanggal, jam, judul, mom').order('tanggal', desc=True).limit(30).execute()
            d_res = supabase.table('documents').select('customer_id, nama_file, kategori_file, file_url').execute()
            if c_res.data: cust_data = json.dumps(c_res.data)
            if m_res.data: meet_data = json.dumps(m_res.data)
            if d_res.data: doc_data = json.dumps(d_res.data)

        system_instruction = f"""
Kamu adalah Asisten AI Cloud CRM. Waktu sekarang (WIB): {waktu_sekarang}
Data Pelanggan & Proyek: {cust_data}
Riwayat Meeting: {meet_data}
Data Dokumen: {doc_data}

Pilih salah satu format JSON murni berikut (tanpa ```json):
1. Tanya jawab biasa: {{"action": "chat", "reply": "Jawaban"}}
2. Buat jadwal/progress: {{"action": "create_meeting", "nama_projek": "Nama Projek spesifik", "perusahaan": "Nama PT", "tanggal": "YYYY-MM-DD", "jam": "HH:MM", "judul": "Judul", "mom": "Catatan", "reply": "Konfirmasi"}}
3. Tambah pelanggan: {{"action": "add_customer", "perusahaan": "Nama PT", "nama_customer": "Nama Kontak", "posisi": "Jabatan", "no_telepon": "No HP", "alamat": "Alamat", "nama_projek": "Nama Projek", "status_projek": "On Progress", "reply": "Konfirmasi"}}
"""

        contents = [system_instruction]
        if voice:
            send_telegram_message(chat_id, "🎧 _Mendengarkan Voice Note..._")
            audio_bytes = get_telegram_file_bytes(voice['file_id'])
            if audio_bytes:
                contents.append(types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg"))
                contents.append("Jalankan perintah suara ini sesuai instruksi JSON.")
            else:
                send_telegram_message(chat_id, "Gagal mengunduh suara.")
                return jsonify({"status": "ok"}), 200
        else:
            contents.append(f"Pesan pengguna: '{text_message}'")

        response = ai_client.models.generate_content(model='gemini-3.8-flash', contents=contents)
        raw_text = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        
        result = json.loads(raw_text)
        action = result.get("action", "chat")
        reply_msg = result.get("reply", "Sudah diproses.")

        if action == "create_meeting" and supabase:
            projek = result.get("nama_projek")
            tgl = result.get("tanggal") or wib_now.strftime("%Y-%m-%d")
            jam = result.get("jam") or "10:00"
            judul = result.get("judul") or "Meeting"
            mom = result.get("mom") or ""
            
            supabase.table('meetings').insert({"nama_projek": projek, "tanggal": tgl, "jam": jam, "judul": judul, "mom": mom}).execute()

            start_str = tgl.replace('-', '') + 'T' + jam.replace(':', '') + '00'
            gcal_params = urllib.parse.urlencode({"action": "TEMPLATE", "text": f"{judul} - {projek}", "dates": f"{start_str}/{start_str}", "details": f"Meeting Proyek: {projek}\nCatatan: {mom}"})
            gcal_url = f"https://calendar.google.com/calendar/render?{gcal_params}"
            reply_msg += f"\n\n📌 *Tersimpan:*\n• Proyek: {projek}\n• Waktu: {tgl} {jam}\n📅 [Simpan ke Google Calendar]({gcal_url})"

        elif action == "add_customer" and supabase:
            pt = result.get("perusahaan", "").strip()
            existing = supabase.table('customers').select('id').ilike('perusahaan', pt).execute()
            if existing.data: reply_msg = f"⚠️ Perusahaan *{pt}* sudah terdaftar!"
            else:
                supabase.table('customers').insert({
                    "perusahaan": pt, "nama_customer": result.get("nama_customer", "-"), "posisi": result.get("posisi", "-"),
                    "no_telepon": result.get("no_telepon", "-"), "alamat": result.get("alamat", "-"),
                    "nama_projek": result.get("nama_projek", "Proyek Baru"), "status_projek": result.get("status_projek", "On Progress"), "status_kerjasama": "Aktif"
                }).execute()

        send_telegram_message(chat_id, reply_msg)
    except Exception as e:
        send_telegram_message(chat_id, f"Kendala memproses perintah: {e}")
    return jsonify({"status": "ok"}), 200

def send_telegram_message(chat_id, text):
    if TELEGRAM_TOKEN: 
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})

if __name__ == '__main__':
    app.run(debug=True)
