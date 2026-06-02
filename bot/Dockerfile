FROM python:3.12-slim

# Create non-root user for security
RUN groupadd --gid 1001 botuser \
    && useradd --uid 1001 --gid botuser --shell /bin/bash --create-home botuser

WORKDIR /app

# Install dependencies as root before switching user
COPY pyproject.toml ./

# Copy application source before pip install so find_packages() resolves correctly
COPY app/ ./app/

RUN pip install --no-cache-dir .

# Switch to non-root user
USER botuser

CMD ["python", "-m", "app.main"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 CMD python -c "import discord; print('ok')" || exit 1
