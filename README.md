# SayItBetterBot

Telegram-бот «Сделай нормально»: отправляешь текст как есть (с ошибками, сленгом, в двух словах) — получаешь понятный естественный вариант в нужном стиле.

Содержание
- [Возможности](#возможности)
- [Быстрый старт](#быстрый-старт)
- [Конфигурация](#конфигурация)
- [LLM-провайдеры](#llm-провайдеры)
- [Архитектура](#архитектура)
- [Прод-режим](#прод-режим)
- [Тесты и CI](#тесты-и-ci)
- [Деплой на Vercel](#деплой-на-vercel)

## Возможности

**Ядро**
1. `/start` → приветствие «Сделай нормально»
2. Любой текст → «Понял. Какой вариант сделать?» → 6 стилей: Нормально, Официально, Дружелюбно, Мягко, Коротко, Уверенно + «Свой стиль»
3. Автоопределение языка (ru/uk/en) + кнопка «Перевести» (выбор языка результата)
4. 3 варианта результата (главный + 2 альтернативы), все разные

**Карточка результата**
5. Редактируется на месте (без лишних сообщений)
6. Копирование по номеру варианта: «Скопировать 1/2/3» (tap-to-copy блок `<pre>`)
7. Быстрые трансформации: Короче / Мягче / Официальнее; «Стиль» — сменить стиль; «Ещё…» раскрывает: Сохранить 1/2/3, Исправить ошибки, Ответить, Перевести
8. Умные подсказки по intent в карточке (отмена → «предложить другую дату», извинение → «сделать мягче» и т.д.)
9. Итдикатор «печатает…» на время генерации; `/cancel` — выход из режимов «свой стиль»/сценарий
10. Контекст: reply на чужое сообщение = ответ; «она пишет: …» = режим «Что ответить?»

**Доп. ввод и функции**
11. Голосовые (Whisper через OpenAI-compatible API), фото (Vision OCR)
12. История: `/history` с пагинацией (страницы стрелками, превью-кнопка, «повторить» на каждом элементе), `/forget`
13. Избранное: `/favorites` с inline-просмотром (тост с полным текстом) и удалением кнопкой; legacy-команда `/delfav_<id>` поддерживается
14. Стиль пользователя (`/mystyle`, `/setstyle`), получатель (`/to`), ситуации (`/situations`), генераторы `/decline /congrats /apology /ask`
15. Inline mode: `@бот текст` в любом чате
16. Приватность: `/privacy`, `/noprivacy`, `/yesprivacy`, `/forget`

**Монетизация, группы и надёжность**
17. Rate limit: 20/день free, 500 premium; апсейл «Premium: /premium» в сообщении о лимите
18. Premium через Telegram Stars (XTR): `/premium` → invoice → pre-checkout → `is_premium`; `/grantprem <tg_id>` для админа
19. Группы: бот отвечает только на reply на своё сообщение или @упоминание (mention вырезается из текста)
20. Интерфейс ru/uk/en (`app/i18n.py`, авто по `language_code` клиента); промпты LLM остаются на русском
21. PENDING переживает рестарт при наличии Redis (write-through + hydrate); без Redis — память (лимит 5000)
22. Телеметрия: таблица events (llm_error / error / gen / feedback / purchase), `/report`, расширенный `/admin` (авто-prune старше 3 дней)

## Быстрый старт

```bash
cp .env.example .env          # впиши BOT_TOKEN + GROQ_API_KEY и/или GEMINI_API_KEY
pip install -r requirements.txt
python -m app.main
```

Docker:

```bash
docker compose up --build
```

Без ключей бот работает в offline-fallback режиме (капитализация/шаблоны) — для проверки UX, но качество AI будет только с ключами.

## Конфигурация

Все переменные задаются в `.env` (шаблон — `.env.example`).

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `BOT_TOKEN` | — | Токен бота (обязателен) |
| `ADMIN_IDS` | — | Telegram id админов через запятую (доступ к `/admin`, `/grantprem`) |
| `GROQ_API_KEY` / `GEMINI_API_KEY` / `OPENAI_API_KEY` | — | Ключи LLM-провайдеров |
| `LLM_ORDER` | `groq,gemini,openai` | Порядок проб бэкендов |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data.db` | Postgres для прода: `postgresql+asyncpg://...` |
| `REDIS_URL` | — | FSM-хранилище + PENDING-кэш (опционально) |
| `WEBHOOK_URL` / `WEBHOOK_SECRET` / `WEBHOOK_PORT` | — | Webhook-режим (см. Прод-режим) |
| `FREE_DAILY_LIMIT` / `PREMIUM_DAILY_LIMIT` | 20 / 500 | Дневные лимиты |
| `PREMIUM_STARS_PRICE` | 150 | Цена Premium в звёздах XTR |
| `LOG_LEVEL` | INFO | Уровень логов |

## LLM-провайдеры

Все три — через OpenAI-совместимый `POST {base}/chat/completions`, пробуются по порядку `LLM_ORDER=groq,gemini,openai` до первого успеха.

| Провайдер | Base URL | Модель по умолчанию | Примечание |
|---|---|---|---|
| Groq (primary) | `https://api.groq.com/openai/v1` | `openai/gpt-oss-20b` | Быстрый, JSON-mode OK. STT: `whisper-large-v3-turbo`, Vision: `qwen/qwen2.5-vl` |
| Gemini (fallback) | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-3.5-flash` + автофолбэк по цепочке моделей | 2.x отключены Google в 2026, 3.x иногда 503 (высокий спрос) — цепочка это переживает |
| OpenAI (опционально) | `https://api.openai.com/v1` | `gpt-4o-mini` | Любой OpenAI-compatible endpoint (OpenRouter, локальные модели) |

Проверено вживую: Groq отвечает стабильно со строгим JSON; Gemini отвечает, но периодически 503 — поэтому он второй в очереди, а не первый.

Интеграционные тесты провайдера (retry, фолбэк бэкендов, JSON-режим, STT/Vision) — `tests/test_provider_integration.py` на `httpx.MockTransport`.

## Архитектура

```
Telegram → Bot API → handlers → rewrite_text() → LLMProvider → Response Formatter → Telegram
```

LLM возвращает строгий JSON: `intent, language, tone, meaning, rewritten_text, alternatives[], suggestion` (см. `app/schemas/rewrite.py`, `app/ai/prompts/`). Валидация и нормализация — `_normalize()` в провайдере.

Сервисы: `services/rewrite`, `services/styles` (каталог стилей + интент-детект), `services/speech` (STT), `services/vision` (OCR), `services/history` (SQLAlchemy-репозитории), `services/templates`.

## Структура проекта

```
app/
  main.py                  # сборка polling/webhook + build_dispatcher()
  i18n.py                  # строки интерфейса ru/uk/en
  vercel_entry.py          # (в корне) serverless ASGI entrypoint
  core/                    # config, db, migrations, redis_client, rate_limit
  bot/
    handlers/              # start, rewrite, voice, photo, history, scenarios,
                           # premium, feedback, admin, inline
    keyboards/             # inline-клавиатуры
    group_gate.py          # гейт для групп (reply/@mention)
    state.py               # PendingStore (Redis write-through + hydrate)
    formatting.py          # карточки результата, tap-to-copy
  services/                # rewrite, styles, templates, speech, vision
  ai/                      # provider.py (Groq/Gemini/OpenAI), prompts/
  database/                # models (users, usage, requests, results, favorites, events)
alembic/versions/          # миграции
scripts/check_migrations.py# 4 сценария ensure_schema (CI)
tests/                     # pytest: core, rate_limit, migrations, webhook, ux, i18n,
                           # provider_integration, pending_store, keyboards
Dockerfile / docker-compose.yml / vercel.json / .env.example
.github/workflows/ci.yml   # ruff + pytest matrix + alembic + docker + smoke
```

## Прод-режим

**Схема БД (alembic).** На старте `ensure_schema()` поднимает схему до head-ревизии:

- чистая БД — миграции создаёт с нуля;
- легаси-БД (создана `create_tables` до alembic) — авто-`stamp head` и апгрейд без пересоздания таблиц;
- любой сбой alembic — fallback на `create_tables()` (бот всё равно стартует);
- после апгрейда выполняется idempotent repair-pass `create_tables()`.

```bash
python -m alembic upgrade head                            # применить миграции
python -m alembic revision --autogenerate -m "описание"   # новая миграция
python -m alembic current / history
```

**Webhook вместо polling.** Задать в `.env`:

```
WEBHOOK_URL=https://your-domain.example/webhook
WEBHOOK_SECRET=change-me
WEBHOOK_PORT=8080
```

и раскомментировать `ports` сервиса bot в `docker-compose.yml`. Без `WEBHOOK_URL` бот работает в polling.

**Rate limit — атомарный.** Условный `UPDATE … WHERE count_text+count_voice+count_vision < limit`: гонки параллельных запросов не превышают лимит (`tests/test_rate_limit.py`).

**Наблюдаемость.** Необработанные ошибки апдейтов логируются и пишутся в events через `@dp.errors`; сбои LLM-бэкендов — через `error_callback` провайдера; уровень логов задаётся `LOG_LEVEL`.

**Healthcheck.** В docker `HEALTHCHECK` использует `python -m app.healthcheck` (в slim-образе нет pgrep/curl): в webhook-режиме дергает `GET /health`, в polling проверяет живость главного процесса; `GET /health` доступен и для балансировщика.

**Ограничение PENDING.** Тексты в ожидании выбора стиля ограничены `MAX_PENDING=5000` (самые старые вытесняются). С `REDIS_URL` store работает write-through в Redis (`tfb:pending`, TTL 24 ч) и `hydrate()` подтягивает записи после рестарта/с другого инстанса; без Redis — чистая память.

**Телеметрия (events).** Модель `Event`: `llm_error` (сбои бэкендов), `error` (необработанные апдейты), `gen` (время генерации в мс), `feedback` (`/report <текст>`), `purchase` (Stars), `grant`. `/admin` показывает 24ч-агрегаты и топ стилей; записи старше 3 дней чистятся автоматически.

**Telegram Stars / Premium.** `/premium` отправляет XTR-invoice (`PREMIUM_STARS_PRICE`, по умолчанию 150 звёзд); после `successful_payment` ставится `is_premium=True`. Апсейл встроен в сообщение о дневном лимите; `/grantprem <telegram_id>` доступен админу.

**Группы.** В группах/супергруппах бот обрабатывает только reply на своё сообщение или `@mention` (mention вырезается из текста) — `app/bot/group_gate.py`. В ЛС ограничений нет.

**Язык интерфейса.** `app/i18n.py`: ~45 ключей ru/uk/en, автоопределение по `language_code` клиента (ru — фолбэк). Кнопки/статусы/инвойс переведены; инструкции для LLM остаются на русском.

## Тесты и CI

```bash
pytest -q                  # весь набор
ruff check app tests vercel_entry.py scripts
python scripts/check_migrations.py   # 4 сценария ensure_schema
```

GitHub Actions (`.github/workflows/ci.yml`) при каждом push/PR запускает:

- Job **lint** — `ruff check`, переменные окружения не нужны;
- Job **tests** — pytest на Python 3.12 и 3.13;
- Job **migrations** — свежий апгрейд alembic + идемпотентный повтор + 4 сценария `ensure_schema`;
- Job **docker** — сборка Docker-образа с кэшем в GHA;
- Job **vercel-entrypoint** — импорт serverless entrypoint;
- Job **validate-vercel-json** — проверка корректности vercel.json.

## Деплой на Vercel

Репозиторий содержит `vercel_entry.py` — лёгкий ASGI-эндпоинт (webhook-only режим) и `vercel.json` (явный entrypoint `src`). Деплой:

```bash
npx vercel deploy
```

 Env-переменные задаются в Vercel Project Settings — те же, что в разделе «Конфигурация»; база данных строго Postgres (`DATABASE_URL`), рекомендован Redis. После деплоя установи webhook бота:

```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=<vercel-url>&secret_token=<WEBHOOK_SECRET>
```

Ограничение: polling на Vercel невозможен (serverless); для polling используй VPS + `docker compose up -d`.
