# CI Audit Application Container
# Used for: workers, producer
FROM registry.fedoraproject.org/fedora:42

# Install Python and dependencies
RUN dnf install -y \
    python3.13 \
    python3-pip \
    git \
    && dnf clean all

# Create application directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy source code and configuration
COPY src/ src/
COPY scripts/ scripts/
COPY config/ config/
COPY setup.py .
COPY README.md .

# Install package in development mode
RUN pip3 install -e .

# Create non-root user for security
RUN useradd -r -u 1001 -m -s /bin/bash ciaudit && \
    chown -R ciaudit:ciaudit /app

# Create data directory (will be bind-mounted in production)
RUN mkdir -p /app/data && chown ciaudit:ciaudit /app/data

# Switch to non-root user
USER ciaudit

# Default command: run worker
# Override with producer or other scripts via podman-compose
CMD ["python3", "scripts/worker.py"]
