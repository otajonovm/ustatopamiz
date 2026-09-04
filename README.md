# Usta Topamiz (@ustatopamiz_uzbot)

Farg‘ona viloyati, Beshariq tumanidagi mijozlar va ustalarni Telegram orqali bog‘laydigan bot.

Mijoz muammo bo‘yicha e’lon qoldiradi — bot buyurtmani tegishli sohaning yopiq guruhiga yuboradi. Ustalar bot orqali ro‘yxatdan o‘tib, tasdiqlangach o‘z sohalari guruhiga bir martalik taklif havolasini oladi.

## Texnologiyalar

- Python 3.11+
- aiogram 3.x
- PostgreSQL + SQLAlchemy (asyncio)
- Alembic
- Redis (FSM)
- Docker Compose

## Tezkor ishga tushirish (Docker)

1. `.env` yarating:

   ```bash
   copy .env.example .env
   ```

2. `BOT_TOKEN` ni to‘ldiring. Hozircha bitta guruh bo‘lsa, `DEFAULT_GROUP_ID` yozing — barcha sohalar shu guruhga yuboriladi.
3. Admin tasdiqlashi uchun `ADMIN_IDS` ga o‘z Telegram `user_id` ingizni yozing.

3. Konteynerlarni ishga tushiring:

   ```bash
   docker compose up --build
   ```

Bot polling rejimida ishlaydi. PostgreSQL va Redis ham Compose ichida ko‘tariladi.

## Lokal ishga tushirish (Docker siz)

PostgreSQL va Redis oldindan ishlashi kerak. `.env` dagi `DATABASE_URL` va `REDIS_URL` `localhost` ga qaratilgan.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python -m bot.main
```

## Telegram sozlash

1. [@BotFather](https://t.me/BotFather) dan token oling, `.env` ga yozing.
2. Botni yopiq guruhga **administrator** qilib qo‘shing (xabar yuborish va taklif havolasi huquqi kerak).
3. Hozircha bitta guruh: `.env` da `DEFAULT_GROUP_ID` ga chat ID yozing. Ishga tushganda barcha sohalar shu guruhga yo‘naltiriladi.
4. Keyinroq har sohaga alohida guruh kerak bo‘lsa, `DEFAULT_GROUP_ID=0` qiling va:

   ```
   /set_group santexnika -1001234567890
   /set_group elektr -1001234567891
   /set_group maishiy -1001234567892
   /set_group qurilish -1001234567893
   ```

5. Holatni tekshirish: `/categories`

`group_id` 0 bo‘lsa, buyurtma guruhga ketmaydi — adminlarga ogohlantirish yuboriladi.

## Sohalar va hududlar

**Sohalar:** Santexnika, Elektr, Muzlatgich/Konditsioner, Qurilish.

**Hududlar (Beshariq):** Markaz, Rapqon, Oqtepa, Tovul, Boshqa.

## Qo‘lda test checklist

- [ ] `/start` — telefon so‘raladi, `request_contact` ishlaydi
- [ ] Asosiy menyu: buyurtma / usta / yordam
- [ ] Buyurtma: soha → hudud → matn / rasm / ovoz → guruhga post va **Bog'lanish**
- [ ] `group_id` sozlanmagan bo‘lsa, mijoz va adminlarga tushunarli xabar
- [ ] Usta arizasi adminlarga keladi: Tasdiqlash / Rad etish
- [ ] Tasdiqdan so‘ng ustaga `member_limit=1` taklif havolasi ketadi
- [ ] Rad etilganda ustaga xabar boradi
- [ ] `/categories` va `/set_group` faqat `ADMIN_IDS` uchun

## Loyiha tuzilmasi

```
├── alembic/
├── bot/
│   ├── database/models/
│   ├── filters/
│   ├── handlers/
│   ├── keyboards/
│   ├── middlewares/
│   ├── services/
│   └── states/
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```
