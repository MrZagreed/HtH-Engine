# Discord Karaoke RPC (Pre-release)

Проект для вывода синхронизированных текстов Spotify в Discord Rich Presence.

## Для пользователя (максимально просто)
1. Распакуйте проект в любую папку.
2. Запустите `run.py` (двойной клик или `py -3.12 run.py`).
3. Выберите режим:
   - `API` — нужен Spotify Premium + Spotify API ключи.
   - `LOCAL` — без Premium, нужен только Discord Client ID.
4. Пройдите мастер первой настройки (вопросы появятся автоматически).
5. Готово: приложение само создаст окружение, установит зависимости и стартует.

## Что полностью автоматизировано
- Выбор совместимого Python (предпочтительно 3.12).
- Создание/пересоздание `duality_venv` при несовместимой версии.
- Установка зависимостей из `requirements.txt`.
- Перезапуск внутри venv.
- Мастер первой настройки по выбранному режиму.

## Где теперь лежат данные
После первого запуска создается папка:
- `duality_data/config/duality_config.json` — конфиг.
- `duality_data/cache/lyrics_cache.db` — SQLite кеш текстов.
- `duality_data/cache/spotify_oauth_cache.json` — OAuth cache Spotify.

Если раньше конфиг был в корне (`duality_config.json`), он автоматически переносится.

## Режимы
### LOCAL (без Premium)
- Запрашивается только `Discord Client ID`.
- Прогресс трека берется через Windows Media Session (точная позиция даже при старте в середине трека).
- Фолбэк: чтение заголовка окна Spotify.

### API (с Premium)
- Запрашиваются `Discord Client ID`, `Spotify Client ID`, `Spotify Secret`.
- Используется Spotify Web API.

## Источники текстов
Приоритет:
1. LRCLIB (synced/plain)
2. Genius
3. Musixmatch
4. AZLyrics
5. lyrics.ovh

Кеширование текстов — SQLite (`lyrics_cache.db`).

## Rich Presence
- Hover текст на картинке: `Discord Karaoke RPC by Mr.Zagreed`.
- Безопасная кнопка `Open in Spotify` (валидация URL).
- Защита от перегрузки RPC (мягкая частота обновлений).

## Быстрый запуск из терминала
```bash
py -3.12 run.py --mode=local
```
или
```bash
py -3.12 run.py --mode=api
```

## Если что-то не работает
1. Полностью перезапустите Discord.
2. Перезапустите приложение.
3. Проверьте логи в папке `logs/` (файлы `debug_*.log`).
