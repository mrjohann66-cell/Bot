# Telegram Video Sotish Boti

Ushbu bot **Python 3.10+** va **aiogram 3.x** yordamida yozilgan.

## Railway va Render Serverlariga Joylash:
Railway/Render "Script start.sh not found" xatosini bermasligi uchun loyihangiz ildiziga **Procfile** va **start.sh** fayllarini qo'shing.

1. **Procfile** fayli ichi:
```
worker: python bot.py
```

2. **start.sh** fayli ichi:
```bash
#!/bin/bash
python bot.py
```

## Lokal Ishga Tushirish:
1. `pip install -r requirements.txt`
2. `.env` faylini to'ldiring.
3. `python bot.py` orqali ishga tushiring.