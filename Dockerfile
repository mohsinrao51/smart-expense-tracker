FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so Docker can cache this layer and skip
# reinstalling packages every time only app code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# gunicorn instead of Flask's dev server (app.run) — the dev server
# is single-threaded, has no production hardening, and app.run() is
# never invoked here anyway since gunicorn imports the `app` object
# directly rather than running this file as __main__.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "3", "app:app"]
