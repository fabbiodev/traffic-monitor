FROM python:3.12-slim

WORKDIR /app
COPY . .

# Speed up builds & keep layers small
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pybabel compile -d translations

EXPOSE 5000
CMD ["gunicorn", "-w", "4", "--bind", "0.0.0.0:5000", "app:app"]
