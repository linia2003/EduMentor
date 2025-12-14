EduMentor: A Learning Management System

EduMentor is a comprehensive learning management system designed to help students, mentors, and administrators stay organized and efficient. By centralizing study information, progress tracking, and feedback in one platform, EduMentor provides a seamless experience for everyone involved in the learning journey.

Whether you're a student looking to log your study hours, a mentor providing valuable feedback, or a developer overseeing system management, EduMentor has a feature for you.

Key Features
For Students:

Study Tracking: Log your study hours, track your progress, and see how much time you're dedicating to each subject.

Subject Analytics: View detailed visualizations of your study habits with the help of interactive charts.

Goal Management: Set academic goals, track your progress, and see whether you’ve met your targets with real-time updates.

Peer Communication: Stay connected with mentors and fellow students through messages to share updates and get feedback.

For Mentors:

Mentor Feedback: Provide structured feedback on student progress, helping students improve over time. Feedback is time-stamped for easy reference.

Progress Monitoring: Get detailed reports on each student’s performance, with insights on their study hours and achievements.

Goal Setting: Help students set achievable academic goals and monitor their progress as they work toward meeting them.

For Developers:

Subject Management: Add and manage subjects, ensuring an up-to-date list of courses for students and mentors to track.

Mentor Management: Add, update, and delete mentors within the system, ensuring that the right people are guiding students.

Global Analytics Report: View system-wide progress and trends across all students and subjects to assess overall learning activities.

Technologies Used:

Backend Framework: Python (Flask)

Database: MySQL

Frontend: HTML/CSS

Data Visualization: Chart.js for progress and study analytics

Security: Password hashing for secure user login

Tools: XAMPP (for local server management), VS Code (for development)

Database Design

EduMentor is built around key relational tables to track students, mentors, subjects, study sessions, and performance. Here's a quick overview:

Students: Stores details like student ID, name, semester, email, and password. It connects to study sessions, progress, mentor feedback, and academic goals.

Mentors: Holds information on mentors, including their expertise and login credentials. Mentors track student progress and provide feedback.

Subjects: Includes a list of subjects with credit hours. Students use it to log study hours, and mentors use it for feedback.

Study Sessions: Logs details about each study session, connecting students, mentors, and subjects.

Mentor Feedback: Records feedback from mentors on student performance.

Student Progress: Tracks each student’s academic progress by calculating percentage values for each subject.

Student Goals: Stores academic goals like target study hours and due dates, helping track progress.

Messages: Enables peer-to-peer communication between students and mentors.

