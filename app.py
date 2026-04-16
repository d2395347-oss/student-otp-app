import os
import time
import hashlib
import random
from urllib.parse import urlparse

from flask import Flask, render_template, request, jsonify, redirect, url_for
from twilio.rest import Client
import mysql.connector
from mysql.connector import pooling
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ================= FILE UPLOAD =================
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ================= DATABASE (USING DB_URL) =================
DB_URL = os.getenv("DB_URL")

if not DB_URL:
    raise Exception("❌ DB_URL not found in environment variables")

url = urlparse(DB_URL)

db_pool = pooling.MySQLConnectionPool(
    pool_name="student_pool",
    pool_size=5,
    host=url.hostname,
    user=url.username,
    password=url.password,
    database=url.path.lstrip("/"),
    port=url.port
)

def get_db():
    return db_pool.get_connection()

# ================= TWILIO =================
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")

client = Client(ACCOUNT_SID, AUTH_TOKEN)

# ================= OTP =================
otp_store = {}
otp_verified = set()

OTP_EXPIRY = 300

# ================= HELPERS =================
def normalize_phone(phone):
    if not phone.startswith("+91"):
        phone = "+91" + phone
    return phone

def hash_aadhaar(aadhaar):
    return hashlib.sha256(aadhaar.encode()).hexdigest()

# ================= ROUTES =================
@app.route("/")
def home():
    return render_template("form.html")

@app.route("/send_otp", methods=["POST"])
def send_otp():
    phone = normalize_phone(request.form.get("phone"))

    otp = str(random.randint(100000, 999999))
    otp_store[phone] = {"otp": otp, "time": time.time()}

    try:
        client.messages.create(
            body=f"Your OTP is {otp}",
            from_=TWILIO_NUMBER,
            to=phone
        )
        return jsonify({"status": "success"})
    except Exception as e:
        print(e)
        return jsonify({"status": "error"})

@app.route("/verify_otp", methods=["POST"])
def verify_otp():
    phone = normalize_phone(request.form.get("phone"))
    otp = request.form.get("otp")

    data = otp_store.get(phone)

    if not data:
        return jsonify({"status": "error", "message": "No OTP"})

    if time.time() - data["time"] > OTP_EXPIRY:
        return jsonify({"status": "error", "message": "Expired"})

    if otp == data["otp"]:
        otp_verified.add(phone)
        return jsonify({"status": "success"})
    else:
        return jsonify({"status": "error", "message": "Wrong OTP"})

# ================= MAIN SUBMIT =================
@app.route("/submit", methods=["POST"])
def submit():
    phone = normalize_phone(request.form.get("mobile"))

    if phone not in otp_verified:
        return "Verify OTP first"

    name = request.form.get("name")
    father = request.form.get("father_name")
    category = request.form.get("category")
    aadhaar = request.form.get("aadhaar")

    aadhaar_hash = hash_aadhaar(aadhaar)

    # ===== FILES =====
    file1 = request.files.get("special_file")
    file2 = request.files.get("extra_file")
    file3 = request.files.get("achievement_file")

    def save_file(file):
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(path)
            return filename
        return None

    file1_name = save_file(file1)
    file2_name = save_file(file2)
    file3_name = save_file(file3)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO students 
        (name, father_name, category, phone, aadhaar_hash, special_file, extra_file, achievement_file)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (name, father, category, phone, aadhaar_hash, file1_name, file2_name, file3_name))

    conn.commit()

    cursor.close()
    conn.close()

    return redirect(url_for("students"))

# ================= VIEW =================
@app.route("/students")
def students():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT name, father_name, category, phone FROM students")
    data = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("students.html", students=data)

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)