# CareConnect Complete

A complete Flask + SQLite healthcare management website for a college project/demo.

## Features
- Home page
- Patient registration/login/dashboard
- Doctor registration/login/dashboard/profile/availability/appointments/prescriptions
- Admin login/dashboard
- Doctor verification: approve/reject
- User management
- Doctor search
- Appointment booking with slot availability
- Patient appointment history
- Patient prescription list
- Medicine reminders
- Duplicate email/phone validation
- Friendly popup messages for errors/success
- Password hashing
- SQLite database created automatically
- No XAMPP required

## Run on Windows PowerShell

```powershell
cd CareConnect_Complete
py -3.12 -m venv venv
.env\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Open:
http://127.0.0.1:5000

## Default admin
Email: admin@careconnect.com
Password: Admin@123

The first run creates `careconnect.db` and sample doctors.

## Important
Email/SMS notification buttons in this college-project version are recorded as notification events in the database. Real email/SMS delivery requires authenticated third-party services and credentials. Do not put real API keys in source code.
