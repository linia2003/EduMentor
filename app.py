from flask import Flask, render_template, request, redirect, session, flash, url_for
import mysql.connector

app = Flask(__name__)
app.secret_key = 'super_secret_key'  # Required for session management

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
        subject_id = request.form['subject']
        mentor_id = request.form['mentor']
        duration = request.form['duration']
        
        insert_query = """
            INSERT INTO StudyLog (student_id, subject_id, mentor_id, duration_hours)
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(insert_query, (session['user_id'], subject_id, mentor_id, duration))
        conn.commit()
        
        cursor.close()
        conn.close()
        return redirect(url_for('dashboard'))

    cursor.execute("SELECT * FROM Subjects")
    subjects = cursor.fetchall()
    
    cursor.execute("SELECT * FROM Mentors")
    mentors = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('log_study.html', subjects=subjects, mentors=mentors)

# --- SYSTEM VIEW: Subjects, Mentors & Analytics ---
@app.route('/subjects')
def subjects():
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