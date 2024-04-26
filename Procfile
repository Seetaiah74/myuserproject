release: python manage.py migrate
echo ${GOOGLE_CREDENTIALS} > /app/google-credentials.json
web: daphne myuserproject.asgi:application --port $PORT --bind 0.0.0.0 -v2