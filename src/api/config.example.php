<?php
/**
 * Database Configuration
 *
 * Copy this file to config.php and fill in your database credentials.
 * NEVER commit config.php to version control.
 *
 * To create the database and table:
 * 1. Log into cPanel -> MySQL Databases
 * 2. Create a new database (e.g., youruser_fomo)
 * 3. Create a new user with a strong password
 * 4. Add the user to the database with ALL PRIVILEGES
 * 5. Go to phpMyAdmin and run the SQL below to create the table
 *
 * CREATE TABLE feedback (
 *     id INT AUTO_INCREMENT PRIMARY KEY,
 *     message TEXT NOT NULL,
 *     user_agent VARCHAR(500),
 *     page_url VARCHAR(500),
 *     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 *     INDEX idx_created_at (created_at)
 * ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
 */

// Detect environment by hostname
$isLocal = in_array($_SERVER['HTTP_HOST'] ?? '', ['localhost', '127.0.0.1'])
        || strpos($_SERVER['HTTP_HOST'] ?? '', 'localhost:') === 0;

if ($isLocal) {
    // Local development (XAMPP)
    define('DB_HOST', 'localhost');
    define('DB_NAME', 'fomo');
    define('DB_USER', 'root');
    define('DB_PASS', '');
} else {
    // Production (Namecheap) - fill in your credentials
    define('DB_HOST', 'localhost');
    define('DB_NAME', 'youruser_fomo');
    define('DB_USER', 'youruser_root');
    define('DB_PASS', 'your_secure_password_here');
}
