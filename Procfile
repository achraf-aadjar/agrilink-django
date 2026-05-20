web: python manage.py collectstatic --noinput && python manage.py migrate && gunicorn agrilink.wsgi --bind 0.0.0.0:$PORT --workers 2
