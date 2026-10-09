# MINISTER LIKE API SRC UID PASSWORD
# POWERED BY : @SIAM_CODEX
# CHANNEL : @SIAM_CoDeXFILE

from flask import Flask, request, jsonify
import asyncio
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToJson
import binascii
import aiohttp
import requests
import json
import like_pb2
import like_count_pb2
import uid_generator_pb2
from collections import defaultdict
from datetime import datetime, timedelta
import random
import os
import urllib.parse
import jwt

# ================= CONFIG =================
API_KEY = os.environ.get("API_KEY", "MASTER")
ACCOUNTS_FILE = "accounts.json"
VALID_SERVERS = ["IND", "BR", "US", "SAC", "NA", "BD", "RU"]
# ==========================================

app = Flask(__name__)
TOKEN_CACHE = {}
liked_cache = defaultdict(set)


# ---------------- Account Loader ----------------
def load_accounts(server_name=None):
    """Load all accounts from accounts.json (flat array)."""
    try:
        if not os.path.exists(ACCOUNTS_FILE):
            print(f"❌ {ACCOUNTS_FILE} not found")
            return []

        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # dict ফরম্যাট হলে server-specific, নাহলে flat array
        if isinstance(data, dict):
            accounts = data.get(server_name, [])
        else:
            accounts = data

        clean = []
        for acc in accounts:
            uid = str(acc.get("uid", "")).strip()
            pwd = str(acc.get("password", "")).strip()
            if uid and pwd:
                clean.append({
                    "uid": uid,
                    "password": pwd,
                    "account_id": acc.get("account_id", ""),
                    "name": acc.get("name", "")
                })

        print(f"📂 Loaded {len(clean)} accounts (server={server_name})")
        return clean
    except Exception as e:
        print(f"❌ Error loading accounts: {e}")
        return []


# ---------------- JWT Token ----------------
async def generate_jwt_token(uid, password):
    try:
        encoded_password = urllib.parse.quote(password, safe='')
        url = f"https://ff-jwt-gen-api.lovable.app/api/public/token?uid={uid}&password={encoded_password}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=24) as response:
                if response.status != 200:
                    return None
                raw = await response.text()
                try:
                    data = json.loads(raw)
                except Exception:
                    return None
                if isinstance(data, dict) and data.get("success") and isinstance(data.get("token"), str):
                    return data["token"]
                return None
    except Exception as e:
        print(f"❌ JWT exception for UID {uid}: {e}")
        return None


async def get_valid_token(uid, password):
    if uid in TOKEN_CACHE:
        cached = TOKEN_CACHE[uid]
        remaining = (cached["expires_at"] - datetime.utcnow()).total_seconds()
        if remaining > 1800:
            return cached["token"]

    token = await generate_jwt_token(uid, password)
    if not token:
        return None

    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        exp = payload.get("exp")
        TOKEN_CACHE[uid] = {"token": token, "expires_at": datetime.utcfromtimestamp(exp)}
    except Exception:
        TOKEN_CACHE[uid] = {"token": token, "expires_at": datetime.utcnow() + timedelta(hours=24)}
    return token


# ---------------- Encryption ----------------
def encrypt_message(plaintext):
    key = b'Yg&tc%DEuh6%Zc^8'
    iv = b'6oyZDr22E3ychjM%'
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_message = pad(plaintext, AES.block_size)
    return binascii.hexlify(cipher.encrypt(padded_message)).decode('utf-8')


def create_protobuf_message(user_id, region):
    message = like_pb2.like()
    message.uid = int(user_id)
    message.region = region
    return message.SerializeToString()


def enc(uid):
    message = uid_generator_pb2.uid_generator()
    message.krishna_ = int(uid)
    message.teamXdarks = 1
    return encrypt_message(message.SerializeToString())


# ---------------- Like Sender ----------------
async def send_like(encrypted_uid, token, url):
    try:
        edata = bytes.fromhex(encrypted_uid)
        headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
            'Authorization': f"Bearer {token}",
            'Content-Type': "application/x-www-form-urlencoded",
            'X-GA': "v1 1",
            'ReleaseVersion': "OB55"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=edata, headers=headers, timeout=8) as response:
                return response.status
    except Exception:
        return 500


async def process_account(target_uid, encrypted_uid, account, url, semaphore):
    async with semaphore:
        token = await get_valid_token(account['uid'], account['password'])
        if not token:
            return 500, account['uid']
        status = await send_like(encrypted_uid, token, url)
        if status == 200:
            liked_cache[target_uid].add(account['uid'])
        return status, account['uid']


async def send_all_likes(target_uid, server_name, url):
    protobuf_message = create_protobuf_message(target_uid, server_name)
    encrypted_uid = encrypt_message(protobuf_message)

    accounts = load_accounts(server_name)
    if not accounts:
        return {'success': 0, 'failed': 0, 'total': 0, 'already_liked': 0, 'fresh_used': 0}

    already_liked = liked_cache.get(target_uid, set())
    fresh_accounts = [acc for acc in accounts if acc['uid'] not in already_liked]

    if not fresh_accounts:
        return {
            'success': 0, 'failed': 0, 'total': len(accounts),
            'already_liked': len(already_liked), 'fresh_used': 0
        }

    random.shuffle(fresh_accounts)

    semaphore = asyncio.Semaphore(25)
    tasks = [process_account(target_uid, encrypted_uid, acc, url, semaphore)
             for acc in fresh_accounts[:2000]]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    successful = failed = 0
    for r in results:
        if isinstance(r, tuple):
            status, _ = r
            if status == 200:
                successful += 1
            else:
                failed += 1

    return {
        'success': successful,
        'failed': failed,
        'total': len(accounts),
        'already_liked': len(already_liked),
        'fresh_used': len(fresh_accounts[:2000])
    }


# ---------------- Player Info ----------------
def decode_protobuf(binary):
    try:
        items = like_count_pb2.Info()
        items.ParseFromString(binary)
        return items
    except Exception:
        return None


def get_player_info(encrypted_uid, server_name, token):
    if server_name == "IND":
        url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
    elif server_name in {"BR", "US", "SAC", "NA"}:
        url = "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
    else:
        url = "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"

    edata = bytes.fromhex(encrypted_uid)
    headers = {
        'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
        'Authorization': f"Bearer {token}",
        'Content-Type': "application/x-www-form-urlencoded",
        'X-GA': "v1 1",
        'ReleaseVersion': "OB55"
    }
    try:
        response = requests.post(url, data=edata, headers=headers, verify=False, timeout=10)
        return decode_protobuf(response.content)
    except Exception:
        return None


# ---------------- Routes ----------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "API is running ♾️",
        "endpoint": "/like?uid={uid}&server_name={server}&key={key}",
        "servers": VALID_SERVERS,
        "credit": "@SIAM_CODEX"
    })


@app.route('/like', methods=['GET'])
def handle_requests():
    uid = request.args.get("uid")
    server_name = request.args.get("server_name", "").upper()
    key = request.args.get("key")

    if key != API_KEY:
        return jsonify({"error": "Invalid or missing API key 🔑"}), 403

    if not uid or not server_name:
        return jsonify({"error": "UID and server_name are required"}), 400

    if server_name not in VALID_SERVERS:
        return jsonify({"error": f"Invalid server. Use: {VALID_SERVERS}"}), 400

    accounts = load_accounts(server_name)
    if not accounts:
        return jsonify({"error": f"No accounts found for server {server_name}"}), 500

    check_token = None
    for account in accounts[:5]:
        check_token = asyncio.run(get_valid_token(account['uid'], account['password']))
        if check_token:
            break

    if not check_token:
        return jsonify({"error": "Token generation failed - no valid accounts"}), 500

    encrypted_uid = enc(uid)

    before = get_player_info(encrypted_uid, server_name, check_token)
    if before is None:
        return jsonify({"error": "Invalid UID or server", "status": 0}), 200

    try:
        before_data = json.loads(MessageToJson(before))
        before_like = int(before_data['AccountInfo'].get('Likes', 0))
    except Exception:
        return jsonify({"error": "Data parsing failed", "status": 0}), 200

    if server_name == "IND":
        like_url = "https://client.ind.freefiremobile.com/LikeProfile"
    elif server_name in {"BR", "US", "SAC", "NA"}:
        like_url = "https://client.us.freefiremobile.com/LikeProfile"
    else:
        like_url = "https://clientbp.ggpolarbear.com/LikeProfile"

    asyncio.run(send_all_likes(uid, server_name, like_url))

    after = get_player_info(encrypted_uid, server_name, check_token)
    if after is None:
        return jsonify({"error": "Could not verify likes after command", "status": 0}), 200

    try:
        after_data = json.loads(MessageToJson(after))
        after_like = int(after_data['AccountInfo']['Likes'])
        player_id = int(after_data['AccountInfo']['UID'])
        player_name = str(after_data['AccountInfo']['PlayerNickname'])

        like_given = after_like - before_like
        status = 1 if like_given != 0 else 2

        return jsonify({
            "LikesGivenByAPI": like_given,
            "LikesafterCommand": after_like,
            "LikesbeforeCommand": before_like,
            "PlayerNickname": player_name,
            "UID": player_id,
            "status": status,
            "remains": "Unlimited ♾️",
            "credit": "MASTER THE GOAT ♑"
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": 0}), 500


@app.route('/reset-cache', methods=['GET'])
def reset_cache():
    key = request.args.get("key")
    if key != API_KEY:
        return jsonify({"error": "Invalid key"}), 403
    liked_cache.clear()
    return jsonify({"message": "Cache cleared", "credit": "@SIAM_CODEX"})


if __name__ == '__main__':
    print("🚀 Server started - Unlimited Like System!")
    print(f"🔑 API Key: {API_KEY}")
    app.run(host='0.0.0.0', port=5008, debug=False, use_reloader=False)