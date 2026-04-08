FROM python:3.10

WORKDIR /app

# Copy both replica and shared modules from project root
COPY replica/ ./replica/
COPY shared/ ./shared/

# Install dependencies
RUN pip install --no-cache-dir fastapi uvicorn requests pydantic

EXPOSE 5000

# Run the real RAFT consensus server
CMD ["sh", "-c", "uvicorn replica.consensus.server:app --host 0.0.0.0 --port ${PORT:-5000}"]