from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from pathlib import Path
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import re

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "careconnect.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = "careconnect-demo-secret-change-this-in-production"

SPECIALIZATIONS = [
    "General Physician", "Cardiologist", "Dermatologist", "Neurologist",
    "Pediatrician", "Orthopedic", "Gynecologist", "Dentist", "ENT Specialist",
    "Psychiatrist", "Ophthalmologist", "Diabetologist"
]

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL CHECK(role IN ('patient','doctor','admin')),
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        phone TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS doctor_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        specialization TEXT NOT NULL,
        qualification TEXT NOT NULL,
        experience INTEGER NOT NULL DEFAULT 0,
        hospital TEXT NOT NULL,
        location TEXT NOT NULL,
        bio TEXT DEFAULT '',
        license_no TEXT NOT NULL UNIQUE,
        verified INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS doctor_availability (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doctor_id INTEGER NOT NULL,
        available_date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        UNIQUE(doctor_id, available_date, start_time, end_time),
        FOREIGN KEY(doctor_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        appointment_no TEXT NOT NULL UNIQUE,
        patient_id INTEGER NOT NULL,
        doctor_id INTEGER NOT NULL,
        appointment_date TEXT NOT NULL,
        appointment_time TEXT NOT NULL,
        reason TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'Booked',
        created_at TEXT NOT NULL,
        FOREIGN KEY(patient_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(doctor_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS prescriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        appointment_id INTEGER,
        patient_id INTEGER NOT NULL,
        doctor_id INTEGER NOT NULL,
        diagnosis TEXT DEFAULT '',
        medicines TEXT NOT NULL,
        instructions TEXT DEFAULT '',
        duration_days INTEGER NOT NULL DEFAULT 1,
        start_date TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(appointment_id) REFERENCES appointments(id) ON DELETE SET NULL,
        FOREIGN KEY(patient_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(doctor_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        channel TEXT NOT NULL,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    admin = conn.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
    if not admin:
        conn.execute(
            "INSERT INTO users(role,name,email,phone,password_hash,created_at) VALUES(?,?,?,?,?,?)",
            ("admin", "CareConnect Admin", "admin@careconnect.com", "9000000000",
             generate_password_hash("Admin@123"), datetime.now().isoformat(timespec="seconds"))
        )

    count = conn.execute("SELECT COUNT(*) AS c FROM doctor_profiles").fetchone()["c"]
    if count == 0:
        sample = [
            ("Dr. Ananya Rao", "ananya@careconnect.demo", "9100000001", "Cardiologist", "MD Cardiology", 10, "City Heart Hospital", "Visakhapatnam"),
            ("Dr. Rahul Kumar", "rahul@careconnect.demo", "9100000002", "General Physician", "MBBS", 7, "Care Multispeciality Hospital", "Visakhapatnam"),
            ("Dr. Priya Sharma", "priya@careconnect.demo", "9100000003", "Dermatologist", "MD Dermatology", 8, "SkinCare Clinic", "Vizianagaram"),
            ("Dr. Arjun Reddy", "arjun@careconnect.demo", "9100000004", "Orthopedic", "MS Orthopedics", 12, "Ortho Plus Hospital", "Visakhapatnam"),
        ]
        for name, email, phone, spec, qual, exp, hospital, location in sample:
            cur = conn.execute(
                "INSERT INTO users(role,name,email,phone,password_hash,created_at) VALUES(?,?,?,?,?,?)",
                ("doctor", name, email, phone, generate_password_hash("Doctor@123"),
                 datetime.now().isoformat(timespec="seconds"))
            )
            conn.execute(
                """INSERT INTO doctor_profiles
                (user_id,specialization,qualification,experience,hospital,location,bio,license_no,verified)
                VALUES(?,?,?,?,?,?,?,?,1)""",
                (cur.lastrowid, spec, qual, exp, hospital, location,
                 f"{spec} with {exp} years of clinical experience.", f"DEMO-{cur.lastrowid:04d}")
            )
        conn.commit()
    conn.close()

def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please login to continue.", "error")
                return redirect(url_for("login", role=role or "patient"))
            if role and session.get("role") != role:
                flash("You do not have permission to open this page.", "error")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator

@app.context_processor
def inject_globals():
    return {"specializations": SPECIALIZATIONS, "today": date.today().isoformat()}

@app.route("/")
def home():
    conn = get_db()
    doctors = conn.execute("""
        SELECT u.id,u.name,dp.specialization,dp.qualification,dp.experience,
               dp.hospital,dp.location
        FROM users u JOIN doctor_profiles dp ON dp.user_id=u.id
        WHERE u.role='doctor' AND dp.verified=1
        ORDER BY u.name LIMIT 6
    """).fetchall()
    conn.close()
    return render_template("home.html", doctors=doctors)

@app.route("/register", methods=["GET","POST"])
def register():
    role = request.args.get("role", "patient")
    if role not in ("patient", "doctor"):
        role = "patient"

    if request.method == "POST":
        role = request.form.get("role", "patient")
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        phone = request.form.get("phone","").strip()
        password = request.form.get("password","")
        confirm = request.form.get("confirm_password","")

        errors = []
        if len(name) < 2:
            errors.append("Please enter a valid full name.")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            errors.append("Please enter a valid email address.")
        if not re.fullmatch(r"\d{10}", phone):
            errors.append("Phone number must contain exactly 10 digits.")
        if len(password) < 8:
            errors.append("Password must contain at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")

        conn = get_db()
        if conn.execute("SELECT 1 FROM users WHERE lower(email)=lower(?)", (email,)).fetchone():
            errors.append("This email is already registered. Please use another email or login.")
        if conn.execute("SELECT 1 FROM users WHERE phone=?", (phone,)).fetchone():
            errors.append("This phone number is already registered. Please use another number or login.")

        doctor_data = {}
        if role == "doctor":
            specialization = request.form.get("specialization","").strip()
            qualification = request.form.get("qualification","").strip()
            hospital = request.form.get("hospital","").strip()
            location = request.form.get("location","").strip()
            license_no = request.form.get("license_no","").strip().upper()
            try:
                experience = int(request.form.get("experience","0"))
            except ValueError:
                experience = -1
            doctor_data = dict(specialization=specialization, qualification=qualification,
                               hospital=hospital, location=location,
                               license_no=license_no, experience=experience)
            if specialization not in SPECIALIZATIONS:
                errors.append("Please select a valid specialization.")
            if not qualification or not hospital or not location or not license_no:
                errors.append("Please complete all doctor profile fields.")
            if experience < 0 or experience > 70:
                errors.append("Experience must be between 0 and 70 years.")
            if conn.execute("SELECT 1 FROM doctor_profiles WHERE upper(license_no)=upper(?)", (license_no,)).fetchone():
                errors.append("This medical license number is already registered.")

        if errors:
            conn.close()
            for e in errors:
                flash(e, "error")
            return render_template("register.html", role=role)

        cur = conn.execute(
            "INSERT INTO users(role,name,email,phone,password_hash,created_at) VALUES(?,?,?,?,?,?)",
            (role,name,email,phone,generate_password_hash(password),
             datetime.now().isoformat(timespec="seconds"))
        )
        user_id = cur.lastrowid

        if role == "doctor":
            conn.execute(
                """INSERT INTO doctor_profiles
                (user_id,specialization,qualification,experience,hospital,location,bio,license_no,verified)
                VALUES(?,?,?,?,?,?,?,?,0)""",
                (user_id, doctor_data["specialization"], doctor_data["qualification"],
                 doctor_data["experience"], doctor_data["hospital"], doctor_data["location"],
                 "", doctor_data["license_no"], 0)
            )
            conn.execute(
                "INSERT INTO notifications(user_id,channel,title,message,created_at) VALUES(?,?,?,?,?)",
                (user_id,"system","Doctor application submitted",
                 "Your doctor registration was submitted. Admin verification is pending.",
                 datetime.now().isoformat(timespec="seconds"))
            )
            flash("Doctor registration successful. Please wait for admin verification before logging in.", "success")
        else:
            flash("Patient registration successful. You can now login.", "success")
        conn.commit()
        conn.close()
        return redirect(url_for("login", role=role))

    return render_template("register.html", role=role)

@app.route("/login", methods=["GET","POST"])
def login():
    role = request.args.get("role", "patient")
    if role not in ("patient","doctor","admin"):
        role = "patient"

    if request.method == "POST":
        role = request.form.get("role", role)
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE lower(email)=lower(?) AND role=?", (email,role)).fetchone()

        if not user or not check_password_hash(user["password_hash"], password):
            conn.close()
            flash("Incorrect email, password, or account type. Please check your details.", "error")
            return render_template("login.html", role=role)

        if role == "doctor":
            profile = conn.execute("SELECT verified FROM doctor_profiles WHERE user_id=?", (user["id"],)).fetchone()
            if not profile or profile["verified"] != 1:
                conn.close()
                flash("Your doctor account is waiting for admin verification.", "error")
                return render_template("login.html", role=role)

        session.clear()
        session["user_id"] = user["id"]
        session["role"] = user["role"]
        session["name"] = user["name"]
        conn.close()
        flash(f"Welcome, {user['name']}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html", role=role)

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))

@app.route("/dashboard")
@login_required()
def dashboard():
    if session["role"] == "patient":
        return redirect(url_for("patient_dashboard"))
    if session["role"] == "doctor":
        return redirect(url_for("doctor_dashboard"))
    return redirect(url_for("admin_dashboard"))

@app.route("/patient/dashboard")
@login_required("patient")
def patient_dashboard():
    conn = get_db()
    appointments = conn.execute("""
        SELECT a.*, u.name AS doctor_name, dp.specialization, dp.hospital
        FROM appointments a
        JOIN users u ON u.id=a.doctor_id
        JOIN doctor_profiles dp ON dp.user_id=u.id
        WHERE a.patient_id=? ORDER BY a.appointment_date DESC, a.appointment_time DESC LIMIT 8
    """,(session["user_id"],)).fetchall()
    prescriptions = conn.execute("""
        SELECT p.*, u.name AS doctor_name
        FROM prescriptions p JOIN users u ON u.id=p.doctor_id
        WHERE p.patient_id=? ORDER BY p.created_at DESC LIMIT 5
    """,(session["user_id"],)).fetchall()
    conn.close()
    return render_template("patient_dashboard.html", appointments=appointments, prescriptions=prescriptions)

@app.route("/doctors")
@login_required("patient")
def doctors():
    q = request.args.get("q","").strip()
    spec = request.args.get("specialization","").strip()
    conn = get_db()
    sql = """
        SELECT u.id,u.name,u.email,u.phone,dp.specialization,dp.qualification,
               dp.experience,dp.hospital,dp.location,dp.bio
        FROM users u JOIN doctor_profiles dp ON dp.user_id=u.id
        WHERE u.role='doctor' AND dp.verified=1
    """
    params=[]
    if q:
        sql += " AND (u.name LIKE ? OR dp.hospital LIKE ? OR dp.location LIKE ? OR dp.specialization LIKE ?)"
        like=f"%{q}%"; params += [like,like,like,like]
    if spec:
        sql += " AND dp.specialization=?"; params.append(spec)
    sql += " ORDER BY u.name"
    rows=conn.execute(sql,params).fetchall()
    conn.close()
    return render_template("doctors.html", doctors=rows, q=q, selected_spec=spec)

@app.route("/book/<int:doctor_id>", methods=["GET","POST"])
@login_required("patient")
def book(doctor_id):
    conn = get_db()
    doctor = conn.execute("""
        SELECT u.id,u.name,dp.* FROM users u JOIN doctor_profiles dp ON dp.user_id=u.id
        WHERE u.id=? AND u.role='doctor' AND dp.verified=1
    """,(doctor_id,)).fetchone()
    if not doctor:
        conn.close()
        flash("Doctor not found or not verified.", "error")
        return redirect(url_for("doctors"))

    availability = conn.execute("""
        SELECT * FROM doctor_availability
        WHERE doctor_id=? AND available_date>=? ORDER BY available_date,start_time
    """,(doctor_id,date.today().isoformat())).fetchall()

    if request.method == "POST":
        appt_date=request.form.get("appointment_date","")
        appt_time=request.form.get("appointment_time","")
        reason=request.form.get("reason","").strip()

        try:
            chosen=date.fromisoformat(appt_date)
        except ValueError:
            chosen=None
        if not chosen or chosen < date.today():
            flash("Please select a valid future appointment date.", "error")
        elif not appt_time:
            flash("Please select an appointment time.", "error")
        else:
            slot=conn.execute("""
                SELECT 1 FROM doctor_availability
                WHERE doctor_id=? AND available_date=? AND start_time<=? AND end_time>?
            """,(doctor_id,appt_date,appt_time,appt_time)).fetchone()
            taken=conn.execute("""
                SELECT 1 FROM appointments WHERE doctor_id=? AND appointment_date=? AND appointment_time=? AND status='Booked'
            """,(doctor_id,appt_date,appt_time)).fetchone()
            if not slot:
                flash("That time is not in the doctor's available schedule.", "error")
            elif taken:
                flash("That appointment slot is already booked. Please choose another time.", "error")
            else:
                appointment_no=f"CC-{datetime.now().strftime('%Y%m%d')}-{datetime.now().strftime('%H%M%S')}-{session['user_id']}"
                conn.execute("""
                    INSERT INTO appointments(appointment_no,patient_id,doctor_id,appointment_date,appointment_time,reason,status,created_at)
                    VALUES(?,?,?,?,?,?,?,?)
                """,(appointment_no,session["user_id"],doctor_id,appt_date,appt_time,reason,"Booked",
                    datetime.now().isoformat(timespec="seconds")))
                conn.commit()
                conn.execute(
                    "INSERT INTO notifications(user_id,channel,title,message,created_at) VALUES(?,?,?,?,?)",
                    (session["user_id"],"system","Appointment booked",
                     f"Appointment {appointment_no} booked with {doctor['name']} on {appt_date} at {appt_time}.",
                     datetime.now().isoformat(timespec="seconds")))
                conn.commit()
                conn.close()
                flash(f"Appointment booked successfully. Your appointment number is {appointment_no}.", "success")
                return redirect(url_for("patient_appointments"))
    conn.close()
    return render_template("book.html", doctor=doctor, availability=availability)

@app.route("/patient/appointments")
@login_required("patient")
def patient_appointments():
    conn=get_db()
    rows=conn.execute("""
        SELECT a.*,u.name AS doctor_name,dp.specialization,dp.hospital,dp.location
        FROM appointments a JOIN users u ON u.id=a.doctor_id
        JOIN doctor_profiles dp ON dp.user_id=u.id
        WHERE a.patient_id=? ORDER BY a.appointment_date DESC,a.appointment_time DESC
    """,(session["user_id"],)).fetchall()
    conn.close()
    return render_template("appointments.html", appointments=rows, patient=True)

@app.post("/patient/appointments/<int:appointment_id>/cancel")
@login_required("patient")
def cancel_appointment(appointment_id):
    conn=get_db()
    row=conn.execute("SELECT * FROM appointments WHERE id=? AND patient_id=?",(appointment_id,session["user_id"])).fetchone()
    if not row:
        conn.close(); flash("Appointment not found.","error"); return redirect(url_for("patient_appointments"))
    conn.execute("UPDATE appointments SET status='Cancelled' WHERE id=?",(appointment_id,))
    conn.commit(); conn.close()
    flash("Appointment cancelled.","success")
    return redirect(url_for("patient_appointments"))

@app.route("/patient/prescriptions")
@login_required("patient")
def patient_prescriptions():
    conn=get_db()
    rows=conn.execute("""
        SELECT p.*,u.name AS doctor_name,dp.specialization
        FROM prescriptions p JOIN users u ON u.id=p.doctor_id
        JOIN doctor_profiles dp ON dp.user_id=u.id
        WHERE p.patient_id=? ORDER BY p.created_at DESC
    """,(session["user_id"],)).fetchall()
    conn.close()
    return render_template("prescriptions.html", prescriptions=rows, patient=True)

@app.route("/patient/reminders")
@login_required("patient")
def reminders():
    conn=get_db()
    rows=conn.execute("""
        SELECT p.*,u.name AS doctor_name
        FROM prescriptions p JOIN users u ON u.id=p.doctor_id
        WHERE p.patient_id=? ORDER BY p.start_date DESC
    """,(session["user_id"],)).fetchall()
    conn.close()
    return render_template("reminders.html", prescriptions=rows)

@app.route("/doctor/dashboard")
@login_required("doctor")
def doctor_dashboard():
    conn=get_db()
    profile=conn.execute("""
        SELECT u.name,u.email,u.phone,dp.* FROM users u JOIN doctor_profiles dp ON dp.user_id=u.id WHERE u.id=?
    """,(session["user_id"],)).fetchone()
    stats={
        "appointments":conn.execute("SELECT COUNT(*) c FROM appointments WHERE doctor_id=?",(session["user_id"],)).fetchone()["c"],
        "today":conn.execute("SELECT COUNT(*) c FROM appointments WHERE doctor_id=? AND appointment_date=? AND status='Booked'",(session["user_id"],date.today().isoformat())).fetchone()["c"],
        "patients":conn.execute("SELECT COUNT(DISTINCT patient_id) c FROM appointments WHERE doctor_id=?",(session["user_id"],)).fetchone()["c"],
        "prescriptions":conn.execute("SELECT COUNT(*) c FROM prescriptions WHERE doctor_id=?",(session["user_id"],)).fetchone()["c"]
    }
    upcoming=conn.execute("""
        SELECT a.*,u.name AS patient_name,u.phone AS patient_phone
        FROM appointments a JOIN users u ON u.id=a.patient_id
        WHERE a.doctor_id=? AND a.status='Booked'
        ORDER BY a.appointment_date,a.appointment_time LIMIT 8
    """,(session["user_id"],)).fetchall()
    conn.close()
    return render_template("doctor_dashboard.html", profile=profile, stats=stats, upcoming=upcoming)

@app.route("/doctor/profile", methods=["GET","POST"])
@login_required("doctor")
def doctor_profile():
    conn=get_db()
    if request.method=="POST":
        hospital=request.form.get("hospital","").strip()
        location=request.form.get("location","").strip()
        bio=request.form.get("bio","").strip()
        qualification=request.form.get("qualification","").strip()
        if not hospital or not location or not qualification:
            flash("Hospital, location and qualification are required.","error")
        else:
            conn.execute("""UPDATE doctor_profiles SET hospital=?,location=?,bio=?,qualification=? WHERE user_id=?""",
                         (hospital,location,bio,qualification,session["user_id"]))
            conn.commit()
            flash("Profile updated successfully.","success")
    profile=conn.execute("""
        SELECT u.name,u.email,u.phone,dp.* FROM users u JOIN doctor_profiles dp ON dp.user_id=u.id WHERE u.id=?
    """,(session["user_id"],)).fetchone()
    conn.close()
    return render_template("doctor_profile.html", profile=profile)

@app.route("/doctor/availability", methods=["GET","POST"])
@login_required("doctor")
def availability():
    conn=get_db()
    if request.method=="POST":
        available_date=request.form.get("available_date","")
        start=request.form.get("start_time","")
        end=request.form.get("end_time","")
        try:
            d=date.fromisoformat(available_date)
        except ValueError:
            d=None
        if not d or d < date.today():
            flash("Please choose today or a future date.","error")
        elif not start or not end or start >= end:
            flash("Please enter a valid start and end time.","error")
        else:
            try:
                conn.execute("""INSERT INTO doctor_availability(doctor_id,available_date,start_time,end_time)
                                VALUES(?,?,?,?)""",(session["user_id"],available_date,start,end))
                conn.commit(); flash("Availability added.","success")
            except sqlite3.IntegrityError:
                flash("This availability slot already exists.","error")
    rows=conn.execute("""SELECT * FROM doctor_availability WHERE doctor_id=? AND available_date>=?
                         ORDER BY available_date,start_time""",(session["user_id"],date.today().isoformat())).fetchall()
    conn.close()
    return render_template("availability.html", availability=rows)

@app.post("/doctor/availability/<int:item_id>/delete")
@login_required("doctor")
def delete_availability(item_id):
    conn=get_db()
    conn.execute("DELETE FROM doctor_availability WHERE id=? AND doctor_id=?",(item_id,session["user_id"]))
    conn.commit(); conn.close()
    flash("Availability removed.","success")
    return redirect(url_for("availability"))

@app.route("/doctor/appointments")
@login_required("doctor")
def doctor_appointments():
    conn=get_db()
    rows=conn.execute("""
        SELECT a.*,u.name AS patient_name,u.email AS patient_email,u.phone AS patient_phone
        FROM appointments a JOIN users u ON u.id=a.patient_id
        WHERE a.doctor_id=? ORDER BY a.appointment_date DESC,a.appointment_time DESC
    """,(session["user_id"],)).fetchall()
    conn.close()
    return render_template("appointments.html", appointments=rows, patient=False)

@app.post("/doctor/appointments/<int:appointment_id>/status")
@login_required("doctor")
def appointment_status(appointment_id):
    status=request.form.get("status","Booked")
    if status not in ("Booked","Completed","Cancelled"):
        flash("Invalid appointment status.","error")
        return redirect(url_for("doctor_appointments"))
    conn=get_db()
    conn.execute("UPDATE appointments SET status=? WHERE id=? AND doctor_id=?",(status,appointment_id,session["user_id"]))
    conn.commit(); conn.close()
    flash("Appointment status updated.","success")
    return redirect(url_for("doctor_appointments"))

@app.route("/doctor/prescriptions", methods=["GET","POST"])
@login_required("doctor")
def doctor_prescriptions():
    conn=get_db()
    if request.method=="POST":
        patient_id=request.form.get("patient_id","")
        appointment_id=request.form.get("appointment_id") or None
        diagnosis=request.form.get("diagnosis","").strip()
        medicines=request.form.get("medicines","").strip()
        instructions=request.form.get("instructions","").strip()
        try:
            duration=int(request.form.get("duration_days","1"))
        except ValueError:
            duration=0
        start_date=request.form.get("start_date","")
        if not patient_id or not medicines or duration < 1 or not start_date:
            flash("Patient, medicine, duration and start date are required.","error")
        else:
            valid_patient=conn.execute("SELECT id FROM users WHERE id=? AND role='patient'",(patient_id,)).fetchone()
            if not valid_patient:
                flash("Selected patient is invalid.","error")
            else:
                conn.execute("""INSERT INTO prescriptions
                    (appointment_id,patient_id,doctor_id,diagnosis,medicines,instructions,duration_days,start_date,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (appointment_id,patient_id,session["user_id"],diagnosis,medicines,instructions,duration,start_date,
                     datetime.now().isoformat(timespec="seconds")))
                conn.execute("""INSERT INTO notifications(user_id,channel,title,message,created_at)
                                VALUES(?,?,?,?,?)""",
                             (patient_id,"system","New prescription",
                              f"A prescription from Dr. {session['name']} is available in your CareConnect account.",
                              datetime.now().isoformat(timespec="seconds")))
                conn.commit()
                flash("Prescription added successfully.","success")
    patients=conn.execute("""
        SELECT DISTINCT u.id,u.name,u.phone FROM users u
        JOIN appointments a ON a.patient_id=u.id
        WHERE a.doctor_id=? AND u.role='patient' ORDER BY u.name
    """,(session["user_id"],)).fetchall()
    prescriptions=conn.execute("""
        SELECT p.*,u.name AS patient_name FROM prescriptions p JOIN users u ON u.id=p.patient_id
        WHERE p.doctor_id=? ORDER BY p.created_at DESC
    """,(session["user_id"],)).fetchall()
    appointments=conn.execute("""
        SELECT id,appointment_no,patient_id,appointment_date,appointment_time
        FROM appointments WHERE doctor_id=? ORDER BY appointment_date DESC LIMIT 50
    """,(session["user_id"],)).fetchall()
    conn.close()
    return render_template("doctor_prescriptions.html", patients=patients,prescriptions=prescriptions,appointments=appointments)

@app.route("/admin/dashboard")
@login_required("admin")
def admin_dashboard():
    conn=get_db()
    stats={
        "patients":conn.execute("SELECT COUNT(*) c FROM users WHERE role='patient'").fetchone()["c"],
        "doctors":conn.execute("SELECT COUNT(*) c FROM users WHERE role='doctor'").fetchone()["c"],
        "pending":conn.execute("SELECT COUNT(*) c FROM doctor_profiles WHERE verified=0").fetchone()["c"],
        "appointments":conn.execute("SELECT COUNT(*) c FROM appointments").fetchone()["c"]
    }
    conn.close()
    return render_template("admin_dashboard.html",stats=stats)

@app.route("/admin/doctors")
@login_required("admin")
def admin_doctors():
    status=request.args.get("status","pending")
    conn=get_db()
    if status=="verified":
        rows=conn.execute("""SELECT u.*,dp.specialization,dp.qualification,dp.experience,dp.hospital,dp.location,dp.license_no,dp.verified
                             FROM users u JOIN doctor_profiles dp ON dp.user_id=u.id
                             WHERE u.role='doctor' AND dp.verified=1 ORDER BY u.created_at DESC""").fetchall()
    else:
        rows=conn.execute("""SELECT u.*,dp.specialization,dp.qualification,dp.experience,dp.hospital,dp.location,dp.license_no,dp.verified
                             FROM users u JOIN doctor_profiles dp ON dp.user_id=u.id
                             WHERE u.role='doctor' AND dp.verified=0 ORDER BY u.created_at DESC""").fetchall()
    conn.close()
    return render_template("admin_doctors.html", doctors=rows,status=status)

@app.post("/admin/doctors/<int:doctor_id>/verify")
@login_required("admin")
def verify_doctor(doctor_id):
    action=request.form.get("action")
    conn=get_db()
    doctor=conn.execute("SELECT id,name FROM users WHERE id=? AND role='doctor'",(doctor_id,)).fetchone()
    if not doctor:
        conn.close(); flash("Doctor not found.","error"); return redirect(url_for("admin_doctors"))
    if action=="approve":
        conn.execute("UPDATE doctor_profiles SET verified=1 WHERE user_id=?",(doctor_id,))
        msg="Your CareConnect doctor account has been approved by admin."
        title="Doctor account approved"
        flash("Doctor approved successfully.","success")
    elif action=="reject":
        conn.execute("DELETE FROM doctor_profiles WHERE user_id=?",(doctor_id,))
        conn.execute("DELETE FROM users WHERE id=? AND role='doctor'",(doctor_id,))
        conn.commit(); conn.close()
        flash("Doctor application rejected and removed.","success")
        return redirect(url_for("admin_doctors"))
    else:
        conn.close(); flash("Invalid verification action.","error"); return redirect(url_for("admin_doctors"))
    conn.execute("INSERT INTO notifications(user_id,channel,title,message,created_at) VALUES(?,?,?,?,?)",
                 (doctor_id,"system",title,msg,datetime.now().isoformat(timespec="seconds")))
    conn.commit(); conn.close()
    return redirect(url_for("admin_doctors"))

@app.route("/admin/users")
@login_required("admin")
def admin_users():
    conn=get_db()
    users=conn.execute("""SELECT id,role,name,email,phone,created_at FROM users
                          WHERE role!='admin' ORDER BY created_at DESC""").fetchall()
    conn.close()
    return render_template("admin_users.html",users=users)

@app.post("/admin/users/<int:user_id>/delete")
@login_required("admin")
def delete_user(user_id):
    conn=get_db()
    if user_id == session["user_id"]:
        conn.close(); flash("Admin account cannot be deleted from this page.","error")
        return redirect(url_for("admin_users"))
    conn.execute("DELETE FROM users WHERE id=? AND role!='admin'",(user_id,))
    conn.commit(); conn.close()
    flash("User removed.","success")
    return redirect(url_for("admin_users"))

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/api/check-email")
def check_email():
    email=request.args.get("email","").strip().lower()
    conn=get_db()
    row=conn.execute("SELECT id FROM users WHERE lower(email)=lower(?)",(email,)).fetchone()
    conn.close()
    return jsonify({"available": row is None})

@app.route("/api/check-phone")
def check_phone():
    phone=request.args.get("phone","").strip()
    conn=get_db()
    row=conn.execute("SELECT id FROM users WHERE phone=?",(phone,)).fetchone()
    conn.close()
    return jsonify({"available": row is None})

@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, message="The page you requested was not found."),404

@app.errorhandler(500)
def server_error(_):
    return render_template("error.html", code=500, message="Something went wrong. Please return to the home page and try again."),500

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
