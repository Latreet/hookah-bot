import qrcode

BOT_USERNAME = "HookahClubGesh_bot"   # без @
url = f"https://t.me/{HookahClubGesh_bot}"

qrcode.make(url).save("bot_qr.png")
print("QR сохранён →", url)