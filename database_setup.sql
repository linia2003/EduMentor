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

-- Table: Messages (NEW FOR TWO-WAY COMMUNICATION)
CREATE TABLE IF NOT EXISTS Messages (
    message_id INT AUTO_INCREMENT PRIMARY KEY,
    sender_id INT NOT NULL,
    recipient_id INT NOT NULL,
    sender_role VARCHAR(10) NOT NULL, -- 'student' or 'mentor'
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_read BOOLEAN DEFAULT FALSE,
    
    -- Indexing for efficient inbox/outbox retrieval
    INDEX idx_recipient (recipient_id),
    INDEX idx_sender (sender_id)
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

-- Drop procedures if they exist to allow recreation
DROP PROCEDURE IF EXISTS GetStudentProgressReport;
DROP PROCEDURE IF EXISTS GetMentorFeedback;
DROP PROCEDURE IF EXISTS AddMentor;
DROP PROCEDURE IF EXISTS AddSubject;
DROP PROCEDURE IF EXISTS DeleteMentor;
DROP PROCEDURE IF EXISTS DeleteSubject;
DROP PROCEDURE IF EXISTS CalculateAndUpdateProgress; 

DELIMITER //

CREATE PROCEDURE GetStudentProgressReport(IN p_student_id INT)
BEGIN
    SELECT 
        s.name AS student_name,
        sub.subject_id,  
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

-- Procedure: DeleteMentor 
-- Removes a mentor by ID
CREATE PROCEDURE DeleteMentor(IN p_mentor_id INT)
BEGIN
    DELETE FROM Mentors WHERE mentor_id = p_mentor_id;
END //

-- Procedure: DeleteSubject 
-- Removes a subject by ID
CREATE PROCEDURE DeleteSubject(IN p_subject_id INT)
BEGIN
    DELETE FROM Subjects WHERE subject_id = p_subject_id;
END //

-- Procedure: CalculateAndUpdateProgress 
-- Calculates progress percentage based on StudyLog hours vs (Credits * 10) expected hours.
CREATE PROCEDURE CalculateAndUpdateProgress(
    IN p_student_id INT,
    IN p_subject_id INT
)
BEGIN
    DECLARE total_logged DECIMAL(5, 2);
    DECLARE subject_credits INT;
    DECLARE calculated_progress DECIMAL(5, 2);
    
    -- 1. Get total logged hours for this student/subject
    SELECT SUM(duration_hours) INTO total_logged
    FROM StudyLog
    WHERE student_id = p_student_id AND subject_id = p_subject_id;

    -- 2. Get subject credits
    SELECT credits INTO subject_credits
    FROM Subjects
    WHERE subject_id = p_subject_id;
    
    -- 3. Calculate Progress (Cap at 100%)
    IF total_logged IS NULL THEN
        SET calculated_progress = 0;
    ELSE
        -- Expected hours = Credits * 10
        SET calculated_progress = LEAST(100.00, (total_logged / (subject_credits * 10)) * 100);
    END IF;

    -- 4. Insert or Update StudentProgress table
    INSERT INTO StudentProgress (student_id, subject_id, progress_percentage)
    VALUES (p_student_id, p_subject_id, calculated_progress)
    ON DUPLICATE KEY UPDATE 
        progress_percentage = calculated_progress,
        last_updated = CURRENT_TIMESTAMP;
END //

DELIMITER ;

-- 5. DATA SEEDING (DML)

-- IMPORTANT: Disable foreign key checks temporarily to allow TRUNCATE on tables with FKs
SET FOREIGN_KEY_CHECKS = 0;

-- Clear data from tables before re-seeding to prevent duplicate entries (TRUNCATE is faster than DELETE)
TRUNCATE TABLE StudyLog;
TRUNCATE TABLE MentorFeedback;
TRUNCATE TABLE StudentProgress;
TRUNCATE TABLE Messages; -- NEW TABLE TRUNCATE
TRUNCATE TABLE Students;
TRUNCATE TABLE Mentors;
TRUNCATE TABLE Subjects;

-- Re-enable foreign key checks
SET FOREIGN_KEY_CHECKS = 1;

INSERT INTO Subjects (subject_name, credits) VALUES 
('Database Management Systems', 4), -- subject_id 1
('Artificial Intelligence', 3),     -- subject_id 2
('Web Development', 3),            -- subject_id 3
('Data Structures', 4),            -- subject_id 4
('Software Engineering', 3),       -- subject_id 5
('Computer Networks', 3),          -- subject_id 6
('Cyber Security', 3),             -- subject_id 7
('Cloud Computing', 4);            -- subject_id 8

INSERT INTO Mentors (name, email, password, expertise_area) VALUES 
('Dr. Alan Turing', 'alan@uni.edu', 'admin123', 'AI & Logic'),               -- mentor_id 1
('Dr. Grace Hopper', 'grace@uni.edu', 'admin123', 'Compilers'),             -- mentor_id 2
('Prof. Ada Lovelace', 'ada@uni.edu', 'admin123', 'Algorithm Design'),      -- mentor_id 3
('Dr. Richard Feynman', 'richard@uni.edu', 'admin123', 'Physics & Computation'), -- mentor_id 4
('Dr. John von Neumann', 'john@uni.edu', 'admin123', 'Game Theory'),        -- mentor_id 5
('Prof. Margaret Hamilton', 'margaret@uni.edu', 'admin123', 'Software Engineering'); -- mentor_id 6

INSERT INTO Students (name, email, password, semester) VALUES 
('Sarah Connor', 'sarah@student.edu', 'student123', '3'),   -- student_id 1
('Kyle Reese', 'kyle@student.edu', 'student123', '3'),     -- student_id 2
('Ellen Ripley', 'ellen@student.edu', 'student123', '2'),   -- student_id 3
('Deckard Blade', 'deckard@student.edu', 'student123', '4'),-- student_id 4
('Gideon Nav', 'gideon@student.edu', 'student123', '1');    -- student_id 5

-- 20+ records for StudyLog to populate dashboards and analytics views
INSERT INTO StudyLog (student_id, subject_id, mentor_id, duration_hours, study_date) VALUES 
-- Sarah Connor (ID 1) logs
(1, 1, 2, 2.0, NOW() - INTERVAL 10 DAY), 
(1, 4, 3, 1.5, NOW() - INTERVAL 9 DAY),  
(1, 2, 1, 3.0, NOW() - INTERVAL 8 DAY),  
(1, 1, 2, 1.0, NOW() - INTERVAL 7 DAY),  
(1, 3, 3, 2.5, NOW() - INTERVAL 6 DAY),  

-- Kyle Reese (ID 2) logs
(2, 6, 4, 1.5, NOW() - INTERVAL 5 DAY),  
(2, 5, 6, 2.0, NOW() - INTERVAL 4 DAY),  
(2, 6, 4, 1.0, NOW() - INTERVAL 3 DAY),  
(2, 7, 1, 3.5, NOW() - INTERVAL 2 DAY),  
(2, 5, 6, 1.5, NOW() - INTERVAL 1 DAY),  

-- Ellen Ripley (ID 3) logs
(3, 8, 5, 2.0, NOW() - INTERVAL 12 HOUR), 
(3, 1, 2, 1.0, NOW() - INTERVAL 11 HOUR), 
(3, 8, 5, 2.5, NOW() - INTERVAL 10 HOUR), 
(3, 4, 3, 3.0, NOW() - INTERVAL 9 HOUR),  

-- Deckard Blade (ID 4) logs
(4, 2, 1, 1.0, NOW() - INTERVAL 7 HOUR),  
(4, 7, 1, 0.5, NOW() - INTERVAL 6 HOUR),  
(4, 3, 6, 2.0, NOW() - INTERVAL 5 HOUR),  

-- Gideon Nav (ID 5) logs
(5, 4, 3, 3.0, NOW() - INTERVAL 4 HOUR),  
(5, 5, 6, 1.0, NOW() - INTERVAL 3 HOUR),  
(5, 8, 5, 1.5, NOW() - INTERVAL 2 HOUR),  

-- Extra Logs for summary variation
(1, 5, 6, 1.5, NOW() - INTERVAL 15 DAY), 
(2, 3, 3, 2.0, NOW() - INTERVAL 15 DAY), 
(1, 4, 3, 3.0, NOW() - INTERVAL 1 DAY);  


-- Sample MentorFeedback
INSERT INTO MentorFeedback (student_id, mentor_id, comments) VALUES
(1, 1, 'Sarah is demonstrating strong aptitude in logical reasoning, a key component of AI. Keep pushing the theoretical concepts.'), 
(2, 6, 'Kyle has excellent practical skills in Software Engineering but needs to document his design choices more thoroughly.'),  
(3, 3, 'Ellen, your Data Structures project showed great efficiency. Next, focus on analyzing the time complexity (O-notation) of your solutions.'), 
(1, 2, 'Good work on the last DBMS query optimization challenge, Sarah. You reduced the execution time by 40%.'), 
(4, 1, 'Deckard, your participation in the Cyber Security seminar was insightful. Please formalize your findings in a brief report.');

-- Sample Messages (NEW DML)
INSERT INTO Messages (sender_id, recipient_id, sender_role, content, is_read) VALUES
-- Turing (M1) to Sarah (S1)
(1, 1, 'mentor', 'Please review the recent AI ethics paper I sent you.', FALSE), 
-- Sarah (S1) to Turing (M1)
(1, 1, 'student', 'Got it, Dr. Turing. Starting on it tomorrow.', FALSE), 
-- Lovelace (M3) to Ellen (S3)
(3, 3, 'mentor', 'I noticed your progress in Data Structures is slowing. Are there any specific topics causing trouble?', FALSE),
-- Kyle (S2) to Hamilton (M6)
(2, 6, 'student', 'The SE task is complete. Ready for the next module review!', TRUE);