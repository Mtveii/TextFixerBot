# PROGRESS — пакет "давай все" (9 пунктов)

ШАГ 1 (item 7): Интеграционные тесты LLM-провайдера — ВЫПОЛНЕН
  tests/test_provider_integration.py (8 тестов): primary success, 503→фолбэк бэкенда,
  429→alt-model в пределах бэкенда, JSON-mode reject→plain retry, all-fail→offline,
  error_callback телеметрия, STT, Vision. `LLMProvider(transport=...)` — инъекция MockTransport.

ШАГ 2 (items 6+9): Telemetry — ВЫПОЛНЕН
  Модель Event (kind/user_id/detail/duration_ms) + миграция 74e2b5b890f0_telemetry_events.
  repo: add_event / count_events_24h / recent_events / avg_gen_ms_24h / prune_events / top_styles.
  main: state.PROVIDER.error_callback → Event("llm_error"); @dp.errors → Event("error");
  _do_rewrite замеряет время генерации → Event("gen"). /report (handlers/feedback.py, kind="feedback").
  /admin расширен: топ стилей, 24h gen avg + llm_error/error/feedback/purchase counts,
  последние 5 фидбеков, prune старше 3 дней. /grantprem <tg_id>.
  ensure_schema после upgrade — repair-pass create_tables() (idempotent).

ШАГ 3 (item 1): Нумерация вариантов — ВЫПОЛНЕН
  format_multi: 1️⃣2️⃣3️⃣ нумерация. result_actions_kb(variants): Row1 «📋 1️⃣/📋 2️⃣/📋 3️⃣»
  (или одиночная «📋 Скопировать»), в expanded — «⭐ 1/2/3». on_fav берёт texts[idx]
  (раньше всегда texts[0]). on_copy уже поддерживал idx.

ШАГ 4 (item 2): Избранное/История inline — ВЫПОЛНЕН
  /favorites: кнопки ⭐<превью→тост> + ⛔(inline-удаление с перерендером; legacy /delfav_<id> остался).
  /history: history_list_kb (превью-кнопка + 🔁 на каждом элементе, пагинация ⬅️/📄x/y/➡️, hist:<page>).
  repo.get_history(+offset), count_history. histshow:<id> с owner-check.

ШАГ 5 (item 4): Premium — ВЫПОЛНЕН
  /premium + Telegram Stars: XTR invoice (PREMIUM_STARS_PRICE, default 150),
  pre_checkout валидация payload="premium_month", F.successful_payment → is_premium=True + Event("purchase").
  Апсейл в лимит-warn («💎 Premium — без дневного лимита: /premium»), /grantprem,
  BotCommand("premium") в main.set_commands. handlers/premium.py подключён в dp.
  Строки premium — uk/en через i18n.

ШАГ 6 (item 5): Групповой режим — ВЫПОЛНЕН
  app/bot/group_gate.py: group_gate(message, text) → (allowed, cleaned_text).
  В группах бот запрещён, кроме: reply-ответ на сообщение бота ИЛИ @mention
  (mention вырезается). state.BOT_USERNAME из bot.get_me() в main.
  Gate применён в on_text (продолжение custom-стиля и FSM-флоу не блокируются),
  voice и photo (reply-to или caption-mention).

ШАГ 7 (item 8): Redis-backed PENDING — ВЫПОЛНЕН
  PendingStore: attach_redis(client), write-through через asyncio.create_task
  (hset json + expire 24h), pop → hdel, async hydrate(uid) (вызывается в on_text,
  _do_rewrite, on_copy, on_fav; setdefault — сознательный no-op для Redis).
  main: PENDING.attach_redis(await get_redis(redis_url)). Тест со stub клиентом
  (tests/test_pending_store.py, 4 теста) + no-op путь.

ШАГ 8 (item 3): i18n — ВЫПОЛНЕН (core)
  app/i18n.py: ~45 ключей ru/uk/en + lang_of(User)/(language_code[:2]→ru fallback) + t/fmt.
  Style catalogue: titles uk/en для всех стилей/действий; style_label(code, lang="ru").
  Команда триггеров premium (invoice, activated, failed, invoice_error), warn лимита — uk/en.

ШАГ 9: Финальные прогоны — ВЫПОЛНЕН
  pytest 48 passed, ruff clean. Миграции: fresh upgrade (2 ревизии) + idempotent +
  ensure_schema legacy/no-version-table/again → 6 таблиц, head 74e2b5b890f0.
  Dry-run: polling wiring OK (set_commands, main() завершается), webhook e2e OK
  (/health 200, авторизация secret token: 200/403, drop_pending_updates).
  docker compose build OK.

