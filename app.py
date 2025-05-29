from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_mysqldb import MySQL
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin
from werkzeug.utils import secure_filename
import os
import pandas as pd
from datetime import datetime, date
from flask import session
from flask_login import current_user
from flask_login import current_user
from werkzeug.utils import secure_filename
import os
import pandas as pd
from io import BytesIO
from flask import send_file
from flask_mail import Mail, Message
import matplotlib.pyplot as plt
import seaborn as sns
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Configure DB
app.config['MYSQL_HOST'] = 'switchback.proxy.rlwy.net'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'VcXCEDRJYLNkpokKHUfkdoodSwAvDAgD'
app.config['MYSQL_DB'] = 'railway'
app.config['MYSQL_PORT'] = 27240
app.config['UPLOAD_FOLDER'] = 'static/uploads'

mysql = MySQL(app)
login_manager = LoginManager(app)


# User class
class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", [user_id])
    user = cur.fetchone()
    cur.close()
    if user:
        return User(id=user[0], username=user[1], role=user[3])
    return None

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']  # In production, hash and check this

        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
        user = cur.fetchone()
        cur.close()

        if user:
            user_obj = User(id=user[0], username=user[1], role=user[3])
            login_user(user_obj)
            session['role'] = user[3]
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid login credentials')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    cur = mysql.connection.cursor()
    today = date.today().isoformat()
    cur.execute("SELECT COUNT(*) FROM sop_failures WHERE DATE(date_of_failure)=%s", (today,))
    daily_sop_count = cur.fetchone()[0]
    cur.close()
    return render_template('dashboard.html', username=current_user.username, role=current_user.role, daily_sop_count=daily_sop_count)

@app.route('/new_sop', methods=['GET', 'POST'])
@login_required
def new_sop():
    if request.method == 'POST':
        # Get form data
        order_number_suffix = request.form.get('order_number_suffix', '')
        order_number = f"BAR-SO0{order_number_suffix}"
        customer_name = request.form['customer_name']
        manager = request.form['manager']
        person = request.form['person']
        sop_failed = request.form['sop_failed']
        sop_action = request.form['sop_action']
        details = request.form['details']
        date_of_failure = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Image handling
        image_file = request.files['image']
        if image_file:
            filename = secure_filename(image_file.filename)
            image_file.save(os.path.join(app.static_folder, 'upload', filename))
            image_path = filename  # Store only the filename
        else:
            image_path = ''

        # Insert into MySQL
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO sop_failures (
                order_number, customer_name, manager_responsible,
                person_responsible, sop_failed, sop_action_failed,
                details, image_path, date_of_failure
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (order_number, customer_name, manager, person, sop_failed,
              sop_action, details, image_path))
        mysql.connection.commit()
        cur.close()

        flash('SOP Failure submitted successfully!')
        return redirect(url_for('dashboard'))

    # Dropdown options
    managers = ['Manager A', 'Manager B']
    sop_list = ['Wrong procedure', 'Missed step', 'Incorrect timing']
    action_list = ['Re-train staff', 'Update SOP', 'Increase supervision']

    return render_template('new_sop.html', managers=managers,
                           sop_list=sop_list, action_list=action_list)

@app.route('/view_sops')
@login_required
def view_sops():
    sop_filter = request.args.get('sop')
    cur = mysql.connection.cursor()
    if sop_filter:
        cur.execute("SELECT * FROM sop_failures WHERE sop_failed=%s ORDER BY date_of_failure DESC", (sop_filter,))
    else:
        cur.execute("SELECT * FROM sop_failures ORDER BY date_of_failure DESC")
    failures = cur.fetchall()
    cur.close()
    return render_template('view_sops.html', failures=failures, sop_filter=sop_filter)

def get_sop_by_id(id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM sop_failures WHERE id = %s", (id,))
    sop = cur.fetchone()
    cur.close()
    if sop:
        # Return as a dict for easier access in the template and update logic
        columns = ['id', 'order_number', 'customer_name', 'manager_responsible', 'person_responsible', 'sop_failed', 'sop_action_failed', 'details', 'image_path', 'date_of_failure']
        return dict(zip(columns, sop))
    return None

@app.route('/edit_sop/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_sop(id):
    sop = get_sop_by_id(id)
    if not sop:
        flash('SOP not found.')
        return redirect(url_for('view_sops'))
    if request.method == 'POST':
        # Update SOP with form data
        order_number = request.form['order_number']
        customer_name = request.form['customer_name']
        manager = request.form['manager']
        person = request.form['person']
        sop_failed = request.form['sop_failed']
        sop_action = request.form['sop_action']
        details = request.form['details']
        # Update in DB
        cur = mysql.connection.cursor()
        cur.execute("""
            UPDATE sop_failures
            SET order_number=%s, customer_name=%s, manager_responsible=%s,
                person_responsible=%s, sop_failed=%s, sop_action_failed=%s, details=%s
            WHERE id=%s
        """, (order_number, customer_name, manager, person, sop_failed, sop_action, details, id))
        mysql.connection.commit()
        cur.close()
        flash('SOP updated successfully!')
        return redirect(url_for('view_sops'))
    managers = ["Planning", "Embroidery", "Alterations", "Gifting", "Sublimation", "Display", "Warehouse", "Scheduling", "Production"]
    return render_template('edit_sop.html', sop=sop, managers=managers)
  
@app.route('/export_excel')
@login_required
def export_excel():
    cur = mysql.connection.cursor()
    cur.execute("SELECT order_number, customer_name, manager_responsible, person_responsible, sop_failed, sop_action_failed, details, date_of_failure FROM sop_failures")
    data = cur.fetchall()
    cur.close()

    # Convert to DataFrame
    df = pd.DataFrame(data, columns=[
        'Order Number', 'Customer Name', 'Manager Responsible',
        'Person Responsible', 'SOP Failed', 'Action Failed',
        'Details', 'Date of Failure'
    ])

    # Create Excel in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='SOP Failures')
    output.seek(0)

    return send_file(
        output,
        download_name="sop_failures.xlsx",
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
  
@app.route('/delete_sop/<int:id>', methods=['POST'])
@login_required
def delete_sop(id):
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM sop_failures WHERE id=%s", (id,))
    mysql.connection.commit()
    cur.close()
    return redirect(url_for('view_sops'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/ai_analysis')
@login_required
def ai_analysis():
    cur = mysql.connection.cursor()
    cur.execute("SELECT sop_failed, sop_action_failed, manager_responsible, person_responsible, date_of_failure FROM sop_failures")
    data = cur.fetchall()
    cur.close()

    import pandas as pd
    df = pd.DataFrame(data, columns=['SOP Failed', 'Action Failed', 'Manager', 'Person', 'Date'])

    if df.empty:
        return "No data for analysis."

    # Count most frequent SOP failures
    top_failures = df['SOP Failed'].value_counts().head(5)

    # Plot and save
    plt.figure(figsize=(8,5))
    sns.barplot(x=top_failures.values, y=top_failures.index, palette="Reds_r")
    plt.title("Top 5 Repeated SOP Failures")
    plt.xlabel("Occurrences")
    plt.ylabel("SOP Failed")
    
    graph_path = os.path.join("static", "ai_sop_failures.png")
    plt.tight_layout()
    plt.savefig(graph_path)
    plt.close()

    return render_template("ai_analysis.html", graph="ai_sop_failures.png")

@app.route('/sop_tiles')
@login_required
def sop_tiles():
    sop_titles = [
        "Delayed unpacking SOP",
        "Double Checking SOP",
        "Scheduling SOP",
        "Production stock to unpacking SOP"
    ]
    return render_template('sop_tiles.html', sop_titles=sop_titles)

if __name__ == '__main__':
    app.run(debug=True)
