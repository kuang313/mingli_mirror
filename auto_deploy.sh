#!/bin/bash

echo "================================================"
echo "   命理镜 - 全自动部署脚本开始运行..."
echo "================================================"

# 1. 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then 
  echo "请使用 root 权限运行此脚本 (sudo bash auto_deploy.sh)"
  exit 
fi

# 2. 更新系统并安装基础软件
echo "[1/7] 正在更新系统并安装环境..."
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv nginx supervisor git

# 3. 创建项目目录
echo "[2/7] 正在创建项目目录..."
mkdir -p /var/www/mingli-mirror
cd /var/www/mingli-mirror

# 4. 处理程序文件
# 检查用户是否上传了文件到 /root
if [ -f "/root/mingli_mirror.py" ]; then
    echo "[3/7] 检测到程序文件，正在移动..."
    cp /root/mingli_mirror.py /var/www/mingli-mirror/mingli_mirror.py
else
    echo "[3/7] 警告：未在 /root 目录找到 mingli_mirror.py，请手动上传后重试。"
    exit 1
fi

# 5. 自动修改配置为生产环境
echo "[4/7] 正在优化生产环境配置..."
# 关闭 Debug 模式
sed -i "s/DEBUG = True/DEBUG = False/g" mingli_mirror.py
# 修改监听地址为本地
sed -i "s/HOST = '0.0.0.0'/HOST = '127.0.0.1'/g" mingli_mirror.py

# 6. 创建虚拟环境并安装依赖
echo "[5/7] 正在安装 Python 依赖..."
python3 -m venv venv
source venv/bin/activate

# 创建 requirements.txt
cat > requirements.txt << 'EOF'
Flask==3.0.0
requests==2.31.0
gunicorn==21.2.0
EOF

pip install --upgrade pip
pip install -r requirements.txt

# 7. 配置 Nginx
echo "[6/7] 正在配置 Nginx..."
cat > /etc/nginx/sites-available/mingli-mirror << 'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    access_log /var/log/nginx/mingli-mirror-access.log;
    error_log /var/log/nginx/mingli-mirror-error.log;
}
EOF

ln -s /etc/nginx/sites-available/mingli-mirror /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default # 删除默认站点
nginx -t
systemctl restart nginx

# 8. 配置 Supervisor (进程守护)
echo "[7/7] 正在配置进程守护..."
cat > /etc/supervisor/conf.d/mingli-mirror.conf << 'EOF'
[program:mingli-mirror]
directory=/var/www/mingli-mirror
command=/var/www/mingli-mirror/venv/bin/python mingli_mirror.py
user=root
autostart=true
autorestart=true
stderr_logfile=/var/log/mingli-mirror.err.log
stdout_logfile=/var/log/mingli-mirror.out.log
environment=PATH="/var/www/mingli-mirror/venv/bin"
EOF

supervisorctl reread
supervisorctl update
supervisorctl start mingli-mirror

echo ""
echo "================================================"
echo "   🎉 部署完成！"
echo "================================================"
echo "   请访问: http://您的公网IP"
echo "   查看日志: tail -f /var/log/mingli-mirror.out.log"
echo "================================================"
