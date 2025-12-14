from flask import Flask, render_template, request, redirect, session, flash, url_for, jsonify
import mysql.connector
import json
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'super_secret_key' # Required for session management

# --- System Configuration ---
DEVELOPER_PIN = "1234" 

# --- XAMPP Database Connection Configuration ---
db_config = {
    'user': 'root',
    'password': '', # Default XAMPP password is empty
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

# --- NEW HELPER: Send Automated Message (For Automated Praise) ---
def send_automated_message(sender_id, recipient_id, content):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            # Sender role is 'mentor' for automated praise
            insert_query = "INSERT INTO Messages (sender_id, recipient_id, sender_role, content) VALUES (%s, %s, 'mentor', %s)"
            cursor.execute(insert_query, (sender_id, recipient_id, content))
            conn.commit()
        except mysql.connector.Error as err:
            print(f"Error sending automated message: {err}")
        finally:
            cursor.close()
            conn.close()


# --- MODIFIED HELPER: Progress Calculation (A) ---
def update_student_progress(student_id, subject_id):
    conn = get_db_connection()
    mentor_id = None
    subject_name = None
    
    if conn:
        cursor = conn.cursor()
        try:
            # Calls the stored procedure to calculate and update progress for the given student/subject pair
            cursor.callproc('CalculateAndUpdateProgress', (student_id, subject_id))
            conn.commit()
            
            # After updating progress, check for goal completion (Automated Praise)
            # Use a dictionary cursor to fetch results clearly for debugging/use if needed
            dict_cursor = conn.cursor(dictionary=True)

            dict_cursor.execute("""
                SELECT sg.mentor_id, sub.subject_name 
                FROM SubjectGoals sg ON sp.student_id = sg.student_id AND sp.subject_id = sg.subject_id
                JOIN Subjects sub ON sg.subject_id = sub.subject_id
                WHERE sp.student_id = %s AND sp.subject_id = %s 
                AND sp.progress_percentage >= 100 AND sg.is_met = FALSE
                LIMIT 1
            """, (student_id, subject_id))
            
            goal_check_result = dict_cursor.fetchone()
            
            if goal_check_result:
                # Need to use the non-dict cursor for subsequent commands
                
                mentor_id = goal_check_result['mentor_id']
                subject_name = goal_check_result['subject_name']
                
                # 1. Update Goal Status to MET to prevent spamming
                update_goal_query = """
                    UPDATE SubjectGoals 
                    SET is_met = TRUE 
                    WHERE student_id = %s AND subject_id = %s AND is_met = FALSE
                """
                cursor.execute(update_goal_query, (student_id, subject_id))
                conn.commit()

                # 2. Fetch student name
                dict_cursor.execute("SELECT name FROM Students WHERE student_id = %s", (student_id,))
                student_name_result = dict_cursor.fetchone()
                
                if student_name_result:
                    student_name = student_name_result['name']

                    # 3. Send Automated Praise Message
                    if mentor_id and student_name:
                        content = f"⚡ SYSTEM ALERT: Progress Node {subject_name.upper()} Criticality Reached (100%+). Excellent Work, {student_name}!"
                        send_automated_message(mentor_id, student_id, content)

        except mysql.connector.Error as err:
            print(f"Error during progress update and goal check: {err}")
        finally:
            # Ensure all cursors are closed
            if 'dict_cursor' in locals() and dict_cursor:
                dict_cursor.close()
            if cursor:
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
        
        # NEW LINE: Fetch the major field
        major = request.form.get('major')

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            if role == 'student':
                # MODIFIED QUERY: Include 'major' column
                query = "INSERT INTO Students (name, email, password, semester, major) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(query, (name, email, password, extra_info, major)) # Add major to tuple
            else:
                query = "INSERT INTO Mentors (name, email, password, expertise_area) VALUES (%s, %s, %s, %s)"
                cursor.execute(query, (name, email, password, extra_info))
            
            conn.commit()
            flash('REGISTRATION SUCCESSFUL. PLEASE LOGIN.', 'success')
            return redirect(url_for('login'))
            
        except mysql.connector.Error as err:
            flash(f"Error: {err}", 'error')
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
    current_goal = None # Initialize new variable

    if session['role'] == 'student':
        student_id = session['user_id']
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
        cursor.execute(query, (student_id,))
        logs = cursor.fetchall()

        # --- NEW FEATURE: Fetch Most Pressing Goal ---
        goal_query = """
            SELECT sg.due_date, sg.target_hours, sub.subject_name
            FROM SubjectGoals sg
            JOIN Subjects sub ON sg.subject_id = sub.subject_id
            WHERE sg.student_id = %s AND sg.is_met = FALSE
            ORDER BY sg.due_date ASC
            LIMIT 1
        """
        cursor.execute(goal_query, (student_id,))
        goal_data = cursor.fetchone()

        if goal_data:
            current_goal = {
                'subject_name': goal_data['subject_name'],
                'target_hours': float(goal_data['target_hours']),
                'due_date': goal_data['due_date'].strftime('%Y-%m-%d'),
                # FIX APPLIED: Removed redundant .date() call on the datetime.date object
                'is_overdue': goal_data['due_date'] < datetime.now().date()
            }
        
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
    
    return render_template('dashboard.html', name=session['name'], role=session['role'], logs=logs, current_goal=current_goal)

@app.route('/log_study', methods=['GET', 'POST'])
def log_study():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    student_id = session['user_id']

    if request.method == 'POST':
        subject_id = request.form['subject']
        mentor_id = request.form['mentor']
        duration = request.form['duration']
        
        # ---------------------------------------------------------------------------------
        # --- MODIFIED: REMOVED INTEGRITY CHECK TO ALLOW LOGGING WITH ANY MENTOR/SUBJECT ---
        # ---------------------------------------------------------------------------------
        
        # The following lines originally checked mentor expertise against subject major
        # and would return an error if they didn't match. This check is now bypassed.
        
        # validation_query_simplified = ...
        # cursor.execute(validation_query_simplified, (mentor_id, subject_id))
        # ...
        # if not is_valid:
        #    flash('ERROR: The selected mentor is not assigned to this subject protocol.', 'error')
        #    cursor.close()
        #    conn.close()
        #    return redirect(url_for('log_study'))
        
        # --- END OF REMOVED INTEGRITY CHECK ---
        
        insert_query = """
            INSERT INTO StudyLog (student_id, subject_id, mentor_id, duration_hours)
            VALUES (%s, %s, %s, %s)
        """
        # Using non-dictionary cursor for execution consistency
        conn.cursor().execute(insert_query, (student_id, subject_id, mentor_id, duration))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        # Call progress update after logging the session
        update_student_progress(student_id, subject_id)
        
        return redirect(url_for('dashboard'))

    # GET Request: Filter Subjects by Student's Major

    # 1. Fetch student's major
    try:
        cursor.execute("SELECT major FROM Students WHERE student_id = %s", (student_id,))
        student_major_result = cursor.fetchone()
        student_major = student_major_result['major'] if student_major_result else 'General'
    except mysql.connector.Error:
        student_major = 'General'
    except TypeError:
        student_major = 'General'

    # 2. Fetch Subjects matching the major or marked as 'General'
    # FIX APPLIED: Corrected the subject filter to be broad and ensure all 122 subjects are visible.
    subject_query = """
        SELECT subject_id, subject_name 
        FROM Subjects 
        WHERE major_area = %s 
        OR major_area IN ('General', 'CSE', 'Database & Security', 'AI & Logic', 'Software Engineering', 'Algorithm Design')
        ORDER BY subject_name
    """
    cursor.execute(subject_query, (student_major,))
    subjects = cursor.fetchall()

    # 3. Fetch Mentors (still fetches all for selection)
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

    # --- 1B. FETCH METRICS ---
    total_hours_query = """
        SELECT SUM(duration_hours) AS total_logged 
        FROM StudyLog
        WHERE student_id = %s AND subject_id = %s;
    """
    cursor.execute(total_hours_query, (student_id, subject_id))
    total_logged_result = cursor.fetchone()
    
    progress_query = """
        SELECT progress_percentage 
        FROM StudentProgress
        WHERE student_id = %s AND subject_id = %s;
    """
    cursor.execute(progress_query, (student_id, subject_id))
    progress_result = cursor.fetchone()

    # Inject the new metrics into the subject dictionary
    subject['total_logged_hours'] = float(total_logged_result['total_logged']) if total_logged_result and total_logged_result['total_logged'] is not None else 0.0
    subject['progress_percentage'] = float(progress_result['progress_percentage']) if progress_result and progress_result['progress_percentage'] is not None else 0.0


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
    
    # --- 3. NEW: Fetch ALL Study Hours for ALL subjects (for allocation breakdown) ---
    allocation_query = """
        SELECT sub.subject_name, SUM(sl.duration_hours) AS total_hours
        FROM StudyLog sl
        JOIN Subjects sub ON sl.subject_id = sub.subject_id
        WHERE sl.student_id = %s
        GROUP BY sub.subject_name
        ORDER BY total_hours DESC;
    """
    cursor.execute(allocation_query, (student_id,))
    allocation_data_raw = cursor.fetchall()

    # Process data for JS rendering (labels and values for the pie chart)
    allocation_labels = json.dumps([item['subject_name'] for item in allocation_data_raw])
    allocation_data = json.dumps([float(item['total_hours']) for item in allocation_data_raw])


    cursor.close()
    conn.close()

    return render_template(
        'subject_analytics.html', 
        subject=subject, 
        mentor_summary=mentor_summary, 
        allocation_labels=allocation_labels,  # NEW
        allocation_data=allocation_data       # NEW
    )

# --- START NEW STUDENT GOALS ROUTE ---
@app.route('/student_goals')
def student_goals():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Fetch ALL goals (met and unmet) for the current student
    goals_query = """
        SELECT sg.goal_id, sg.student_id, sg.subject_id, m.name as mentor_name, sub.subject_name, sg.target_hours, sg.due_date, sg.is_met
        FROM SubjectGoals sg
        JOIN Mentors m ON sg.mentor_id = m.mentor_id
        JOIN Subjects sub ON sg.subject_id = sub.subject_id
        WHERE sg.student_id = %s
        ORDER BY sg.due_date DESC;
    """
    
    try:
        cursor.execute(goals_query, (student_id,))
        goals = cursor.fetchall()
        
        # Calculate progress for each goal (required for the view)
        for goal in goals:
            # Fetch Current Logged Hours 
            hours_query = "SELECT SUM(duration_hours) AS current_hours FROM StudyLog WHERE student_id = %s AND subject_id = %s"
            cursor.execute(hours_query, (goal['student_id'], goal['subject_id']))
            hours_result = cursor.fetchone()
            
            current_hours = float(hours_result['current_hours']) if hours_result and hours_result['current_hours'] is not None else 0.0
            target_hours = float(goal['target_hours'])

            # Inject current hours
            goal['current_hours'] = current_hours
            
            # DIRECT PROGRESS CALCULATION
            if target_hours > 0:
                calculated_percent = (current_hours / target_hours) * 100
                goal['progress_percent'] = min(calculated_percent, 100.0) 
            else:
                goal['progress_percent'] = 0.0

    except mysql.connector.Error as err:
        print(f"Error fetching student goals: {err}")
        goals = []
    
    cursor.close()
    conn.close()

    # Calculate today's date as a string for template comparison
    today_date = datetime.now().strftime('%Y-%m-%d')
    
    return render_template('student_goals.html', goals=goals, today_date=today_date) 
# --- END NEW STUDENT GOALS ROUTE ---

# --- NEW FEATURE: Automated Goal Setting Routes (For Mentors) ---

@app.route('/goals', methods=['GET', 'POST'])
def goals_management():
    if 'user_id' not in session or session['role'] != 'mentor':
        flash('Goal management is restricted to mentors.', 'error')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    mentor_id = session['user_id']
    
    if request.method == 'POST':
        student_id = request.form['student_id']
        subject_id = request.form['subject_id']
        target_hours = request.form['target_hours']
        due_date = request.form['due_date']
        
        try:
            # Call the stored procedure to add/update a goal
            cursor.callproc('AddSubjectGoal', (student_id, subject_id, mentor_id, target_hours, due_date))
            conn.commit()
            flash(f"Goal set/updated successfully for Student ID {student_id}.", 'success')
        except mysql.connector.Error as err:
            flash(f"Error setting goal: {err}", 'error')
        finally:
            cursor.close()
            conn.close()

        return redirect(url_for('goals_management'))

    # GET Request: Dynamic Filtering
    
    # 1. Fetch ALL students who have logged activity with this mentor (Associated Students)
    associated_students_query = """
        SELECT DISTINCT S.student_id, S.name, S.semester 
        FROM Students S
        JOIN StudyLog SL ON S.student_id = SL.student_id
        WHERE SL.mentor_id = %s;
    """
    cursor.execute(associated_students_query, (mentor_id,))
    students = cursor.fetchall()
    
    # Extract the IDs of the associated students for the next filter
    student_ids = [s['student_id'] for s in students]
    
    # 2. Fetch Subjects taken by *any* of the associated students (Filtered Subjects)
    if student_ids:
        # Construct a tuple of placeholders for the IN clause
        placeholders = ', '.join(['%s'] * len(student_ids))
        
        subject_filter_query = f"""
            SELECT DISTINCT sub.subject_id, sub.subject_name 
            FROM Subjects sub
            JOIN StudyLog sl ON sub.subject_id = sl.subject_id
            WHERE sl.student_id IN ({placeholders})
            ORDER BY sub.subject_name;
        """
        cursor.execute(subject_filter_query, tuple(student_ids))
        subjects = cursor.fetchall()
    else:
        subjects = [] # No associated students, no subjects to show

    # Fetch existing goals for the mentor's view (now shows ALL goals)
    goals_query = """
        SELECT sg.goal_id, sg.student_id, sg.subject_id, s.name as student_name, sub.subject_name, sg.target_hours, sg.due_date, sg.is_met
        FROM SubjectGoals sg
        JOIN Students s ON sg.student_id = s.student_id
        JOIN Subjects sub ON sg.subject_id = sub.subject_id
        WHERE sg.mentor_id = %s
        ORDER BY sg.due_date;
    """
    
    try:
        cursor.execute(goals_query, (mentor_id,))
        goals = cursor.fetchall()
        
        # --- NEW: Fetch CURRENT PROGRESS for EACH goal & Calculate Percentage in Python (Fix for 0.0% Error) ---
        for goal in goals:
            # Fetch Current Logged Hours (Hours must be fetched to calculate percentage)
            hours_query = "SELECT SUM(duration_hours) AS current_hours FROM StudyLog WHERE student_id = %s AND subject_id = %s"
            cursor.execute(hours_query, (goal['student_id'], goal['subject_id']))
            hours_result = cursor.fetchone()
            
            current_hours = float(hours_result['current_hours']) if hours_result and hours_result['current_hours'] is not None else 0.0
            target_hours = float(goal['target_hours'])

            # Inject current hours
            goal['current_hours'] = current_hours
            
            # DIRECT PROGRESS CALCULATION
            if target_hours > 0:
                calculated_percent = (current_hours / target_hours) * 100
                # Cap the display at 100% (the progress bar doesn't need to show 150%)
                goal['progress_percent'] = min(calculated_percent, 100.0) 
            else:
                goal['progress_percent'] = 0.0
            
    except mysql.connector.Error as err:
        goals = []
    
    cursor.close()
    conn.close()
    
    # Calculate today's date as a string for template comparison (FIX for UndefinedError)
    today_date = datetime.now().strftime('%Y-%m-%d')
    
    return render_template('goals.html', 
                           students=students, 
                           subjects=subjects, 
                           goals=goals,
                           today_date=today_date)

@app.route('/toggle_goal_met/<int:goal_id>', methods=['POST'])
def toggle_goal_met(goal_id):
    if 'user_id' not in session or session['role'] != 'mentor':
        flash('Permission Denied.', 'error')
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True) 
    mentor_id = session['user_id']
    
    try:
        # Step 1: Toggle the goal status
        toggle_query = """
            UPDATE SubjectGoals 
            SET is_met = CASE WHEN is_met = TRUE THEN FALSE ELSE TRUE END 
            WHERE goal_id = %s AND mentor_id = %s;
        """
        # Execute with non-dictionary cursor for the UPDATE
        conn.cursor().execute(toggle_query, (goal_id, mentor_id))
        conn.commit()
        
        # Step 2: Retrieve the necessary IDs (Use the dict cursor results)
        select_ids_query = "SELECT student_id, subject_id FROM SubjectGoals WHERE goal_id = %s"
        cursor.execute(select_ids_query, (goal_id,))
        goal_data = cursor.fetchone()
        
        # Step 3: Call the progress update helper
        if goal_data:
            # Explicitly pass the retrieved IDs using their dictionary keys
            update_student_progress(goal_data['student_id'], goal_data['subject_id'])
        
        flash('Goal status updated successfully.', 'success')
    
    except mysql.connector.Error as err:
        flash(f'Error toggling goal status: {err}', 'error')
    finally:
        # Close the dictionary cursor
        cursor.close()
        conn.close()
        
    return redirect(url_for('goals_management'))

# --- NEW MENTOR FEATURE: Student Feedback History View ---

@app.route('/mentor_feedback_history/<int:student_id>')
def mentor_feedback_history(student_id):
    # WARNING: This route is currently accessible only by mentors.
    # To use this for students, you must either remove the role check OR
    # implement a new student-specific goal history route/template.
    
    if 'user_id' not in session or session['role'] != 'mentor':
        flash('Permission Denied.', 'error')
        return redirect(url_for('login'))
        
    mentor_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # 1. Get the student's name for the page header
    cursor.execute("SELECT name FROM Students WHERE student_id = %s", (student_id,))
    student_name_result = cursor.fetchone()
    if not student_name_result:
        flash("Student not found.", 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('dashboard'))
        
    student_name = student_name_result['name']
    
    # 2. Fetch all feedback records given by the current mentor to this specific student
    feedback_query = """
        SELECT comments, rating, feedback_date 
        FROM MentorFeedback
        WHERE mentor_id = %s AND student_id = %s
        ORDER BY feedback_date DESC;
    """
    cursor.execute(feedback_query, (mentor_id, student_id))
    history = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('mentor_feedback_history.html', 
                           student_id=student_id,
                           student_name=student_name,
                           history=history)

# --- NEW MENTOR FEATURE: Subject Performance Overview Routes ---

@app.route('/mentor/subject_selector')
def subject_selector():
    if 'user_id' not in session or session['role'] != 'mentor':
        return redirect(url_for('login'))
        
    mentor_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    mentor_expertise_query = "SELECT expertise_area FROM Mentors WHERE mentor_id = %s"
    cursor.execute(mentor_expertise_query, (mentor_id,))
    expertise = cursor.fetchone()
    
    subjects = []
    if expertise:
        expertise_area = expertise['expertise_area']
        
        # Use StudyLog as the most reliable way to list subjects the mentor has experience with
        subjects_logged_query = """
            SELECT DISTINCT s.subject_id, s.subject_name, s.major_area, s.credits
            FROM Subjects s
            JOIN StudyLog sl ON s.subject_id = sl.subject_id
            WHERE sl.mentor_id = %s
            ORDER BY s.subject_name;
        """
        cursor.execute(subjects_logged_query, (mentor_id,))
        subjects = cursor.fetchall()

    cursor.close()
    conn.close()
    
    return render_template('mentor_subject_selector.html', subjects=subjects)

@app.route('/mentor/subject_performance_report/<int:subject_id>')
def subject_performance_report(subject_id):
    if 'user_id' not in session or session['role'] != 'mentor':
        return redirect(url_for('login'))
        
    mentor_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # 1. Get Subject Name and Credits
    cursor.execute("SELECT subject_name, credits FROM Subjects WHERE subject_id = %s", (subject_id,))
    subject_details = cursor.fetchone()
    if not subject_details:
        flash("Subject not found.", 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('subject_selector'))

    # 2. Fetch All Students associated with this mentor/subject and their progress
    student_report_query = """
        SELECT 
            S.student_id, 
            S.name AS student_name, 
            S.semester,
            SUM(SL.duration_hours) AS total_logged_hours,
            SP.progress_percentage
        FROM Students S
        JOIN StudyLog SL ON S.student_id = SL.student_id
        LEFT JOIN StudentProgress SP ON S.student_id = SP.student_id AND SP.subject_id = %s
        WHERE SL.subject_id = %s AND SL.mentor_id = %s
        GROUP BY S.student_id, S.name, S.semester, SP.progress_percentage
        ORDER BY S.name;
    """
    cursor.execute(student_report_query, (subject_id, subject_id, mentor_id))
    student_report = cursor.fetchall()
    
    # Process report to ensure total_logged_hours and percentage are floats (to handle potential NULLs safely)
    for student in student_report:
        student['total_logged_hours'] = float(student['total_logged_hours']) if student['total_logged_hours'] is not None else 0.0
        student['progress_percentage'] = float(student['progress_percentage']) if student['progress_percentage'] is not None else 0.0
    
    cursor.close()
    conn.close()
    
    return render_template('mentor_performance_report.html', 
                           subject=subject_details,
                           report=student_report)

# --- NEW FEATURE: Messaging Routes ---

@app.route('/messages', methods=['GET'])
def message_inbox():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    role = session['role']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # --- UPDATED INBOX QUERY ---
    # Fetch all messages where the current user is the recipient (user_id).
    # Use COALESCE to reliably retrieve the sender's name regardless of sender_role.
    inbox_query = """
        SELECT m.content, m.timestamp, m.sender_role, m.is_read, m.sender_id,
               COALESCE(S.name, T.name) AS sender_name
        FROM Messages m
        LEFT JOIN Students S ON m.sender_id = S.student_id AND m.sender_role = 'student'
        LEFT JOIN Mentors T ON m.sender_id = T.mentor_id AND m.sender_role = 'mentor'
        WHERE m.recipient_id = %s
        ORDER BY m.timestamp DESC;
    """
    # Pass only user_id to the query. The redundant role filtering is removed.
    cursor.execute(inbox_query, (user_id,))
    inbox = cursor.fetchall()

    # Query to fetch available contacts for sending new messages
    contacts = []
    if role == 'student':
        # STUDENT CONTACTS: FILTERED TO SHOW ONLY MENTORS WHOSE COURSES THE STUDENT IS TAKING
        student_mentor_filter_query = """
            SELECT DISTINCT
                M.mentor_id as id, 
                M.name, 
                M.expertise_area as info, 
                'mentor' as role 
            FROM Mentors M
            JOIN StudyLog SL ON M.mentor_id = SL.mentor_id
            WHERE SL.student_id = %s
            ORDER BY M.name;
        """
        # Note: For students, user_id is their student_id
        cursor.execute(student_mentor_filter_query, (user_id,))
        contacts = cursor.fetchall()
    else:
        # MENTOR CONTACTS: FILTERED TO SHOW ONLY STUDENTS LOGGING TIME WITH THIS MENTOR
        mentor_student_filter_query = """
            SELECT DISTINCT
                S.student_id as id, 
                S.name, 
                S.semester as info, 
                'student' as role 
            FROM Students S
            JOIN StudyLog SL ON S.student_id = SL.student_id
            WHERE SL.mentor_id = %s
            ORDER BY S.name;
        """
        # Note: For mentors, user_id is their mentor_id
        cursor.execute(mentor_student_filter_query, (user_id,))
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

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
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

# --- MODIFIED ROUTE: Mentor Reaction (B) ---
@app.route('/react_message', methods=['POST'])
def react_message():
    if 'user_id' not in session or session['role'] != 'mentor':
        return redirect(url_for('login'))

    sender_id = session['user_id'] # Mentor ID
    sender_role = session['role'] # 'mentor'
    
    recipient_id = request.form['original_sender_id'] 
    reaction_text = request.form['reaction']
    
    # MODIFICATION: Use reaction_text as content, and add an emoji for flair
    if reaction_text == 'Understood':
        content = f"✅ ACKNOWLEDGE: {reaction_text}"
    elif reaction_text == 'Good Progress':
        content = f"👍 Good Progress"
    elif reaction_text == 'Please Elaborate':
        content = f"🔄 REQUEST: {reaction_text}"
    # NEW VISUAL REACTIONS
    elif reaction_text == 'Neon Spark':
        content = f"✨ NEON SPARK! Great work."
    elif reaction_text == 'Cyber Thumbs':
        content = f"🦾 CYBER THUMBS UP!"
    else:
        content = reaction_text # Fallback

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        insert_query = "INSERT INTO Messages (sender_id, recipient_id, sender_role, content) VALUES (%s, %s, %s, %s)"
        cursor.execute(insert_query, (sender_id, recipient_id, sender_role, content))
        conn.commit()
        
        flash(f"Reaction '{reaction_text}' transmitted successfully!", "success")
    except mysql.connector.Error as err:
        print(f"Error sending reaction: {err}")
        flash(f"Error sending reaction: {err}", "error")
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

# --- SYSTEM ROUTE: Force Progress Recalculation Helper (No Route Decorator) ---
def force_update_all_progress():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # 1. Find all unique student-subject pairs in the StudyLog that need calculation
            query = "SELECT DISTINCT student_id, subject_id FROM StudyLog"
            cursor.execute(query)
            pairs = cursor.fetchall()
            
            # 2. Iterate and trigger the update for each pair
            for pair in pairs:
                # Call the existing update function for each pair
                # The helper itself handles connection closing.
                update_student_progress(pair['student_id'], pair['subject_id'])
            
            print(f"FORCED PROGRESS UPDATE COMPLETE for {len(pairs)} pairs.")
            return True
        except mysql.connector.Error as err:
            print(f"Error during forced progress update: {err}")
            return False
        finally:
            cursor.close()
            conn.close()

@app.route('/system/force_progress_recalc')
def force_recalc_route():
    # Use the same access check as the /subjects route
    if not session.get('sys_access'):
        # Allow access if the secret PIN is provided as a query param (e.g., /system/force_progress_recalc?pin=1234)
        if request.args.get('pin') == DEVELOPER_PIN:
            session['sys_access'] = True
        else:
            flash('ACCESS DENIED: PIN required for system maintenance.', 'error')
            return redirect(url_for('subjects_pin'))

    success = force_update_all_progress()
    
    if success:
        flash('SYSTEM ALERT: All student progress logs recalculated successfully.', 'success')
    else:
        flash('SYSTEM CRITICAL: Progress recalculation failed. Check console for database errors.', 'error')
        
    return redirect(url_for('subjects')) # Redirect back to the system view

# --- SYSTEM VIEW: Subjects, Mentors & Analytics ---
@app.route('/subjects', methods=['GET', 'POST'])
def subjects():
    # 1. Check for valid session access flag (set after successful PIN entry)
    if not session.get('sys_access'):
        
        # If accessing via POST (submitting the PIN form)
        if request.method == 'POST':
            pin = request.form.get('pin')
            if pin == DEVELOPER_PIN:
                session['sys_access'] = True # Grant access for the session
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
        return redirect(url_for('subjects_pin'))

    if request.method == 'POST':
        subject_name = request.form['subject_name']
        credits = request.form['credits']

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Note: This DDL call is incorrect in your schema as it doesn't take major_area.
            # However, inserting via SQL setup is the preferred method for the current task.
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

# --- FEEDBACK SYSTEM ---

@app.route('/feedback')
def feedback():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    role = session['role']
    history = []
    students = []
    mentor_id = session['user_id'] # Defined for mentor context

    if role == 'mentor':
        # --- MODIFIED QUERY: Fetch only associated students ---
        
        # 1. Fetch list of students who have logged study hours with this mentor
        associated_students_query = """
            SELECT DISTINCT
                S.student_id, 
                S.name, 
                S.semester 
            FROM Students S
            JOIN StudyLog SL ON S.student_id = SL.student_id
            WHERE SL.mentor_id = %s
            ORDER BY S.name;
        """
        cursor.execute(associated_students_query, (mentor_id,))
        students = cursor.fetchall()

        # 2. Fetch feedback history given BY this mentor (Using Stored Procedure)
        try:
            cursor.callproc('GetMentorFeedback', (mentor_id,))
            # Fetch the results from the stored procedure call
            for result in cursor.stored_results():
                history = result.fetchall()
        except mysql.connector.Error as err:
            print(f"Error fetching mentor feedback: {err}")

    else:
        # Student View: Fetch feedback received FOR this student (No Change)
        query = """
            SELECT mf.comments, mf.rating, mf.feedback_date, m.name as mentor_name
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
    rating = request.form['rating']
    comments = request.form['comments']
    mentor_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        query = "INSERT INTO MentorFeedback (student_id, mentor_id, rating, comments) VALUES (%s, %s, %s, %s)"
        cursor.execute(query, (student_id, mentor_id, rating, comments))
        conn.commit()
        flash("Progress Report submitted successfully!", "success")
    except mysql.connector.Error as err:
        print(f"Error submitting feedback: {err}")
        flash("Error submitting progress report.", "error")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('feedback'))

if __name__ == '__main__':
    app.run(debug=True)