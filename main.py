#!/usr/bin/env python

import os
import sys
import json
import time
import shutil
import asyncio
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread
from queue import Queue

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode

# Original DCC imports
from dcc import (
    dcc_main, create_tmp_directory, backup_jni_project_folder,
    restore_jni_project_folder, clean_tmp_directory, Logger
)

# ==================== CONFIGURATION ====================
BOT_TOKEN = "8208647691:AAHixR-Hud15jshdphkH22Hth01q5cHUTqU"  # <-- Enter your bot token here
OWNER_ID = 5827445104  # <-- Enter your Telegram user ID here

USER_LIMITS = {
    "default": 5,  # Normal users ke liye limit (5 conversions)
    "owner": float('inf')  # Owner ke liye unlimited
}

# Database file for user limits
DB_FILE = "user_db.json"

# Allowed file extensions
ALLOWED_EXTENSIONS = ['.apk']

# Processing status
processing_users = {}
user_conversion_count = {}
# ========================================================

def load_user_db():
    """User database load karo"""
    global user_conversion_count
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                user_conversion_count = json.load(f)
        except:
            user_conversion_count = {}
    else:
        user_conversion_count = {}

def save_user_db():
    """User database save karo"""
    with open(DB_FILE, 'w') as f:
        json.dump(user_conversion_count, f)

def get_user_limit(user_id):
    """User ki limit check karo"""
    if user_id == OWNER_ID:
        return USER_LIMITS["owner"]
    return USER_LIMITS["default"]

def check_user_limit(user_id):
    """Check if user can convert more APKs"""
    if user_id == OWNER_ID:
        return True, float('inf')
    
    count = user_conversion_count.get(str(user_id), 0)
    limit = USER_LIMITS["default"]
    remaining = max(0, limit - count)
    return count < limit, remaining

async def ensure_directories():
    """Required directories create karo"""
    dirs = ['.tmp', 'downloads', 'output', 'project', 'tools']
    for dir_name in dirs:
        Path(dir_name).mkdir(exist_ok=True)
    
    # DCC config create karo agar nahi hai
    if not os.path.exists('dcc.cfg'):
        dcc_config = {
            "apktool": "tools/apktool.jar",
            "ndk_dir": "",
            "signature": {
                "keystore_path": "tools/debug.keystore",
                "alias": "androiddebugkey",
                "keystore_pass": "android",
                "store_pass": "android",
                "v1_enabled": True,
                "v2_enabled": True,
                "v3_enabled": True
            }
        }
        with open('dcc.cfg', 'w') as f:
            json.dump(dcc_config, f, indent=4)

async def check_tools():
    """Required tools check karo"""
    tools_status = []
    
    # Check apktool
    apktool_paths = [
        'tools/apktool.jar',
        'tools/apktool',
        'tools/apktool.bat'
    ]
    
    apktool_found = False
    for path in apktool_paths:
        if os.path.exists(path):
            apktool_found = True
            break
    
    tools_status.append(f"Apktool: {'✅' if apktool_found else '❌'}")
    
    # Check NDK
    ndk_found = False
    if os.path.exists('ndk-build') or os.path.exists('ndk-build.cmd'):
        ndk_found = True
    else:
        # Check in PATH
        ndk_path = shutil.which('ndk-build')
        if ndk_path:
            ndk_found = True
    
    tools_status.append(f"Android NDK: {'✅' if ndk_found else '❌'}")
    
    # Check apksigner
    signer_found = os.path.exists('tools/apksigner.jar')
    tools_status.append(f"APK Signer: {'✅' if signer_found else '❌'}")
    
    return tools_status, apktool_found and ndk_found and signer_found

# ==================== BOT HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    welcome_msg = f"""
🌟 *Welcome to DCC Bot!* 🌟

Hello {user.first_name}! I can convert Android APKs to C++ code using Dex2C.

📱 *What I can do:*
• Convert APK to C++ source
• Rebuild and sign APK
• Optimize Android code

🎯 *Commands:*
/start - Show this message
/help - Detailed help
/status - Check system status
/limit - Check your usage limit
/convert - Convert APK (send APK file)
/about - About this bot

✨ *How to use:*
1. Send me an APK file
2. Wait for processing
3. Download converted APK

⚡ *User Limit: {USER_LIMITS["default"]} conversions* (Owner: Unlimited)
"""
    await update.message.reply_text(welcome_msg, parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = """
📚 *Detailed Help Guide*

🔧 *Setup Requirements:*
• Android NDK installed
• Apktool in tools/ folder
• Java Runtime Environment
• Debug keystore for signing

📋 *Supported Features:*
• Full APK to C++ conversion
• Method filtering
• String obfuscation
• Custom loader support
• Automatic APK signing

⚙️ *Advanced Options:*
Send APK with caption:
`--obfuscate` - Obfuscate strings
`--filter file.txt` - Custom filter
`--custom-loader class` - Custom loader

💡 *Example:*
Send APK with caption: `--obfuscate --filter myfilter.txt`

⚠️ *Limits:*
• Normal users: {USER_LIMITS["default"]} conversions
• Owner: Unlimited
• Max file size: 100MB

❓ *Need help?*
Contact: @username
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """System status check"""
    status_msg = "🔍 *System Status*\n\n"
    
    # Check directories
    status_msg += "📁 *Directories:*\n"
    for dir_name in ['.tmp', 'downloads', 'output', 'project', 'tools']:
        exists = os.path.exists(dir_name)
        status_msg += f"• {dir_name}: {'✅' if exists else '❌'}\n"
    
    # Check tools
    status_msg += "\n🛠️ *Tools:*\n"
    tools_status, all_ok = await check_tools()
    for status in tools_status:
        status_msg += f"• {status}\n"
    
    # Check config
    status_msg += "\n⚙️ *Configuration:*\n"
    if os.path.exists('dcc.cfg'):
        with open('dcc.cfg', 'r') as f:
            config = json.load(f)
        status_msg += f"• NDK Dir: {'✅' if config.get('ndk_dir') else '❌'}\n"
        status_msg += f"• Signing: {'✅' if config.get('signature') else '❌'}\n"
    else:
        status_msg += "• dcc.cfg: ❌\n"
    
    # Overall status
    status_msg += f"\n📊 *Overall Status:* {'✅ READY' if all_ok else '❌ NOT READY'}\n"
    
    await update.message.reply_text(status_msg, parse_mode=ParseMode.MARKDOWN)

async def limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check user limit"""
    user_id = update.effective_user.id
    count = user_conversion_count.get(str(user_id), 0)
    limit = get_user_limit(user_id)
    
    if user_id == OWNER_ID:
        remaining = "Unlimited"
        msg = f"""
👤 *User:* Owner
📊 *Conversions:* {count}
∞ *Remaining:* Unlimited
✨ *Status:* Premium User
"""
    else:
        remaining = max(0, limit - count)
        msg = f"""
👤 *User:* {update.effective_user.first_name}
📊 *Conversions:* {count}/{limit}
🎯 *Remaining:* {remaining}
💎 *Upgrade:* Contact owner
"""
    
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """About bot"""
    about_text = """
🤖 *DCC Bot v1.0*

A Telegram bot for Android APK to C++ conversion using Dex2C technology.

✨ *Features:*
• APK to C++ conversion
• Method filtering
• String obfuscation
• Custom loader support
• Automatic signing
• User limit system

🔧 *Powered by:*
• Androguard
• Dex2C
• Apktool
• Android NDK

👨‍💻 *Developer:* @username
📱 *Version:* 1.0.0
⚡ *Status:* Active

📌 *Note:* Educational purposes only
"""
    await update.message.reply_text(about_text, parse_mode=ParseMode.MARKDOWN)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel ongoing operation"""
    user_id = update.effective_user.id
    if user_id in processing_users:
        processing_users[user_id]['cancelled'] = True
        await update.message.reply_text("✅ Operation cancelled!")
    else:
        await update.message.reply_text("❌ No ongoing operation!")

async def handle_apk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle APK file upload"""
    user_id = update.effective_user.id
    
    # Check if user is already processing
    if user_id in processing_users:
        await update.message.reply_text("⏳ You already have a conversion in progress! Please wait or use /cancel")
        return
    
    # Check user limit
    can_convert, remaining = check_user_limit(user_id)
    if not can_convert:
        keyboard = [[InlineKeyboardButton("👤 Contact Owner", url=f"tg://user?id={OWNER_ID}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"❌ You have reached your limit of {USER_LIMITS['default']} conversions!\n"
            f"Contact owner to increase your limit.",
            reply_markup=reply_markup
        )
        return
    
    # Get file
    file = await update.message.effective_attachment.get_file()
    
    # Check file extension
    if not file.file_path.endswith('.apk'):
        await update.message.reply_text("❌ Please send an APK file!")
        return
    
    # Check file size (100MB limit)
    if file.file_size > 100 * 1024 * 1024:
        await update.message.reply_text("❌ File too large! Maximum size is 100MB")
        return
    
    # Parse options from caption
    caption = update.message.caption or ""
    obfuscate = '--obfuscate' in caption
    filter_file = None
    custom_loader = "dcc.Dex2c.vaibhavsatpute"
    
    if '--filter' in caption:
        parts = caption.split('--filter')
        if len(parts) > 1:
            filter_file = parts[1].strip().split()[0]
    
    if '--custom-loader' in caption:
        parts = caption.split('--custom-loader')
        if len(parts) > 1:
            custom_loader = parts[1].strip().split()[0]
    
    # Download APK
    progress_msg = await update.message.reply_text("📥 Downloading APK...")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    input_path = f"downloads/{user_id}_{timestamp}.apk"
    output_path = f"output/{user_id}_{timestamp}_converted.apk"
    
    await file.download_to_drive(input_path)
    await progress_msg.edit_text("✅ APK downloaded!\n🔄 Starting conversion...")
    
    # Set processing flag
    processing_users[user_id] = {
        'input': input_path,
        'output': output_path,
        'progress_msg': progress_msg,
        'cancelled': False,
        'start_time': time.time()
    }
    
    try:
        # Ensure directories
        create_tmp_directory()
        
        # Backup jni folder
        backup_path = backup_jni_project_folder()
        
        # Run conversion in thread
        queue = Queue()
        thread = Thread(
            target=run_conversion,
            args=(input_path, output_path, obfuscate, filter_file, custom_loader, queue)
        )
        thread.start()
        
        # Wait for result with periodic cancellation check
        while thread.is_alive():
            await asyncio.sleep(1)
            if processing_users[user_id]['cancelled']:
                # Cleanup
                if os.path.exists(input_path):
                    os.remove(input_path)
                if os.path.exists(output_path):
                    os.remove(output_path)
                await progress_msg.edit_text("❌ Conversion cancelled!")
                del processing_users[user_id]
                restore_jni_project_folder(backup_path)
                clean_tmp_directory()
                return
        
        # Get result
        success, message = queue.get()
        
        if success and os.path.exists(output_path):
            # Update user count
            user_conversion_count[str(user_id)] = user_conversion_count.get(str(user_id), 0) + 1
            save_user_db()
            
            # Send converted APK
            await progress_msg.edit_text("✅ Conversion complete!\n📤 Uploading APK...")
            
            with open(output_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"converted_{timestamp}.apk",
                    caption=f"✅ Conversion successful!\n"
                           f"📊 Total conversions: {user_conversion_count[str(user_id)]}/{get_user_limit(user_id)}"
                )
            
            # Cleanup
            os.remove(output_path)
        else:
            await progress_msg.edit_text(f"❌ Conversion failed!\nError: {message}")
        
        # Cleanup input file
        if os.path.exists(input_path):
            os.remove(input_path)
        
        # Restore jni folder and clean tmp
        restore_jni_project_folder(backup_path)
        clean_tmp_directory()
        
    except Exception as e:
        await progress_msg.edit_text(f"❌ Error: {str(e)[:200]}")
    finally:
        # Remove from processing
        if user_id in processing_users:
            del processing_users[user_id]

def run_conversion(input_path, output_path, obfuscate, filter_file, custom_loader, queue):
    """Run DCC conversion in separate thread"""
    try:
        # Create filter file if provided
        filtercfg = "filter.txt"
        if filter_file and os.path.exists(filter_file):
            filtercfg = filter_file
        
        # Run dcc_main
        dcc_main(
            apkfile=input_path,
            obfus=obfuscate,
            filtercfg=filtercfg,
            custom_loader=custom_loader,
            outapk=output_path,
            do_compile=True,
            project_dir=None,
            source_archive="project-source.zip"
        )
        
        queue.put((True, "Success"))
    except Exception as e:
        queue.put((False, str(e)))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "check_status":
        await status_command(update, context)
    elif query.data == "check_limit":
        await limit_command(update, context)

def main():
    """Main function"""
    # Load user database
    load_user_db()
    
    # Ensure directories
    asyncio.run(ensure_directories())
    
    # Create bot application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("limit", limit_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_apk))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("🤖 DCC Bot is running...")
    print(f"👤 Owner ID: {OWNER_ID}")
    print(f"📊 User Limit: {USER_LIMITS['default']}")
    print("Press Ctrl+C to stop")
    
    # Start bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    # Update requirements.txt
    requirements = """python-telegram-bot==20.7
networkx
pydot>=1.4.1
future
pyasn1
cryptography
lxml>=4.3.0
asn1crypto>=0.24.0
androguard==3.4.0a1
dex2c
pillow
aiofiles
"""
    with open('requirements.txt', 'w') as f:
        f.write(requirements)
    
    print("✅ requirements.txt updated!")
    print("\n📦 Install requirements:")
    print("pip install -r requirements.txt")
    print("\n🤖 Edit main.py and set:")
    print("1. BOT_TOKEN = 'your_bot_token'")
    print("2. OWNER_ID = your_telegram_id")
    print("\n🚀 Run bot:")
    print("python main.py")
    
    # Check if BOT_TOKEN is set
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("\n⚠️  WARNING: Please set your BOT_TOKEN in main.py!")
    else:
        main()