#!/usr/bin/env python3
"""
Claude Code Telegram Control Bot

A production-grade Telegram bot for remote control and monitoring of Claude Code sessions.
Enables mobile-first AI development workflow with instant notifications and approval management.

Author: Ariel Shapira
License: MIT
"""

import os
import sys
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv('TELEGRAM_BOT_TOKEN')
AUTHORIZED_USER_ID: Optional[str] = os.getenv('TELEGRAM_USER_ID')

# File paths (configurable via environment)
STATUS_FILE = Path(os.getenv('CLAUDE_STATUS_FILE', 
                              '/mnt/c/Users/Roselyn Sheffield/claude_code_status.txt'))
APPROVAL_FILE = Path(os.getenv('CLAUDE_APPROVAL_FILE',
                               '/mnt/c/Users/Roselyn Sheffield/claude_approval_needed.txt'))
RESPONSE_FILE = Path(os.getenv('CLAUDE_RESPONSE_FILE',
                               '/mnt/c/Users/Roselyn Sheffield/claude_approval_response.txt'))
TASKS_DIR = Path(os.getenv('CLAUDE_TASKS_DIR',
                           '/mnt/c/Users/Roselyn Sheffield/.claude/tasks'))


def is_authorized(user_id: int) -> bool:
    """Check if user is authorized to use the bot."""
    if not AUTHORIZED_USER_ID:
        logger.warning("No TELEGRAM_USER_ID set - bot is open to all users!")
        return True
    return str(user_id) == AUTHORIZED_USER_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized")
        return
    
    await update.message.reply_text(
        "✅ **Claude Code Remote Control**\n\n"
        "/task <desc> - Create task\n"
        "/tasks - List tasks\n"
        "/status - Current status\n"
        "/approve - Approve action\n"
        "/reject - Reject action\n"
        "/ping - Test bot"
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ping command."""
    if not is_authorized(update.effective_user.id):
        return
    await update.message.reply_text("🏓 Pong!")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command."""
    if not is_authorized(update.effective_user.id):
        return
    
    try:
        result = subprocess.run(
            ["powershell.exe", "-Command", 
             "Get-Process python -ErrorAction SilentlyContinue | Measure-Object | Select-Object -ExpandProperty Count"],
            capture_output=True, text=True, timeout=5
        )
        python_count = result.stdout.strip() or "0"
        
        status_msg = f"📊 **Status**\n\nPython processes: {python_count}\n"
        
        if STATUS_FILE.exists():
            status_msg += f"\n{STATUS_FILE.read_text()}"
        else:
            status_msg += "\n⚪ No status file"
        
        if APPROVAL_FILE.exists():
            status_msg += "\n\n🚨 **APPROVAL PENDING**"
        
        await update.message.reply_text(status_msg)
    except Exception as e:
        logger.error(f"Status error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


async def create_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /task command."""
    if not is_authorized(update.effective_user.id):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: `/task <description>`")
        return
    
    try:
        description = ' '.join(context.args)
        TASKS_DIR.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_file = TASKS_DIR / f"telegram_{timestamp}.md"
        
        task_file.write_text(f"""# Task from Telegram

**Created:** {datetime.now().isoformat()}
**Status:** pending

## Description
{description}

## Instructions
Execute autonomously. Report progress to status file.
""")
        
        STATUS_FILE.write_text(f"""🟢 New Task

Task: {description}
Started: {datetime.now().strftime('%I:%M %p')}
File: {task_file.name}
""")
        
        await update.message.reply_text(
            f"✅ Task Created\n\n{description}\n\n`{task_file.name}`"
        )
        logger.info(f"Task created: {description}")
    except Exception as e:
        logger.error(f"Task creation error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /approve command."""
    if not is_authorized(update.effective_user.id):
        return
    
    try:
        if not APPROVAL_FILE.exists():
            await update.message.reply_text("✅ No pending approvals")
            return
        
        RESPONSE_FILE.write_text("APPROVED")
        APPROVAL_FILE.unlink()
        await update.message.reply_text("✅ APPROVED")
        logger.info("Approved by user")
    except Exception as e:
        logger.error(f"Approve error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


def main() -> None:
    """Main entry point."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("task", create_task))
    app.add_handler(CommandHandler("approve", approve))
    
    logger.info("🤖 Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
