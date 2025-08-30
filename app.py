from flask import Flask, render_template, request, redirect, flash, url_for, session, send_from_directory
import pandas as pd
import os
from werkzeug.utils import secure_filename
from datetime import datetime
from math import ceil

# ----- Config -----
app = Flask(__name__)
app.secret_key = "secret123"   # change to a stronger secret in production

UPLOAD_FOLDER = 'uploads'      # root uploads folder (served by /uploads/<path>)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DATA_FILE = 'records.csv'      # CSV file to store rows

# Simple login (change these if you want)
ADMIN_USER = "admin"
ADMIN_PASS = "1234"

# Fields (same labels you used)
form_fields = [
    # IDENTITY & CONTACT
    "Army No", "Rank", "Name", "Email Address", "Mobile Number", "Alternate Phone Number",
    "Permanent Address", "Correspondence Address", "CSD Card Number",

    # SERVICE DETAILS
    "Unit", "Unit Location", "WKSP",
    "Date of Enlistment", "Date of Commission", "Date of Promotion", "Present Appointment", "Enrolment Type", "Posting History", "Record Office", "Record Office Address",

    # QUALIFICATIONS & TRAINING
    "Educational Qualification", "Military Qualification", "Special Skills", "Courses Attended", "Languages Known",

    # DOCUMENTS & IDs
    "I-Card No", "Aadhar No", "PAN Card No", "Passport Number", "Driving License Number", "Driving License Expiry",

    # FAMILY & DEPENDENTS
    "Marital Status", "Spouse Name", "Spouse Occupation", "Number of Dependents", "Children Names", "Children Education",
    "Next of Kin Name", "Next of Kin Relationship", "Next of Kin Contact", "Dependents Address",

    # HEALTH & FITNESS
    "DOB", "Age", "Gender", "Blood Group", "Disability Status", "Medical Category",
    "Last Medical Examination Date", "Height (cm)", "Weight (kg)", "Body Marks",

    # BANK & FINANCE
    "Bank Name", "IFSC Code", "Account Number", "Account Holder Type", "Nominee Name",

    # LEAVE & AWARDS
    "Last Leave Availed", "Leave Balance", "Awards & Decorations", "Disciplinary Actions",

    # OTHER PERSONAL INFO
    "Religion", "Caste", "Category", "Hobbies/Interests", "Remarks",

    # Additional requested fields
    "Nearest Railway Station", "Pending Legal Cases", "Court/Disciplinary Proceedings Status"
]

extra_fields = ["PAN Upload Path", "Aadhar Upload Path", "Photo Upload Path", "Created On", "Last Modified"]
all_fields = form_fields + extra_fields

multi_entry_fields = [
    "Nearest Railway Station",
    "Pending Legal Cases",
    "Court/Disciplinary Proceedings Status",
    "Children Names",
    "Posting History"
]

ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'pdf'}

# --------------------

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def read_df():
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE, dtype=str).fillna('')
    else:
        df = pd.DataFrame(columns=all_fields)
    return df

def save_df(df):
    df.to_csv(DATA_FILE, index=False)

# --------- Auth helpers ----------
def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('user'):
            flash("Please login to continue.", "warning")
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapper

# ----- Routes -----
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username', '')
        p = request.form.get('password', '')
        if u == ADMIN_USER and p == ADMIN_PASS:
            session['user'] = u
            flash("Logged in successfully.", "success")
            return redirect(url_for('index'))
        else:
            flash("Invalid credentials.", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        entry = {}
        for field in form_fields:
            v = request.form.get(field, '')
            if field in multi_entry_fields:
                v = '; '.join([line.strip() for line in v.splitlines() if line.strip()])
            entry[field] = v

        # handle file uploads
        army_no_safe = secure_filename(entry.get("Army No") or datetime.now().strftime("%Y%m%d%H%M%S"))
        for doc_field, form_field in [("PAN Upload Path", "pan_file"), ("Aadhar Upload Path", "aadhar_file"), ("Photo Upload Path", "photo_file")]:
            f = request.files.get(form_field)
            if f and f.filename and allowed_file(f.filename):
                folder = os.path.join(app.config['UPLOAD_FOLDER'], army_no_safe)
                os.makedirs(folder, exist_ok=True)
                filename = datetime.now().strftime('%Y%m%d%H%M%S_') + secure_filename(f.filename)
                filepath = os.path.join(folder, filename)
                f.save(filepath)
                entry[doc_field] = filepath.replace('\\', '/')
            else:
                entry[doc_field] = ''

        entry["Created On"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry["Last Modified"] = ''

        df = read_df()
        df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True, sort=False)
        save_df(df)
        flash("✅ Entry saved successfully!", "success")
        return redirect(url_for('records'))

    return render_template('form.html', fields=form_fields, multi_entry_fields=multi_entry_fields)

@app.route('/records')
@login_required
def records():
    page = int(request.args.get('page', 1))
    per_page = 10
    df = read_df()
    total = len(df)
    pages = max(1, ceil(total / per_page))
    start = (page - 1) * per_page
    stop = start + per_page
    subset = df.iloc[start:stop]
    # send index values to template so we can reference rows by their CSV index
    rows = list(subset.reset_index().to_dict(orient='records'))
    return render_template('records.html', rows=rows, page=page, pages=pages)

@app.route('/edit/<int:idx>', methods=['GET', 'POST'])
@login_required
def edit(idx):
    df = read_df()
    if idx < 0 or idx >= len(df):
        flash("Record not found.", "danger")
        return redirect(url_for('records'))
    row = df.iloc[idx].to_dict()
    if request.method == 'POST':
        for field in form_fields:
            v = request.form.get(field, '')
            if field in multi_entry_fields:
                v = '; '.join([line.strip() for line in v.splitlines() if line.strip()])
            row[field] = v
        # handle file uploads (overwrite if provided)
        army_no_safe = secure_filename(row.get("Army No") or f"rec{idx}")
        for doc_field, form_field in [("PAN Upload Path", "pan_file"), ("Aadhar Upload Path", "aadhar_file"), ("Photo Upload Path", "photo_file")]:
            f = request.files.get(form_field)
            if f and f.filename and allowed_file(f.filename):
                folder = os.path.join(app.config['UPLOAD_FOLDER'], army_no_safe)
                os.makedirs(folder, exist_ok=True)
                filename = datetime.now().strftime('%Y%m%d%H%M%S_') + secure_filename(f.filename)
                filepath = os.path.join(folder, filename)
                f.save(filepath)
                row[doc_field] = filepath.replace('\\', '/')
        row["Last Modified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # write back
        for col in all_fields:
            df.at[idx, col] = row.get(col, '')
        save_df(df)
        flash("✏️ Record updated.", "success")
        return redirect(url_for('records'))
    # GET - show form with values
    return render_template('edit.html', row=row, idx=idx, fields=form_fields, multi_entry_fields=multi_entry_fields)

@app.route('/delete/<int:idx>', methods=['POST'])
@login_required
def delete(idx):
    df = read_df()
    if idx < 0 or idx >= len(df):
        flash("Record not found.", "danger")
        return redirect(url_for('records'))
    # Optionally, remove files - we will not delete uploaded files automatically to be safe
    df = df.drop(index=idx).reset_index(drop=True)
    save_df(df)
    flash("🗑 Record deleted.", "warning")
    return redirect(url_for('records'))

@app.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    # Serve files saved under uploads/ - Flask will ensure path is relative
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=False)

@app.route('/query', methods=['GET', 'POST'])
@login_required
def query():
    results = None
    keyword = ''
    if request.method == 'POST':
        keyword = request.form.get('keyword', '').strip().lower()
        if keyword:
            df = read_df()
            try:
                mask = df.apply(lambda row: row.astype(str).str.lower().str.contains(keyword).any(), axis=1)
                filtered = df[mask]
                results = filtered.reset_index().to_dict(orient='records')
            except Exception as e:
                flash(f"Error searching: {e}", "danger")
    return render_template('query.html', results=results, keyword=keyword)

if __name__ == '__main__':
    app.run(debug=True)
