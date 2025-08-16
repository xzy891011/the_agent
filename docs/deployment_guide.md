# 天然气碳同位素智能分析系统 - 部署指南

## 概述

本指南详细说明了天然气碳同位素智能分析系统的部署流程，包括单机部署、集群部署、Docker容器化部署等多种方案。

## 部署架构

### 单机部署架构

```
┌─────────────────────────────────────────────────┐
│                    单机服务器                     │
├─────────────────────────────────────────────────┤
│  Frontend (React)     │  Backend (FastAPI)      │
├─────────────────────────────────────────────────┤
│  PostgreSQL  │  Redis  │  Elasticsearch  │  MinIO │
└─────────────────────────────────────────────────┘
```

### 集群部署架构

```
┌─────────────────────────────────────────────────┐
│                    负载均衡器                     │
├─────────────────────────────────────────────────┤
│  Frontend Node 1  │  Frontend Node 2           │
├─────────────────────────────────────────────────┤
│  Backend Node 1   │  Backend Node 2            │
├─────────────────────────────────────────────────┤
│  PostgreSQL主从   │  Redis集群   │  ES集群      │
└─────────────────────────────────────────────────┘
```

## 系统要求

### 硬件要求

**最低配置**:
- CPU: 4核心
- 内存: 8GB
- 存储: 100GB SSD
- 网络: 1Gbps

**推荐配置**:
- CPU: 8核心 (Intel i7 或 AMD Ryzen 7)
- 内存: 32GB
- 存储: 500GB NVMe SSD
- 网络: 10Gbps
- GPU: NVIDIA GTX 1080 或更高 (可选)

**生产环境**:
- CPU: 16核心 (Intel Xeon 或 AMD EPYC)
- 内存: 64GB+
- 存储: 1TB+ NVMe SSD (RAID 10)
- 网络: 10Gbps+
- GPU: NVIDIA RTX 3080 或更高 (可选)

### 软件要求

**操作系统**:
- Ubuntu 20.04 LTS 或更高版本
- CentOS 8 或更高版本
- Red Hat Enterprise Linux 8+
- Debian 11+

**依赖软件**:
- Python 3.9+
- Node.js 18+
- PostgreSQL 13+
- Redis 6+
- Elasticsearch 7.x/8.x
- MinIO Server
- Nginx 1.18+

## 快速部署 (Docker)

### 1. 准备工作

```bash
# 克隆项目
git clone <repository-url>
cd isotope-analysis-system

# 创建环境文件
cp .env.example .env
# 编辑 .env 文件配置参数
```

### 2. Docker Compose 部署

```bash
# 构建和启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f app
```

### 3. 验证部署

```bash
# 检查API服务
curl http://localhost:7102/health

# 检查前端服务
curl http://localhost:3000

# 检查数据库连接
docker-compose exec app python -c "from app.core.config import ConfigManager; print('Config OK')"
```

## 详细部署步骤

### 1. 环境准备

#### 1.1 创建部署用户

```bash
# 创建应用用户
sudo useradd -m -s /bin/bash isotope
sudo usermod -aG sudo isotope

# 切换到应用用户
sudo su - isotope
```

#### 1.2 安装系统依赖

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3.10-dev \
    postgresql postgresql-contrib redis-server nginx \
    git curl wget unzip build-essential

# CentOS/RHEL
sudo yum update
sudo yum install -y python39 python39-devel postgresql-server \
    redis nginx git curl wget unzip gcc gcc-c++ make
```

#### 1.3 安装 Node.js

```bash
# 使用 NodeSource 仓库
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# 验证安装
node --version
npm --version
```

### 2. 数据库配置

#### 2.1 PostgreSQL 配置

```bash
# 初始化数据库
sudo postgresql-setup initdb  # CentOS/RHEL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# 创建数据库和用户
sudo -u postgres psql
```

```sql
-- 在 PostgreSQL 中执行
CREATE USER isotope_user WITH PASSWORD 'your_password';
CREATE DATABASE isotope_db OWNER isotope_user;
GRANT ALL PRIVILEGES ON DATABASE isotope_db TO isotope_user;
\q
```

#### 2.2 Redis 配置

```bash
# 启动 Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# 配置 Redis
sudo vim /etc/redis/redis.conf
# 设置密码: requirepass your_redis_password
sudo systemctl restart redis-server
```

#### 2.3 Elasticsearch 配置

```bash
# 下载和安装 Elasticsearch
wget https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-8.8.0-linux-x86_64.tar.gz
tar -xzf elasticsearch-8.8.0-linux-x86_64.tar.gz
sudo mv elasticsearch-8.8.0 /opt/elasticsearch
sudo chown -R isotope:isotope /opt/elasticsearch

# 配置 Elasticsearch
vim /opt/elasticsearch/config/elasticsearch.yml
```

```yaml
# elasticsearch.yml
cluster.name: isotope-cluster
node.name: isotope-node-1
network.host: 127.0.0.1
http.port: 9200
discovery.type: single-node
xpack.security.enabled: false
```

```bash
# 启动 Elasticsearch
/opt/elasticsearch/bin/elasticsearch -d
```

#### 2.4 MinIO 配置

```bash
# 下载 MinIO
wget https://dl.min.io/server/minio/release/linux-amd64/minio
chmod +x minio
sudo mv minio /usr/local/bin/

# 创建数据目录
sudo mkdir -p /opt/minio/data
sudo chown -R isotope:isotope /opt/minio

# 创建启动脚本
vim /opt/minio/start-minio.sh
```

```bash
#!/bin/bash
export MINIO_ROOT_USER=minioadmin
export MINIO_ROOT_PASSWORD=minioadmin123
/usr/local/bin/minio server /opt/minio/data --console-address ":9001"
```

```bash
chmod +x /opt/minio/start-minio.sh
nohup /opt/minio/start-minio.sh > /opt/minio/minio.log 2>&1 &
```

### 3. 应用部署

#### 3.1 代码部署

```bash
# 创建应用目录
sudo mkdir -p /opt/isotope
sudo chown -R isotope:isotope /opt/isotope

# 克隆代码
cd /opt/isotope
git clone <repository-url> .

# 创建虚拟环境
python3.10 -m venv venv
source venv/bin/activate
```

#### 3.2 安装依赖

```bash
# 安装 Python 依赖
pip install --upgrade pip
pip install -r requirements.txt

# 安装前端依赖
cd app/ui/petro_agent
npm install
npm run build
cd ../../..
```

#### 3.3 配置应用

```bash
# 复制配置文件
cp .env.example .env
cp config/config.example.yaml config/config.yaml

# 编辑配置文件
vim .env
```

```bash
# .env 配置示例
OPENAI_API_KEY=sk-your-openai-key
CLAUDE_API_KEY=sk-your-claude-key
MODEL_PROVIDER=openai

# 数据库配置
POSTGRES_URL=postgresql://isotope_user:your_password@localhost:5432/isotope_db
REDIS_URL=redis://:your_redis_password@localhost:6379
ELASTICSEARCH_URL=http://localhost:9200

# MinIO 配置
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123

# 记忆系统配置
MEMORY_NAMESPACE_ENABLED=true
MEMORY_FILTER_ENABLED=true
DYNAMIC_PROMPT_ENABLED=true
MEMORY_MONITOR_ENABLED=true
```

#### 3.4 初始化数据库

```bash
# 运行数据库初始化脚本
python scripts/init_database.py --create-tables
python scripts/init_elasticsearch.py --create-indices
```

### 4. 服务配置

#### 4.1 创建 Systemd 服务

```bash
# 创建后端服务
sudo vim /etc/systemd/system/isotope-backend.service
```

```ini
[Unit]
Description=Isotope Analysis System Backend
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=isotope
Group=isotope
WorkingDirectory=/opt/isotope
Environment=PATH=/opt/isotope/venv/bin
ExecStart=/opt/isotope/venv/bin/python -m app.api.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# 启用和启动服务
sudo systemctl daemon-reload
sudo systemctl enable isotope-backend
sudo systemctl start isotope-backend
```

#### 4.2 配置 Nginx

```bash
# 创建 Nginx 配置
sudo vim /etc/nginx/sites-available/isotope
```

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # 前端静态文件
    location / {
        root /opt/isotope/app/ui/petro_agent/dist;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
    
    # API 代理
    location /api/ {
        proxy_pass http://127.0.0.1:7102;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # WebSocket 代理
    location /ws/ {
        proxy_pass http://127.0.0.1:7102;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # 文件上传配置
    client_max_body_size 100M;
    
    # 日志配置
    access_log /var/log/nginx/isotope.access.log;
    error_log /var/log/nginx/isotope.error.log;
}
```

```bash
# 启用配置
sudo ln -s /etc/nginx/sites-available/isotope /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 5. SSL 配置 (可选)

```bash
# 安装 Certbot
sudo apt install certbot python3-certbot-nginx

# 获取 SSL 证书
sudo certbot --nginx -d your-domain.com

# 自动续期
sudo crontab -e
# 添加: 0 12 * * * /usr/bin/certbot renew --quiet
```

## 高可用部署

### 1. 负载均衡配置

```bash
# 安装 HAProxy
sudo apt install haproxy

# 配置 HAProxy
sudo vim /etc/haproxy/haproxy.cfg
```

```
global
    daemon
    maxconn 4096

defaults
    mode http
    timeout connect 5000ms
    timeout client 50000ms
    timeout server 50000ms

frontend isotope_frontend
    bind *:80
    default_backend isotope_backend

backend isotope_backend
    balance roundrobin
    server backend1 10.0.0.11:7102 check
    server backend2 10.0.0.12:7102 check
    server backend3 10.0.0.13:7102 check
```

### 2. 数据库集群

#### PostgreSQL 主从配置

```bash
# 主库配置 (postgresql.conf)
listen_addresses = '*'
wal_level = replica
max_wal_senders = 3
wal_keep_segments = 32
archive_mode = on
archive_command = 'cp %p /var/lib/postgresql/archive/%f'

# 从库配置
# 使用 pg_basebackup 创建从库
pg_basebackup -h master_ip -D /var/lib/postgresql/data -U replicator -P -v -R -X stream
```

#### Redis 集群配置

```bash
# 创建 Redis 集群
redis-cli --cluster create \
    10.0.0.11:7000 10.0.0.12:7000 10.0.0.13:7000 \
    10.0.0.11:7001 10.0.0.12:7001 10.0.0.13:7001 \
    --cluster-replicas 1
```

### 3. 文件存储集群

```bash
# MinIO 集群配置
minio server http://10.0.0.{11...14}/data{1...4} \
    --console-address ":9001"
```

## 监控配置

### 1. 系统监控

#### 安装 Prometheus

```bash
# 下载 Prometheus
wget https://github.com/prometheus/prometheus/releases/download/v2.40.0/prometheus-2.40.0.linux-amd64.tar.gz
tar -xzf prometheus-2.40.0.linux-amd64.tar.gz
sudo mv prometheus-2.40.0.linux-amd64 /opt/prometheus
sudo chown -R isotope:isotope /opt/prometheus

# 创建配置文件
vim /opt/prometheus/prometheus.yml
```

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'isotope-backend'
    static_configs:
      - targets: ['localhost:7102']
  
  - job_name: 'postgresql'
    static_configs:
      - targets: ['localhost:9187']
      
  - job_name: 'redis'
    static_configs:
      - targets: ['localhost:9121']
```

#### 安装 Grafana

```bash
# 安装 Grafana
wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -
echo "deb https://packages.grafana.com/oss/deb stable main" | sudo tee -a /etc/apt/sources.list.d/grafana.list
sudo apt update
sudo apt install grafana

# 启动 Grafana
sudo systemctl enable grafana-server
sudo systemctl start grafana-server
```

### 2. 应用监控

```python
# 在应用中添加监控指标
from prometheus_client import Counter, Histogram, Gauge

# 请求计数器
REQUEST_COUNT = Counter('requests_total', 'Total requests', ['method', 'endpoint'])

# 响应时间
REQUEST_DURATION = Histogram('request_duration_seconds', 'Request duration')

# 记忆使用情况
MEMORY_USAGE = Gauge('memory_usage_bytes', 'Memory usage by agent', ['agent_type'])
```

### 3. 日志管理

```bash
# 安装 ELK Stack
# Elasticsearch (已安装)
# Logstash
wget https://artifacts.elastic.co/downloads/logstash/logstash-8.8.0-linux-x86_64.tar.gz
tar -xzf logstash-8.8.0-linux-x86_64.tar.gz
sudo mv logstash-8.8.0 /opt/logstash

# Kibana
wget https://artifacts.elastic.co/downloads/kibana/kibana-8.8.0-linux-x86_64.tar.gz
tar -xzf kibana-8.8.0-linux-x86_64.tar.gz
sudo mv kibana-8.8.0 /opt/kibana

# 配置 Logstash
vim /opt/logstash/config/logstash.conf
```

```ruby
input {
  file {
    path => "/opt/isotope/logs/*.log"
    type => "isotope-logs"
  }
}

filter {
  if [type] == "isotope-logs" {
    grok {
      match => { "message" => "%{TIMESTAMP_ISO8601:timestamp} %{LOGLEVEL:level} %{GREEDYDATA:msg}" }
    }
  }
}

output {
  elasticsearch {
    hosts => ["localhost:9200"]
    index => "isotope-logs-%{+YYYY.MM.dd}"
  }
}
```

## 备份和恢复

### 1. 数据库备份

```bash
# 创建备份脚本
vim /opt/isotope/scripts/backup.sh
```

```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/opt/backup"

# 创建备份目录
mkdir -p $BACKUP_DIR

# PostgreSQL 备份
pg_dump -h localhost -U isotope_user isotope_db | gzip > $BACKUP_DIR/postgres_$DATE.sql.gz

# Redis 备份
redis-cli --rdb $BACKUP_DIR/redis_$DATE.rdb

# MinIO 备份
mc mirror minio/isotope-bucket $BACKUP_DIR/minio_$DATE/

# 删除 7 天前的备份
find $BACKUP_DIR -name "*" -mtime +7 -delete

echo "备份完成: $DATE"
```

```bash
# 设置定时备份
crontab -e
# 添加: 0 2 * * * /opt/isotope/scripts/backup.sh
```

### 2. 应用备份

```bash
# 备份配置文件
tar -czf /opt/backup/config_$(date +%Y%m%d).tar.gz \
    /opt/isotope/.env \
    /opt/isotope/config/ \
    /etc/nginx/sites-available/isotope
```

### 3. 恢复操作

```bash
# 恢复数据库
gunzip -c /opt/backup/postgres_20240101_020000.sql.gz | psql -h localhost -U isotope_user isotope_db

# 恢复 Redis
redis-cli --rdb /opt/backup/redis_20240101_020000.rdb

# 恢复 MinIO
mc mirror /opt/backup/minio_20240101_020000/ minio/isotope-bucket
```

## 性能优化

### 1. 系统优化

```bash
# 内核参数优化
sudo vim /etc/sysctl.conf
```

```
# 网络优化
net.core.rmem_max = 67108864
net.core.wmem_max = 67108864
net.ipv4.tcp_rmem = 4096 87380 67108864
net.ipv4.tcp_wmem = 4096 65536 67108864

# 文件描述符限制
fs.file-max = 2097152
```

```bash
# 应用用户限制
sudo vim /etc/security/limits.conf
```

```
isotope soft nofile 65536
isotope hard nofile 65536
isotope soft nproc 65536
isotope hard nproc 65536
```

### 2. 应用优化

```python
# 配置应用性能参数
# config/config.yaml
performance:
  max_workers: 8
  worker_connections: 1000
  keepalive_timeout: 65
  max_requests: 1000
  max_requests_jitter: 50
  
memory:
  cache_size: 10000
  max_memory_per_session: 100
  memory_cleanup_interval: 3600
```

### 3. 数据库优化

```sql
-- PostgreSQL 优化
-- postgresql.conf
shared_buffers = 2GB
effective_cache_size = 6GB
maintenance_work_mem = 512MB
work_mem = 64MB
max_connections = 200
```

## 故障排除

### 1. 常见问题

#### 服务无法启动
```bash
# 查看服务状态
sudo systemctl status isotope-backend

# 查看日志
sudo journalctl -u isotope-backend -f

# 检查端口占用
sudo netstat -tlnp | grep 7102
```

#### 数据库连接失败
```bash
# 检查数据库状态
sudo systemctl status postgresql

# 测试连接
psql -h localhost -U isotope_user -d isotope_db

# 检查配置
grep -n "listen_addresses" /etc/postgresql/*/main/postgresql.conf
```

#### 内存使用过高
```bash
# 查看内存使用
free -h
top -p $(pgrep -f "python.*app.api.main")

# 调整配置
# 减少 max_memory_per_session
# 启用内存压缩
# 增加内存清理频率
```

### 2. 性能问题

#### 响应缓慢
```bash
# 分析慢查询
tail -f /var/log/postgresql/postgresql-*.log | grep "slow"

# 检查缓存命中率
redis-cli info stats | grep keyspace

# 查看系统负载
htop
iostat -x 1
```

#### 磁盘空间不足
```bash
# 查看磁盘使用
df -h
du -sh /opt/isotope/data/*

# 清理日志
sudo logrotate -f /etc/logrotate.conf

# 清理过期数据
python /opt/isotope/scripts/cleanup_expired_data.py
```

### 3. 恢复操作

#### 紧急恢复
```bash
# 停止服务
sudo systemctl stop isotope-backend

# 恢复数据
./scripts/restore_database.sh latest

# 启动服务
sudo systemctl start isotope-backend

# 验证恢复
curl http://localhost:7102/health
```

#### 灾难恢复
```bash
# 从备份恢复整个系统
./scripts/disaster_recovery.sh --backup-date 20240101 --full-restore

# 验证系统
./scripts/verify_deployment.sh
```

## 安全配置

### 1. 防火墙配置

```bash
# 配置 UFW
sudo ufw enable
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow from 10.0.0.0/8 to any port 5432
sudo ufw allow from 10.0.0.0/8 to any port 6379
```

### 2. SSL/TLS 配置

```bash
# 生成强 DH 参数
sudo openssl dhparam -out /etc/ssl/certs/dhparam.pem 2048

# 配置 Nginx SSL
sudo vim /etc/nginx/sites-available/isotope
```

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_dhparam /etc/ssl/certs/dhparam.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    
    # 其他配置...
}
```

### 3. 访问控制

```bash
# 创建访问控制规则
sudo vim /etc/nginx/conf.d/security.conf
```

```nginx
# 限制访问频率
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=upload:10m rate=1r/s;

server {
    # API 限制
    location /api/ {
        limit_req zone=api burst=20 nodelay;
    }
    
    # 上传限制
    location /api/v1/files/upload {
        limit_req zone=upload burst=5 nodelay;
    }
    
    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';" always;
}
```

## 维护计划

### 1. 日常维护

```bash
# 创建维护脚本
vim /opt/isotope/scripts/daily_maintenance.sh
```

```bash
#!/bin/bash
# 日常维护脚本

# 检查服务状态
systemctl is-active isotope-backend > /dev/null || systemctl restart isotope-backend

# 清理临时文件
find /opt/isotope/data/temp -name "*" -mtime +1 -delete

# 检查磁盘空间
DISK_USAGE=$(df /opt/isotope | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 80 ]; then
    echo "磁盘空间不足: ${DISK_USAGE}%" | mail -s "磁盘空间警告" admin@yourcompany.com
fi

# 检查内存使用
MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.2f", $3/$2 * 100.0}')
if (( $(echo "$MEMORY_USAGE > 90" | bc -l) )); then
    echo "内存使用过高: ${MEMORY_USAGE}%" | mail -s "内存使用警告" admin@yourcompany.com
fi
```

### 2. 定期维护

```bash
# 周维护
vim /opt/isotope/scripts/weekly_maintenance.sh
```

```bash
#!/bin/bash
# 周维护脚本

# 数据库维护
psql -h localhost -U isotope_user -d isotope_db -c "VACUUM ANALYZE;"

# 清理过期记忆
python /opt/isotope/scripts/cleanup_expired_memories.py

# 优化缓存
redis-cli FLUSHDB
```

### 3. 月度维护

```bash
# 月维护
vim /opt/isotope/scripts/monthly_maintenance.sh
```

```bash
#!/bin/bash
# 月维护脚本

# 完整备份
/opt/isotope/scripts/full_backup.sh

# 系统更新
sudo apt update && sudo apt upgrade -y

# 日志轮转
sudo logrotate -f /etc/logrotate.conf

# 性能分析
python /opt/isotope/scripts/performance_analysis.py --output /opt/isotope/reports/
```

---

*本部署指南版本: v2.0.0*  
*最后更新: 2024年12月*  
*维护人员: 运维团队* 