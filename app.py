from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import os
import threading
import uuid
import zipfile
import shutil

app = Flask(__name__)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Session-based progress tracking
progress_store = {}

def download_playlist(url, format_type, session_id):
    session_path = os.path.join(DOWNLOAD_DIR, session_id)
    os.makedirs(session_path, exist_ok=True)

    progress_store[session_id] = {
        "status": "starting",
        "current": 0,
        "total": 0,
        "current_title": "",
        "done": False,
        "error": None,
        "zip_ready": False
    }

    def progress_hook(d):
        if d['status'] == 'downloading':
            progress_store[session_id]['status'] = 'downloading'
            progress_store[session_id]['current_title'] = d.get('info_dict', {}).get('title', '')
        elif d['status'] == 'finished':
            progress_store[session_id]['current'] += 1

    ydl_opts = {
        'outtmpl': os.path.join(session_path, '%(playlist_index)s - %(title)s.%(ext)s'),
        'progress_hooks': [progress_hook],
        'cookiefile': os.environ.get('COOKIES_PATH', 'cookies.txt'),
        'ignoreerrors': True,
        'quiet': True,
        'no_warnings': True,
    }

    if format_type == 'mp3':
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    else:
        ydl_opts.update({
            'format': 'best',
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                total = len([e for e in info['entries'] if e])
            else:
                total = 1
            progress_store[session_id]['total'] = total
            ydl.download([url])

        # Zip everything
        zip_path = os.path.join(DOWNLOAD_DIR, f"{session_id}.zip")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fname in os.listdir(session_path):
                zf.write(os.path.join(session_path, fname), fname)

        shutil.rmtree(session_path)
        progress_store[session_id]['done'] = True
        progress_store[session_id]['zip_ready'] = True
        progress_store[session_id]['status'] = 'complete'

    except Exception as e:
        progress_store[session_id]['error'] = str(e)
        progress_store[session_id]['done'] = True
        progress_store[session_id]['status'] = 'error'


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/start', methods=['POST'])
def start_download():
    data = request.json
    url = data.get('url', '').strip()
    fmt = data.get('format', 'mp3')

    if not url:
        return jsonify({'error': 'URL boşdur'}), 400

    session_id = str(uuid.uuid4())
    thread = threading.Thread(target=download_playlist, args=(url, fmt, session_id))
    thread.daemon = True
    thread.start()

    return jsonify({'session_id': session_id})


@app.route('/progress/<session_id>')
def get_progress(session_id):
    data = progress_store.get(session_id)
    if not data:
        return jsonify({'error': 'Tapılmadı'}), 404
    return jsonify(data)


@app.route('/download/<session_id>')
def download_zip(session_id):
    zip_path = os.path.join(DOWNLOAD_DIR, f"{session_id}.zip")
    if not os.path.exists(zip_path):
        return jsonify({'error': 'Fayl hazır deyil'}), 404
    return send_file(zip_path, as_attachment=True, download_name='playlist.zip')


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
