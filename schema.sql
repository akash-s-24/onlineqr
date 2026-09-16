-- =========================================================
-- EventMate – College Event Management System Database Schema
-- Database: MySQL
-- =========================================================

CREATE DATABASE IF NOT EXISTS eventmate_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE eventmate_db;

-- ---------------------------------------------------------
-- Reset Existing Tables
-- ---------------------------------------------------------
DROP TABLE IF EXISTS certificates;
DROP TABLE IF EXISTS attendance;
DROP TABLE IF EXISTS registrations;
DROP TABLE IF EXISTS participants;
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS users;

-- ---------------------------------------------------------
-- Table: users
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'student',
    full_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------
-- Table: events
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    event_name VARCHAR(100) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    event_date VARCHAR(30) NOT NULL,
    event_time VARCHAR(30) NOT NULL,
    venue VARCHAR(100) NOT NULL,
    description TEXT,
    max_participants INT DEFAULT 100,
    is_group INT DEFAULT 0,
    min_team_size INT DEFAULT 1,
    max_team_size INT DEFAULT 1,
    event_fee INT DEFAULT 0,
    banner_image VARCHAR(255) DEFAULT 'event_default.jpg',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------
-- Table: participants
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS participants (
    id SERIAL PRIMARY KEY,
    user_id INT NULL,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    college_name VARCHAR(150) NOT NULL,
    department VARCHAR(100) NOT NULL,
    semester VARCHAR(20) DEFAULT '5th Sem',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- ---------------------------------------------------------
-- Table: registrations
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS registrations (
    id SERIAL PRIMARY KEY,
    registration_uid VARCHAR(20) UNIQUE,
    participant_id INT NOT NULL,
    event_id INT NOT NULL,
    registered_by INT NULL,
    is_group INT DEFAULT 0,
    team_name VARCHAR(100) NULL,
    team_size INT DEFAULT 1,
    team_members TEXT NULL,
    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending',
    payment_status VARCHAR(20) DEFAULT 'unpaid',
    amount_paid INT DEFAULT 0,
    payment_method VARCHAR(50) DEFAULT 'None',
    utr_number VARCHAR(100) NULL,
    UNIQUE (participant_id, event_id),
    FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
    FOREIGN KEY (registered_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS registrations_utr_unique
    ON registrations (utr_number);

-- ---------------------------------------------------------
-- Table: attendance
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS attendance (
    id SERIAL PRIMARY KEY,
    registration_id INT NOT NULL UNIQUE,
    status VARCHAR(20) DEFAULT 'absent',
    marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    marked_by VARCHAR(50) DEFAULT 'admin',
    FOREIGN KEY (registration_id) REFERENCES registrations(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------
-- Table: certificates
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS certificates (
    id SERIAL PRIMARY KEY,
    certificate_code VARCHAR(50) NOT NULL UNIQUE,
    registration_id INT NOT NULL UNIQUE,
    participant_id INT NOT NULL,
    event_id INT NOT NULL,
    issue_date VARCHAR(30) NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    email_status VARCHAR(20) DEFAULT 'pending',
    sent_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (registration_id) REFERENCES registrations(id) ON DELETE CASCADE,
    FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------
-- Seed Data
-- ---------------------------------------------------------

-- 2. Core Events Required by User (including Binary Brains, Digital Dynamos, CodeCraft, etc.)
INSERT INTO events (id, event_name, event_type, event_date, event_time, venue, description, max_participants, is_group, min_team_size, max_team_size) VALUES
(1, 'Binary Brains', 'Technical Quiz & Logic Duel', '18-sep-2026', '11:00 AM', 'Seminar Hall 1', 'Rapid-fire technical quiz, logic reasoning puzzles, and algorithmic brain teasers for dynamic teams.', 60, 1, 2, 4),
(2, 'Digital Dynamos', 'Full-Stack Innovation Duel', '19-sep-2026', '01:30 PM', 'Innovation & Web Lab', 'Collaborative web application design, UI/UX sprint, and creative software project showcase for squads.', 50, 1, 2, 4),
(3, 'CodeCraft', 'Hackathon / Coding', '18-sep-2026', '09:30 AM', 'Lab 1 - Turing Computing Centre', 'The premier college hackathon challenging students to build innovative software solutions within a 6-hour sprint.', 60, 0, 1, 1),
(4, 'CodeStorm', 'Debugging & DSA', '19-sep-2026', '10:00 AM', 'Main Auditorium & CS Lab 2', 'A high-intensity coding & algorithmic problem solving competition testing speed, precision, and bug eradication skills.', 80, 0, 1, 1),
(5, 'CodeVerse', 'Web & App Design', '19-sep-2026', '02:00 PM', 'Seminar Hall 3', 'Showcase of modern UI/UX design, full-stack application development, and interactive web architecture presentations.', 50, 0, 1, 1),
(6, 'ByteBattle', 'Speed Coding Duel', '20-sep-2026', '11:00 AM', 'Advanced Computing Lab', '1-on-1 fast-paced knockout speed coding rounds on algorithms, data structures, and mathematical puzzles.', 40, 0, 1, 1);

-- 3. Initial Sample Participants
INSERT INTO participants (id, user_id, full_name, email, phone, college_name, department, semester) VALUES
(1, 2, 'Varshitha H', 'varshitha@college.edu', '9876543210', 'Shree Daksha Academy', 'BCA', '5th Sem'),
(2, NULL, 'Rahul Kumar', 'rahul.k@univ.ac.in', '9845123456', 'City College of Technology', 'BSc Computer Science', '3rd Sem'),
(3, NULL, 'Ananya Sharma', 'ananya.s@tech.edu', '9123456780', 'Shree Daksha Academy', 'BCA', '5th Sem'),
(4, NULL, 'Karthik Rao', 'karthik.rao@gmail.com', '9880011223', 'National Institute of Engineering', 'B.Tech IT', '7th Sem');

-- 4. Initial Registrations
INSERT INTO registrations (id, registration_uid, participant_id, event_id, registered_by, is_group, team_name, team_size, team_members, status, payment_status) VALUES
(1, 'REG-1001', 1, 1, 2, 1, 'CyberKnights', 3, 'Varshitha H, Sneha Patel, Ananya Sharma', 'confirmed', 'paid'),
(2, 'REG-1002', 1, 3, 2, 0, NULL, 1, NULL, 'confirmed', 'unpaid'),
(3, 'REG-1003', 2, 2, 3, 1, 'Tech Titans', 2, 'Rahul Kumar, Karthik Rao', 'confirmed', 'paid'),
(4, 'REG-1004', 3, 1, NULL, 1, 'Binary Beasts', 3, 'Ananya Sharma, Rahul Kumar, Sneha Patel', 'confirmed', 'unpaid'),
(5, 'REG-1005', 4, 3, 4, 0, NULL, 1, NULL, 'confirmed', 'paid');

-- 5. Initial Attendance
INSERT INTO attendance (id, registration_id, status, marked_by) VALUES
(1, 1, 'present', 'admin'),
(2, 2, 'present', 'admin'),
(3, 3, 'present', 'admin'),
(4, 4, 'present', 'admin'),
(5, 5, 'absent', 'admin');
