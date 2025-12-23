<?php
/**
 * Feedback API Endpoint
 *
 * Receives user feedback submissions and stores them in MySQL database.
 *
 * POST /api/feedback.php
 * Body: { "message": "User feedback text" }
 *
 * Response: { "success": true } or { "success": false, "error": "..." }
 */

// Load database configuration
$configPath = __DIR__ . '/config.php';
if (!file_exists($configPath)) {
    http_response_code(500);
    echo json_encode(['success' => false, 'error' => 'Server configuration missing']);
    exit;
}
require_once $configPath;

// Set response headers
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

// Handle preflight requests
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

// Only allow POST requests
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['success' => false, 'error' => 'Method not allowed']);
    exit;
}

// Parse JSON body
$input = file_get_contents('php://input');
$data = json_decode($input, true);

if (!$data || !isset($data['message'])) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'Missing message field']);
    exit;
}

$message = trim($data['message']);

// Validate message
if (empty($message)) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'Message cannot be empty']);
    exit;
}

if (strlen($message) > 10000) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'Message too long (max 10000 characters)']);
    exit;
}

// Get optional metadata
$userAgent = isset($_SERVER['HTTP_USER_AGENT']) ? substr($_SERVER['HTTP_USER_AGENT'], 0, 500) : null;
$pageUrl = isset($data['page_url']) ? substr($data['page_url'], 0, 500) : null;

try {
    // Connect to database
    $pdo = new PDO(
        "mysql:host=" . DB_HOST . ";dbname=" . DB_NAME . ";charset=utf8mb4",
        DB_USER,
        DB_PASS,
        [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES => false
        ]
    );

    // Insert feedback
    $stmt = $pdo->prepare("
        INSERT INTO feedback (message, user_agent, page_url, created_at)
        VALUES (:message, :user_agent, :page_url, NOW())
    ");

    $stmt->execute([
        ':message' => $message,
        ':user_agent' => $userAgent,
        ':page_url' => $pageUrl
    ]);

    echo json_encode(['success' => true]);

} catch (PDOException $e) {
    // Log error but don't expose details to client
    error_log("Feedback API error: " . $e->getMessage());
    http_response_code(500);
    echo json_encode(['success' => false, 'error' => 'Database error']);
}
