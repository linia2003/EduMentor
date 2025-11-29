-- ==========================================
-- EDUMENTOR DATABASE SCHEMA
-- Concepts: Normalization (3NF), ACID, Integrity, Indexing
-- ==========================================

-- 1. DATABASE INITIALIZATION
CREATE DATABASE IF NOT EXISTS edumentor_db;
USE edumentor_db;

-- 2. TABLE DEFINITIONS (DDL)

-- Table: Students
-- Concepts: Entity Integrity (PK), Domain Integrity (NOT NULL, UNIQUE)
CREATE TABLE IF NOT EXISTS Students (
    student_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL, -- Indexed automatically for fast lookup
    password VARCHAR(255) NOT NULL,
    semester VARCHAR(50)
) ENGINE=InnoDB; -- Ensures ACID Compliance

-- Table: Mentors
-- Concepts: 3NF (Separated from Students to avoid redundancy)
CREATE TABLE IF NOT EXISTS Mentors (
    mentor_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    expertise_area VARCHAR(100)
) ENGINE=InnoDB;

-- Table: Subjects
-- Concepts: Atomic Values (1NF)
CREATE TABLE IF NOT EXISTS Subjects (
    subject_id INT AUTO_INCREMENT PRIMARY KEY,
    subject_name VARCHAR(100) NOT NULL,
    credits INT DEFAULT 3
) ENGINE=InnoDB;

-- Table: StudyLog
-- Concepts: Foreign Keys (Referential Integrity), Many-to-Many Resolution
CREATE TABLE IF NOT EXISTS StudyLog (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT,
    subject_id INT,
    mentor_id INT,
    duration_hours DECIMAL(4, 2) NOT NULL,
    study_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign Key Constraints
    FOREIGN KEY (student_id) REFERENCES Students(student_id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES Subjects(subject_id),
    FOREIGN KEY (mentor_id) REFERENCES Mentors(mentor_id),

    -- Indexing for Performance Optimization
    INDEX idx_study_date (study_date),
    INDEX idx_student_subject (student_id, subject_id)
) ENGINE=InnoDB;

-- Table: MentorFeedback
CREATE TABLE IF NOT EXISTS MentorFeedback (
    feedback_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT,
    mentor_id INT,
    comments TEXT,
    feedback_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (student_id) REFERENCES Students(student_id) ON DELETE CASCADE,
    FOREIGN KEY (mentor_id) REFERENCES Mentors(mentor_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Table: StudentProgress
-- Concepts: Domain Integrity (CHECK Constraint)
CREATE TABLE IF NOT EXISTS StudentProgress (
    progress_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT,
    subject_id INT,
    progress_percentage DECIMAL(5, 2),
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- Constraint: Progress must be valid percentage
    CONSTRAINT chk_progress_valid CHECK (progress_percentage BETWEEN 0 AND 100),
    
    FOREIGN KEY (student_id) REFERENCES Students(student_id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES Subjects(subject_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 3. VIRTUAL TABLES (VIEWS) 
-- Concept: Data Abstraction & Join Simplification

-- View: StudentStudySummary (Complex JOIN)
CREATE OR REPLACE VIEW StudentStudySummary AS
SELECT 
    s.student_id,
    s.name AS student_name,
    sub.subject_name,
    SUM(sl.duration_hours) AS total_study_hours
FROM Students s
JOIN StudyLog sl ON s.student_id = sl.student_id
JOIN Subjects sub ON sl.subject_id = sub.subject_id
GROUP BY s.student_id, sub.subject_id;

-- View: MentorFeedbackReport (Reporting Layer)
CREATE OR REPLACE VIEW MentorFeedbackReport AS
SELECT 
    mf.feedback_id,
    m.name AS mentor_name,
    s.name AS student_name,
    mf.comments,
    mf.feedback_date
FROM MentorFeedback mf
JOIN Mentors m ON mf.mentor_id = m.mentor_id
JOIN Students s ON mf.student_id = s.student_id;

-- 4. STORED PROCEDURES
-- Concept: Encapsulation & Logic Reuse

DELIMITER //

CREATE PROCEDURE GetStudentProgressReport(IN p_student_id INT)
BEGIN
    SELECT 
        s.name AS student_name,
        sub.subject_name,
        sp.progress_percentage,
        sp.last_updated
    FROM StudentProgress sp
    JOIN Students s ON sp.student_id = s.student_id
    JOIN Subjects sub ON sp.subject_id = sub.subject_id
    WHERE s.student_id = p_student_id;
END //

CREATE PROCEDURE GetMentorFeedback(IN p_mentor_id INT)
BEGIN
    SELECT 
        s.name AS student_name,
        mf.comments,
        mf.feedback_date
    FROM MentorFeedback mf
    JOIN Students s ON mf.student_id = s.student_id
    WHERE mf.mentor_id = p_mentor_id
    ORDER BY mf.feedback_date DESC;
END //

CREATE PROCEDURE AddMentor(
    IN p_name VARCHAR(100),
    IN p_email VARCHAR(100),
    IN p_password VARCHAR(255),
    IN p_expertise VARCHAR(100)
)
BEGIN
    INSERT INTO Mentors (name, email, password, expertise_area)
    VALUES (p_name, p_email, p_password, p_expertise);
END //

CREATE PROCEDURE AddSubject(
    IN p_subject_name VARCHAR(100),
    IN p_credits INT
)
BEGIN
    INSERT INTO Subjects (subject_name, credits)
    VALUES (p_subject_name, p_credits);
END //

-- Procedure: DeleteMentor (NEW)
-- Removes a mentor by ID
CREATE PROCEDURE DeleteMentor(IN p_mentor_id INT)
BEGIN
    DELETE FROM Mentors WHERE mentor_id = p_mentor_id;
END //

-- Procedure: DeleteSubject (NEW)
-- Removes a subject by ID
CREATE PROCEDURE DeleteSubject(IN p_subject_id INT)
BEGIN
    DELETE FROM Subjects WHERE subject_id = p_subject_id;
END //

DELIMITER ;

-- 5. DATA SEEDING (DML)
INSERT INTO Subjects (subject_name, credits) VALUES 
('Database Management Systems', 4),
('Artificial Intelligence', 3),
('Web Development', 3),
('Data Structures', 4),
('Software Engineering', 3),
('Computer Networks', 3),
('Cyber Security', 3),
('Cloud Computing', 4);

INSERT INTO Mentors (name, email, password, expertise_area) VALUES 
('Dr. Alan Turing', 'alan@uni.edu', 'admin123', 'AI & Logic'),
('Dr. Grace Hopper', 'grace@uni.edu', 'admin123', 'Compilers'),
('Prof. Ada Lovelace', 'ada@uni.edu', 'admin123', 'Algorithm Design'),
('Dr. Richard Feynman', 'richard@uni.edu', 'admin123', 'Physics & Computation'),
('Dr. John von Neumann', 'john@uni.edu', 'admin123', 'Game Theory'),
('Prof. Margaret Hamilton', 'margaret@uni.edu', 'admin123', 'Software Engineering');