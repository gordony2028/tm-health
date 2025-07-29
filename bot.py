# TM-Health - Simplified Professional Teen Mental Health Support Bot
# File: bot.py

import os
import json
import logging
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import asyncio
from enum import Enum

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import dependencies with error handling
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
    logger.info("✅ Google Generative AI available")
except ImportError as e:
    logger.warning(f"⚠️ Google Generative AI not available: {e}")
    GEMINI_AVAILABLE = False
    genai = None

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
    logger.info("✅ Telegram bot library imported")
except ImportError as e:
    logger.error(f"❌ Failed to import telegram library: {e}")
    sys.exit(1)

try:
    from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, Float, BigInteger, JSON
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker, Session
    logger.info("✅ SQLAlchemy imported")
except ImportError as e:
    logger.error(f"❌ Failed to import SQLAlchemy: {e}")
    sys.exit(1)

# Simplified Database Models
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(50))
    first_name = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    conversation_count = Column(Integer, default=0)

class Assessment(Base):
    __tablename__ = 'assessments'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    assessment_type = Column(String(50))
    score = Column(Integer)
    responses = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)

class ConversationState(Base):
    __tablename__ = 'conversation_states'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    state = Column(String(50))  # 'normal', 'assessment_phq', 'assessment_gad', etc.
    step = Column(Integer, default=0)
    data = Column(JSON)
    updated_at = Column(DateTime, default=datetime.utcnow)

# Configuration
class Config:
    def __init__(self):
        self.PORT = int(os.getenv('PORT', 10000))
        self.TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
        self.GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
        self.DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///tm_health.db')
    
    def validate(self):
        if not self.TELEGRAM_TOKEN:
            logger.error("❌ TELEGRAM_TOKEN environment variable not found")
            sys.exit(1)
        
        if not self.TELEGRAM_TOKEN.count(':') == 1:
            logger.error("❌ TELEGRAM_TOKEN appears to be invalid format")
            sys.exit(1)
        
        logger.info("✅ Configuration validated")
        return True

# Database Manager
class Database:
    def __init__(self, database_url: str):
        try:
            self.engine = create_engine(database_url, pool_pre_ping=True, pool_recycle=300, echo=False)
            Base.metadata.create_all(self.engine)
            self.SessionLocal = sessionmaker(bind=self.engine)
            logger.info("✅ Database initialized")
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise
    
    def get_session(self) -> Session:
        return self.SessionLocal()
    
    def get_or_create_user(self, telegram_user) -> User:
        session = self.get_session()
        try:
            user = session.query(User).filter_by(telegram_id=telegram_user.id).first()
            if not user:
                user = User(
                    telegram_id=telegram_user.id,
                    username=telegram_user.username,
                    first_name=telegram_user.first_name
                )
                session.add(user)
                session.commit()
                session.refresh(user)
                logger.info(f"Created new user: {telegram_user.id}")
            else:
                user.last_active = datetime.utcnow()
                session.commit()
            return user
        except Exception as e:
            logger.error(f"Error in get_or_create_user: {e}")
            session.rollback()
            raise
        finally:
            session.close()
    
    def get_conversation_state(self, user_id: int):
        session = self.get_session()
        try:
            return session.query(ConversationState).filter_by(user_id=user_id).first()
        finally:
            session.close()
    
    def set_conversation_state(self, user_id: int, state: str, step: int = 0, data: dict = None):
        session = self.get_session()
        try:
            conv_state = session.query(ConversationState).filter_by(user_id=user_id).first()
            if conv_state:
                conv_state.state = state
                conv_state.step = step
                conv_state.data = data or {}
                conv_state.updated_at = datetime.utcnow()
            else:
                conv_state = ConversationState(
                    user_id=user_id,
                    state=state,
                    step=step,
                    data=data or {}
                )
                session.add(conv_state)
            session.commit()
        except Exception as e:
            logger.error(f"Error setting conversation state: {e}")
            session.rollback()
        finally:
            session.close()
    
    def clear_conversation_state(self, user_id: int):
        session = self.get_session()
        try:
            session.query(ConversationState).filter_by(user_id=user_id).delete()
            session.commit()
        except Exception as e:
            logger.error(f"Error clearing conversation state: {e}")
            session.rollback()
        finally:
            session.close()

# Simple AI Assistant
class SimpleAI:
    def __init__(self, api_key: str = None):
        self.enabled = False
        
        if GEMINI_AVAILABLE and api_key:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel('gemini-1.5-flash')
                test_response = self.model.generate_content("Say 'AI ready'")
                if test_response and test_response.text:
                    self.enabled = True
                    logger.info("✅ AI enabled")
            except Exception as e:
                logger.warning(f"⚠️ AI initialization failed: {e}")
    
    async def get_response(self, message: str, user_name: str = "friend") -> str:
        if not self.enabled:
            return self.fallback_response(message, user_name)
        
        prompt = f"""
You are a professional mental health support assistant for teenagers. Respond to this message with:
1. Empathy and validation
2. Practical coping strategies
3. Professional guidance when appropriate
4. Keep responses under 200 words

User says: "{message}"

Provide a supportive, professional response:
        """
        
        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            return response.text.strip() if response and response.text else self.fallback_response(message, user_name)
        except Exception as e:
            logger.warning(f"AI response failed: {e}")
            return self.fallback_response(message, user_name)
    
    def fallback_response(self, message: str, user_name: str) -> str:
        message_lower = message.lower()
        
        # Crisis keywords
        if any(word in message_lower for word in ['suicide', 'kill myself', 'end it all', 'hurt myself']):
            return f"""I'm very concerned about you right now, {user_name}. Your safety is the most important thing.

**Please reach out immediately:**
📞 **Lifeline: 13 11 14** (24/7)
🧒 **Kids Helpline: 1800 55 1800** (24/7)
🚨 **Emergency: 000**

You don't have to go through this alone. Professional help is available right now. 💙"""
        
        # Anxiety
        if any(word in message_lower for word in ['anxious', 'anxiety', 'panic', 'worried']):
            return f"""I understand you're feeling anxious, {user_name}. That's really tough to deal with.

**Try this grounding technique:**
• 5 things you can see
• 4 things you can touch
• 3 things you can hear
• 2 things you can smell
• 1 thing you can taste

**Remember:** Anxiety is temporary and manageable. You've gotten through difficult times before.

What's causing you the most anxiety right now? 🌸"""
        
        # Depression
        if any(word in message_lower for word in ['depressed', 'sad', 'hopeless', 'empty']):
            return f"""I hear the pain in your message, {user_name}. Depression can make everything feel overwhelming.

**Small steps that can help:**
• One tiny activity you used to enjoy
• Reaching out to one person who cares
• Taking a warm shower or bath
• Listening to music

**Remember:** You matter, and these feelings can change with support.

Is there one small thing you could do for yourself today? 💜"""
        
        # Stress
        if any(word in message_lower for word in ['stressed', 'overwhelmed', 'pressure']):
            return f"""It sounds like you're under a lot of pressure, {user_name}. That's exhausting.

**Quick stress relief:**
• Take 3 deep breaths (in for 4, out for 6)
• Name 3 things you're grateful for
• Do some gentle stretching

**For ongoing stress:** Break big problems into smaller, manageable pieces.

What's the biggest source of stress for you right now? 📚"""
        
        # General greeting
        if any(word in message_lower for word in ['hello', 'hi', 'hey', 'good morning', 'good afternoon']):
            return f"""Hello {user_name}! 🌟 I'm here to provide mental health support and coping strategies.

You can:
• Talk to me about how you're feeling
• Use /assess for mental health screening
• Use /crisis for emergency resources
• Use /help for all available commands

How are you feeling today? I'm here to listen and support you. 💙"""
        
        # Default supportive response
        return f"""Thank you for sharing that with me, {user_name}. I'm here to listen and provide support.

**Available resources:**
• /assess - Mental health screening
• /crisis - Emergency support numbers
• /help - All available commands

What's most on your mind right now? I'm here to help you work through it. 🌟"""
    
    def detect_crisis(self, message: str) -> bool:
        crisis_phrases = ['suicide', 'kill myself', 'end it all', 'hurt myself', 'want to die', 'better off dead']
        return any(phrase in message.lower() for phrase in crisis_phrases)

# Main Bot Class
class TeenSupportBot:
    def __init__(self, token: str, database_url: str, gemini_api_key: str = None):
        try:
            self.db = Database(database_url)
            self.ai = SimpleAI(gemini_api_key)
            
            # Create application
            self.app = (Application.builder()
                       .token(token)
                       .connect_timeout(60)
                       .read_timeout(60)
                       .build())
            
            self.setup_handlers()
            logger.info("✅ Bot initialized successfully")
        except Exception as e:
            logger.error(f"❌ Bot initialization failed: {e}")
            raise
    
    def setup_handlers(self):
        # Commands
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("assess", self.assess_command))
        self.app.add_handler(CommandHandler("crisis", self.crisis_command))
        self.app.add_handler(CommandHandler("cancel", self.cancel_command))
        
        # Messages and callbacks
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        logger.info("✅ Handlers set up")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            user = self.db.get_or_create_user(update.effective_user)
            
            welcome_msg = f"""🌟 **Welcome to TM-Health Professional**

Hi {user.first_name}! I'm your mental health support companion, providing evidence-based tools and professional guidance for teens.

**What I can help with:**
• Mental health screening and assessment
• Coping strategies for anxiety and depression  
• Crisis support and safety resources
• Professional mental health guidance

**Available commands:**
/assess - Take a mental health screening
/crisis - Emergency support resources
/help - View all commands

**Important:** I provide support and coping skills, but I'm not a replacement for professional therapy or emergency services.

How are you feeling today? 💙"""
            
            await update.message.reply_text(welcome_msg)
            
        except Exception as e:
            logger.error(f"Error in start_command: {e}")
            await update.message.reply_text("Welcome! I'm here to provide mental health support. Use /help to see what I can do.")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_msg = """🌟 **TM-Health Commands**

**Core Commands:**
/start - Welcome and introduction
/help - Show this help menu  
/cancel - Cancel any active process

**Mental Health Tools:**
/assess - Professional mental health screening
/crisis - Emergency crisis support resources

**How to use:**
• Just message me about how you're feeling
• I'll provide supportive responses and coping strategies
• Use /assess for formal mental health screening
• Use /crisis if you need immediate help

**Crisis Support (24/7):**
📞 Lifeline: 13 11 14
🧒 Kids Helpline: 1800 55 1800
🚨 Emergency: 000

I'm here to listen and support you! 💙"""
        
        await update.message.reply_text(help_msg)
    
    async def assess_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("📋 Depression Screening (PHQ-9)", callback_data="assess_depression")],
            [InlineKeyboardButton("😰 Anxiety Screening (GAD-7)", callback_data="assess_anxiety")],
            [InlineKeyboardButton("🛡️ Safety Assessment", callback_data="assess_safety")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        assess_msg = """📊 **Professional Mental Health Assessment**

Choose a clinically validated assessment tool:

**Depression Screening (PHQ-9)** - 9 questions, 3 minutes
**Anxiety Screening (GAD-7)** - 7 questions, 2 minutes  
**Safety Assessment** - Crisis risk evaluation

These are the same tools used by mental health professionals. Your responses help identify if additional support would be beneficial.

Which assessment would you like to complete?"""
        
        await update.message.reply_text(assess_msg, reply_markup=reply_markup)
    
    async def crisis_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        crisis_msg = """🆘 **Crisis Support Resources - Australia**

**If you're in immediate danger, call 000 now.**

**24/7 Crisis Support:**
📞 **Lifeline Australia: 13 11 14**
   • Suicide prevention and crisis support
   • Available 24/7, free and confidential

🧒 **Kids Helpline: 1800 55 1800**  
   • For people aged 5-25 years
   • Phone and online counseling 24/7

💬 **Crisis Text Support:**
   • Text **HELLO** to **0477 13 11 14**
   • Available 6PM - midnight AEST

🌐 **Beyond Blue: 1300 22 4636**
   • Depression, anxiety, suicide prevention
   • 24/7 support and information

**Online Crisis Chat:**
• lifeline.org.au (click 'Crisis Chat')
• kidshelpline.com.au (web chat)

**Remember:** Crisis feelings are temporary. You don't have to face this alone. Professional help is available right now.

Your life has value and meaning. 💙"""
        
        await update.message.reply_text(crisis_msg)
    
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        state = self.db.get_conversation_state(user_id)
        
        if state:
            self.db.clear_conversation_state(user_id)
            await update.message.reply_text("✅ Process cancelled. You can start fresh anytime!")
        else:
            await update.message.reply_text("No active process to cancel. Use /help to see available commands.")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            user_id = update.effective_user.id
            message_text = update.message.text
            
            # Get or create user
            user = self.db.get_or_create_user(update.effective_user)
            user_name = user.first_name
            
            # Check conversation state
            state = self.db.get_conversation_state(user_id)
            
            if state and state.state.startswith('assessment'):
                # Handle assessment responses
                await self.handle_assessment_response(update, state)
                return
            
            # Crisis detection
            if self.ai.detect_crisis(message_text):
                response = f"""🚨 **I'm very concerned about your safety, {user_name}.**

Please reach out for immediate help:
📞 **Lifeline: 13 11 14** (24/7)
🧒 **Kids Helpline: 1800 55 1800** (24/7)
🚨 **Emergency: 000**

You matter and professional help is available right now. 💙"""
                
                await update.message.reply_text(response)
                return
            
            # Normal AI response
            response = await self.ai.get_response(message_text, user_name)
            await update.message.reply_text(response)
            
            # Update conversation count
            session = self.db.get_session()
            try:
                user.conversation_count = (user.conversation_count or 0) + 1
                session.add(user)
                session.commit()
            finally:
                session.close()
            
        except Exception as e:
            logger.error(f"Error in handle_message: {e}")
            await update.message.reply_text(
                "I'm having a technical issue. If this is urgent:\n\n"
                "📞 Lifeline: 13 11 14\n"
                "🧒 Kids Helpline: 1800 55 1800\n" 
                "🚨 Emergency: 000"
            )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            query = update.callback_query
            await query.answer()
            
            user_id = query.from_user.id
            
            if query.data == "assess_depression":
                self.db.set_conversation_state(user_id, 'assessment_phq', 0, {'responses': []})
                await self.start_phq_assessment(query)
            elif query.data == "assess_anxiety":
                self.db.set_conversation_state(user_id, 'assessment_gad', 0, {'responses': []})
                await self.start_gad_assessment(query)
            elif query.data == "assess_safety":
                await query.edit_message_text("Safety assessment coming soon. For immediate help, call Lifeline: 13 11 14")
                
        except Exception as e:
            logger.error(f"Error in handle_callback: {e}")
    
    async def start_phq_assessment(self, query):
        await query.edit_message_text(
            """📋 **Depression Screening (PHQ-9)**

Over the last 2 weeks, how often have you been bothered by the following problems?

**Respond with:**
0 = Not at all
1 = Several days
2 = More than half the days
3 = Nearly every day

**Question 1 of 9:**
"Little interest or pleasure in doing things"

Please respond with 0, 1, 2, or 3"""
        )
    
    async def start_gad_assessment(self, query):
        await query.edit_message_text(
            """😰 **Anxiety Screening (GAD-7)**

Over the last 2 weeks, how often have you been bothered by the following problems?

**Respond with:**
0 = Not at all
1 = Several days  
2 = More than half the days
3 = Nearly every day

**Question 1 of 7:**
"Feeling nervous, anxious, or on edge"

Please respond with 0, 1, 2, or 3"""
        )
    
    async def handle_assessment_response(self, update: Update, state):
        try:
            user_id = update.effective_user.id
            response = update.message.text.strip()
            
            # Validate response
            try:
                score = int(response)
                if score not in [0, 1, 2, 3]:
                    await update.message.reply_text(
                        "Please respond with 0, 1, 2, or 3:\n"
                        "0 = Not at all\n1 = Several days\n2 = More than half the days\n3 = Nearly every day"
                    )
                    return
            except ValueError:
                await update.message.reply_text("Please respond with a number: 0, 1, 2, or 3")
                return
            
            # Store response
            responses = state.data.get('responses', [])
            responses.append(score)
            
            # Continue or complete assessment
            if state.state == 'assessment_phq':
                await self.continue_phq(update, user_id, responses)
            elif state.state == 'assessment_gad':
                await self.continue_gad(update, user_id, responses)
                
        except Exception as e:
            logger.error(f"Error in assessment response: {e}")
            await update.message.reply_text("Assessment error. Please try /assess again.")
    
    async def continue_phq(self, update: Update, user_id: int, responses: list):
        questions = [
            "Little interest or pleasure in doing things",
            "Feeling down, depressed, or hopeless",
            "Trouble falling or staying asleep, or sleeping too much",
            "Feeling tired or having little energy",
            "Poor appetite or overeating",
            "Feeling bad about yourself — or that you are a failure or have let yourself or your family down",
            "Trouble concentrating on things",
            "Moving or speaking so slowly that other people could have noticed",
            "Thoughts that you would be better off dead, or of hurting yourself"
        ]
        
        step = len(responses)
        
        if step < len(questions):
            # Continue assessment
            self.db.set_conversation_state(user_id, 'assessment_phq', step, {'responses': responses})
            await update.message.reply_text(
                f"**Question {step + 1} of {len(questions)}:**\n"
                f'"{questions[step]}"\n\n'
                f"0 = Not at all\n1 = Several days\n2 = More than half the days\n3 = Nearly every day"
            )
        else:
            # Complete assessment
            await self.complete_phq(update, user_id, responses)
    
    async def continue_gad(self, update: Update, user_id: int, responses: list):
        questions = [
            "Feeling nervous, anxious, or on edge",
            "Not being able to stop or control worrying",
            "Worrying too much about different things",
            "Trouble relaxing",
            "Being so restless that it is hard to sit still",
            "Becoming easily annoyed or irritable",
            "Feeling afraid as if something awful might happen"
        ]
        
        step = len(responses)
        
        if step < len(questions):
            self.db.set_conversation_state(user_id, 'assessment_gad', step, {'responses': responses})
            await update.message.reply_text(
                f"**Question {step + 1} of {len(questions)}:**\n"
                f'"{questions[step]}"\n\n'
                f"0 = Not at all\n1 = Several days\n2 = More than half the days\n3 = Nearly every day"
            )
        else:
            await self.complete_gad(update, user_id, responses)
    
    async def complete_phq(self, update: Update, user_id: int, responses: list):
        total_score = sum(responses)
        
        # Interpret score
        if total_score <= 4:
            severity = "Minimal depression"
            recommendation = "Your responses suggest minimal depression symptoms. Continue with healthy habits."
        elif total_score <= 9:
            severity = "Mild depression"
            recommendation = "Your responses suggest mild depression. Consider speaking with a counselor."
        elif total_score <= 14:
            severity = "Moderate depression"
            recommendation = "Your responses suggest moderate depression. I recommend professional support."
        elif total_score <= 19:
            severity = "Moderately severe depression"
            recommendation = "Your responses suggest moderately severe depression. Please see a mental health professional."
        else:
            severity = "Severe depression"
            recommendation = "Your responses suggest severe depression. Please see a mental health professional soon."
        
        # Save results
        session = self.db.get_session()
        try:
            assessment = Assessment(
                user_id=user_id,
                assessment_type='PHQ-9',
                score=total_score,
                responses=responses
            )
            session.add(assessment)
            session.commit()
        finally:
            session.close()
        
        # Clear state
        self.db.clear_conversation_state(user_id)
        
        # Send results
        results_msg = f"""📋 **Depression Assessment Results**

**Your Score:** {total_score}/27
**Level:** {severity}

**Recommendation:** {recommendation}

**Next Steps:**
• Continue self-care and healthy habits
• Consider professional support if symptoms persist
• Contact crisis support if you have thoughts of self-harm

**Resources:**
• GP for Mental Health Care Plan
• Headspace (12-25 years): headspace.org.au
• Kids Helpline: 1800 55 1800

Remember: This is a screening tool, not a diagnosis."""
        
        await update.message.reply_text(results_msg)
        
        # Show crisis resources for high scores
        if total_score >= 15:
            await update.message.reply_text(
                "Given your score, please consider reaching out for professional support. "
                "If you have thoughts of self-harm, please call Lifeline: 13 11 14 immediately."
            )
    
    async def complete_gad(self, update: Update, user_id: int, responses: list):
        total_score = sum(responses)
        
        if total_score <= 4:
            severity = "Minimal anxiety"
            recommendation = "Your responses suggest minimal anxiety symptoms."
        elif total_score <= 9:
            severity = "Mild anxiety"
            recommendation = "Your responses suggest mild anxiety. Consider anxiety management techniques."
        elif total_score <= 14:
            severity = "Moderate anxiety"
            recommendation = "Your responses suggest moderate anxiety. Consider professional support."
        else:
            severity = "Severe anxiety"
            recommendation = "Your responses suggest severe anxiety. Please consider professional help."
        
        # Save and clear
        session = self.db.get_session()
        try:
            assessment = Assessment(
                user_id=user_id,
                assessment_type='GAD-7',
                score=total_score,
                responses=responses
            )
            session.add(assessment)
            session.commit()
        finally:
            session.close()
        
        self.db.clear_conversation_state(user_id)
        
        results_msg = f"""😰 **Anxiety Assessment Results**

**Your Score:** {total_score}/21
**Level:** {severity}

**Recommendation:** {recommendation}

**Anxiety Management:**
• Deep breathing exercises
• Progressive muscle relaxation
• Mindfulness techniques
• Regular exercise

**Professional Support:**
• GP for Mental Health Care Plan
• Anxiety-specific therapy (CBT)
• Headspace or local counseling

This is a screening tool, not a diagnosis."""
        
        await update.message.reply_text(results_msg)
    
    def start_health_server(self, port: int):
        """Health check server for Render"""
        import threading
        from http.server import HTTPServer, BaseHTTPRequestHandler
        
        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'Teen Support Bot is running')
            
            def log_message(self, format, *args):
                pass
        
        def run_server():
            try:
                server = HTTPServer(('0.0.0.0', port), HealthHandler)
                logger.info(f"✅ Health server started on port {port}")
                server.serve_forever()
            except Exception as e:
                logger.warning(f"⚠️ Health server failed: {e}")
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
    
    def run(self):
        """Start the bot"""
        try:
            logger.info("🌸 Starting Teen Support Bot...")
            print("🌸 Starting Teen Support Bot...")
            
            # Start health server
            port = int(os.getenv('PORT', 10000))
            self.start_health_server(port)
            
            # Start bot with retries
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    print(f"🔄 Connection attempt {attempt + 1}/{max_retries}...")
                    
                    self.app.run_polling(
                        drop_pending_updates=True,
                        allowed_updates=['message', 'callback_query'],
                        poll_interval=3.0,
                        timeout=20,
                        bootstrap_retries=5
                    )
                    break
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        import time
                        delay = 10 * (attempt + 1)
                        print(f"⏳ Retrying in {delay} seconds...")
                        time.sleep(delay)
                        continue
                    raise e
                    
        except Exception as e:
            logger.error(f"❌ Bot failed to start: {e}")
            print(f"❌ Bot failed to start: {e}")
            
            # Keep service alive
            import time
            while True:
                time.sleep(300)
                print("💤 Service alive")

def main():
    """Main function"""
    try:
        config = Config()
        config.validate()
        
        print("✅ Configuration validated")
        
        bot = TeenSupportBot(
            config.TELEGRAM_TOKEN,
            config.DATABASE_URL,
            config.GEMINI_API_KEY
        )
        
        print("🌟 Teen Support Bot ready!")
        bot.run()
        
    except KeyboardInterrupt:
        print("👋 Bot stopped")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        print(f"❌ Fatal error: {e}")
        
        # Keep service alive for health checks
        import time
        while True:
            time.sleep(300)
            print("💤 Service staying alive")

if __name__ == "__main__":
    main()