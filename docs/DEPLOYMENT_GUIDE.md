# Инструкция по развертыванию на Windows Server

Упрощенное руководство по развертыванию MCP-сервера синтаксис-помощника 1С на Windows Server в локальной сети.

## 📋 Содержание

1. [Требования](#требования)
2. [Подготовка Docker образа](#подготовка-docker-образа)
3. [Развертывание на сервере](#развертывание-на-сервере)
4. [Проверка работоспособности](#проверка-работоспособности)
5. [Подключение клиентов](#подключение-клиентов)
6. [Обновление .hbk файла](#обновление-hbk-файла)
7. [Управление сервисом](#управление-сервисом)

---

## 🖥️ Требования

### На сервере должно быть установлено:
- Windows Server 2019+
- Docker Desktop
- 4+ ГБ RAM (рекомендуется 8 ГБ)

### Проверка Docker:
```powershell
docker --version
docker compose version
```

---

## 📦 Подготовка Docker образа

### На вашей рабочей машине:

```powershell
# 1. Перейти в директорию проекта
cd d:\Projects\python\help1c

# 2. Собрать Docker образ (обратите внимание на точку в конце!)
docker build -t help1c-mcp .

# 3. Экспортировать образ в файл
docker save help1c-mcp -o help1c-mcp.tar

# Образ сохранится в файл help1c-mcp.tar (~500 МБ)
```

---

## 🚀 Развертывание на сервере

### Шаг 1: Копирование файлов на сервер

Скопируйте на сервер в папку `C:\help1c-mcp\`:

```
C:\help1c-mcp\
├── help1c-mcp.tar           # Docker образ (из предыдущего шага)
├── docker-compose.yml       # Конфигурация
└── data\
    └── hbk\
        └── 1c_documentation.hbk  # Файл документации 1С
```

**Через сетевую папку:**
```powershell
# Создать директорию на сервере
New-Item -Path "C:\help1c-mcp" -ItemType Directory
New-Item -Path "C:\help1c-mcp\data\hbk" -ItemType Directory

# Скопировать файлы
Copy-Item "d:\Projects\python\help1c\help1c-mcp.tar" "\\SERVER\C$\help1c-mcp\"
Copy-Item "d:\Projects\python\help1c\docker-compose.yml" "\\SERVER\C$\help1c-mcp\"
Copy-Item "d:\Projects\python\help1c\data\hbk\*.hbk" "\\SERVER\C$\help1c-mcp\data\hbk\"
```

### Шаг 2: Загрузка образа на сервере

На сервере в PowerShell:

```powershell
# Перейти в директорию
cd C:\help1c-mcp

# Загрузить Docker образ
docker load -i help1c-mcp.tar

# Проверить, что образ загружен
docker images | Select-String "help1c-mcp"
```

### Шаг 3: Обновить docker-compose.yml

Замените в `C:\help1c-mcp\docker-compose.yml` строку `build: .` на `image: help1c-mcp`:

```yaml
mcp-server:
  image: help1c-mcp          # ← Изменить эту строку (было: build: .)
  container_name: mcp-1c-helper
  ports:
    - "8000:8000"
  # ... остальное без изменений
```

### Шаг 4: Запуск сервиса

```powershell
# Запустить контейнеры
docker compose up -d

# Проверить статус
docker compose ps
```

**Ожидаемый результат:**
```
NAME              STATUS              PORTS
es-1c-helper      Up 2 minutes        0.0.0.0:9200->9200/tcp
mcp-1c-helper     Up 1 minute         0.0.0.0:8000->8000/tcp
```

---

## ✅ Проверка работоспособности

### На сервере:

```powershell
# Проверка health endpoint
Invoke-RestMethod http://localhost:8000/health

# Проверка статуса индекса
Invoke-RestMethod http://localhost:8000/index/status
```

**Ожидаемый результат:**
```json
{
  "status": "healthy",
  "elasticsearch": "connected",
  "index_exists": true,
  "documents_count": 1234
}
```

### С клиентской машины:

Замените `SERVER_IP` на IP адрес сервера (например, `192.168.1.100`):

```powershell
Invoke-RestMethod http://SERVER_IP:8000/health
```

---

## 💻 Подключение клиентов

### Настройка VS Code на клиентских машинах

**Файл:** `%APPDATA%\Code\User\settings.json` (Windows) или `~/.config/Code/User/settings.json` (Linux)

```json
{
  "mcp.servers": {
    "1c-syntax-helper": {
      "command": "curl",
      "args": [
        "-X", "POST",
        "-H", "Content-Type: application/json",
        "-d", "@-",
        "http://SERVER_IP:8000/mcp"
      ]
    }
  }
}
```

**Замените `SERVER_IP`** на реальный IP адрес сервера:
- Пример: `http://192.168.1.100:8000/mcp`
- Или DNS имя: `http://help1c-server.local:8000/mcp`

### Проверка подключения в VS Code

1. Откройте VS Code
2. Нажмите `Ctrl+Shift+P`
3. Введите "MCP" и выберите команду для проверки подключения
4. В чате с AI попросите: "Найди справку по СтрДлина"

---

## 🔄 Обновление .hbk файла

### Способ 1: Обновление БЕЗ перезапуска контейнера (рекомендуется)

```bash
# 1. Заменить файл на сервере
cd /opt/help1c-mcp
cp /путь/к/новому/файлу.hbk data/hbk/1c_documentation.hbk

# 2. Запустить реиндексацию через API
curl -X POST http://localhost:8000/index/rebuild

# 3. Проверить результат
curl http://localhost:8000/index/status

# Готово! Контейнеры продолжают работать, пользователи не отключаются
```

**Время обновления:** ~1-5 минут в зависимости от размера файла

**Преимущества:**
- ✅ Нет простоя сервиса
- ✅ Пользователи не теряют подключение
- ✅ Elasticsearch данные сохраняются

### Способ 2: Обновление с перезапуском (если нужна полная очистка)

```bash
# 1. Заменить файл
cp /путь/к/новому/файлу.hbk data/hbk/1c_documentation.hbk

# 2. ПерезапусБЕЗ перезапуска (рекомендуется)

```powershell
# 1. Заменить файл на сервере
Copy-Item "путь\к\новому\файлу.hbk" "C:\help1c-mcp\data\hbk\1c_documentation.hbk" -Force

# 2. Запустить реиндексацию
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/index/rebuild"

# 3. Проверить результат
Invoke-RestMethod -Uri "http://localhost:8000/index/status"
```

⏱️ Время обновления: 1-5 минут  
✅ Пользователи не отключаются

### Способ 2: С перезапуском

```powershell
# 1. Заменить файл
Copy-Item "путь\к\новому\файлу.hbk" "C:\help1c-mcp\data\hbk\1c_documentation.hbk" -Force

# 2. Перезапустить контейнер
cd C:\help1c-mcp
docker compose restart mcp-server
```

⏱️ Простой: ~30 секунд

### Автоматизация

Создайте файл `C:\help1c-mcp\update-hbk.ps1`:

```powershell
$HbkSource = "\\server\share\1c_documentation.hbk"
$HbkDest = "C:\help1c-mcp\data\hbk\1c_documentation.hbk"

Write-Host "Копирование файла..."
Copy-Item $HbkSource $HbkDest -Force

Write-Host "Реиндексация..."
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/index/rebuild"

Write-Host "Готово!"
Invoke-RestMethod -Uri "http://localhost:8000/index/status"
```

Запускать: `.\update-hbk.ps1Просмотр логов только MCP сервера
docker compose logs -f mcp-server

# Просмотр статуса
docker compose ps

# Обновление образов (после изменения кода)
docker compose up -d --build

# Полная очистка (с удалением данных)
docker compose down -v
```

### Автоматический запуск при загрузке сервера

**Linux (systemd):**

Создайте файл `/etc/systemd/system/help1c-mcp.service`:

```ini
[Unit]
Description=1C Syntax Helper MCP Server
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/help1c-mcp
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Активируйте сервис:
```bash
sudo systemctl daemon-reload
sudo systemctl enable help1c-mcp
sudo systemctl start help1c-mcp
sudo systemctl status help1c-mcp
```

**Windows Server:**

В `docker-compose.yml` уже установлен `restart: unless-stopped`, поэтому контейнеры автоматически запустятся при загрузке сервера (если Docker Desktop настроен на автозапуск).

---

## 🛠️ Устранение проблем

### Проблема: Контейнеры не запускаются

**Диагностика:**
```bash
docpowershell
cd C:\help1c-mcp

# Запуск
docker compose up -d

# Остановка
docker compose down

# Перезапуск
docker compose restart

# Просмотр логов
docker compose logs -f

# Проверка статуса
docker compose ps
```

### Автозапуск

Контейнеры автоматически запускаются при загрузке сервера (настроено в docker-compose.yml: `restart: unless-stopped`

**Диагностика:**
```bash
curl http://localhost:8000/index/status
docker logs mcp-1c-helper -f
```

**Решение:**
```bash
# Проверить наличие .hbk файла
ls -lh /opt/help1c-mcp/data/hbk/

# Перезапустить с принудительной реиндексацией
docker compose restart mcp-server

# Или вручную через API
curl -X POST http://localhost:8000/index/rebuild
```

### Проблема: Нет доступа с клиентских машин

**Диагностика:**
```bash
# На сервере проверить, слушает ли порт
sudo netstat -tulpn | grep 8000

# С клиента проверить доступность
telnet SERVER_IP 8000
# или
curl http://SERVER_IP:8000/health
```

**Решение 1: Проверить firewall (Linux):**
```bash
# Ubuntu/Debian
sudo ufw allow 8000/tcp
sudo ufw reload

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

**Решение 2: Проверить firewall (Windows Server):**
```powershell
New-NetFirewallRule -DisplayName "Help1C MCP Server" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

### Проблема: Медленная работа поиска

**Д✅ Типичные проблемы

### Контейнеры не запускаются

```powershell
# Посмотреть логи
docker compose logs

# Порты заняты? Проверить:
netstat -ano | findstr ":8000"
netstat -ano | findstr ":9200"
```

### Нет доступа с клиентских машин

```powershell
# Открыть порт в firewall
New-NetFirewallRule -DisplayName "Help1C MCP" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow

# Проверить доступность
Test-NetConnection -ComputerName SERVER_IP -Port 8000
```

### Индексация не работает

```powershell
# Проверить наличие файла
dir C:\help1c-mcp\data\hbk\

# Перезапустить реиндексацию
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/index/rebuild"
```

---

## ✅ Чек-лист развертывания

- [ ] Docker Desktop установлен и запущен
- [ ] Образ загружен: `docker images | Select-String "help1c-mcp"`
- [ ] Файлы скопированы в `C:\help1c-mcp\`
- [ ] .hbk файл на месте: `C:\help1c-mcp\data\hbk\1c_documentation.hbk`
- [ ] Контейнеры запущены: `docker compose ps`
- [ ] Health check работает: `Invoke-RestMethod http://localhost:8000/health`
- [ ] Порт 8000 открыт в firewall
- [ ] Клиенты могут подключиться с других машин

---

**Дата:** 27.12.2025  
**Версия:** 2