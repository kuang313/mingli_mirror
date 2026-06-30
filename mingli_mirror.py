#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命理镜 - AI赋能的情绪陪伴与自我探索工具
技术栈: Python + Flask + SQLite + GLM-4-Flash
"""

import os
import json
import sqlite3
import datetime
import hashlib
import random
from flask import Flask, render_template, request, jsonify, session
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ==================== 配置 ====================
class Config:
    # Flask配置
    SECRET_KEY = 'mingli-mirror-secret-key-2024'
    DEBUG = True
    HOST = '0.0.0.0'
    PORT = 5000

    # GLM-4-Flash配置
    GLM_API_KEY = '22b25f526f2f4f35a59c21d1cef58970.I1cD5MhVzOR2B5oZ'
    GLM_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    GLM_MODEL = "glm-4-flash"

    # 数据库配置
    DB_PATH = os.path.join(os.path.dirname(__file__), 'mingli_mirror.db')


# ==================== 数据库层 ====================
class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """初始化数据库表结构"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 用户表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    membership_level TEXT DEFAULT 'free',
                    membership_expire_at TIMESTAMP
                )
            ''')

            # 八字记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bazi_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    birth_date TEXT NOT NULL,
                    birth_time TEXT NOT NULL,
                    gender TEXT NOT NULL,
                    name TEXT,
                    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    result_preview TEXT,
                    result_full TEXT,
                    is_unlocked INTEGER DEFAULT 0,
                    payment_id TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            # 运势记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fortune_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    fortune_date TEXT NOT NULL,
                    fortune_type TEXT NOT NULL,
                    fortune_score REAL,
                    fortune_content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            # 塔罗记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tarot_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    draw_date TEXT NOT NULL,
                    card_name TEXT NOT NULL,
                    card_meaning TEXT NOT NULL,
                    card_position TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            # 趣味测试记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS quiz_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    quiz_type TEXT NOT NULL,
                    quiz_date TEXT NOT NULL,
                    quiz_result TEXT NOT NULL,
                    quiz_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            # AI对话记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ai_conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    conversation_date TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            # 支付记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    payment_id TEXT UNIQUE NOT NULL,
                    amount REAL NOT NULL,
                    payment_type TEXT NOT NULL,
                    payment_status TEXT NOT NULL,
                    payment_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            # 用户打卡表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS checkins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    checkin_date TEXT NOT NULL,
                    checkin_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    mood_score REAL,
                    mood_note TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    UNIQUE(user_id, checkin_date)
                )
            ''')

            conn.commit()

    def create_user(self, username, email, password):
        """创建新用户"""
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (username, email, password_hash)
                VALUES (?, ?, ?)
            ''', (username, email, password_hash))
            conn.commit()
            return cursor.lastrowid

    def get_user_by_email(self, email):
        """通过邮箱获取用户"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE email = ? AND is_active = 1', (email,))
            return cursor.fetchone()

    def update_last_login(self, user_id):
        """更新用户最后登录时间"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET last_login = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (user_id,))
            conn.commit()

    def save_bazi_result(self, user_id, birth_data, result_preview, result_full=None):
        """保存八字测算结果"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO bazi_records 
                (user_id, birth_date, birth_time, gender, name, result_preview, result_full)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, birth_data['date'], birth_data['time'],
                  birth_data['gender'], birth_data.get('name', ''),
                  result_preview, result_full))
            conn.commit()
            return cursor.lastrowid

    def get_bazi_records(self, user_id, limit=10):
        """获取用户八字测算记录"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM bazi_records 
                WHERE user_id = ? 
                ORDER BY calculated_at DESC 
                LIMIT ?
            ''', (user_id, limit))
            return cursor.fetchall()

    def save_fortune(self, user_id, fortune_date, fortune_type, fortune_score, fortune_content):
        """保存运势记录"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO fortune_records 
                (user_id, fortune_date, fortune_type, fortune_score, fortune_content)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, fortune_date, fortune_type, fortune_score, fortune_content))
            conn.commit()
            return cursor.lastrowid

    def get_today_fortune(self, user_id, fortune_type='daily'):
        """获取今日运势"""
        today = datetime.date.today().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM fortune_records 
                WHERE user_id = ? AND fortune_date = ? AND fortune_type = ?
            ''', (user_id, today, fortune_type))
            return cursor.fetchone()

    def save_tarot_draw(self, user_id, card_name, card_meaning, card_position):
        """保存塔罗抽牌记录"""
        today = datetime.date.today().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO tarot_records 
                (user_id, draw_date, card_name, card_meaning, card_position)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, today, card_name, card_meaning, card_position))
            conn.commit()
            return cursor.lastrowid

    def get_recent_tarot_draws(self, user_id, days=7):
        """获取近期塔罗抽牌记录"""
        start_date = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM tarot_records 
                WHERE user_id = ? AND draw_date >= ?
                ORDER BY draw_date DESC, created_at DESC
            ''', (user_id, start_date))
            return cursor.fetchall()

    def save_quiz_result(self, user_id, quiz_type, quiz_result, quiz_data=None):
        """保存趣味测试结果"""
        today = datetime.date.today().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO quiz_records 
                (user_id, quiz_type, quiz_date, quiz_result, quiz_data)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, quiz_type, today, quiz_result, json.dumps(quiz_data) if quiz_data else None))
            conn.commit()
            return cursor.lastrowid

    def save_ai_conversation(self, user_id, role, content):
        """保存AI对话记录"""
        today = datetime.date.today().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO ai_conversations 
                (user_id, conversation_date, role, content)
                VALUES (?, ?, ?, ?)
            ''', (user_id, today, role, content))
            conn.commit()
            return cursor.lastrowid

    def get_recent_conversations(self, user_id, limit=20):
        """获取近期对话记录"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM ai_conversations 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (user_id, limit))
            return cursor.fetchall()

    def create_payment(self, user_id, amount, payment_type):
        """创建支付记录"""
        payment_id = f"PAY{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO payments 
                (user_id, payment_id, amount, payment_type, payment_status)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, payment_id, amount, payment_type, 'pending'))
            conn.commit()
            return payment_id

    def update_payment_status(self, payment_id, status):
        """更新支付状态"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE payments SET payment_status = ? 
                WHERE payment_id = ?
            ''', (status, payment_id))
            conn.commit()

    def unlock_bazi_result(self, user_id, payment_id):
        """解锁八字完整结果"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE bazi_records 
                SET is_unlocked = 1, payment_id = ?
                WHERE user_id = ? AND payment_id = ?
            ''', (payment_id, user_id, payment_id))
            conn.commit()
            return cursor.rowcount > 0

    def save_checkin(self, user_id, mood_score=None, mood_note=None):
        """保存打卡记录"""
        today = datetime.date.today().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO checkins 
                    (user_id, checkin_date, mood_score, mood_note)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, today, mood_score, mood_note))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def get_checkin_streak(self, user_id):
        """获取连续打卡天数"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT checkin_date FROM checkins 
                WHERE user_id = ? 
                ORDER BY checkin_date DESC
            ''', (user_id,))
            checkins = [row['checkin_date'] for row in cursor.fetchall()]

            if not checkins:
                return 0

            streak = 0
            current_date = datetime.date.today()

            for checkin_date in checkins:
                checkin = datetime.date.fromisoformat(checkin_date)
                if checkin == current_date:
                    streak += 1
                    current_date -= datetime.timedelta(days=1)
                elif checkin == current_date - datetime.timedelta(days=1):
                    streak += 1
                    current_date -= datetime.timedelta(days=1)
                else:
                    break

            return streak


# ==================== GLM-4-Flash 集成 ====================
class GLMClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.api_url = Config.GLM_API_URL
        self.model = Config.GLM_MODEL
        self.session = self._create_session()

    def _create_session(self):
        """创建带重试机制的HTTP会话"""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def chat_completion(self, messages, temperature=0.7, max_tokens=1000):
        """调用GLM-4-Flash聊天完成API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        try:
            response = self.session.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            result = response.json()

            if 'choices' in result and len(result['choices']) > 0:
                return result['choices'][0]['message']['content']
            else:
                raise Exception("API返回数据格式异常")

        except requests.exceptions.RequestException as e:
            raise Exception(f"API请求失败: {str(e)}")
        except Exception as e:
            raise Exception(f"GLM调用异常: {str(e)}")

    def generate_bazi_interpretation(self, birth_data, user_focus=None):
        """生成八字解读"""
        system_prompt = """你是一位专业的命理分析师，擅长用温暖、鼓励的语气解读八字命盘。
请遵循以下原则：
1. 不做严肃命理咨询，不替代专业命理师，不提供人生决策建议
2. 所有结果均标注"AI生成，仅供娱乐"
3. 提供情绪价值和心理慰藉，帮助用户认识自己
4. 用3个"人生关键词"概括命理底色
5. 解读要具体、生动，避免空泛

输出格式要求：
【人生关键词】：关键词1、关键词2、关键词3

【性格天赋】：（100-150字）

【核心优势】：（100-150字）

【潜在挑战】：（100-150字）

【成长建议】：（100-150字）

⚠️ 本内容由AI生成，仅供娱乐参考，不构成任何人生决策建议。"""

        user_message = f"""请为以下出生信息生成八字命理解读：
出生日期：{birth_data['date']}
出生时间：{birth_data['time']}
性别：{birth_data['gender']}
姓名：{birth_data.get('name', '未提供')}
"""

        if user_focus:
            user_message += f"\n用户特别关注：{user_focus}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        return self.chat_completion(messages, temperature=0.8, max_tokens=800)

    def generate_fortune_interpretation(self, fortune_type, user_context=None):
        """生成运势解读"""
        system_prompt = """你是一位运势解读专家，擅长用有趣、温暖的语言解读每日运势。
请遵循以下原则：
1. 提供情绪价值和心理慰藉
2. 运势评分为1-5分，保留1位小数
3. 给出具体的行动建议
4. 用轻松、鼓励的语气

输出格式要求：
【运势评分】：X.X分

【今日关键词】：关键词

【运势解读】：（100-150字）

【行动建议】：（50-100字）

【幸运元素】：（1-2个幸运元素，如颜色、数字等）

⚠️ 本内容由AI生成，仅供娱乐参考。"""

        today = datetime.date.today().strftime("%Y年%m月%d日")
        fortune_types = {
            'daily': '综合运势',
            'career': '事业运',
            'love': '感情运',
            'wealth': '财运',
            'health': '健康运'
        }

        user_message = f"""请生成{today}的{fortune_types.get(fortune_type, '综合')}运势解读："""

        if user_context:
            user_message += f"\n用户背景信息：{user_context}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        return self.chat_completion(messages, temperature=0.9, max_tokens=500)

    def generate_tarot_interpretation(self, card_name, card_position, user_question=None):
        """生成塔罗牌解读"""
        system_prompt = """你是一位塔罗牌解读专家，擅长用神秘而温暖的语言解读塔罗牌意。
请遵循以下原则：
1. 提供情绪价值和心理指引
2. 牌面解读要具体、生动
3. 给出实用的行动建议
4. 用鼓励、积极的语气

输出格式要求：
【牌面含义】：（100-150字）

【指引建议】：（100-150字）

【今日启示】：（50-100字）

⚠️ 本内容由AI生成，仅供娱乐参考。"""

        user_message = f"""请解读以下塔罗牌：
牌名：{card_name}
牌位：{card_position}
"""

        if user_question:
            user_message += f"\n用户问题：{user_question}"
        else:
            user_message += "\n用户问题：今日运势指引"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        return self.chat_completion(messages, temperature=0.9, max_tokens=500)

    def generate_quiz_result(self, quiz_type, user_answers):
        """生成趣味测试结果"""
        system_prompt = """你是一位趣味心理测试专家，擅长用有趣、温暖的语言解读测试结果。
请遵循以下原则：
1. 提供情绪价值和自我认知
2. 测试结果要具体、生动
3. 给出3个"个人标签"
4. 用轻松、鼓励的语气

输出格式要求：
【测试结果】：结果名称

【个人标签】：#标签1 #标签2 #标签3

【详细解读】：（200-300字）

【成长建议】：（50-100字）

⚠️ 本内容由AI生成，仅供娱乐参考。"""

        user_message = f"""请根据以下回答生成{quiz_type}测试结果："""

        if isinstance(user_answers, dict):
            for question, answer in user_answers.items():
                user_message += f"\n{question}：{answer}"
        else:
            user_message += f"\n用户回答：{user_answers}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        return self.chat_completion(messages, temperature=0.9, max_tokens=600)

    def generate_soulmate_profile(self, user_birth_data, user_preferences=None):
        """生成灵魂伴侣画像"""
        system_prompt = """你是一位情感关系专家，擅长用温暖、浪漫的语言描绘理想伴侣画像。
请遵循以下原则：
1. 提供情感价值和美好憧憬
2. 画像要具体、生动，包含外貌、性格、相遇场景等
3. 给出你们的"相遇故事"微小说（100-150字）
4. 用浪漫、鼓励的语气

输出格式要求：
【理想伴侣画像】：
外貌特征：（50-100字）
性格特质：（50-100字）
兴趣爱好：（50-100字）

【相遇故事】：（100-150字微小说）

【关系建议】：（50-100字）

⚠️ 本内容由AI生成，仅供娱乐参考。"""

        user_message = f"""请根据以下信息生成理想伴侣画像：
用户出生信息：{user_birth_data}
"""

        if user_preferences:
            user_message += f"\n用户偏好：{user_preferences}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        return self.chat_completion(messages, temperature=0.9, max_tokens=700)

    def chat_with_ai(self, user_message, conversation_history, ai_personality='witty'):
        """与AI进行对话"""
        personalities = {
            'witty': {
                'name': '毒舌大师',
                'style': '犀利、幽默、直接',
                'prompt': """你是一位毒舌但真诚的命理师，擅长用犀利但幽默的语言解答用户困惑。
原则：
1. 话虽然扎心，但要有理有据
2. 用幽默化解负面情绪
3. 给出实用、接地气的建议
4. 偶尔自嘲，拉近距离
5. 每次回复不超过150字"""
            },
            'gentle': {
                'name': '治愈仙女',
                'style': '温柔、体贴、鼓励',
                'prompt': """你是一位温柔治愈的命理师，擅长用温暖体贴的语言解答用户困惑。
原则：
1. 语言温柔、体贴，给予情感支持
2. 关注用户情绪状态
3. 给出积极、鼓励的建议
4. 用比喻、故事等温暖的方式表达
5. 每次回复不超过150字"""
            }
        }

        personality = personalities.get(ai_personality, personalities['witty'])

        system_prompt = f"""你是{personality['name']}，风格{personality['style']}。
{personality['prompt']}

⚠️ 本内容由AI生成，仅供娱乐参考。"""

        messages = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            for msg in conversation_history[-10:]:
                messages.append({
                    "role": msg['role'],
                    "content": msg['content']
                })

        messages.append({"role": "user", "content": user_message})

        return self.chat_completion(messages, temperature=0.8, max_tokens=300)


# ==================== 业务逻辑层 ====================
class MingliService:
    def __init__(self, db, glm_client):
        self.db = db
        self.glm_client = glm_client

    def register_user(self, username, email, password):
        """用户注册"""
        try:
            user_id = self.db.create_user(username, email, password)
            return {'success': True, 'user_id': user_id}
        except sqlite3.IntegrityError:
            return {'success': False, 'message': '用户名或邮箱已存在'}

    def login_user(self, email, password):
        """用户登录"""
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        user = self.db.get_user_by_email(email)

        if user and user['password_hash'] == password_hash:
            self.db.update_last_login(user['id'])
            session['user_id'] = user['id']
            session['username'] = user['username']
            return {'success': True, 'user': dict(user)}
        else:
            return {'success': False, 'message': '邮箱或密码错误'}

    def logout_user(self):
        """用户登出"""
        session.clear()
        return {'success': True}

    def calculate_bazi(self, birth_data, user_focus=None):
        """八字测算"""
        user_id = session.get('user_id', 1)  # 默认用户ID为1（临时访客）

        try:
            interpretation = self.glm_client.generate_bazi_interpretation(birth_data, user_focus)
            preview = interpretation[:300] + "..." if len(interpretation) > 300 else interpretation
            record_id = self.db.save_bazi_result(user_id, birth_data, preview, interpretation)

            return {
                'success': True,
                'record_id': record_id,
                'preview': preview,
                'full_result': interpretation
            }
        except Exception as e:
            return {'success': False, 'message': f'测算失败：{str(e)}'}

    def get_daily_fortune(self, fortune_type='daily'):
        """获取每日运势"""
        user_id = session.get('user_id', 1)

        existing = self.db.get_today_fortune(user_id, fortune_type)
        if existing:
            return {
                'success': True,
                'fortune': dict(existing)
            }

        try:
            fortune_content = self.glm_client.generate_fortune_interpretation(fortune_type)

            import re
            score_match = re.search(r'【运势评分】：(\d+\.?\d*)分', fortune_content)
            fortune_score = float(score_match.group(1)) if score_match else 3.5

            record_id = self.db.save_fortune(
                user_id,
                datetime.date.today().isoformat(),
                fortune_type,
                fortune_score,
                fortune_content
            )

            return {
                'success': True,
                'fortune': {
                    'id': record_id,
                    'fortune_score': fortune_score,
                    'fortune_content': fortune_content
                }
            }
        except Exception as e:
            return {'success': False, 'message': f'获取运势失败：{str(e)}'}

    def draw_tarot_card(self, card_position='今日指引', user_question=None):
        """塔罗抽牌"""
        user_id = session.get('user_id', 1)

        major_arcana = [
            ('愚者', '新的开始、冒险、纯真'),
            ('魔术师', '创造力、技能、意志力'),
            ('女祭司', '直觉、神秘、内在智慧'),
            ('皇后', '丰饶、母性、自然'),
            ('皇帝', '权威、结构、控制'),
            ('教皇', '传统、信仰、教导'),
            ('恋人', '爱情、选择、价值观'),
            ('战车', '胜利、意志、决心'),
            ('力量', '勇气、耐心、控制'),
            ('隐士', '内省、探索、指引'),
            ('命运之轮', '改变、循环、命运'),
            ('正义', '公平、真理、法律'),
            ('倒吊人', '牺牲、新视角、等待'),
            ('死神', '结束、转变、重生'),
            ('节制', '平衡、适度、耐心'),
            ('恶魔', '束缚、物质、欲望'),
            ('高塔', '突变、混乱、启示'),
            ('星星', '希望、灵感、平静'),
            ('月亮', '幻觉、恐惧、潜意识'),
            ('太阳', '成功、喜悦、活力'),
            ('审判', '重生、召唤、觉醒'),
            ('世界', '完成、整合、旅行')
        ]

        card_name, card_basic_meaning = random.choice(major_arcana)

        try:
            interpretation = self.glm_client.generate_tarot_interpretation(
                card_name, card_position, user_question
            )

            record_id = self.db.save_tarot_draw(user_id, card_name, interpretation, card_position)

            return {
                'success': True,
                'record_id': record_id,
                'card': {
                    'name': card_name,
                    'basic_meaning': card_basic_meaning,
                    'interpretation': interpretation
                }
            }
        except Exception as e:
            return {'success': False, 'message': f'抽牌失败：{str(e)}'}

    def take_quiz(self, quiz_type, user_answers):
        """趣味测试"""
        user_id = session.get('user_id', 1)

        try:
            result = self.glm_client.generate_quiz_result(quiz_type, user_answers)
            record_id = self.db.save_quiz_result(user_id, quiz_type, result, user_answers)

            return {
                'success': True,
                'record_id': record_id,
                'result': result
            }
        except Exception as e:
            return {'success': False, 'message': f'测试失败：{str(e)}'}

    def generate_soulmate(self, user_birth_data, user_preferences=None):
        """生成灵魂伴侣画像"""
        user_id = session.get('user_id', 1)

        try:
            profile = self.glm_client.generate_soulmate_profile(user_birth_data, user_preferences)

            return {
                'success': True,
                'profile': profile
            }
        except Exception as e:
            return {'success': False, 'message': f'生成画像失败：{str(e)}'}

    def chat_with_ai(self, message, ai_personality='witty'):
        """AI对话"""
        user_id = session.get('user_id', 1)

        try:
            conversation_history = []
            history_records = self.db.get_recent_conversations(user_id, limit=10)

            for record in reversed(history_records):
                conversation_history.append({
                    'role': record['role'],
                    'content': record['content']
                })

            ai_response = self.glm_client.chat_with_ai(message, conversation_history, ai_personality)

            self.db.save_ai_conversation(user_id, 'user', message)
            self.db.save_ai_conversation(user_id, 'assistant', ai_response)

            return {
                'success': True,
                'response': ai_response
            }
        except Exception as e:
            return {'success': False, 'message': f'对话失败：{str(e)}'}

    def create_payment_order(self, amount, payment_type):
        """创建支付订单"""
        user_id = session.get('user_id', 1)

        try:
            payment_id = self.db.create_payment(user_id, amount, payment_type)
            return {
                'success': True,
                'payment_id': payment_id,
                'amount': amount
            }
        except Exception as e:
            return {'success': False, 'message': f'创建订单失败：{str(e)}'}

    def simulate_payment(self, payment_id):
        """模拟支付成功"""
        user_id = session.get('user_id', 1)

        try:
            self.db.update_payment_status(payment_id, 'success')

            if self.db.unlock_bazi_result(user_id, payment_id):
                return {'success': True, 'message': '支付成功，内容已解锁'}
            else:
                return {'success': True, 'message': '支付成功'}
        except Exception as e:
            return {'success': False, 'message': f'支付失败：{str(e)}'}

    def daily_checkin(self, mood_score=None, mood_note=None):
        """每日打卡"""
        user_id = session.get('user_id', 1)

        try:
            success = self.db.save_checkin(user_id, mood_score, mood_note)
            if success:
                streak = self.db.get_checkin_streak(user_id)
                return {
                    'success': True,
                    'message': '打卡成功',
                    'streak': streak
                }
            else:
                return {'success': False, 'message': '今日已打卡'}
        except Exception as e:
            return {'success': False, 'message': f'打卡失败：{str(e)}'}

    def get_user_stats(self):
        """获取用户统计数据"""
        user_id = session.get('user_id', 1)

        try:
            bazi_count = len(self.db.get_bazi_records(user_id))
            streak = self.db.get_checkin_streak(user_id)
            tarot_draws = len(self.db.get_recent_tarot_draws(user_id, days=7))

            return {
                'success': True,
                'stats': {
                    'bazi_count': bazi_count,
                    'checkin_streak': streak,
                    'weekly_tarot': tarot_draws,
                    'username': session.get('username', '用户')
                }
            }
        except Exception as e:
            return {'success': False, 'message': f'获取统计失败：{str(e)}'}


# ==================== Flask Web应用 ====================
app = Flask(__name__)
app.config.from_object(Config)

# 初始化数据库和GLM客户端
db = Database(Config.DB_PATH)
glm_client = GLMClient(Config.GLM_API_KEY) if Config.GLM_API_KEY else None
service = MingliService(db, glm_client)

# HTML模板
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>命理镜 - 照见你的另一种可能</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { text-align: center; color: white; padding: 40px 0; }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; text-shadow: 2px 2px 4px rgba(0,0,0,0.2); }
        .card { background: white; border-radius: 15px; padding: 30px; margin-bottom: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
        .features { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 30px 0; }
        .feature-card { background: white; border-radius: 15px; padding: 25px; text-align: center; cursor: pointer; transition: transform 0.3s, box-shadow 0.3s; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
        .feature-card:hover { transform: translateY(-5px); box-shadow: 0 8px 25px rgba(0,0,0,0.15); }
        .feature-icon { font-size: 3em; margin-bottom: 15px; }
        .feature-title { font-size: 1.3em; font-weight: bold; margin-bottom: 10px; color: #667eea; }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 8px; font-weight: 500; color: #555; }
        .form-group input, .form-group select, .form-group textarea {
            width: 100%; padding: 12px; border: 2px solid #e1e1e1; border-radius: 8px; font-size: 16px;
        }
        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; border: none; padding: 12px 30px; border-radius: 25px;
            font-size: 16px; font-weight: bold; cursor: pointer;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }
        .result-area { background: #f8f9fa; border-radius: 10px; padding: 20px; margin-top: 20px; white-space: pre-wrap; line-height: 1.8; display: none; }
        .result-area.show { display: block; animation: fadeIn 0.5s; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.5); align-items: center; justify-content: center; }
        .modal.show { display: flex; }
        .modal-content { background: white; padding: 30px; border-radius: 15px; max-width: 500px; width: 90%; max-height: 80vh; overflow-y: auto; }
        .close-btn { float: right; font-size: 24px; cursor: pointer; color: #999; }
        .chat-container { max-height: 400px; overflow-y: auto; border: 1px solid #e1e1e1; border-radius: 10px; padding: 15px; margin-bottom: 15px; background: #f8f9fa; }
        .message { margin-bottom: 15px; padding: 10px 15px; border-radius: 10px; max-width: 80%; }
        .message.user { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; margin-left: auto; }
        .message.ai { background: white; border: 1px solid #e1e1e1; }
        .tabs { display: flex; border-bottom: 2px solid #e1e1e1; margin-bottom: 20px; }
        .tab { padding: 10px 20px; cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -2px; }
        .tab.active { border-bottom-color: #667eea; color: #667eea; font-weight: bold; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin: 20px 0; }
        .stat-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; text-align: center; }
        .stat-value { font-size: 2em; font-weight: bold; margin-bottom: 5px; }
        .disclaimer { text-align: center; color: #999; font-size: 12px; padding: 20px; border-top: 1px solid #e1e1e1; margin-top: 30px; }
    </style>
</head>
<body>
    <div class="header">
        <div class="container">
            <h1>🔮 命理镜</h1>
            <p>照见你的另一种可能</p>
        </div>
    </div>

    <div class="container">
        <div class="features">
            <div class="feature-card" onclick="showModal('bazi-modal')">
                <div class="feature-icon">📜</div>
                <div class="feature-title">八字排盘</div>
            </div>

            <div class="feature-card" onclick="showModal('fortune-modal')">
                <div class="feature-icon">🌟</div>
                <div class="feature-title">每日运势</div>
            </div>

            <div class="feature-card" onclick="showModal('tarot-modal')">
                <div class="feature-icon">🎴</div>
                <div class="feature-title">塔罗占卜</div>
            </div>

            <div class="feature-card" onclick="showModal('quiz-modal')">
                <div class="feature-icon">🧩</div>
                <div class="feature-title">趣味测试</div>
            </div>

            <div class="feature-card" onclick="showModal('soulmate-modal')">
                <div class="feature-icon">💕</div>
                <div class="feature-title">灵魂伴侣</div>
            </div>

            <div class="feature-card" onclick="showModal('ai-chat-modal')">
                <div class="feature-icon">🗣️</div>
                <div class="feature-title">毒舌AI</div>
            </div>
        </div>

        <div class="card">
            <h2>📊 我的数据</h2>
            <div class="stats-grid" id="user-stats">
                <div class="stat-card">
                    <div class="stat-value" id="bazi-count">0</div>
                    <div class="stat-label">八字测算次数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="checkin-streak">0</div>
                    <div class="stat-label">连续打卡天数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="weekly-tarot">0</div>
                    <div class="stat-label">本周抽牌次数</div>
                </div>
            </div>
            <div style="text-align: center;">
                <button class="btn" onclick="dailyCheckin()">📅 今日打卡</button>
            </div>
        </div>

        <div class="disclaimer">
            ⚠️ 本内容由AI生成，仅供娱乐参考，不构成任何人生决策建议。
        </div>
    </div>

    <!-- 模态框 -->
    <div id="bazi-modal" class="modal">
        <div class="modal-content">
            <span class="close-btn" onclick="hideModal('bazi-modal')">&times;</span>
            <h2>📜 八字排盘</h2>
            <div class="form-group">
                <label>出生日期</label>
                <input type="date" id="bazi-date">
            </div>
            <div class="form-group">
                <label>出生时间</label>
                <select id="bazi-time">
                    <option value="12:00" selected>午时 (11:00-13:00)</option>
                    <option value="00:00">子时 (23:00-01:00)</option>
                    <option value="02:00">丑时 (01:00-03:00)</option>
                    <option value="04:00">寅时 (03:00-05:00)</option>
                    <option value="06:00">卯时 (05:00-07:00)</option>
                    <option value="08:00">辰时 (07:00-09:00)</option>
                    <option value="10:00">巳时 (09:00-11:00)</option>
                    <option value="14:00">未时 (13:00-15:00)</option>
                    <option value="16:00">申时 (15:00-17:00)</option>
                    <option value="18:00">酉时 (17:00-19:00)</option>
                    <option value="20:00">戌时 (19:00-21:00)</option>
                    <option value="22:00">亥时 (21:00-23:00)</option>
                </select>
            </div>
            <div class="form-group">
                <label>性别</label>
                <select id="bazi-gender">
                    <option value="男">男</option>
                    <option value="女">女</option>
                </select>
            </div>
            <button class="btn" onclick="calculateBazi()" style="width: 100%;">开始测算</button>
            <div id="bazi-result" class="result-area"></div>
        </div>
    </div>

    <div id="fortune-modal" class="modal">
        <div class="modal-content">
            <span class="close-btn" onclick="hideModal('fortune-modal')">&times;</span>
            <h2>🌟 每日运势</h2>
            <div class="tabs">
                <div class="tab active" onclick="switchFortuneTab('daily')">综合运势</div>
                <div class="tab" onclick="switchFortuneTab('career')">事业运</div>
                <div class="tab" onclick="switchFortuneTab('love')">感情运</div>
                <div class="tab" onclick="switchFortuneTab('wealth')">财运</div>
            </div>
            <div id="fortune-result" class="result-area"></div>
            <button class="btn" onclick="getDailyFortune()" style="width: 100%;">查看今日运势</button>
        </div>
    </div>

    <div id="tarot-modal" class="modal">
        <div class="modal-content">
            <span class="close-btn" onclick="hideModal('tarot-modal')">&times;</span>
            <h2>🎴 塔罗占卜</h2>
            <div class="form-group">
                <label>抽牌问题</label>
                <input type="text" id="tarot-question" placeholder="你想问什么？（可选）">
            </div>
            <button class="btn" onclick="drawTarot()" style="width: 100%;">抽一张牌</button>
            <div id="tarot-result" class="result-area"></div>
        </div>
    </div>

    <div id="quiz-modal" class="modal">
        <div class="modal-content">
            <span class="close-btn" onclick="hideModal('quiz-modal')">&times;</span>
            <h2>🧩 趣味测试</h2>
            <div class="form-group">
                <label>选择测试类型</label>
                <select id="quiz-type">
                    <option value="命理人格类型">命理人格类型测试</option>
                    <option value="前世故事">前世故事测试</option>
                    <option value="灵魂动物">灵魂动物测试</option>
                    <option value="幸运色彩">幸运色彩测试</option>
                </select>
            </div>
            <div class="form-group">
                <label>你的回答</label>
                <textarea id="quiz-answer" rows="4" placeholder="请描述你的性格特点..."></textarea>
            </div>
            <button class="btn" onclick="takeQuiz()" style="width: 100%;">开始测试</button>
            <div id="quiz-result" class="result-area"></div>
        </div>
    </div>

    <div id="soulmate-modal" class="modal">
        <div class="modal-content">
            <span class="close-btn" onclick="hideModal('soulmate-modal')">&times;</span>
            <h2>💕 灵魂伴侣画像</h2>
            <div class="form-group">
                <label>你的出生日期</label>
                <input type="date" id="soulmate-date">
            </div>
            <div class="form-group">
                <label>你的性别</label>
                <select id="soulmate-gender">
                    <option value="男">男</option>
                    <option value="女">女</option>
                </select>
            </div>
            <div class="form-group">
                <label>理想伴侣偏好（可选）</label>
                <textarea id="soulmate-preferences" rows="3" placeholder="描述你理想中的伴侣特点..."></textarea>
            </div>
            <button class="btn" onclick="generateSoulmate()" style="width: 100%;">生成画像</button>
            <div id="soulmate-result" class="result-area"></div>
        </div>
    </div>

    <div id="ai-chat-modal" class="modal">
        <div class="modal-content">
            <span class="close-btn" onclick="hideModal('ai-chat-modal')">&times;</span>
            <h2>🗣️ 毒舌AI</h2>
            <div class="form-group">
                <label>选择AI性格</label>
                <select id="ai-personality">
                    <option value="witty">毒舌大师（犀利幽默）</option>
                    <option value="gentle">治愈仙女（温柔体贴）</option>
                </select>
            </div>
            <div class="chat-container" id="chat-messages">
                <div class="message ai">嗨，我是毒舌大师。有什么想问的尽管说，我会给你最真实的建议！</div>
            </div>
            <div class="form-group" style="display: flex; gap: 10px;">
                <input type="text" id="chat-input" placeholder="输入你的问题..." style="flex: 1;">
                <button class="btn" onclick="sendChatMessage()">发送</button>
            </div>
        </div>
    </div>

    <script>
        function showModal(modalId) { document.getElementById(modalId).classList.add('show'); }
        function hideModal(modalId) { document.getElementById(modalId).classList.remove('show'); }
        window.onclick = function(event) { if (event.target.classList.contains('modal')) { event.target.classList.remove('show'); } }

        let currentFortuneType = 'daily';
        function switchFortuneTab(type) {
            currentFortuneType = type;
            document.querySelectorAll('#fortune-modal .tab').forEach(tab => tab.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById('fortune-result').classList.remove('show');
        }

        function calculateBazi() {
            const date = document.getElementById('bazi-date').value;
            const time = document.getElementById('bazi-time').value;
            const gender = document.getElementById('bazi-gender').value;

            if (!date) { alert('请选择出生日期'); return; }

            const resultDiv = document.getElementById('bazi-result');
            resultDiv.textContent = '🔮 命理大师正在推演你的命盘...';
            resultDiv.classList.add('show');

            fetch('/api/bazi/calculate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ birth_date: date, birth_time: time, gender: gender })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    resultDiv.textContent = data.full_result;
                    updateUserStats();
                } else {
                    alert('测算失败：' + data.message);
                    resultDiv.classList.remove('show');
                }
            })
            .catch(error => {
                alert('网络错误，请稍后重试');
                resultDiv.classList.remove('show');
            });
        }

        function getDailyFortune() {
            const resultDiv = document.getElementById('fortune-result');
            resultDiv.textContent = '🌟 正在为你推算今日运势...';
            resultDiv.classList.add('show');

            fetch(`/api/fortune/daily?type=${currentFortuneType}`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    resultDiv.textContent = data.fortune.fortune_content;
                } else {
                    alert('获取运势失败：' + data.message);
                    resultDiv.classList.remove('show');
                }
            })
            .catch(error => {
                alert('网络错误，请稍后重试');
                resultDiv.classList.remove('show');
            });
        }

        function drawTarot() {
            const question = document.getElementById('tarot-question').value;
            const resultDiv = document.getElementById('tarot-result');
            resultDiv.textContent = '🎴 塔罗牌正在为你指引方向...';
            resultDiv.classList.add('show');

            fetch('/api/tarot/draw', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ position: '今日指引', question: question || null })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    resultDiv.textContent = `🎴 ${data.card.name}\n\n${data.card.interpretation}`;
                    updateUserStats();
                } else {
                    alert('抽牌失败：' + data.message);
                    resultDiv.classList.remove('show');
                }
            })
            .catch(error => {
                alert('网络错误，请稍后重试');
                resultDiv.classList.remove('show');
            });
        }

        function takeQuiz() {
            const type = document.getElementById('quiz-type').value;
            const answer = document.getElementById('quiz-answer').value;

            if (!answer.trim()) { alert('请输入你的回答'); return; }

            const resultDiv = document.getElementById('quiz-result');
            resultDiv.textContent = '🧩 正在分析你的测试结果...';
            resultDiv.classList.add('show');

            fetch('/api/quiz/take', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ quiz_type: type, answers: {answer: answer} })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    resultDiv.textContent = data.result;
                } else {
                    alert('测试失败：' + data.message);
                    resultDiv.classList.remove('show');
                }
            })
            .catch(error => {
                alert('网络错误，请稍后重试');
                resultDiv.classList.remove('show');
            });
        }

        function generateSoulmate() {
            const date = document.getElementById('soulmate-date').value;
            const gender = document.getElementById('soulmate-gender').value;
            const preferences = document.getElementById('soulmate-preferences').value;

            if (!date) { alert('请选择出生日期'); return; }

            const resultDiv = document.getElementById('soulmate-result');
            resultDiv.textContent = '💕 正在为你描绘理想伴侣...';
            resultDiv.classList.add('show');

            fetch('/api/soulmate/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ birth_date: date, birth_time: '12:00', gender: gender, preferences: preferences || null })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    resultDiv.textContent = data.profile;
                } else {
                    alert('生成画像失败：' + data.message);
                    resultDiv.classList.remove('show');
                }
            })
            .catch(error => {
                alert('网络错误，请稍后重试');
                resultDiv.classList.remove('show');
            });
        }

        function sendChatMessage() {
            const input = document.getElementById('chat-input');
            const message = input.value.trim();
            const personality = document.getElementById('ai-personality').value;

            if (!message) return;

            const chatContainer = document.getElementById('chat-messages');

            const userMsg = document.createElement('div');
            userMsg.className = 'message user';
            userMsg.textContent = message;
            chatContainer.appendChild(userMsg);

            input.value = '';
            chatContainer.scrollTop = chatContainer.scrollHeight;

            const aiMsg = document.createElement('div');
            aiMsg.className = 'message ai';
            aiMsg.textContent = '正在思考...';
            chatContainer.appendChild(aiMsg);

            fetch('/api/ai/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ message: message, personality: personality })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    aiMsg.textContent = data.response;
                } else {
                    aiMsg.textContent = '抱歉，我现在无法回答。' + data.message;
                }
                chatContainer.scrollTop = chatContainer.scrollHeight;
            })
            .catch(error => {
                aiMsg.textContent = '网络错误，请稍后重试';
            });
        }

        function dailyCheckin() {
            fetch('/api/checkin', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert(`🎉 打卡成功！\\n连续打卡：${data.streak} 天`);
                    updateUserStats();
                } else {
                    alert(data.message);
                }
            })
            .catch(error => {
                alert('网络错误，请稍后重试');
            });
        }

        function updateUserStats() {
            fetch('/api/user/stats')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    document.getElementById('bazi-count').textContent = data.stats.bazi_count;
                    document.getElementById('checkin-streak').textContent = data.stats.checkin_streak;
                    document.getElementById('weekly-tarot').textContent = data.stats.weekly_tarot;
                }
            })
            .catch(error => {
                console.error('Failed to update user stats:', error);
            });
        }

        document.addEventListener('DOMContentLoaded', updateUserStats);
        document.getElementById('chat-input').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') sendChatMessage();
        });
    </script>
</body>
</html>
"""


# ==================== 路由定义 ====================
@app.route('/')
def index():
    """首页"""
    return HTML_TEMPLATE


@app.route('/api/bazi/calculate', methods=['POST'])
def calculate_bazi():
    """八字测算"""
    data = request.json
    result = service.calculate_bazi(
        {
            'date': data.get('birth_date'),
            'time': data.get('birth_time', '12:00'),
            'gender': data.get('gender'),
            'name': data.get('name', '')
        },
        data.get('user_focus')
    )
    return jsonify(result)


@app.route('/api/fortune/daily', methods=['GET'])
def get_daily_fortune():
    """获取每日运势"""
    fortune_type = request.args.get('type', 'daily')
    result = service.get_daily_fortune(fortune_type)
    return jsonify(result)


@app.route('/api/tarot/draw', methods=['POST'])
def draw_tarot():
    """塔罗抽牌"""
    data = request.json
    result = service.draw_tarot_card(
        data.get('position', '今日指引'),
        data.get('question')
    )
    return jsonify(result)


@app.route('/api/quiz/take', methods=['POST'])
def take_quiz():
    """趣味测试"""
    data = request.json
    result = service.take_quiz(
        data.get('quiz_type'),
        data.get('answers', {})
    )
    return jsonify(result)


@app.route('/api/soulmate/generate', methods=['POST'])
def generate_soulmate():
    """生成灵魂伴侣画像"""
    data = request.json
    result = service.generate_soulmate(
        {
            'date': data.get('birth_date'),
            'time': data.get('birth_time', '12:00'),
            'gender': data.get('gender')
        },
        data.get('preferences')
    )
    return jsonify(result)


@app.route('/api/ai/chat', methods=['POST'])
def chat_with_ai():
    """AI对话"""
    data = request.json
    result = service.chat_with_ai(
        data.get('message'),
        data.get('personality', 'witty')
    )
    return jsonify(result)


@app.route('/api/checkin', methods=['POST'])
def daily_checkin():
    """每日打卡"""
    data = request.json
    result = service.daily_checkin(
        data.get('mood_score'),
        data.get('mood_note')
    )
    return jsonify(result)


@app.route('/api/user/stats', methods=['GET'])
def get_user_stats():
    """获取用户统计"""
    result = service.get_user_stats()
    return jsonify(result)


# ==================== 错误处理 ====================
@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'message': '资源不存在'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'message': '服务器内部错误'}), 500


# ==================== 启动应用 ====================
if __name__ == '__main__':
    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║           🔮 命理镜 - AI赋能的情绪陪伴工具                    ║
    ║                                                               ║
    ║           技术栈: Python + Flask + SQLite + GLM-4-Flash     ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)

    print(f"🚀 服务器启动中...")
    print(f"📍 访问地址: http://{Config.HOST}:{Config.PORT}")
    print(f"💾 数据库路径: {Config.DB_PATH}")
    print()

    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
