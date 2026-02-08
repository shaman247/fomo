<?php
/**
 * User Authentication API
 *
 * Handles user registration, login, logout, and session management.
 * Authentication is optional - anonymous edits are allowed.
 *
 * Endpoints:
 *   POST /api/auth.php?action=register - Create new account
 *   POST /api/auth.php?action=login    - Log in
 *   POST /api/auth.php?action=logout   - Log out
 *   GET  /api/auth.php?action=me       - Get current user info
 */

require_once __DIR__ . '/config.php';

// CORS headers
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
header('Content-Type: application/json');

// Handle preflight
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

// Start session for auth
session_start();

// Database connection
try {
    $pdo = new PDO(
        "mysql:host=" . DB_HOST . ";dbname=" . DB_NAME . ";charset=utf8mb4",
        DB_USER,
        DB_PASS,
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]
    );
} catch (PDOException $e) {
    jsonError('Database connection failed', 500);
}

$action = $_GET['action'] ?? '';

switch ($action) {
    case 'register':
        handleRegister($pdo);
        break;
    case 'login':
        handleLogin($pdo);
        break;
    case 'logout':
        handleLogout();
        break;
    case 'me':
        handleMe($pdo);
        break;
    default:
        jsonError('Invalid action. Use: register, login, logout, or me', 400);
}

/**
 * Register a new user.
 */
function handleRegister(PDO $pdo): void {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        jsonError('POST required', 405);
    }

    $input = getJsonInput();

    $email = trim($input['email'] ?? '');
    $password = $input['password'] ?? '';
    $displayName = trim($input['display_name'] ?? '');

    // Validation
    if (empty($email) || !filter_var($email, FILTER_VALIDATE_EMAIL)) {
        jsonError('Valid email is required', 400);
    }

    if (strlen($password) < 8) {
        jsonError('Password must be at least 8 characters', 400);
    }

    if (strlen($displayName) > 100) {
        jsonError('Display name must be 100 characters or less', 400);
    }

    // Check if email already exists
    $stmt = $pdo->prepare("SELECT id FROM users WHERE email = ?");
    $stmt->execute([$email]);
    if ($stmt->fetch()) {
        jsonError('Email already registered', 409);
    }

    // Create user
    $passwordHash = password_hash($password, PASSWORD_DEFAULT);

    $stmt = $pdo->prepare("
        INSERT INTO users (email, display_name, password_hash, created_at)
        VALUES (?, ?, ?, NOW())
    ");
    $stmt->execute([$email, $displayName ?: null, $passwordHash]);

    $userId = (int)$pdo->lastInsertId();

    // Auto-login after registration
    $_SESSION['user_id'] = $userId;
    $_SESSION['user_email'] = $email;
    $_SESSION['user_display_name'] = $displayName;

    jsonSuccess([
        'user' => [
            'id' => $userId,
            'email' => $email,
            'display_name' => $displayName ?: null,
            'is_admin' => false
        ],
        'message' => 'Registration successful'
    ]);
}

/**
 * Log in an existing user.
 */
function handleLogin(PDO $pdo): void {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        jsonError('POST required', 405);
    }

    $input = getJsonInput();

    $email = trim($input['email'] ?? '');
    $password = $input['password'] ?? '';

    if (empty($email) || empty($password)) {
        jsonError('Email and password are required', 400);
    }

    // Find user
    $stmt = $pdo->prepare("
        SELECT id, email, display_name, password_hash, is_admin
        FROM users WHERE email = ?
    ");
    $stmt->execute([$email]);
    $user = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$user || !password_verify($password, $user['password_hash'])) {
        jsonError('Invalid email or password', 401);
    }

    // Update last login
    $stmt = $pdo->prepare("UPDATE users SET last_login_at = NOW() WHERE id = ?");
    $stmt->execute([$user['id']]);

    // Set session
    $_SESSION['user_id'] = (int)$user['id'];
    $_SESSION['user_email'] = $user['email'];
    $_SESSION['user_display_name'] = $user['display_name'];
    $_SESSION['user_is_admin'] = (bool)$user['is_admin'];

    jsonSuccess([
        'user' => [
            'id' => (int)$user['id'],
            'email' => $user['email'],
            'display_name' => $user['display_name'],
            'is_admin' => (bool)$user['is_admin']
        ],
        'message' => 'Login successful'
    ]);
}

/**
 * Log out the current user.
 */
function handleLogout(): void {
    // Clear session
    $_SESSION = [];

    if (ini_get('session.use_cookies')) {
        $params = session_get_cookie_params();
        setcookie(
            session_name(),
            '',
            time() - 42000,
            $params['path'],
            $params['domain'],
            $params['secure'],
            $params['httponly']
        );
    }

    session_destroy();

    jsonSuccess(['message' => 'Logged out']);
}

/**
 * Get current user info.
 */
function handleMe(PDO $pdo): void {
    if (!isset($_SESSION['user_id'])) {
        jsonSuccess([
            'authenticated' => false,
            'user' => null
        ]);
        return;
    }

    // Get fresh user data
    $stmt = $pdo->prepare("
        SELECT id, email, display_name, is_admin, created_at, last_login_at
        FROM users WHERE id = ?
    ");
    $stmt->execute([$_SESSION['user_id']]);
    $user = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$user) {
        // User was deleted
        handleLogout();
        return;
    }

    jsonSuccess([
        'authenticated' => true,
        'user' => [
            'id' => (int)$user['id'],
            'email' => $user['email'],
            'display_name' => $user['display_name'],
            'is_admin' => (bool)$user['is_admin'],
            'created_at' => $user['created_at'],
            'last_login_at' => $user['last_login_at']
        ]
    ]);
}

/**
 * Get JSON input from request body.
 */
function getJsonInput(): array {
    $rawInput = file_get_contents('php://input');
    if (empty($rawInput)) {
        return [];
    }

    $data = json_decode($rawInput, true);
    if (json_last_error() !== JSON_ERROR_NONE) {
        jsonError('Invalid JSON', 400);
    }

    return $data ?? [];
}

/**
 * Return JSON success response.
 */
function jsonSuccess(array $data): void {
    echo json_encode(array_merge(['success' => true], $data));
    exit;
}

/**
 * Return JSON error response.
 */
function jsonError(string $message, int $statusCode = 400): void {
    http_response_code($statusCode);
    echo json_encode([
        'success' => false,
        'error' => $message
    ]);
    exit;
}
