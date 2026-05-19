from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
from datetime import datetime, timedelta
import os
import random
import string
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'gym_secret_key'

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''  # Set your password if any
app.config['MYSQL_DB'] = 'gym_db'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

# Upload Configuration
UPLOAD_FOLDER = os.path.join('static', 'uploads', 'profiles')
MEDICAL_CERT_FOLDER = os.path.join('static', 'uploads', 'medical_certs')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MEDICAL_CERT_FOLDER'] = MEDICAL_CERT_FOLDER

# Ensure upload directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MEDICAL_CERT_FOLDER, exist_ok=True)

mysql = MySQL(app)


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_transaction_id():
    chars = string.ascii_uppercase + string.digits
    return f"FN-{''.join(random.choices(chars, k=4))}-{''.join(random.choices(chars, k=4))}"


# --- AUTH HELPERS ---
def is_logged_in():
    return 'user_id' in session


def is_admin():
    return session.get('role') == 'admin'


# =========================================
# PUBLIC ROUTES
# =========================================

@app.route("/")
def index():
    if is_logged_in():
        if is_admin():
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('user_dashboard'))
    return render_template("landing.html")


@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s", (request.form['username'],))
        user = cur.fetchone()
        cur.close()
        # FIX #4: Use check_password_hash for secure password comparison
        if user and check_password_hash(user['password'], request.form['password']):
            session.update({
                'user_id': user['id'],
                'username': user['username'],
                'role': user['role']
            })
            flash('Logged in!', 'success')
            return redirect(url_for('index'))
        flash('Invalid credentials', 'danger')
    return render_template("login.html")


@app.route("/register", methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        cur = mysql.connection.cursor()
        try:
            # FIX #4: Hash password before storing
            hashed_password = generate_password_hash(request.form['password'])
            cur.execute(
                "INSERT INTO users (username, password, role, full_name, email) "
                "VALUES (%s, %s, 'user', %s, %s)",
                (request.form['username'], hashed_password,
                 request.form['full_name'], request.form['email'])
            )
            mysql.connection.commit()
            flash('Registered successfully!', 'success')
            return redirect(url_for('login'))
        except Exception:
            flash('Username or email already taken.', 'danger')
        finally:
            cur.close()
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))


# =========================================
# USER ROUTES
# =========================================

@app.route("/user/dashboard")
def user_dashboard():
    if not is_logged_in():
        return redirect(url_for('login'))
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM plans")
    plans = cur.fetchall()
    cur.execute(
        "SELECT a.*, p.name as plan_name FROM applications a "
        "JOIN plans p ON a.plan_id = p.id WHERE a.user_id = %s",
        (session['user_id'],)
    )
    apps = cur.fetchall()
    cur.execute(
        "SELECT m.*, p.name as plan_name FROM memberships m "
        "JOIN plans p ON m.plan_id = p.id "
        "WHERE m.user_id = %s AND m.status IN ('active', 'frozen')",
        (session['user_id'],)
    )
    mem = cur.fetchone()
    
    freeze_req = None
    if mem:
        cur.execute(
            "SELECT * FROM freeze_requests WHERE membership_id = %s ORDER BY id DESC LIMIT 1",
            (mem['id'],)
        )
        freeze_req = cur.fetchone()
        
    cur.execute(
        "SELECT * FROM user_profiles WHERE user_id = %s",
        (session['user_id'],)
    )
    prof = cur.fetchone()
    cur.close()
    return render_template("user_dashboard.html", plans=plans,
                           applications=apps, active_membership=mem,
                           profile=prof, freeze_req=freeze_req)


@app.route("/user/profile", methods=['GET', 'POST'])
def user_profile():
    if not is_logged_in():
        return redirect(url_for('login'))
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        profile_pic_filename = None
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"user_{session['user_id']}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                profile_pic_filename = filename

        cur.execute("SELECT id FROM user_profiles WHERE user_id=%s", (session['user_id'],))
        if cur.fetchone():
            if profile_pic_filename:
                cur.execute(
                    "UPDATE user_profiles SET age=%s, gender=%s, height=%s, "
                    "weight=%s, health_goal=%s, profile_pic=%s WHERE user_id=%s",
                    (request.form['age'], request.form['gender'],
                     request.form['height'], request.form['weight'],
                     request.form['goal'], profile_pic_filename, session['user_id'])
                )
            else:
                cur.execute(
                    "UPDATE user_profiles SET age=%s, gender=%s, height=%s, "
                    "weight=%s, health_goal=%s WHERE user_id=%s",
                    (request.form['age'], request.form['gender'],
                     request.form['height'], request.form['weight'],
                     request.form['goal'], session['user_id'])
                )
        else:
            cur.execute(
                "INSERT INTO user_profiles "
                "(user_id, age, gender, height, weight, health_goal, profile_pic) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (session['user_id'], request.form['age'], request.form['gender'],
                 request.form['height'], request.form['weight'],
                 request.form['goal'], profile_pic_filename)
            )
        mysql.connection.commit()
        cur.close()
        flash('Profile updated!', 'success')
        return redirect(url_for('user_dashboard'))

    cur.execute("SELECT * FROM user_profiles WHERE user_id=%s", (session['user_id'],))
    prof = cur.fetchone()
    cur.close()
    return render_template("profile.html", profile=prof)


@app.route("/user/freeze", methods=['GET', 'POST'])
def request_freeze():
    if not is_logged_in():
        return redirect(url_for('login'))
        
    cur = mysql.connection.cursor()
    # Check if user has an active membership
    cur.execute(
        "SELECT id FROM memberships WHERE user_id = %s AND status = 'active'",
        (session['user_id'],)
    )
    mem = cur.fetchone()
    
    if not mem:
        flash('You do not have an active membership to freeze.', 'danger')
        cur.close()
        return redirect(url_for('user_dashboard'))
        
    if request.method == 'POST':
        reason = request.form['reason']
        cert_filename = None
        
        if 'medical_cert' in request.files:
            file = request.files['medical_cert']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"cert_{session['user_id']}_{file.filename}")
                file.save(os.path.join(app.config['MEDICAL_CERT_FOLDER'], filename))
                cert_filename = filename
                
        if not cert_filename:
            flash('Please upload a valid medical certificate or image of the injury (PNG, JPG, JPEG, GIF).', 'danger')
            cur.close()
            return redirect(request.url)
            
        cur.execute(
            "INSERT INTO freeze_requests (user_id, membership_id, reason, medical_certificate, status) "
            "VALUES (%s, %s, %s, %s, 'pending')",
            (session['user_id'], mem['id'], reason, cert_filename)
        )
        mysql.connection.commit()
        flash('Membership freeze request submitted successfully. Waiting for admin approval.', 'success')
        cur.close()
        return redirect(url_for('user_dashboard'))
        
    cur.close()
    return render_template("freeze.html")


@app.route("/apply/<int:plan_id>", methods=['GET', 'POST'])
def apply(plan_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        payment_method = request.form['payment_method']
        cur.execute("SELECT price FROM plans WHERE id=%s", (plan_id,))
        p = cur.fetchone()
        tx_id = generate_transaction_id()

        if payment_method == 'Cash':
            cur.execute(
                "INSERT INTO applications (user_id, plan_id, status) VALUES (%s, %s, 'pending')",
                (session['user_id'], plan_id)
            )
            # FIX #1: payment_method values now match the expanded ENUM
            cur.execute(
                "INSERT INTO payments (user_id, plan_id, amount, payment_method, transaction_id) "
                "VALUES (%s,%s,%s,%s,%s)",
                (session['user_id'], plan_id, p['price'], payment_method, tx_id)
            )
            payment_id = cur.lastrowid
            mysql.connection.commit()
            cur.close()
            flash('Application submitted! Please present this receipt at the desk.', 'success')
            return redirect(url_for('receipt', payment_id=payment_id))
        else:
            # Online Payment: Automatic Approval
            cur.execute(
                "INSERT INTO applications (user_id, plan_id, status) VALUES (%s, %s, 'approved')",
                (session['user_id'], plan_id)
            )
            # FIX #1: GCash, PayPal, Card all stored as-is — matches new ENUM
            cur.execute(
                "INSERT INTO payments (user_id, plan_id, amount, payment_method, transaction_id) "
                "VALUES (%s,%s,%s,%s,%s)",
                (session['user_id'], plan_id, p['price'], payment_method, tx_id)
            )
            payment_id = cur.lastrowid

            # Calculate expiry and create membership
            cur.execute("SELECT duration_months FROM plans WHERE id=%s", (plan_id,))
            dur = cur.fetchone()['duration_months']
            exp = datetime.now().date() + timedelta(days=30 * dur)
            cur.execute(
                "INSERT INTO memberships (user_id, plan_id, start_date, expiry_date, status) "
                "VALUES (%s, %s, %s, %s, 'active')",
                (session['user_id'], plan_id, datetime.now().date(), exp)
            )
            mysql.connection.commit()
            cur.close()
            flash(f'Payment via {payment_method} successful! Your membership is now active.', 'success')
            return redirect(url_for('receipt', payment_id=payment_id))

    cur.execute("SELECT * FROM plans WHERE id=%s", (plan_id,))
    plan = cur.fetchone()
    cur.close()
    return render_template("apply.html", plan=plan)


@app.route("/receipt/<int:payment_id>")
def receipt(payment_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT p.*, u.full_name, u.email, pl.name as plan_name, pl.description as plan_desc
        FROM payments p
        JOIN users u ON p.user_id = u.id
        JOIN plans pl ON p.plan_id = pl.id
        WHERE p.id = %s AND p.user_id = %s
    """, (payment_id, session['user_id']))
    pay = cur.fetchone()
    cur.close()
    if not pay:
        flash('Receipt not found.', 'danger')
        return redirect(url_for('user_dashboard'))
    return render_template("receipt.html", payment=pay)


# =========================================
# ADMIN ROUTES
# =========================================

@app.route("/admin/dashboard")
def admin_dashboard():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) as count FROM users WHERE role='user'")
    u = cur.fetchone()['count']
    cur.execute("SELECT COUNT(*) as count FROM applications WHERE status='pending'")
    a = cur.fetchone()['count']
    cur.execute("SELECT SUM(amount) as total FROM payments")
    r = cur.fetchone()['total'] or 0
    cur.close()
    return render_template("admin_dashboard.html", total_users=u,
                           pending_apps=a, total_revenue=r)


@app.route("/admin/plans")
def manage_plans():
    # FIX #6: Added missing auth check
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM plans")
    plans = cur.fetchall()
    cur.close()
    return render_template("manage_plans.html", plans=plans)


@app.route("/admin/plans/add", methods=['GET', 'POST'])
def add_plan():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    if request.method == 'POST':
        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO plans (name, description, price, duration_months) "
            "VALUES (%s, %s, %s, %s)",
            (request.form['name'], request.form['description'],
             request.form['price'], request.form['duration'])
        )
        mysql.connection.commit()
        cur.close()
        flash('Plan created successfully!', 'success')
        return redirect(url_for('manage_plans'))
    return render_template("add_plan.html")


@app.route("/admin/plans/delete/<int:id>")
def delete_plan(id):
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM plans WHERE id=%s", (id,))
    mysql.connection.commit()
    cur.close()
    flash('Plan deleted.', 'success')
    return redirect(url_for('manage_plans'))


@app.route("/admin/applications")
def view_applications():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT a.*, u.username, u.full_name, p.name as plan_name "
        "FROM applications a "
        "JOIN users u ON a.user_id=u.id "
        "JOIN plans p ON a.plan_id=p.id"
    )
    apps = cur.fetchall()
    cur.close()
    return render_template("view_applications.html", applications=apps)


@app.route("/admin/applications/update/<int:id>/<string:status>")
def update_application(id, status):
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    # Whitelist allowed statuses
    if status not in ('approved', 'rejected'):
        flash('Invalid status.', 'danger')
        return redirect(url_for('view_applications'))
    cur = mysql.connection.cursor()
    cur.execute("UPDATE applications SET status=%s WHERE id=%s", (status, id))
    if status == 'approved':
        cur.execute("SELECT user_id, plan_id FROM applications WHERE id=%s", (id,))
        app_d = cur.fetchone()
        cur.execute("SELECT duration_months FROM plans WHERE id=%s", (app_d['plan_id'],))
        dur = cur.fetchone()['duration_months']
        exp = datetime.now().date() + timedelta(days=30 * dur)
        cur.execute(
            "INSERT INTO memberships (user_id, plan_id, start_date, expiry_date, status) "
            "VALUES (%s, %s, %s, %s, 'active')",
            (app_d['user_id'], app_d['plan_id'], datetime.now().date(), exp)
        )
    mysql.connection.commit()
    cur.close()
    flash(f'Application {status}.', 'success')
    return redirect(url_for('view_applications'))


@app.route("/admin/payments")
def view_payments():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT p.*, u.full_name, pl.name as plan_name "
        "FROM payments p "
        "JOIN users u ON p.user_id=u.id "
        "JOIN plans pl ON p.plan_id=pl.id"
    )
    pays = cur.fetchall()
    cur.close()
    return render_template("view_payments.html", payments=pays)


@app.route("/admin/members")
def view_members():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))

    sort = request.args.get('sort', 'newest')

    # FIX #5: Whitelist dict prevents any unsanitized input reaching SQL
    sort_options = {
        'newest':      'u.id DESC',
        'oldest':      'u.id ASC',
        'name_asc':    'u.full_name ASC',
        'name_desc':   'u.full_name DESC',
        'expiry_asc':  'm.expiry_date ASC',
        'expiry_desc': 'm.expiry_date DESC',
        'plan':        'p.name ASC'
    }
    order_by = sort_options.get(sort, 'u.id DESC')

    cur = mysql.connection.cursor()
    cur.execute(f"""
        SELECT u.id, u.full_name, u.email, p.name as plan_name, m.expiry_date
        FROM users u
        LEFT JOIN memberships m ON u.id = m.user_id AND m.status = 'active'
        LEFT JOIN plans p ON m.plan_id = p.id
        WHERE u.role = 'user'
        ORDER BY {order_by}
    """)
    mems = cur.fetchall()
    cur.close()
    return render_template("view_member.html", members=mems, current_sort=sort)


@app.route("/admin/members/delete/<int:id>")
def delete_member(id):
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    cur = mysql.connection.cursor()
    # FIX #3: Role guard prevents accidental admin deletion
    cur.execute("DELETE FROM users WHERE id=%s AND role='user'", (id,))
    mysql.connection.commit()
    cur.close()
    flash('Member removed successfully!', 'success')
    return redirect(url_for('view_members'))


@app.route("/admin/freeze_requests")
def view_freeze_requests():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
        
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT f.*, u.full_name, u.email, m.expiry_date, p.name as plan_name
        FROM freeze_requests f
        JOIN users u ON f.user_id = u.id
        JOIN memberships m ON f.membership_id = m.id
        JOIN plans p ON m.plan_id = p.id
        ORDER BY f.request_date DESC
    """)
    requests = cur.fetchall()
    cur.close()
    return render_template("freeze.html", requests=requests)


@app.route("/admin/freeze/update/<int:id>/<string:action>")
def update_freeze_request(id, action):
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
        
    if action not in ('approve', 'reject', 'resume'):
        flash('Invalid action.', 'danger')
        return redirect(url_for('view_freeze_requests'))
        
    cur = mysql.connection.cursor()
    
    cur.execute("SELECT * FROM freeze_requests WHERE id=%s", (id,))
    req = cur.fetchone()
    
    if not req:
        flash('Request not found.', 'danger')
        cur.close()
        return redirect(url_for('view_freeze_requests'))
        
    if action == 'approve':
        # Change freeze request status
        cur.execute("UPDATE freeze_requests SET status='approved', frozen_date=NOW() WHERE id=%s", (id,))
        # Change membership status to frozen
        cur.execute("UPDATE memberships SET status='frozen' WHERE id=%s", (req['membership_id'],))
        flash('Freeze request approved. Membership is now frozen.', 'success')
        
    elif action == 'reject':
        cur.execute("UPDATE freeze_requests SET status='rejected' WHERE id=%s", (id,))
        flash('Freeze request rejected.', 'success')
        
    elif action == 'resume':
        if req['status'] != 'approved':
            flash('Cannot resume a request that is not approved.', 'danger')
        else:
            # Calculate days frozen
            cur.execute("SELECT DATEDIFF(NOW(), frozen_date) as days_frozen FROM freeze_requests WHERE id=%s", (id,))
            res = cur.fetchone()
            days_frozen = res['days_frozen'] if res['days_frozen'] is not None else 0
            
            # Extend expiry date and change membership status back to active
            cur.execute(
                "UPDATE memberships SET status='active', expiry_date = DATE_ADD(expiry_date, INTERVAL %s DAY) WHERE id=%s",
                (days_frozen, req['membership_id'])
            )
            cur.execute("UPDATE freeze_requests SET status='resumed' WHERE id=%s", (id,))
            flash(f'Membership resumed. Expiry extended by {days_frozen} days.', 'success')
            
    mysql.connection.commit()
    cur.close()
    return redirect(url_for('view_freeze_requests'))


if __name__ == "__main__":
    app.run(debug=True, port=5001)