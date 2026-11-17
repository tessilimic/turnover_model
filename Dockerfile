FROM python:3.12-slim

# Hugging Face Spaces runs the container as UID 1000.
RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# No PostgreSQL on Hugging Face Spaces: default to a SQLite file
# (ephemeral, lost on restart). docker-compose.yml overrides it with PostgreSQL.
RUN mkdir -p $HOME/db
ENV DATABASE_URL=sqlite:////home/user/db/turnover.db

WORKDIR $HOME/app

# Dependencies first, so this layer is cached when only the code changes.
COPY --chown=user requirements.txt .
RUN pip install --user -r requirements.txt

COPY --chown=user . .

# Port expected by Spaces (app_port in README.md).
EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
