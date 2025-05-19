FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴與 Playwright 相依套件
RUN apt-get update && apt-get install -y \
    curl gnupg unzip wget \
    libglib2.0-0 libnss3 libgconf-2-4 libfontconfig1 \
    libxss1 libasound2 libatk1.0-0 libatk-bridge2.0-0 \
    libgtk-3-0 libx11-xcb1 libxcb-dri3-0 libdrm2 \
    libxcomposite1 libxdamage1 libxrandr2 \
    libu2f-udev libvulkan1 libpci3 \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Cloud SQL Proxy
RUN curl -Lo /usr/local/bin/cloud_sql_proxy https://github.com/GoogleCloudPlatform/cloud-sql-proxy/releases/download/v2.10.0/cloud-sql-proxy.linux.amd64 && \
    chmod +x /usr/local/bin/cloud_sql_proxy


# 拷貝 requirements.txt 並安裝 Python 套件（這一層會被快取）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 安裝 Playwright 瀏覽器（獨立執行，利於 cache）
RUN playwright install --with-deps chromium

# 再拷貝剩餘程式碼（這一層若變動不會影響 requirements 安裝）
COPY . .

# 設定環境變數
ENV FLASK_APP=run.py
ENV PYTHONUNBUFFERED=1

# 掛載 Cloud SQL socket
VOLUME ["/cloudsql"]

# 開放埠口
EXPOSE 8080

# 執行 Cloud SQL Proxy + Flask 應用
ENTRYPOINT ["bash", "-c"]
CMD ["cloud_sql_proxy --unix-socket /cloudsql/$CLOUD_SQL_CONNECTION_NAME & exec flask run --host=0.0.0.0 --port=8080"]

