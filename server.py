from flask import Flask, jsonify, send_file, request
import requests
import os
import io

app = Flask(__name__)

# هنا سيقرأ الوسيط المفتاح السري من إعدادات Render (وليس من الكود)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_OWNER = os.environ.get("REPO_OWNER")
REPO_NAME = os.environ.get("REPO_NAME")

@app.route('/check-update', methods=['GET'])
def check_update():
    if not GITHUB_TOKEN:
        return jsonify({"error": "Server configuration error"}), 500

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    # الوسيط يذهب إلى GitHub ليعرف آخر إصدار
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        latest_version = data["tag_name"]
        if len(data["assets"]) > 0:
            download_url = data["assets"][0]["url"] 
            return jsonify({
                "version": latest_version,
                "download_endpoint": f"/download?url={download_url}"
            })
        else:
            return jsonify({"error": "No assets found in release"}), 404
    else:
        return jsonify({"error": "Failed to fetch release"}), response.status_code

@app.route('/download', methods=['GET'])
def download_file():
    file_url = request.args.get("url")
    if not file_url:
        return jsonify({"error": "Missing URL"}), 400

    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    req = requests.get(file_url, headers=headers, stream=True)
    
    if req.status_code == 200:
        return send_file(
            io.BytesIO(req.content), 
            as_attachment=True, 
            download_name="ODEJ-Updater.exe"
        )
    else:
        return jsonify({"error": "Failed to download file"}), req.status_code

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)