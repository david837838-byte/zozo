#!/bin/bash
# سكريبت سريع لنشر التطبيق على PythonAnywhere
# Quick deployment script for PythonAnywhere

# الألوان للمخرجات
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# متغيرات
USERNAME=${1:-}
ENV_NAME=${2:-zozo_env}
PYTHON_VERSION="3.9"

if [ -z "$USERNAME" ]; then
    echo -e "${RED}❌ Usage: bash deploy.sh <YOUR_USERNAME> [ENV_NAME]${NC}"
    echo -e "${BLUE}Example: bash deploy.sh john_doe zozo_env${NC}"
    exit 1
fi

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Deploying Farm Management System     ║${NC}"
echo -e "${BLUE}║   نشر نظام إدارة المزرعة              ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"

# 1. استنسخ المستودع
echo -e "${YELLOW}\n📥 Step 1: Cloning repository...${NC}"
cd ~
git clone https://github.com/david837838-byte/zozo.git
cd zozo

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to clone repository${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Repository cloned${NC}"

# 2. إنشاء البيئة الافتراضية
echo -e "${YELLOW}\n🐍 Step 2: Creating virtual environment...${NC}"
mkvirtualenv --python=/usr/bin/python${PYTHON_VERSION} $ENV_NAME

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to create virtual environment${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Virtual environment created${NC}"

# 3. تفعيل البيئة الافتراضية
echo -e "${YELLOW}\n⚡ Step 3: Activating virtual environment...${NC}"
source ~/.virtualenvs/$ENV_NAME/bin/activate

# 4. تثبيت المكتبات
echo -e "${YELLOW}\n📦 Step 4: Installing dependencies...${NC}"
pip install --upgrade pip
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to install dependencies${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Dependencies installed${NC}"

# 5. إعداد قاعدة البيانات
echo -e "${YELLOW}\n🗄️  Step 5: Setting up database...${NC}"
python init_db.py || python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all(); print('Database created')"

if [ $? -ne 0 ]; then
    echo -e "${YELLOW}⚠️  Database creation might need manual setup${NC}"
fi
echo -e "${GREEN}✅ Database setup complete${NC}"

# 6. ملخص التكوين
echo -e "${YELLOW}\n⚙️  Step 6: Configuration Summary${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "Username: ${GREEN}$USERNAME${NC}"
echo -e "Virtual Env: ${GREEN}$ENV_NAME${NC}"
echo -e "Python Version: ${GREEN}$PYTHON_VERSION${NC}"
echo -e "Project Path: ${GREEN}/home/$USERNAME/zozo${NC}"
echo -e "Venv Path: ${GREEN}/home/$USERNAME/.virtualenvs/$ENV_NAME${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# 7. تعليمات الخطوات التالية
echo -e "${YELLOW}\n📋 Next Steps on PythonAnywhere Dashboard:${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "1️⃣  Go to ${GREEN}Web${NC} tab → Add a new web app"
echo -e "2️⃣  Choose ${GREEN}Manual configuration${NC} → Python 3.9+"
echo -e "3️⃣  Edit ${GREEN}WSGI configuration file${NC}:"
echo -e "    ${BLUE}Paste this code:${NC}"
echo -e ""
echo -e "    ${GREEN}import sys${NC}"
echo -e "    ${GREEN}path = '/home/$USERNAME/zozo'${NC}"
echo -e "    ${GREEN}if path not in sys.path:${NC}"
echo -e "    ${GREEN}    sys.path.append(path)${NC}"
echo -e ""
echo -e "    ${GREEN}from wsgi import app${NC}"
echo -e ""
echo -e "4️⃣  Set ${GREEN}Virtualenv${NC} to:"
echo -e "    ${BLUE}/home/$USERNAME/.virtualenvs/$ENV_NAME${NC}"
echo -e "5️⃣  Add ${GREEN}Static files${NC}:"
echo -e "    URL: ${BLUE}/static/${NC}"
echo -e "    Directory: ${GREEN}/home/$USERNAME/zozo/app/static${NC}"
echo -e "6️⃣  Click ${GREEN}Reload${NC} button (green)"
echo -e ""
echo -e "🌐 Your app will be available at:"
echo -e "   ${GREEN}https://$USERNAME.pythonanywhere.com${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# 8. إنشاء حساب Admin (اختياري)
echo -e "${YELLOW}\n👤 Step 7: Create Admin Account? (y/n)${NC}"
read -r create_admin
if [ "$create_admin" = "y" ] || [ "$create_admin" = "Y" ]; then
    python create_admin.py
    echo -e "${GREEN}✅ Admin account created${NC}"
fi

echo -e "${GREEN}\n✨ Deployment preparation complete!${NC}"
echo -e "${BLUE}Please follow the steps above in your PythonAnywhere dashboard.${NC}"
