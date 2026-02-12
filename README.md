# Claude Code Telegram Control 🤖📱

**Remote control your Claude Code sessions from anywhere via Telegram**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

> **Mobile-first AI development** - Never let family events or travel block your development.

---

## 🎯 Problem → Solution

**Before:** Claude Code asks for approval → You're at kid's swim meet → Development blocked  
**After:** Get Telegram notification → Tap `/approve` → Development continues

---

## ⚡ Quick Start (5 minutes)

### 1. Create Telegram Bot
```
Telegram → @BotFather → /newbot → Copy token
Telegram → @getidsbot → /start → Copy user ID
```

### 2. Install
```bash
git clone https://github.com/ariel-shapira/claude-code-telegram-control
cd claude-code-telegram-control
pip3 install -r requirements.txt
cp .env.example .env
# Edit .env with your token and user ID
python3 bot.py
```

### 3. Test
```
Telegram → Find your bot → /start → /ping
```

---

## 📱 Commands

```
/task <description> - Create new task
/status             - Check Claude Code status  
/approve            - Approve pending action
/tasks              - List all tasks
/ping               - Test connection
```

**Example:** `/task Deploy progressive disclosure feature`

---

## 🏗️ How It Works

```
Phone (Telegram) → Bot (WSL) → Claude Code (Desktop)
     ↓                ↓              ↓
  Commands      File System      Executes Tasks
```

1. Send command from phone
2. Bot creates task file
3. Claude Code reads and executes
4. Bot sends status updates

---

## 🔒 Security

✅ User ID authentication  
✅ No exposed ports  
✅ Environment variables for secrets  
✅ File-based approval system  
✅ Audit logging  

---

## 📖 Use Cases

**Family Events:** Approve tasks during kid's sports games  
**Travel:** Deploy hotfixes from airport  
**Remote Work:** Monitor progress from coffee shops  

---

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md)

---

## 📜 License

MIT License - see [LICENSE](LICENSE)

---

**Built with ❤️ by [@ariel-shapira](https://github.com/ariel-shapira) - a dad who codes at swim meets**
