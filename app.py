from flask import Flask, render_template, request, redirect, session, flash, url_for, jsonify
import mysql.connector
import json
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'super_secret_key'  # Required for session management

# --- System Configuration ---
DEVELOPER_PIN = "1234" 

# --- XAMPP Database Connection Configuration ---
db_config = {
    'user': 'root',
    'password': '',       # Default XAMPP password is empty
    'host': 'localhost',
    'database': 'edumentor_db'
}

# --- Helper Function to Connect to DB ---
def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except mysql.connector.Error as err:
        print(f"Error connecting to database: {err}")
        return None

# --- NEW HELPER: Progress Calculation ---
def update_student_progress(student_id, subject_id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            # Calls the stored procedure to calculate and update progress for the given student/subject pair
            cursor.callproc('CalculateAndUpdateProgress', (student_id, subject_id))
            conn.commit()
        except mysql.connector.Error as err:
            print(f"Error calculating progress: {err}")
        finally:
            cursor.close()
            conn.close()

# --- Routes ---

@app.route('/')
def index():
    """ Renders the Homepage """
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """ Handles User Login for Students and Mentors """
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        role = request.form['role'] 

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if role == 'student':
            query = "SELECT * FROM Students WHERE email = %s AND password = %s"
        else:
            query = "SELECT * FROM Mentors WHERE email = %s AND password = %s"

        cursor.execute(query, (email, password))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user:
            # Note: For mentors, we still use 'user_id' but store their 'mentor_id'
            session['user_id'] = user['student_id'] if role == 'student' else user['mentor_id']
            session['name'] = user['name']
            session['role'] = role
            return redirect(url_for('dashboard'))
        else:
            flash('ACCESS DENIED: Invalid Credentials', 'error')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """ Handles New User Registration """
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        extra_info = request.form['extra_info'] 

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            if role == 'student':
                query = "INSERT INTO Students (name, email, password, semester) VALUES (%s, %s, %s, %s)"
                cursor.execute(query, (name, email, password, extra_info))
            else:
                query = "INSERT INTO Mentors (name, email, password, expertise_area) VALUES (%s, %s, %s, %s)"
                cursor.execute(query, (name, email, password, extra_info))
            
            conn.commit()
            flash('REGISTRATION SUCCESSFUL. PLEASE LOGIN.', 'success')
            return redirect(url_for('login'))
            
        except mysql.connector.Error as err:
            flash(f'Error: {err}', 'error')
            return redirect(url_for('register'))
        finally:
            cursor.close()
            conn.close()

    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    logs = []
    if session['role'] == 'student':
        # Student View: Fetch logs created BY this student
        query = """
            SELECT StudyLog.study_date, StudyLog.duration_hours, 
                   Subjects.subject_name, Mentors.name as mentor_name
            FROM StudyLog
            JOIN Subjects ON StudyLog.subject_id = Subjects.subject_id
            JOIN Mentors ON StudyLog.mentor_id = Mentors.mentor_id
            WHERE StudyLog.student_id = %s
            ORDER BY StudyLog.study_date DESC
        """
        cursor.execute(query, (session['user_id'],))
        logs = cursor.fetchall()
        
    elif session['role'] == 'mentor':
        # Mentor View: Fetch logs assigned TO this mentor
        query = """
            SELECT StudyLog.study_date, StudyLog.duration_hours, 
                   Subjects.subject_name, Students.name as student_name, Students.semester
            FROM StudyLog
            JOIN Subjects ON StudyLog.subject_id = Subjects.subject_id
            JOIN Students ON StudyLog.student_id = Students.student_id
            WHERE StudyLog.mentor_id = %s
            ORDER BY StudyLog.study_date DESC
        """
        cursor.execute(query, (session['user_id'],))
        logs = cursor.fetchall()


    cursor.close()
    conn.close()
    
    return render_template('dashboard.html', name=session['name'], role=session['role'], logs=logs)

@app.route('/log_study', methods=['GET', 'POST'])
def log_study():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        student_id = session['user_id']
        subject_id = request.form['subject']
        mentor_id = request.form['mentor']
        duration = request.form['duration']
        
        insert_query = """
            INSERT INTO StudyLog (student_id, subject_id, mentor_id, duration_hours)
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(insert_query, (student_id, subject_id, mentor_id, duration))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        # Call progress update after logging the session
        update_student_progress(student_id, subject_id)
        
        return redirect(url_for('dashboard'))

    cursor.execute("SELECT * FROM Subjects")
    subjects = cursor.fetchall()
    
    cursor.execute("SELECT * FROM Mentors")
    mentors = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('log_study.html', subjects=subjects, mentors=mentors)

# --- NEW ROUTE: Student Progress Page ---
@app.route('/progress')
def progress_report():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    report = []
    
    try:
        # Call the stored procedure to get the report
        cursor.callproc('GetStudentProgressReport', (student_id,))
        for result in cursor.stored_results():
            report = result.fetchall()
    except mysql.connector.Error as err:
        print(f"Error fetching progress report: {err}")
    finally:
        cursor.close()
        conn.close()

    return render_template('progress.html', report=report)

# --- NEW ROUTE: Dedicated Subject Analytics Page ---
@app.route('/subject_analytics/<int:subject_id>')
def subject_analytics(subject_id):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # --- 1. Fetch Subject Details ---
    cursor.execute("SELECT subject_id, subject_name, credits FROM Subjects WHERE subject_id = %s", (subject_id,))
    subject = cursor.fetchone()
    if not subject:
        cursor.close()
        conn.close()
        flash("Subject not found.", 'error')
        return redirect(url_for('progress_report'))

    # --- 2. Mentor Log Summary Query ---
    mentor_summary_query = """
        SELECT M.name AS mentor_name, SUM(SL.duration_hours) AS total_hours
        FROM StudyLog SL
        JOIN Mentors M ON SL.mentor_id = M.mentor_id
        WHERE SL.student_id = %s AND SL.subject_id = %s
        GROUP BY M.name
        ORDER BY total_hours DESC;
    """
    cursor.execute(mentor_summary_query, (student_id, subject_id))
    mentor_summary = cursor.fetchall()
    
    # --- 3. 30-Day Log Visualization Data ---
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=29)
    
    # Generate all dates in the range (for the X-axis)
    date_range = [start_date + timedelta(days=i) for i in range(30)]
    date_labels = [d.strftime('%m-%d') for d in date_range]
    
    # Fetch study hours logged for this subject in the last 30 days
    chart_query = """
        SELECT DATE(study_date) AS study_day, SUM(duration_hours) AS daily_hours
        FROM StudyLog
        WHERE student_id = %s AND subject_id = %s AND study_date >= %s
        GROUP BY study_day;
    """
    cursor.execute(chart_query, (student_id, subject_id, start_date))
    raw_chart_data = cursor.fetchall()
    
    # Map raw data to the 30-day date range
    hours_map = {item['study_day'].strftime('%m-%d'): float(item['daily_hours']) for item in raw_chart_data}
    chart_data_points = [hours_map.get(label, 0.0) for label in date_labels]

    chart_data = {
        'labels': json.dumps(date_labels),
        'data': json.dumps(chart_data_points)
    }

    cursor.close()
    conn.close()

    return render_template(
        'subject_analytics.html', 
        subject=subject, 
        mentor_summary=mentor_summary, 
        chart_data=chart_data
    )

# --- NEW FEATURE: Messaging Routes ---

@app.route('/messages', methods=['GET'])
def message_inbox():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    role = session['role']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Query to fetch all messages where the current user is the recipient
    inbox_query = """
        SELECT m.content, m.timestamp, m.sender_role, m.is_read,
               CASE 
                   WHEN m.sender_role = 'student' THEN S.name
                   ELSE T.name
               END AS sender_name
        FROM Messages m
        LEFT JOIN Students S ON m.sender_id = S.student_id AND m.sender_role = 'student'
        LEFT JOIN Mentors T ON m.sender_id = T.mentor_id AND m.sender_role = 'mentor'
        WHERE m.recipient_id = %s AND 
              (m.sender_role != %s OR m.sender_role = %s)
        ORDER BY m.timestamp DESC;
    """
    # Note: Logic assumes recipient_id stores the correct ID based on the user's current role.
    cursor.execute(inbox_query, (user_id, role, role))
    inbox = cursor.fetchall()

    # Query to fetch available contacts for sending new messages
    contacts = []
    if role == 'student':
        # Student contacts Mentors
        cursor.execute("SELECT mentor_id as id, name, expertise_area as info, 'mentor' as role FROM Mentors")
        contacts = cursor.fetchall()
    else:
        # Mentor contacts Students
        cursor.execute("SELECT student_id as id, name, semester as info, 'student' as role FROM Students")
        contacts = cursor.fetchall()

    cursor.close()
    conn.close()
    
    return render_template('messages.html', inbox=inbox, contacts=contacts, role=role)

@app.route('/send_message', methods=['POST'])
def send_message():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    sender_id = session['user_id']
    sender_role = session['role']
    recipient_id = request.form['recipient_id']
    content = request.form['content']
    recipient_role = request.form['recipient_role']
    
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        query = """
            INSERT INTO Messages (sender_id, recipient_id, sender_role, content, recipient_role) 
            VALUES (%s, %s, %s, %s, %s)
        """
        # NOTE: We need to modify the Messages table schema slightly to include recipient_role 
        # for a more robust sending process, but for now, we rely on the client form input.
        # Since recipient_role is inferred from the select box, we pass it.
        # (Using the contacts list logic for recipient_role determination)

        # For this simplified implementation, let's skip recipient_role and assume the recipient is 
        # the *other* role for now, or just use the existing Messages table structure.
        # Since the messages table doesn't have recipient_role, we insert using the 4 required fields:
        
        insert_query = "INSERT INTO Messages (sender_id, recipient_id, sender_role, content) VALUES (%s, %s, %s, %s)"
        cursor.execute(insert_query, (sender_id, recipient_id, sender_role, content))
        conn.commit()
        
        flash("Message sent successfully!", "success")
    except mysql.connector.Error as err:
        print(f"Error sending message: {err}")
        flash(f"Error sending message: {err}", "error")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('message_inbox'))


# --- System View PIN Entry ---
@app.route('/subjects_pin')
def subjects_pin():
    """ Renders the PIN entry form for System View access. """
    if session.get('sys_access'):
        return redirect(url_for('subjects'))
    return render_template('subjects_pin.html')

# --- SYSTEM VIEW: Subjects, Mentors & Analytics ---
@app.route('/subjects', methods=['GET', 'POST'])
def subjects():
    # 1. Check for valid session access flag (set after successful PIN entry)
    if not session.get('sys_access'):
        
        # If accessing via POST (submitting the PIN form)
        if request.method == 'POST':
            pin = request.form.get('pin')
            if pin == DEVELOPER_PIN:
                session['sys_access'] = True  # Grant access for the session
                # Continue to Step 2 (Database connection)
            else:
                flash('ACCESS DENIED: Invalid PIN', 'error')
                return redirect(url_for('subjects_pin'))
        
        # If accessing via GET and no access flag exists
        else:
            return redirect(url_for('subjects_pin'))

    # --- 2. Database connection (Only runs if session['sys_access'] is True) ---
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch Subjects
        cursor.execute("SELECT * FROM Subjects")
        subjects_data = cursor.fetchall()
        
        # 2. Fetch Mentors
        cursor.execute("SELECT * FROM Mentors")
        mentors_data = cursor.fetchall()

        # 3. Fetch Analytics
        try:
            cursor.execute("SELECT * FROM StudentStudySummary")
            analytics_data = cursor.fetchall()
        except mysql.connector.Error:
            analytics_data = [] 

        cursor.close()
        conn.close()
        return render_template('subjects.html', subjects=subjects_data, mentors=mentors_data, analytics=analytics_data)
    else:
        return "Database Connection Failed."

# --- ACTIONS: Add/Delete Mentor ---

@app.route('/add_mentor_action', methods=['POST'])
def add_mentor_action():
    if not session.get('sys_access'):
        flash('Permission Denied. Re-enter PIN.', 'error')
        return redirect(url_for('subjects_pin'))

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        expertise = request.form['expertise']

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.callproc('AddMentor', (name, email, password, expertise))
            conn.commit()
        except mysql.connector.Error as err:
            print(f"Error: {err}")
        finally:
            cursor.close()
            conn.close()

        return redirect(url_for('subjects'))

@app.route('/delete_mentor/<int:mentor_id>', methods=['POST'])
def delete_mentor(mentor_id):
    if not session.get('sys_access'):
        flash('Permission Denied. Re-enter PIN.', 'error')
        return redirect(url_for('subjects_pin'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.callproc('DeleteMentor', (mentor_id,))
        conn.commit()
    except mysql.connector.Error as err:
        print(f"Error deleting mentor: {err}")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('subjects'))

# --- ACTIONS: Add/Delete Subject ---

@app.route('/add_subject_action', methods=['POST'])
def add_subject_action():
    if not session.get('sys_access'):
        flash('Permission Denied. Re-enter PIN.', 'error')
        return redirect(url_for('subjects_pin'))

    if request.method == 'POST':
        subject_name = request.form['subject_name']
        credits = request.form['credits']

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.callproc('AddSubject', (subject_name, credits))
            conn.commit()
        except mysql.connector.Error as err:
            print(f"Error: {err}")
        finally:
            cursor.close()
            conn.close()

        return redirect(url_for('subjects'))

@app.route('/delete_subject/<int:subject_id>', methods=['POST'])
def delete_subject(subject_id):
    if not session.get('sys_access'):
        flash('Permission Denied. Re-enter PIN.', 'error')
        return redirect(url_for('subjects_pin'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.callproc('DeleteSubject', (subject_id,))
        conn.commit()
    except mysql.connector.Error as err:
        print(f"Error deleting subject: {err}")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('subjects'))

# --- FEEDBACK SYSTEM (New) ---

@app.route('/feedback')
def feedback():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    role = session['role']
    history = []
    students = []

    if role == 'mentor':
        # 1. Fetch list of all students for the dropdown
        cursor.execute("SELECT * FROM Students")
        students = cursor.fetchall()

        # 2. Fetch feedback history given BY this mentor (Using Stored Procedure)
        try:
            cursor.callproc('GetMentorFeedback', (session['user_id'],))
            for result in cursor.stored_results():
                history = result.fetchall()
        except mysql.connector.Error as err:
            print(f"Error fetching mentor feedback: {err}")

    else:
        # Student View: Fetch feedback received FOR this student
        query = """
            SELECT mf.comments, mf.feedback_date, m.name as mentor_name
            FROM MentorFeedback mf
            JOIN Mentors m ON mf.mentor_id = m.mentor_id
            WHERE mf.student_id = %s
            ORDER BY mf.feedback_date DESC
        """
        cursor.execute(query, (session['user_id'],))
        history = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('feedback.html', session_role=role, students=students, history=history)

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    if 'user_id' not in session or session['role'] != 'mentor':
        return redirect(url_for('login'))

    student_id = request.form['student_id']
    comments = request.form['comments']
    mentor_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        query = "INSERT INTO MentorFeedback (student_id, mentor_id, comments) VALUES (%s, %s, %s)"
        cursor.execute(query, (student_id, mentor_id, comments))
        conn.commit()
        flash("Feedback submitted successfully!", "success")
    except mysql.connector.Error as err:
        print(f"Error submitting feedback: {err}")
        flash("Error submitting feedback.", "error")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('feedback'))

if __name__ == '__main__':
    app.run(debug=True)