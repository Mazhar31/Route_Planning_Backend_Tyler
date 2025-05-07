FROM python:3.12-slim

# Install required system packages and runtime dependencies
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    curl \
    gnupg \
    jq \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    libx11-6 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxtst6 \
    libxrandr2 \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgtk-3-0 \
    libxss1 \
    libu2f-udev \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Install latest stable Chrome and ChromeDriver via CfT JSON API
RUN curl -sSL https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json -o /tmp/versions.json && \
    CHROME_URL=$(jq -r '.channels.Stable.downloads.chrome[] | select(.platform == "linux64") | .url' /tmp/versions.json) && \
    CHROMEDRIVER_URL=$(jq -r '.channels.Stable.downloads.chromedriver[] | select(.platform == "linux64") | .url' /tmp/versions.json) && \
    mkdir -p /opt/chrome && \
    curl -sSL $CHROME_URL -o /tmp/chrome.zip && \
    unzip /tmp/chrome.zip -d /opt/chrome && \
    ln -s /opt/chrome/chrome-linux64/chrome /usr/bin/google-chrome && \
    curl -sSL $CHROMEDRIVER_URL -o /tmp/chromedriver.zip && \
    unzip /tmp/chromedriver.zip -d /tmp/ && \
    mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver && \
    chmod +x /usr/local/bin/chromedriver && \
    rm -rf /tmp/*

# Set environment variables
ENV PATH="/usr/local/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy app files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Expose Cloud Run's default port
EXPOSE 8080

# Start FastAPI app
CMD ["python", "run.py"]
