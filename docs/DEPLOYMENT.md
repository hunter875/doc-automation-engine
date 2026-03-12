# 🚀 Deployment Guide - Enterprise Multi-Tenant RAG

> Hướng dẫn chi tiết triển khai hệ thống RAG lên môi trường Production.

---

## 📑 Mục Lục

- [Yêu Cầu Hệ Thống](#-yêu-cầu-hệ-thống)
- [Docker Compose (Development/Staging)](#-docker-compose-developmentstaging)
- [AWS Production Deployment](#-aws-production-deployment)
- [Database Setup](#-database-setup)
- [SSL/TLS Configuration](#-ssltls-configuration)
- [Environment Variables](#-environment-variables)
- [Health Checks & Monitoring](#-health-checks--monitoring)
- [Backup & Recovery](#-backup--recovery)
- [Scaling Guide](#-scaling-guide)
- [Troubleshooting](#-troubleshooting)

---

## 💻 Yêu Cầu Hệ Thống

### Minimum Requirements (Development)

| Component | Specification |
|-----------|---------------|
| CPU | 2 cores |
| RAM | 4 GB |
| Storage | 20 GB SSD |
| OS | Ubuntu 20.04+ / Amazon Linux 2 |

### Recommended (Production)

| Component | Specification |
|-----------|---------------|
| API Server | 4 cores, 8 GB RAM |
| Celery Worker | 4 cores, 8 GB RAM |
| PostgreSQL | 2 cores, 4 GB RAM, 100 GB SSD |
| OpenSearch | 4 cores, 8 GB RAM, 200 GB SSD |
| Redis | 2 cores, 4 GB RAM |

### Software Requirements

- Docker 24.0+
- Docker Compose 2.20+
- Python 3.10+
- Nginx 1.24+ (reverse proxy)
- Certbot (SSL certificates)

---

## 🐳 Docker Compose (Development/Staging)

### docker-compose.yml

```yaml
version: "3.8"

services:
  # ============================================
  # API Server
  # ============================================
  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: rag-api
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - APP_ENV=development
      - DEBUG=true
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - POSTGRES_USER=${POSTGRES_USER:-raguser}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-ragpassword}
      - POSTGRES_DB=${POSTGRES_DB:-ragdb}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - OPENSEARCH_HOST=opensearch
      - OPENSEARCH_PORT=9200
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY:-minioadmin}
      - MINIO_SECRET_KEY=${MINIO_SECRET_KEY:-minioadmin}
      - MINIO_BUCKET=rag-documents
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - SECRET_KEY=${SECRET_KEY:-change-this-in-production}
    volumes:
      - ./app:/app/app:ro
      - ./logs:/app/logs
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      opensearch:
        condition: service_healthy
      minio:
        condition: service_started
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    networks:
      - rag-network

  # ============================================
  # Celery Worker
  # ============================================
  celery_worker:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: rag-celery-worker
    restart: unless-stopped
    command: celery -A app.worker.celery_app worker --loglevel=info --concurrency=4
    environment:
      - APP_ENV=development
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - POSTGRES_USER=${POSTGRES_USER:-raguser}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-ragpassword}
      - POSTGRES_DB=${POSTGRES_DB:-ragdb}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - OPENSEARCH_HOST=opensearch
      - OPENSEARCH_PORT=9200
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY:-minioadmin}
      - MINIO_SECRET_KEY=${MINIO_SECRET_KEY:-minioadmin}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./app:/app/app:ro
      - ./logs:/app/logs
    depends_on:
      - redis
      - postgres
      - opensearch
    networks:
      - rag-network

  # ============================================
  # Celery Beat (Scheduler)
  # ============================================
  celery_beat:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: rag-celery-beat
    restart: unless-stopped
    command: celery -A app.worker.celery_app beat --loglevel=info
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
    depends_on:
      - redis
    networks:
      - rag-network

  # ============================================
  # PostgreSQL
  # ============================================
  postgres:
    image: postgres:15-alpine
    container_name: rag-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-raguser}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-ragpassword}
      POSTGRES_DB: ${POSTGRES_DB:-ragdb}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/init-db.sql:/docker-entrypoint-initdb.d/init.sql:ro
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-raguser} -d ${POSTGRES_DB:-ragdb}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - rag-network

  # ============================================
  # Redis
  # ============================================
  redis:
    image: redis:7-alpine
    container_name: rag-redis
    restart: unless-stopped
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - rag-network

  # ============================================
  # OpenSearch
  # ============================================
  opensearch:
    image: opensearchproject/opensearch:2.11.0
    container_name: rag-opensearch
    restart: unless-stopped
    environment:
      - discovery.type=single-node
      - plugins.security.disabled=true
      - bootstrap.memory_lock=true
      - "OPENSEARCH_JAVA_OPTS=-Xms1g -Xmx1g"
      - cluster.name=rag-cluster
    ulimits:
      memlock:
        soft: -1
        hard: -1
      nofile:
        soft: 65536
        hard: 65536
    volumes:
      - opensearch_data:/usr/share/opensearch/data
    ports:
      - "9200:9200"
      - "9600:9600"
    healthcheck:
      test: ["CMD-SHELL", "curl -s http://localhost:9200/_cluster/health | grep -q '\"status\":\"green\"\\|\"status\":\"yellow\"'"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s
    networks:
      - rag-network

  # ============================================
  # OpenSearch Dashboards (Optional - Dev only)
  # ============================================
  opensearch-dashboards:
    image: opensearchproject/opensearch-dashboards:2.11.0
    container_name: rag-opensearch-dashboards
    restart: unless-stopped
    environment:
      - OPENSEARCH_HOSTS=["http://opensearch:9200"]
      - DISABLE_SECURITY_DASHBOARDS_PLUGIN=true
    ports:
      - "5601:5601"
    depends_on:
      - opensearch
    profiles:
      - dev
    networks:
      - rag-network

  # ============================================
  # MinIO (S3-compatible storage)
  # ============================================
  minio:
    image: minio/minio:latest
    container_name: rag-minio
    restart: unless-stopped
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ACCESS_KEY:-minioadmin}
      MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY:-minioadmin}
    volumes:
      - minio_data:/data
    ports:
      - "9000:9000"
      - "9001:9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - rag-network

  # ============================================
  # Nginx (Reverse Proxy)
  # ============================================
  nginx:
    image: nginx:1.25-alpine
    container_name: rag-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./certbot/conf:/etc/letsencrypt:ro
      - ./certbot/www:/var/www/certbot:ro
    depends_on:
      - api
    profiles:
      - production
    networks:
      - rag-network

# ============================================
# Volumes
# ============================================
volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local
  opensearch_data:
    driver: local
  minio_data:
    driver: local

# ============================================
# Networks
# ============================================
networks:
  rag-network:
    driver: bridge
```

### Dockerfile

```dockerfile
# Dockerfile
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser
RUN chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Chạy Docker Compose

```bash
# Development mode (with OpenSearch Dashboards)
docker-compose --profile dev up -d

# Production mode (with Nginx)
docker-compose --profile production up -d

# View logs
docker-compose logs -f api celery_worker

# Stop all services
docker-compose down

# Stop and remove volumes (CAUTION: Deletes all data)
docker-compose down -v
```

---

## ☁️ AWS Production Deployment

### Architecture Overview

```
                    ┌─────────────────┐
                    │   Route 53      │
                    │   (DNS)         │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   CloudFront    │
                    │   (CDN/WAF)     │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │      ALB        │
                    │ (Load Balancer) │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
┌────────▼────────┐ ┌────────▼────────┐ ┌────────▼────────┐
│   EC2 (API)     │ │   EC2 (API)     │ │   EC2 (Worker)  │
│   + Uvicorn     │ │   + Uvicorn     │ │   + Celery      │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
┌────────▼────────┐ ┌────────▼────────┐ ┌────────▼────────┐
│  RDS PostgreSQL │ │   OpenSearch    │ │  ElastiCache    │
│  (Private)      │ │   (Private)     │ │  (Redis)        │
└─────────────────┘ └─────────────────┘ └─────────────────┘
                             │
                    ┌────────▼────────┐
                    │       S3        │
                    │  (Documents)    │
                    └─────────────────┘
```

### Step 1: VPC Setup

```bash
# Tạo VPC với 2 public + 2 private subnets
aws ec2 create-vpc --cidr-block 10.0.0.0/16 --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=rag-vpc}]'

# Ghi lại VPC_ID
export VPC_ID=vpc-xxxxxxxxx
```

**VPC Configuration:**
- CIDR: `10.0.0.0/16`
- Public Subnets: `10.0.1.0/24`, `10.0.2.0/24` (multi-AZ)
- Private Subnets: `10.0.3.0/24`, `10.0.4.0/24` (multi-AZ)
- Internet Gateway attached to public subnets
- NAT Gateway for private subnets (outbound internet)

### Step 2: Security Groups

```bash
# API Server Security Group
aws ec2 create-security-group \
  --group-name rag-api-sg \
  --description "Security group for RAG API servers" \
  --vpc-id $VPC_ID

# Inbound rules for API SG
aws ec2 authorize-security-group-ingress \
  --group-id sg-api-xxxxx \
  --protocol tcp \
  --port 8000 \
  --source-group sg-alb-xxxxx  # Only from ALB

# RDS Security Group
aws ec2 create-security-group \
  --group-name rag-rds-sg \
  --description "Security group for RDS" \
  --vpc-id $VPC_ID

# Allow PostgreSQL from API SG only
aws ec2 authorize-security-group-ingress \
  --group-id sg-rds-xxxxx \
  --protocol tcp \
  --port 5432 \
  --source-group sg-api-xxxxx
```

**Security Group Rules:**

| Security Group | Inbound Port | Source |
|----------------|--------------|--------|
| ALB-SG | 80, 443 | 0.0.0.0/0 |
| API-SG | 8000 | ALB-SG |
| API-SG | 22 | Bastion-SG (SSH) |
| RDS-SG | 5432 | API-SG |
| Redis-SG | 6379 | API-SG |
| OpenSearch-SG | 9200 | API-SG |

### Step 3: RDS PostgreSQL

```bash
# Tạo RDS Subnet Group
aws rds create-db-subnet-group \
  --db-subnet-group-name rag-db-subnet \
  --db-subnet-group-description "Subnet group for RAG RDS" \
  --subnet-ids subnet-private-1 subnet-private-2

# Tạo RDS Instance
aws rds create-db-instance \
  --db-instance-identifier rag-postgres \
  --db-instance-class db.t3.medium \
  --engine postgres \
  --engine-version 15.4 \
  --master-username ragadmin \
  --master-user-password "YourSecurePassword123!" \
  --allocated-storage 100 \
  --storage-type gp3 \
  --vpc-security-group-ids sg-rds-xxxxx \
  --db-subnet-group-name rag-db-subnet \
  --backup-retention-period 7 \
  --multi-az \
  --storage-encrypted \
  --no-publicly-accessible \
  --db-name ragdb
```

### Step 4: ElastiCache Redis

```bash
# Tạo ElastiCache Subnet Group
aws elasticache create-cache-subnet-group \
  --cache-subnet-group-name rag-redis-subnet \
  --cache-subnet-group-description "Subnet group for RAG Redis" \
  --subnet-ids subnet-private-1 subnet-private-2

# Tạo Redis Cluster
aws elasticache create-replication-group \
  --replication-group-id rag-redis \
  --replication-group-description "RAG Redis cluster" \
  --engine redis \
  --engine-version 7.0 \
  --cache-node-type cache.t3.medium \
  --num-cache-clusters 2 \
  --cache-subnet-group-name rag-redis-subnet \
  --security-group-ids sg-redis-xxxxx \
  --at-rest-encryption-enabled \
  --transit-encryption-enabled
```

### Step 5: OpenSearch Domain

```bash
# Tạo OpenSearch Domain
aws opensearch create-domain \
  --domain-name rag-search \
  --engine-version OpenSearch_2.11 \
  --cluster-config \
    InstanceType=r6g.large.search,InstanceCount=2,DedicatedMasterEnabled=false \
  --ebs-options EBSEnabled=true,VolumeType=gp3,VolumeSize=200 \
  --vpc-options SubnetIds=subnet-private-1,SecurityGroupIds=sg-opensearch-xxxxx \
  --encryption-at-rest-options Enabled=true \
  --node-to-node-encryption-options Enabled=true \
  --domain-endpoint-options EnforceHTTPS=true \
  --access-policies '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"AWS": "*"},
      "Action": "es:*",
      "Resource": "arn:aws:es:ap-southeast-1:123456789:domain/rag-search/*"
    }]
  }'
```

### Step 6: S3 Bucket

```bash
# Tạo S3 Bucket
aws s3api create-bucket \
  --bucket rag-documents-prod \
  --region ap-southeast-1 \
  --create-bucket-configuration LocationConstraint=ap-southeast-1

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket rag-documents-prod \
  --versioning-configuration Status=Enabled

# Block public access
aws s3api put-public-access-block \
  --bucket rag-documents-prod \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# Enable encryption
aws s3api put-bucket-encryption \
  --bucket rag-documents-prod \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms"
      }
    }]
  }'
```

### Step 7: IAM Role cho EC2

```json
// rag-ec2-policy.json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::rag-documents-prod/*"
    },
    {
      "Sid": "S3ListBucket",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::rag-documents-prod"
    },
    {
      "Sid": "SecretsManagerAccess",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:ap-southeast-1:*:secret:rag/*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:log-group:/rag/*"
    }
  ]
}
```

```bash
# Tạo IAM Role
aws iam create-role \
  --role-name rag-ec2-role \
  --assume-role-policy-document file://trust-policy.json

# Attach policy
aws iam put-role-policy \
  --role-name rag-ec2-role \
  --policy-name rag-ec2-policy \
  --policy-document file://rag-ec2-policy.json

# Tạo Instance Profile
aws iam create-instance-profile --instance-profile-name rag-ec2-profile
aws iam add-role-to-instance-profile \
  --instance-profile-name rag-ec2-profile \
  --role-name rag-ec2-role
```

### Step 8: EC2 Launch Template

```bash
# User Data script (base64 encoded)
cat << 'EOF' > user-data.sh
#!/bin/bash
set -e

# Update system
yum update -y
amazon-linux-extras install docker -y

# Start Docker
systemctl start docker
systemctl enable docker

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/download/v2.23.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Clone application (hoặc pull từ ECR)
cd /opt
git clone https://github.com/your-org/ragPJ.git
cd ragPJ

# Get secrets from Secrets Manager
export OPENAI_API_KEY=$(aws secretsmanager get-secret-value --secret-id rag/openai --query SecretString --output text)
export DB_PASSWORD=$(aws secretsmanager get-secret-value --secret-id rag/database --query SecretString --output text)

# Start application
docker-compose -f docker-compose.prod.yml up -d
EOF

# Tạo Launch Template
aws ec2 create-launch-template \
  --launch-template-name rag-api-template \
  --version-description "v1.0" \
  --launch-template-data '{
    "ImageId": "ami-xxxxxxxxx",
    "InstanceType": "t3.large",
    "IamInstanceProfile": {"Name": "rag-ec2-profile"},
    "SecurityGroupIds": ["sg-api-xxxxx"],
    "UserData": "'$(base64 -w0 user-data.sh)'",
    "BlockDeviceMappings": [{
      "DeviceName": "/dev/xvda",
      "Ebs": {
        "VolumeSize": 50,
        "VolumeType": "gp3",
        "Encrypted": true
      }
    }],
    "TagSpecifications": [{
      "ResourceType": "instance",
      "Tags": [{"Key": "Name", "Value": "rag-api"}]
    }]
  }'
```

### Step 9: Auto Scaling Group

```bash
# Tạo Auto Scaling Group
aws autoscaling create-auto-scaling-group \
  --auto-scaling-group-name rag-api-asg \
  --launch-template LaunchTemplateName=rag-api-template,Version='$Latest' \
  --min-size 2 \
  --max-size 10 \
  --desired-capacity 2 \
  --vpc-zone-identifier "subnet-public-1,subnet-public-2" \
  --target-group-arns arn:aws:elasticloadbalancing:...:targetgroup/rag-api-tg/... \
  --health-check-type ELB \
  --health-check-grace-period 300

# Tạo Scaling Policy
aws autoscaling put-scaling-policy \
  --auto-scaling-group-name rag-api-asg \
  --policy-name rag-cpu-scale-out \
  --policy-type TargetTrackingScaling \
  --target-tracking-configuration '{
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ASGAverageCPUUtilization"
    },
    "TargetValue": 70.0
  }'
```

### Step 10: Application Load Balancer

```bash
# Tạo ALB
aws elbv2 create-load-balancer \
  --name rag-api-alb \
  --subnets subnet-public-1 subnet-public-2 \
  --security-groups sg-alb-xxxxx \
  --scheme internet-facing \
  --type application

# Tạo Target Group
aws elbv2 create-target-group \
  --name rag-api-tg \
  --protocol HTTP \
  --port 8000 \
  --vpc-id $VPC_ID \
  --health-check-path /health \
  --health-check-interval-seconds 30 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3

# Tạo HTTPS Listener
aws elbv2 create-listener \
  --load-balancer-arn arn:aws:elasticloadbalancing:...:loadbalancer/app/rag-api-alb/... \
  --protocol HTTPS \
  --port 443 \
  --certificates CertificateArn=arn:aws:acm:...:certificate/... \
  --default-actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:...:targetgroup/rag-api-tg/...

# Redirect HTTP to HTTPS
aws elbv2 create-listener \
  --load-balancer-arn arn:aws:elasticloadbalancing:...:loadbalancer/app/rag-api-alb/... \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=redirect,RedirectConfig='{Protocol=HTTPS,Port=443,StatusCode=HTTP_301}'
```

---

## 🗄 Database Setup

### PostgreSQL Initial Setup

```sql
-- scripts/init-db.sql

-- Create database (if not exists)
CREATE DATABASE ragdb;

-- Connect to database
\c ragdb;

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search

-- Create tables
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    billing_status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE user_tenant_roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL CHECK (role IN ('owner', 'admin', 'viewer')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, tenant_id)
);

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    file_name VARCHAR(255) NOT NULL,
    file_size_bytes BIGINT,
    mime_type VARCHAR(100),
    s3_key VARCHAR(500),
    status VARCHAR(50) DEFAULT 'processing' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    chunk_count INTEGER DEFAULT 0,
    embedding_model VARCHAR(100),
    error_message TEXT,
    tags TEXT[],
    uploaded_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE tenant_usage_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    operation_type VARCHAR(50),
    model_name VARCHAR(100),
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cost_usd DECIMAL(10, 6),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_documents_tenant ON documents(tenant_id);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_tags ON documents USING GIN(tags);
CREATE INDEX idx_usage_tenant_date ON tenant_usage_logs(tenant_id, created_at);
CREATE INDEX idx_user_roles_user ON user_tenant_roles(user_id);
CREATE INDEX idx_user_roles_tenant ON user_tenant_roles(tenant_id);
CREATE INDEX idx_users_email ON users(email);

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_tenants_updated_at BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

### OpenSearch Index Setup

```bash
# Tạo index với mapping
curl -X PUT "http://localhost:9200/rag_vectors" \
  -H "Content-Type: application/json" \
  -d '{
    "settings": {
      "index": {
        "number_of_shards": 3,
        "number_of_replicas": 1,
        "knn": true,
        "knn.algo_param.ef_search": 100
      }
    },
    "mappings": {
      "properties": {
        "tenant_id": { "type": "keyword" },
        "document_id": { "type": "keyword" },
        "chunk_id": { "type": "keyword" },
        "embedding_model": { "type": "keyword" },
        "content": {
          "type": "text",
          "analyzer": "standard"
        },
        "vector": {
          "type": "knn_vector",
          "dimension": 1536,
          "method": {
            "engine": "nmslib",
            "space_type": "cosinesimil",
            "name": "hnsw",
            "parameters": {
              "ef_construction": 256,
              "m": 48
            }
          }
        },
        "metadata": {
          "type": "object",
          "properties": {
            "page_number": { "type": "integer" },
            "chunk_index": { "type": "integer" },
            "tags": { "type": "keyword" },
            "file_name": { "type": "keyword" }
          }
        },
        "created_at": { "type": "date" }
      }
    }
  }'
```

---

## 🔒 SSL/TLS Configuration

### Option 1: Let's Encrypt với Certbot

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Obtain certificate
sudo certbot --nginx -d api.your-domain.com

# Auto renewal (crontab)
0 0 1 * * /usr/bin/certbot renew --quiet
```

### Option 2: AWS Certificate Manager

```bash
# Request certificate
aws acm request-certificate \
  --domain-name api.your-domain.com \
  --validation-method DNS \
  --subject-alternative-names "*.your-domain.com"

# Sau khi validate DNS, attach vào ALB
```

### Nginx SSL Configuration

```nginx
# /etc/nginx/conf.d/rag-api.conf

upstream rag_backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name api.your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.your-domain.com;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/api.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.your-domain.com/privkey.pem;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_session_tickets off;

    # Modern SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    # HSTS
    add_header Strict-Transport-Security "max-age=63072000" always;

    # Security Headers
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # File upload limit
    client_max_body_size 10M;

    # Gzip
    gzip on;
    gzip_types application/json;

    location / {
        proxy_pass http://rag_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # Buffer
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
    }

    # Health check endpoint (no logging)
    location /health {
        proxy_pass http://rag_backend/health;
        access_log off;
    }

    # SSE streaming support
    location /api/v1/tenants/*/query/stream {
        proxy_pass http://rag_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Cache-Control "no-cache";
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
}
```

---

## 🔧 Environment Variables

### Production .env Template

```bash
# .env.production

# ============================================
# Application
# ============================================
APP_ENV=production
DEBUG=false
APP_NAME="Enterprise RAG System"
SECRET_KEY=your-256-bit-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# ============================================
# PostgreSQL (RDS)
# ============================================
POSTGRES_HOST=rag-postgres.xxxxx.ap-southeast-1.rds.amazonaws.com
POSTGRES_PORT=5432
POSTGRES_USER=ragadmin
POSTGRES_PASSWORD=from-secrets-manager
POSTGRES_DB=ragdb
POSTGRES_SSL_MODE=require

# ============================================
# OpenSearch
# ============================================
OPENSEARCH_HOST=vpc-rag-search-xxxxx.ap-southeast-1.es.amazonaws.com
OPENSEARCH_PORT=443
OPENSEARCH_USE_SSL=true
# Nếu dùng Fine-grained access control
OPENSEARCH_USER=admin
OPENSEARCH_PASSWORD=from-secrets-manager

# ============================================
# Redis (ElastiCache)
# ============================================
REDIS_HOST=rag-redis.xxxxx.0001.apse1.cache.amazonaws.com
REDIS_PORT=6379
REDIS_SSL=true

# ============================================
# S3
# ============================================
S3_BUCKET=rag-documents-prod
S3_REGION=ap-southeast-1
# Không cần ACCESS_KEY nếu dùng IAM Role

# ============================================
# OpenAI
# ============================================
OPENAI_API_KEY=from-secrets-manager
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_TIMEOUT=15
OPENAI_MAX_RETRIES=3

# ============================================
# Rate Limiting
# ============================================
RATE_LIMIT_ENABLED=true
RATE_LIMIT_DEFAULT=100/minute

# ============================================
# File Upload
# ============================================
MAX_FILE_SIZE_MB=10
ALLOWED_MIME_TYPES=application/pdf,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document

# ============================================
# Logging
# ============================================
LOG_LEVEL=INFO
LOG_FORMAT=json

# ============================================
# Celery
# ============================================
CELERY_BROKER_URL=rediss://rag-redis.xxxxx.cache.amazonaws.com:6379/0
CELERY_RESULT_BACKEND=rediss://rag-redis.xxxxx.cache.amazonaws.com:6379/1
CELERY_TASK_DEFAULT_QUEUE=rag-tasks
```

### AWS Secrets Manager

```bash
# Store secrets
aws secretsmanager create-secret \
  --name rag/database \
  --secret-string '{"password":"YourSecurePassword"}'

aws secretsmanager create-secret \
  --name rag/openai \
  --secret-string '{"api_key":"sk-xxxxx"}'

# Retrieve in application
import boto3

def get_secret(secret_name):
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_name)
    return response['SecretString']
```

---

## 📊 Health Checks & Monitoring

### Health Check Implementation

```python
# app/api/v1/health.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import redis
from opensearchpy import OpenSearch

router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}

@router.get("/health/detailed")
async def detailed_health_check(db: Session = Depends(get_db)):
    components = {}
    
    # PostgreSQL
    try:
        db.execute("SELECT 1")
        components["postgresql"] = {"status": "healthy"}
    except Exception as e:
        components["postgresql"] = {"status": "unhealthy", "error": str(e)}
    
    # Redis
    try:
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        components["redis"] = {"status": "healthy"}
    except Exception as e:
        components["redis"] = {"status": "unhealthy", "error": str(e)}
    
    # OpenSearch
    try:
        os_client = OpenSearch(hosts=[settings.OPENSEARCH_HOST])
        os_client.cluster.health()
        components["opensearch"] = {"status": "healthy"}
    except Exception as e:
        components["opensearch"] = {"status": "unhealthy", "error": str(e)}
    
    overall = "healthy" if all(c["status"] == "healthy" for c in components.values()) else "unhealthy"
    
    return {
        "status": overall,
        "components": components,
        "version": "1.0.0"
    }
```

### CloudWatch Metrics

```bash
# Install CloudWatch Agent
sudo yum install amazon-cloudwatch-agent -y

# Configure agent
cat << EOF > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
{
  "agent": {
    "metrics_collection_interval": 60
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/app/logs/app.log",
            "log_group_name": "/rag/application",
            "log_stream_name": "{instance_id}"
          }
        ]
      }
    }
  },
  "metrics": {
    "namespace": "RAG/Application",
    "metrics_collected": {
      "cpu": {},
      "mem": {},
      "disk": {}
    }
  }
}
EOF

# Start agent
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json -s
```

### CloudWatch Alarms

```bash
# High CPU Alarm
aws cloudwatch put-metric-alarm \
  --alarm-name "RAG-High-CPU" \
  --alarm-description "CPU utilization > 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/EC2 \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --alarm-actions arn:aws:sns:ap-southeast-1:xxxxx:rag-alerts

# API Error Rate Alarm
aws cloudwatch put-metric-alarm \
  --alarm-name "RAG-High-Error-Rate" \
  --alarm-description "5xx error rate > 1%" \
  --metric-name HTTPCode_Target_5XX_Count \
  --namespace AWS/ApplicationELB \
  --statistic Sum \
  --period 60 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 3 \
  --alarm-actions arn:aws:sns:ap-southeast-1:xxxxx:rag-alerts
```

---

## 💾 Backup & Recovery

### PostgreSQL Backup

```bash
# Manual backup
pg_dump -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB > backup_$(date +%Y%m%d).sql

# Upload to S3
aws s3 cp backup_$(date +%Y%m%d).sql s3://rag-backups/postgres/

# RDS Automated Backup (đã cấu hình khi tạo RDS)
# Retention: 7 days
# Backup window: 03:00-04:00 UTC
```

### OpenSearch Snapshot

```bash
# Register S3 repository
curl -X PUT "https://vpc-rag-search-xxxxx.es.amazonaws.com/_snapshot/s3_backup" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "s3",
    "settings": {
      "bucket": "rag-backups",
      "region": "ap-southeast-1",
      "role_arn": "arn:aws:iam::xxxxx:role/opensearch-snapshot-role"
    }
  }'

# Create snapshot
curl -X PUT "https://vpc-rag-search-xxxxx.es.amazonaws.com/_snapshot/s3_backup/snapshot_$(date +%Y%m%d)"

# Restore snapshot
curl -X POST "https://vpc-rag-search-xxxxx.es.amazonaws.com/_snapshot/s3_backup/snapshot_20260223/_restore"
```

### Disaster Recovery Plan

| Component | RTO | RPO | Backup Strategy |
|-----------|-----|-----|-----------------|
| PostgreSQL | 1 hour | 5 minutes | Multi-AZ, Automated backups |
| OpenSearch | 2 hours | 1 hour | Daily snapshots to S3 |
| S3 | 0 | 0 | Cross-region replication |
| Application | 15 minutes | N/A | AMI snapshots, IaC |

---

## 📈 Scaling Guide

### Horizontal Scaling (API)

```bash
# Tăng desired capacity
aws autoscaling set-desired-capacity \
  --auto-scaling-group-name rag-api-asg \
  --desired-capacity 4

# Update max capacity
aws autoscaling update-auto-scaling-group \
  --auto-scaling-group-name rag-api-asg \
  --max-size 20
```

### Vertical Scaling (Database)

```bash
# RDS instance class upgrade
aws rds modify-db-instance \
  --db-instance-identifier rag-postgres \
  --db-instance-class db.r6g.large \
  --apply-immediately

# ElastiCache upgrade
aws elasticache modify-replication-group \
  --replication-group-id rag-redis \
  --cache-node-type cache.r6g.large \
  --apply-immediately
```

### OpenSearch Scaling

```bash
# Add data nodes
aws opensearch update-domain-config \
  --domain-name rag-search \
  --cluster-config InstanceCount=4
```

---

## 🐛 Troubleshooting

### Common Issues

#### 1. Container không start

```bash
# Check logs
docker-compose logs api

# Check container status
docker ps -a

# Restart với rebuild
docker-compose up -d --build api
```

#### 2. Database connection refused

```bash
# Check PostgreSQL status
docker-compose exec postgres pg_isready

# Check security group (AWS)
aws ec2 describe-security-groups --group-ids sg-xxxxx

# Test connection
psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB
```

#### 3. OpenSearch cluster red

```bash
# Check cluster health
curl -X GET "http://localhost:9200/_cluster/health?pretty"

# Check node status
curl -X GET "http://localhost:9200/_cat/nodes?v"

# Check unassigned shards
curl -X GET "http://localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"
```

#### 4. Celery tasks stuck

```bash
# Check Celery status
celery -A app.worker.celery_app inspect active

# Purge all tasks
celery -A app.worker.celery_app purge

# Restart worker
docker-compose restart celery_worker
```

#### 5. OpenAI API errors

```bash
# Check API key
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# Check rate limits
# Response headers: x-ratelimit-remaining-requests
```

### Log Analysis

```bash
# View application logs
docker-compose logs -f --tail=100 api

# Filter errors
docker-compose logs api 2>&1 | grep -i error

# View Celery task logs
docker-compose logs celery_worker | grep -E "(Task|ERROR|RETRY)"
```

---

## 📝 Deployment Checklist

### Pre-deployment

- [ ] Environment variables đã set
- [ ] Database migrations đã chạy
- [ ] OpenSearch index đã tạo
- [ ] S3 bucket đã tạo với đúng permissions
- [ ] SSL certificate đã ready
- [ ] Backup strategy đã configure
- [ ] Monitoring alerts đã setup

### Post-deployment

- [ ] Health check endpoint returning 200
- [ ] Detailed health check passing
- [ ] Sample API call works
- [ ] Document upload works
- [ ] RAG query works
- [ ] Logs đang được collect
- [ ] Metrics đang được report

---

<p align="center">
  <strong>Happy Deploying! 🚀</strong>
</p>
