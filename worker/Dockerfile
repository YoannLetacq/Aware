FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /app

# Install dependencies as root before switching user
COPY pyproject.toml ./

# Copy application source before pip install so find_packages() resolves correctly
COPY app/ ./app/

RUN pip install --no-cache-dir . \
    && chown -R pwuser:pwuser /app

# Reuse the existing non-root pwuser from the base image (UID/GID 1001)
USER pwuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import google.genai; print('ok')" || exit 1

CMD ["python", "-m", "app.main"]
