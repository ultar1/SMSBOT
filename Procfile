web: hypercorn telegram_bot:app --bind "0.0.0.0:$PORT" --workers 1 --worker-class asyncio --graceful-timeout 60 --keep-alive 120 --access-log - --error-log - --log-level info