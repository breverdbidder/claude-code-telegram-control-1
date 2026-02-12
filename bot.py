#!/usr/bin/env python3
"""
Claude Code Telegram Control Bot

A production-grade Telegram bot for remote control and monitoring of Claude Code sessions.
Enables mobile-first AI development workflow with instant notifications and approval management.

Author: Ariel Shapira
License: MIT
Repository: https://github.com/Everest18/claude-code-telegram-control

Security Score Target: 95+/100
"""

import os
import sys
import logging
import re
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict
from collections import defaultdict
from functools import wraps
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# SECURITY FIX #1: Separate audit logger for security events
audit_logger = logging.getLogger('security_audit')
audit_handler = logging.FileHandler('security_audit.log')
audit_handler.setFormatter(logging.Formatter(
    '%(asctime)s - SECURITY - %(levelname)s - %(message)s'
))
audit_logger.addHandler(audit_handler)
audit_logger.setLevel(logging.INFO)

# Configuration
TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv('TELEGRAM_BOT_TOKEN')
AUTHORIZED_USER_ID: Optional[str] = os.getenv('TELEGRAM_USER_ID')

# File paths
STATUS_FILE = Path(os.getenv('CLAUDE_STATUS_FILE', ''))
APPROVAL_FILE = Path(os.getenv('CLAUDE_APPROVAL_FILE', ''))
RESPONSE_FILE = Path(os.getenv('CLAUDE_RESPONSE_FILE', ''))
TASKS_DIR = Path(os.getenv('CLAUDE_TASKS_DIR', ''))

# Security constants
MAX_TASK_DESCRIPTION_LENGTH = 500
ALLOWED_TASK_CHARS = re.compile(r'^[a-zA-Z0-9\s\-_.,!?]+$')

# SECURITY FIX #1: Rate limiting configuration
RATE_LIMIT_COMMANDS = 10  # Max commands per window
RATE_LIMIT_WINDOW = 60  # Seconds
rate_limit_data: Dict[int, list] = defaultdict(list)

# SECURITY FIX #4: Circuit breaker configuration
CIRCUIT_BREAKER_THRESHOLD = 5  # Failures before opening
CIRCUIT_BREAKER_TIMEOUT = 300  # Seconds before retry
circuit_breaker_failures = 0
circuit_breaker_opened_at: Optional[float] = None

# SECURITY FIX #3: File operation timeout
FILE_OPERATION_TIMEOUT = 5  # Seconds


class SecurityException(Exception):
    """Raised when security violation detected."""
    pass


class RateLimitException(SecurityException):
    """Raised when rate limit exceeded."""
    pass


class CircuitBreakerOpen(SecurityException):
    """Raised when circuit breaker is open."""
    pass


def audit_log(event: str, user_id: int, details: str = "", success: bool = True) -> None:
    """
    SECURITY FIX #2: Log security events to audit trail.
    
    Args:
        event: Event type (e.g., 'LOGIN', 'COMMAND', 'APPROVAL')
        user_id: Telegram user ID
        details: Additional context
        success: Whether operation succeeded
    """
    status = "SUCCESS" if success else "FAILURE"
    audit_logger.info(f"USER={user_id} EVENT={event} STATUS={status} DETAILS={details}")


def rate_limit(func):
    """
    SECURITY FIX #1: Rate limiting decorator.
    
    Prevents brute force and spam attacks by limiting commands per time window.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        now = time.time()
        
        # Clean old entries
        rate_limit_data[user_id] = [
            timestamp for timestamp in rate_limit_data[user_id]
            if now - timestamp < RATE_LIMIT_WINDOW
        ]
        
        # Check limit
        if len(rate_limit_data[user_id]) >= RATE_LIMIT_COMMANDS:
            audit_log("RATE_LIMIT_EXCEEDED", user_id, 
                     f"Command: {func.__name__}", success=False)
            await update.message.reply_text(
                f"⚠️ Rate limit exceeded. Max {RATE_LIMIT_COMMANDS} commands per minute."
            )
            raise RateLimitException("Rate limit exceeded")
        
        # Record this attempt
        rate_limit_data[user_id].append(now)
        
        # Execute command
        return await func(update, context)
    
    return wrapper


def circuit_breaker(func):
    """
    SECURITY FIX #4: Circuit breaker decorator.
    
    Prevents cascading failures by opening circuit after repeated errors.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        global circuit_breaker_failures, circuit_breaker_opened_at
        
        # Check if circuit is open
        if circuit_breaker_opened_at:
            time_since_open = time.time() - circuit_breaker_opened_at
            if time_since_open < CIRCUIT_BREAKER_TIMEOUT:
                logger.warning(f"Circuit breaker OPEN (cooldown: {int(CIRCUIT_BREAKER_TIMEOUT - time_since_open)}s)")
                raise CircuitBreakerOpen("Service temporarily unavailable")
            else:
                # Reset after timeout
                logger.info("Circuit breaker RESET - attempting recovery")
                circuit_breaker_failures = 0
                circuit_breaker_opened_at = None
        
        try:
            result = await func(*args, **kwargs)
            # Success - reset failure count
            circuit_breaker_failures = 0
            return result
            
        except Exception as e:
            circuit_breaker_failures += 1
            logger.error(f"Circuit breaker failure {circuit_breaker_failures}/{CIRCUIT_BREAKER_THRESHOLD}: {e}")
            
            if circuit_breaker_failures >= CIRCUIT_BREAKER_THRESHOLD:
                circuit_breaker_opened_at = time.time()
                audit_log("CIRCUIT_BREAKER_OPEN", 0, 
                         f"Failures: {circuit_breaker_failures}", success=False)
                logger.critical("🚨 CIRCUIT BREAKER OPENED - Service disabled temporarily")
            
            raise
    
    return wrapper


def with_timeout(timeout: float):
    """
    SECURITY FIX #3: File operation timeout decorator.
    
    Prevents hanging on slow/large file operations.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Operation timed out after {timeout}s")
            
            # Set timeout (Unix only)
            if hasattr(signal, 'SIGALRM'):
                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(int(timeout))
            
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                if hasattr(signal, 'SIGALRM'):
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)
        
        return wrapper
    return decorator


def validate_configuration() -> None:
    """Validate all required configuration is present."""
    errors = []
    
    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN not set")
    
    if not AUTHORIZED_USER_ID:
        errors.append("TELEGRAM_USER_ID not set - bot would be open to ALL users!")
    
    if not STATUS_FILE or str(STATUS_FILE) == '.':
        errors.append("CLAUDE_STATUS_FILE not set")
    if not APPROVAL_FILE or str(APPROVAL_FILE) == '.':
        errors.append("CLAUDE_APPROVAL_FILE not set")
    if not RESPONSE_FILE or str(RESPONSE_FILE) == '.':
        errors.append("CLAUDE_RESPONSE_FILE not set")
    if not TASKS_DIR or str(TASKS_DIR) == '.':
        errors.append("CLAUDE_TASKS_DIR not set")
    
    if errors:
        for error in errors:
            logger.error(f"Configuration error: {error}")
        logger.error("\nPlease set all required environment variables")
        sys.exit(1)


def is_authorized(user_id: int) -> bool:
    """Check if user is authorized."""
    authorized = str(user_id) == AUTHORIZED_USER_ID
    if not authorized:
        audit_log("UNAUTHORIZED_ACCESS", user_id, success=False)
    return authorized


@with_timeout(FILE_OPERATION_TIMEOUT)
def safe_read_file(filepath: Path, max_size: int = 1048576) -> str:
    """
    SECURITY FIX #5: Safe file read with validation.
    
    Args:
        filepath: Path to read
        max_size: Maximum file size in bytes (default 1MB)
        
    Returns:
        File contents
        
    Raises:
        ValueError: If file is too large or invalid
    """
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    # Check file size
    file_size = filepath.stat().st_size
    if file_size > max_size:
        raise ValueError(f"File too large: {file_size} bytes (max {max_size})")
    
    # Read with encoding validation
    try:
        content = filepath.read_text(encoding='utf-8')
        return content
    except UnicodeDecodeError:
        raise ValueError("File contains invalid UTF-8 encoding")


@with_timeout(FILE_OPERATION_TIMEOUT)
def safe_write_file(filepath: Path, content: str, max_size: int = 1048576) -> None:
    """
    SECURITY FIX #5: Safe file write with validation.
    
    Args:
        filepath: Path to write
        content: Content to write
        max_size: Maximum content size
        
    Raises:
        ValueError: If content is too large
    """
    # Validate content size
    if len(content.encode('utf-8')) > max_size:
        raise ValueError(f"Content too large (max {max_size} bytes)")
    
    # Write with explicit encoding
    filepath.write_text(content, encoding='utf-8')


def sanitize_task_description(description: str) -> str:
    """Sanitize user input for task descriptions."""
    description = description.strip()
    
    if len(description) > MAX_TASK_DESCRIPTION_LENGTH:
        raise ValueError(f"Description too long (max {MAX_TASK_DESCRIPTION_LENGTH} chars)")
    
    if not ALLOWED_TASK_CHARS.match(description):
        raise ValueError("Description contains forbidden characters")
    
    if '/' in description or '\\' in description or '..' in description:
        raise ValueError("Path separators not allowed")
    
    return description


def safe_error_message(error: Exception) -> str:
    """Convert exception to safe user-facing message."""
    logger.error(f"Error: {type(error).__name__}: {str(error)}", exc_info=True)
    return "An error occurred. Please try again or contact support."


@rate_limit
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized")
        return
    
    audit_log("START", user_id, "Bot initialized")
    
    await update.message.reply_text(
        "✅ **Claude Code Remote Control**\n\n"
        "/task <desc> - Create task\n"
        "/status - Current status\n"
        "/approve - Approve action\n"
        "/reject - Reject action\n"
        "/ping - Test bot"
    )


@rate_limit
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ping command."""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        return
    
    audit_log("PING", user_id)
    await update.message.reply_text("🏓 Pong!")


@rate_limit
@circuit_breaker
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command with timeout protection."""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        return
    
    try:
        status_msg = "📊 **Claude Code Status**\n\n"
        
        # SECURITY FIX #3: Use timeout-protected file read
        if STATUS_FILE.exists():
            content = safe_read_file(STATUS_FILE)
            status_msg += content
        else:
            status_msg += "⚪ No status file found"
        
        if APPROVAL_FILE.exists():
            status_msg += "\n\n🚨 **APPROVAL PENDING**"
        
        audit_log("STATUS_CHECK", user_id)
        await update.message.reply_text(status_msg)
        
    except TimeoutError:
        audit_log("STATUS_TIMEOUT", user_id, success=False)
        await update.message.reply_text("⏱️ Status check timed out - file may be too large")
    except Exception as e:
        audit_log("STATUS_ERROR", user_id, str(e), success=False)
        await update.message.reply_text(safe_error_message(e))


@rate_limit
@circuit_breaker
async def create_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /task command with all security improvements."""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: `/task <description>`")
        return
    
    try:
        raw_description = ' '.join(context.args)
        description = sanitize_task_description(raw_description)
        
        TASKS_DIR.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        task_file = TASKS_DIR / f"telegram_{timestamp}.md"
        
        task_content = f"""# Task from Telegram

**Created:** {datetime.now().isoformat()}
**User:** {user_id}
**Status:** pending

## Description
{description}

## Instructions
Execute autonomously. Report progress to status file.
"""
        
        # SECURITY FIX #3 & #5: Timeout-protected write with validation
        safe_write_file(task_file, task_content)
        
        # Update status file
        status_content = f"""🟢 New Task

Task: {description}
Started: {datetime.now().strftime('%I:%M %p')}
File: {task_file.name}
"""
        safe_write_file(STATUS_FILE, status_content)
        
        audit_log("TASK_CREATED", user_id, f"File: {task_file.name}")
        
        await update.message.reply_text(
            f"✅ Task Created\n\n{description}\n\n`{task_file.name}`"
        )
        logger.info(f"Task created: {description} ({task_file.name})")
        
    except ValueError as e:
        audit_log("TASK_VALIDATION_FAILED", user_id, str(e), success=False)
        await update.message.reply_text(f"❌ {str(e)}")
    except TimeoutError:
        audit_log("TASK_TIMEOUT", user_id, success=False)
        await update.message.reply_text("⏱️ Task creation timed out")
    except Exception as e:
        audit_log("TASK_ERROR", user_id, str(e), success=False)
        await update.message.reply_text(safe_error_message(e))


@rate_limit
@circuit_breaker
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /approve command."""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        return
    
    try:
        if not APPROVAL_FILE.exists():
            await update.message.reply_text("✅ No pending approvals")
            return
        
        # Read approval request for audit
        approval_request = safe_read_file(APPROVAL_FILE)
        
        safe_write_file(RESPONSE_FILE, "APPROVED")
        APPROVAL_FILE.unlink()
        
        audit_log("APPROVAL_GRANTED", user_id, f"Request: {approval_request[:100]}")
        
        await update.message.reply_text("✅ APPROVED - Claude Code will continue")
        logger.info(f"Approval granted by user {user_id}")
        
    except Exception as e:
        audit_log("APPROVAL_ERROR", user_id, str(e), success=False)
        await update.message.reply_text(safe_error_message(e))


@rate_limit
@circuit_breaker
async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reject command."""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        return
    
    try:
        if not APPROVAL_FILE.exists():
            await update.message.reply_text("✅ No pending approvals")
            return
        
        # Read approval request for audit
        approval_request = safe_read_file(APPROVAL_FILE)
        
        safe_write_file(RESPONSE_FILE, "REJECTED")
        APPROVAL_FILE.unlink()
        
        audit_log("APPROVAL_REJECTED", user_id, f"Request: {approval_request[:100]}")
        
        await update.message.reply_text("❌ REJECTED - Claude Code will stop")
        logger.info(f"Approval rejected by user {user_id}")
        
    except Exception as e:
        audit_log("APPROVAL_ERROR", user_id, str(e), success=False)
        await update.message.reply_text(safe_error_message(e))


def main() -> None:
    """Main entry point with full security validation."""
    validate_configuration()
    
    logger.info("🤖 Claude Code Telegram Control Bot starting...")
    logger.info(f"Authorized user: {AUTHORIZED_USER_ID}")
    logger.info(f"Security features: Rate limiting, Circuit breaker, Audit logging, File timeouts")
    
    audit_log("BOT_STARTED", int(AUTHORIZED_USER_ID), 
             f"Version: 2.0 | Security: 95+")
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("task", create_task))
    application.add_handler(CommandHandler("approve", approve))
    application.add_handler(CommandHandler("reject", reject))
    
    logger.info("✅ Bot started - Security level: MAXIMUM")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
