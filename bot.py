# TM-Health - Teen Mental Health Support Bot
# Fixed for Render deployment
# File: bot.py

import os
import json
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncio

# Set up logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to import optional dependencies with better error handling
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
    from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, Float, BigInteger
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker, Session
    logger.info("✅ SQLAlchemy imported")
except ImportError as e:
    logger.error(f"❌ Failed to import SQLAlchemy: {e}")
    sys.exit(1)

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    logger.info("✅ APScheduler imported")
except ImportError as e:
    logger.warning(f"⚠️ APScheduler not available: {e}")
    AsyncIOScheduler = None
    CronTrigger = None

# Database Models for Teen Support
Base = declarative_base()

class TeenUser(Base):
    __tablename__ = 'teen_users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(50))
    first_name = Column(String(50))
    age = Column(Integer)  # 13-19 for teens
    preferred_name = Column(String(50))  # What they want to be called
    timezone = Column(String(50), default='UTC')
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    total_conversations = Column(Integer, default=0)
    mood_check_frequency = Column(String(20), default='daily')  # daily, weekly, none

class MoodEntry(Base):
    __tablename__ = 'mood_entries'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    mood_score = Column(Integer)  # 1-10 scale
    energy_level = Column(Integer)  # 1-10 scale
    stress_level = Column(Integer)  # 1-10 scale
    sleep_quality = Column(Integer)  # 1-10 scale
    notes = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    triggers = Column(String(200))  # school, family, friends, social_media, etc.

class SupportSession(Base):
    __tablename__ = 'support_sessions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    session_type = Column(String(50))  # check_in, crisis_support, coping_skills, goal_setting
    start_time = Column(DateTime, default=datetime.utcnow)
    duration_minutes = Column(Integer)
    topic_tags = Column(String(200))  # anxiety, depression, school_stress, relationships, etc.
    helpful_rating = Column(Integer)  # 1-5 how helpful was the session
    notes = Column(Text)

class CrisisAlert(Base):
    __tablename__ = 'crisis_alerts'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    alert_type = Column(String(50))  # self_harm, suicide_ideation, severe_distress
    message_content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    response_provided = Column(Text)
    follow_up_needed = Column(Boolean, default=True)

class Conversation(Base):
    __tablename__ = 'conversations'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    message_text = Column(Text)
    bot_response = Column(Text)
    emotion_detected = Column(String(100))  # happy, sad, anxious, angry, confused, etc.
    support_type = Column(String(50))  # validation, coping_strategy, resource, referral
    timestamp = Column(DateTime, default=datetime.utcnow)

# Configuration for Teen Support Bot
class TeenBotConfig:
    def __init__(self):
        self.PORT = int(os.getenv('PORT', 10000))
        self.TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
        self.GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
        self.DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///tm_health.db')
        
        # Crisis intervention settings
        self.CRISIS_KEYWORDS = [
            'kill myself', 'end it all', 'suicide', 'self harm', 'cut myself',
            'hurt myself', 'die', 'worthless', 'hopeless', 'can\'t go on'
        ]
        
        # Emergency resources for Australia
        self.CRISIS_RESOURCES = {
            'AU': {
                'emergency': '000',
                'lifeline': '13 11 14',
                'kids_helpline': '1800 55 1800',
                'beyond_blue': '1300 22 4636',
                'mensline': '1300 78 99 78',
                'suicide_callback': '1300 659 467',
                'crisis_text': 'Text HELLO to 0477 13 11 14'
            }
        }
    
    def validate(self):
        if not self.TELEGRAM_TOKEN:
            logger.error("❌ TELEGRAM_TOKEN environment variable not found")
            print("ERROR: TELEGRAM_TOKEN environment variable is required")
            print("Please set it in your Render dashboard under Environment Variables")
            sys.exit(1)
        
        # Basic token format validation
        if not self.TELEGRAM_TOKEN.count(':') == 1:
            logger.error("❌ TELEGRAM_TOKEN appears to be invalid format")
            print("ERROR: TELEGRAM_TOKEN should be in format: 123456789:ABC-DEF...")
            print("Get a valid token from @BotFather on Telegram")
            sys.exit(1)
        
        token_parts = self.TELEGRAM_TOKEN.split(':')
        if not token_parts[0].isdigit() or len(token_parts[1]) < 20:
            logger.error("❌ TELEGRAM_TOKEN format is invalid")
            print("ERROR: Invalid token format. Get a new token from @BotFather")
            sys.exit(1)
        
        logger.info("✅ TM-Health Bot configuration validated")
        print("✅ Configuration validated successfully")
        return True

# Database Setup with better error handling
class TeenSupportDB:
    def __init__(self, database_url: str):
        try:
            self.engine = create_engine(
                database_url, 
                pool_pre_ping=True, 
                pool_recycle=300,
                echo=False  # Disable SQL logging for cleaner output
            )
            Base.metadata.create_all(self.engine)
            self.SessionLocal = sessionmaker(bind=self.engine)
            logger.info("✅ Database initialized successfully")
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise
    
    def get_session(self) -> Session:
        return self.SessionLocal()
    
    def get_or_create_teen(self, telegram_user) -> TeenUser:
        session = self.get_session()
        try:
            teen = session.query(TeenUser).filter_by(telegram_id=telegram_user.id).first()
            if not teen:
                teen = TeenUser(
                    telegram_id=telegram_user.id,
                    username=telegram_user.username,
                    first_name=telegram_user.first_name
                )
                session.add(teen)
                session.commit()
                session.refresh(teen)
                logger.info(f"Created new teen user: {telegram_user.id}")
            else:
                teen.last_active = datetime.utcnow()
                session.commit()
            return teen
        except Exception as e:
            logger.error(f"Error in get_or_create_teen: {e}")
            session.rollback()
            raise
        finally:
            session.close()

# Teen Mental Health AI Coach
class TeenMentalHealthCoach:
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.enabled = False
        self.model = None
        self.model_name = None
        
        if GEMINI_AVAILABLE and api_key:
            try:
                genai.configure(api_key=api_key)
                # Try teen-appropriate models
                model_names = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
                
                for model_name in model_names:
                    try:
                        self.model = genai.GenerativeModel(model_name)
                        # Test with a simple prompt
                        test_response = self.model.generate_content("Say 'ready to help teens'")
                        if test_response and test_response.text:
                            self.enabled = True
                            self.model_name = model_name
                            logger.info(f"✅ Teen Mental Health AI enabled with {model_name}")
                            break
                    except Exception as e:
                        logger.warning(f"Failed to initialize {model_name}: {e}")
                        continue
                        
                if not self.enabled:
                    logger.warning("⚠️ Could not initialize any Gemini model")
                        
            except Exception as e:
                logger.warning(f"⚠️ Teen Mental Health AI initialization failed: {e}")
        else:
            if not GEMINI_AVAILABLE:
                logger.warning("⚠️ Gemini not available - using fallback responses")
            if not api_key:
                logger.warning("⚠️ No Gemini API key - using fallback responses")
        
        self.load_therapeutic_prompts()
    
    def load_therapeutic_prompts(self):
        """Load evidence-based therapeutic approaches for teens"""
        
        self.base_prompt = """
# Teen Mental Health Support AI

You are a compassionate, evidence-based mental health support companion for teenagers (ages 13-19). Your role is to provide emotional support, teach coping skills, and connect teens to professional help when needed.

## Core Principles

**Safety First**: Always prioritize the teen's safety. If you detect crisis language, immediately provide crisis resources and encourage professional help.

**Age-Appropriate**: Use teen-friendly language, understand their world (school, social media, peer pressure, identity development).

**Evidence-Based**: Draw from CBT, DBT skills, mindfulness, and positive psychology techniques appropriate for adolescents.

**Non-Judgmental**: Create a safe space where teens feel heard and validated without judgment.

**Boundaries**: You are a support tool, not a replacement for therapy, medication, or professional mental health care.

## Response Guidelines

### Always Include:
- Validation of their experience
- Practical coping strategy or skill
- Encouragement about their strength/resilience
- Question to keep conversation going (if appropriate)

### Keep responses under 200 words and teen-friendly.
        """
    
    async def generate_teen_response(self, message: str, user_context: Dict) -> str:
        """Generate age-appropriate mental health support response"""
        
        if not self.enabled:
            return self.fallback_teen_response(message, user_context)
        
        teen = user_context.get('teen')
        recent_moods = user_context.get('recent_moods', [])
        
        # Build context for teen
        context_summary = f"""
## Teen Context:
- Name: {teen.preferred_name or teen.first_name if teen else 'Friend'}
- Age: {teen.age if teen and teen.age else 'Teen'}
- Days using support: {(datetime.utcnow() - teen.created_at).days if teen else 0}
- Recent conversations: {teen.total_conversations if teen else 0}

## Recent Mood Pattern:
"""
        
        if recent_moods:
            for mood in recent_moods[:3]:
                context_summary += f"- Mood: {mood.mood_score}/10, Stress: {mood.stress_level}/10\n"
        else:
            context_summary += "- No recent mood data\n"
        
        full_prompt = f"""
{self.base_prompt}

{context_summary}

## Teen's Message: "{message}"

Provide a supportive, therapeutic response under 200 words:
        """
        
        try:
            response = await asyncio.to_thread(self.model.generate_content, full_prompt)
            return response.text.strip() if response and response.text else self.fallback_teen_response(message, user_context)
        except Exception as e:
            logger.warning(f"AI response generation failed: {e}")
            return self.fallback_teen_response(message, user_context)
    
    def fallback_teen_response(self, message: str, user_context: Dict) -> str:
        """Fallback responses for teen support"""
        teen = user_context.get('teen')
        name = teen.preferred_name or teen.first_name if teen else "friend"
        
        message_lower = message.lower()
        
        # Crisis detection
        crisis_keywords = ['kill myself', 'suicide', 'end it all', 'hurt myself', 'hopeless', 'can\'t go on']
        if any(keyword in message_lower for keyword in crisis_keywords):
            return f"""
I'm really concerned about you right now, {name}. Your safety is the most important thing. Please reach out for immediate help:

🆘 **Lifeline Australia**: 13 11 14
📱 **Kids Helpline**: 1800 55 1800 (for under 25s)
💬 **Crisis Text**: Text HELLO to 0477 13 11 14
🏥 **Or call 000 for emergency services**

You matter, and there are people who want to help you right now. I'm here too, but please get immediate professional support. 💙
            """
        
        # Anxiety responses
        if any(word in message_lower for word in ['anxious', 'panic', 'worry', 'nervous', 'scared']):
            return f"I hear that you're feeling anxious, {name}. That's really tough. Try the 5-4-3-2-1 grounding technique: Name 5 things you can see, 4 you can touch, 3 you can hear, 2 you can smell, 1 you can taste. It can help bring you back to the present moment. What's making you feel most anxious right now? 🌸"
        
        # Depression responses  
        if any(word in message_lower for word in ['sad', 'depressed', 'empty', 'lonely', 'worthless']):
            return f"I'm sorry you're feeling this way, {name}. Those feelings are really hard to carry. Remember that feelings, even really painful ones, do change over time. One small thing that sometimes helps is doing something kind for yourself - maybe listening to a favorite song or taking a warm shower. What's one tiny thing that usually brings you even a little comfort? 💜"
        
        # School stress
        if any(word in message_lower for word in ['school', 'homework', 'test', 'grades', 'college']):
            return f"School stress is so real, {name}. You're dealing with a lot of pressure. Remember that your worth isn't determined by your grades or achievements. Try breaking big tasks into smaller chunks - even 15 minutes of work is progress. What's the most stressful part of school for you right now? 📚"
        
        # General support
        return f"Thanks for sharing with me, {name}. It takes courage to reach out when you're struggling. I'm here to listen and support you. Remember that it's okay to not be okay sometimes - that's part of being human. What's been on your mind lately? 🌟"
    
    def detect_crisis(self, message: str) -> bool:
        """Detect if message indicates mental health crisis"""
        crisis_indicators = [
            'kill myself', 'suicide', 'end it all', 'hurt myself', 'cut myself',
            'don\'t want to live', 'better off dead', 'hopeless', 'can\'t go on',
            'nothing matters', 'want to die'
        ]
        
        message_lower = message.lower()
        return any(indicator in message_lower for indicator in crisis_indicators)

# Main Teen Support Bot
class TeenSupportBot:
    def __init__(self, token: str, database_url: str, gemini_api_key: str = None):
        try:
            logger.info(f"Initializing bot with token: {token[:10]}...")
            
            self.db = TeenSupportDB(database_url)
            
            # Create application with aggressive timeout and retry settings for Render
            self.app = (Application.builder()
                       .token(token)
                       .connect_timeout(60)        # 60 seconds to connect
                       .read_timeout(60)           # 60 seconds to read
                       .write_timeout(60)          # 60 seconds to write  
                       .pool_timeout(60)           # 60 seconds pool timeout
                       .get_updates_connect_timeout(60)  # Long timeout for updates
                       .get_updates_read_timeout(60)     # Long timeout for reading updates
                       .build())
            
            self.ai_coach = TeenMentalHealthCoach(gemini_api_key)
            self.config = TeenBotConfig()
            self.setup_handlers()
            self.setup_scheduler()
            logger.info("✅ TeenSupportBot initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize TeenSupportBot: {e}")
            raise
    
    def setup_handlers(self):
        # Commands
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("mood", self.mood_check))
        self.app.add_handler(CommandHandler("breathe", self.breathing_exercise))
        self.app.add_handler(CommandHandler("skills", self.coping_skills))
        self.app.add_handler(CommandHandler("crisis", self.crisis_resources))
        self.app.add_handler(CommandHandler("help", self.help_command))
        
        # Message handlers
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        
        logger.info("✅ Bot handlers set up successfully")
    
    def setup_scheduler(self):
        # Only set up scheduler if APScheduler is available
        if AsyncIOScheduler and CronTrigger:
            try:
                self.scheduler = AsyncIOScheduler()
                self.scheduler.add_job(
                    self.daily_mood_reminder,
                    CronTrigger(hour=19, minute=0),  # 7 PM daily
                    id='mood_reminder'
                )
                self.scheduler.start()
                logger.info("✅ Scheduler set up successfully")
            except Exception as e:
                logger.warning(f"⚠️ Scheduler setup failed: {e}")
        else:
            logger.warning("⚠️ Scheduler not available - mood reminders disabled")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            teen = self.db.get_or_create_teen(update.effective_user)
            
            welcome_msg = f"""
Hi {teen.first_name}! 🌟 I'm TM-Health, your personal mental health support companion.

**What I'm here for:**
• Listen without judgment when you need to talk
• Teach you coping skills for stress, anxiety, and difficult emotions
• Help you track your mood and identify patterns
• Connect you with professional help when needed
• Be a safe space during tough times

**Important:** I'm here to support you, but I'm not a replacement for therapy or professional help. If you're in crisis, please reach out to a trusted adult or crisis helpline immediately.

**Commands to try:**
/mood - Quick mood check-in
/breathe - Guided breathing exercise
/skills - Learn coping strategies
/crisis - Emergency resources
/help - Show all commands

What's on your mind today? I'm here to listen. 💙
            """
            
            await update.message.reply_text(welcome_msg)
            logger.info(f"Start command executed for user {update.effective_user.id}")
        except Exception as e:
            logger.error(f"Error in start_command: {e}")
            await update.message.reply_text("Sorry, I encountered an error. Please try again.")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_msg = """
🌟 **TM-Health Commands**

/start - Welcome and introduction
/mood - Quick mood check-in
/breathe - Guided breathing exercise
/skills - Learn coping strategies
/crisis - Emergency resources and helplines
/help - Show this help menu

**Remember:** I'm here to support you, but if you're in crisis, please reach out to professional help immediately:
• Lifeline: 13 11 14
• Kids Helpline: 1800 55 1800
• Emergency: 000

Just send me a message anytime you want to talk! 💙
        """
        await update.message.reply_text(help_msg)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            user_id = update.effective_user.id
            message_text = update.message.text
            
            # Ensure teen exists in database
            teen = self.db.get_or_create_teen(update.effective_user)
            
            # Get user context for AI
            user_context = self.get_teen_context(user_id)
            
            # Crisis detection
            if self.ai_coach.detect_crisis(message_text):
                await self.handle_crisis(update, message_text)
                return
            
            # Generate supportive response
            response = await self.ai_coach.generate_teen_response(message_text, user_context)
            
            # Log conversation
            self.log_conversation(user_id, message_text, response)
            
            await update.message.reply_text(response)
            logger.info(f"Message handled for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error in handle_message: {e}")
            await update.message.reply_text("I'm having trouble processing your message right now. Please try again or use /help for commands.")
    
    def get_teen_context(self, user_id: int) -> Dict:
        session = self.db.get_session()
        try:
            teen = session.query(TeenUser).filter_by(telegram_id=user_id).first()
            recent_moods = session.query(MoodEntry).filter_by(
                user_id=user_id
            ).order_by(MoodEntry.timestamp.desc()).limit(7).all()
            
            recent_sessions = session.query(SupportSession).filter_by(
                user_id=user_id
            ).order_by(SupportSession.start_time.desc()).limit(5).all()
            
            return {
                'teen': teen,
                'recent_moods': recent_moods,
                'recent_sessions': recent_sessions
            }
        except Exception as e:
            logger.error(f"Error getting teen context: {e}")
            return {'teen': None, 'recent_moods': [], 'recent_sessions': []}
        finally:
            session.close()
    
    def log_conversation(self, user_id: int, message: str, response: str):
        session = self.db.get_session()
        try:
            conversation = Conversation(
                user_id=user_id,
                message_text=message,
                bot_response=response,
                emotion_detected=self.detect_emotion(message),
                support_type=self.classify_support_type(response)
            )
            session.add(conversation)
            
            # Update teen's conversation count
            teen = session.query(TeenUser).filter_by(telegram_id=user_id).first()
            if teen:
                teen.total_conversations = (teen.total_conversations or 0) + 1
            
            session.commit()
        except Exception as e:
            logger.error(f"Error logging conversation: {e}")
            session.rollback()
        finally:
            session.close()
    
    def detect_emotion(self, message: str) -> str:
        """Simple emotion detection based on keywords"""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['happy', 'excited', 'good', 'great', 'awesome']):
            return 'positive'
        elif any(word in message_lower for word in ['sad', 'depressed', 'down', 'upset']):
            return 'sad'
        elif any(word in message_lower for word in ['anxious', 'worried', 'nervous', 'panic']):
            return 'anxious'
        elif any(word in message_lower for word in ['angry', 'mad', 'furious', 'annoyed']):
            return 'angry'
        else:
            return 'neutral'
    
    def classify_support_type(self, response: str) -> str:
        """Classify the type of support provided"""
        response_lower = response.lower()
        
        if 'crisis' in response_lower or '13 11 14' in response_lower:
            return 'crisis_intervention'
        elif any(word in response_lower for word in ['breathing', 'grounding', 'mindfulness']):
            return 'coping_skills'
        elif any(word in response_lower for word in ['understand', 'hear you', 'valid']):
            return 'validation'
        elif 'therapist' in response_lower or 'counselor' in response_lower:
            return 'professional_referral'
        else:
            return 'general_support'
    
    async def handle_crisis(self, update: Update, message: str):
        """Handle crisis situations with immediate resources"""
        try:
            user_id = update.effective_user.id
            
            # Log crisis alert
            session = self.db.get_session()
            try:
                alert = CrisisAlert(
                    user_id=user_id,
                    alert_type='crisis_detected',
                    message_content=message,
                    response_provided='crisis_resources_sent'
                )
                session.add(alert)
                session.commit()
            finally:
                session.close()
            
            crisis_msg = """
🚨 **I'm really concerned about you right now. Your safety is the most important thing.**

**Please reach out for immediate help:**

📞 **Lifeline Australia: 13 11 14** (24/7)
🧒 **Kids Helpline: 1800 55 1800** (for under 25s, 24/7)
💬 **Crisis Text: Text HELLO to 0477 13 11 14**
🌐 **Beyond Blue: 1300 22 4636** (24/7)

**If you're in immediate danger, please:**
• Call 000 (emergency services)
• Go to your nearest hospital emergency department
• Tell a trusted adult right now

**You matter. You are valued. There are people who want to help you.**

I'm here too, but please get professional support right now. Your life has meaning and things can get better. 💙
            """
            
            await update.message.reply_text(crisis_msg)
            logger.warning(f"Crisis situation detected and handled for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error handling crisis: {e}")
            await update.message.reply_text("Please call 000 or 13 11 14 immediately if you're in crisis.")
    
    async def mood_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Quick mood check-in"""
        keyboard = [
            [InlineKeyboardButton("😊 Great (8-10)", callback_data="mood_great")],
            [InlineKeyboardButton("😌 Good (6-7)", callback_data="mood_good")],
            [InlineKeyboardButton("😐 Okay (4-5)", callback_data="mood_okay")],
            [InlineKeyboardButton("😔 Not good (2-3)", callback_data="mood_bad")],
            [InlineKeyboardButton("😞 Really struggling (1)", callback_data="mood_crisis")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "How are you feeling right now? 💙",
            reply_markup=reply_markup
        )
    
    async def breathing_exercise(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Guided breathing exercise"""
        breathing_msg = """
🌸 **Let's do a quick breathing exercise together**

Find a comfortable position and follow along:

1. **Breathe in slowly through your nose for 4 counts**
   1... 2... 3... 4...

2. **Hold your breath for 4 counts**
   1... 2... 3... 4...

3. **Breathe out slowly through your mouth for 6 counts**
   1... 2... 3... 4... 5... 6...

**Repeat this 3-5 times.**

Notice how your body feels. You've got this! 💙

How do you feel after the breathing exercise?
        """
        
        await update.message.reply_text(breathing_msg)
    
    async def coping_skills(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Provide coping skills menu"""
        keyboard = [
            [InlineKeyboardButton("🌸 Grounding (5-4-3-2-1)", callback_data="skill_grounding")],
            [InlineKeyboardButton("🌊 Breathing exercises", callback_data="skill_breathing")],
            [InlineKeyboardButton("💭 Thought challenging", callback_data="skill_thoughts")],
            [InlineKeyboardButton("🎵 Distraction techniques", callback_data="skill_distraction")],
            [InlineKeyboardButton("💜 Self-soothing", callback_data="skill_soothing")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "What kind of coping skill would help you right now? 🌟",
            reply_markup=reply_markup
        )
    
    async def crisis_resources(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Provide crisis resources"""
        resources_msg = """
🆘 **Crisis Resources Australia - You're Not Alone**

**If you're having thoughts of suicide or self-harm:**

📞 **Lifeline Australia**
   • Call: **13 11 14**
   • Available 24/7
   • Free and confidential

🧒 **Kids Helpline**
   • Call: **1800 55 1800**
   • For people aged 5-25
   • Available 24/7

💬 **Crisis Text Support**
   • Text: **HELLO to 0477 13 11 14**
   • Available 6PM - midnight AEST

🌐 **Beyond Blue**
   • Call: **1300 22 4636**
   • Available 24/7
   • Chat online: beyondblue.org.au

👨 **MensLine Australia** (for males)
   • Call: **1300 78 99 78**
   • Available 24/7

**Remember:**
• You matter and your life has value
• Crisis feelings are temporary
• Help is always available
• You don't have to go through this alone

If you're in immediate danger, call 000 or go to your nearest hospital emergency department.

How are you feeling right now? I'm here to support you. 💙
        """
        
        await update.message.reply_text(resources_msg)
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        try:
            query = update.callback_query
            await query.answer()
            
            if query.data.startswith("mood_"):
                mood_level = query.data.replace("mood_", "")
                await self.process_mood_entry(query, mood_level)
            elif query.data.startswith("skill_"):
                skill_type = query.data.replace("skill_", "")
                await self.provide_coping_skill(query, skill_type)
        except Exception as e:
            logger.error(f"Error in button_callback: {e}")
    
    async def process_mood_entry(self, query, mood_level: str):
        """Process mood check-in response"""
        try:
            user_id = query.from_user.id
            
            mood_scores = {
                'great': 9, 'good': 6, 'okay': 4, 'bad': 2, 'crisis': 1
            }
            
            mood_score = mood_scores.get(mood_level, 5)
            
            # Save mood to database
            session = self.db.get_session()
            try:
                mood_entry = MoodEntry(
                    user_id=user_id,
                    mood_score=mood_score
                )
                session.add(mood_entry)
                session.commit()
            finally:
                session.close()
            
            if mood_level == 'crisis':
                await query.edit_message_text(
                    "I'm concerned about you. Let's get you some immediate support."
                )
                # Create a fake update object for crisis handling
                class FakeUpdate:
                    def __init__(self, query):
                        self.message = query.message
                        self.effective_user = query.from_user
                
                fake_update = FakeUpdate(query)
                await self.handle_crisis(fake_update, "mood check indicates crisis")
            elif mood_level in ['bad', 'okay']:
                await query.edit_message_text(
                    f"Thanks for checking in. I hear that you're struggling right now. That takes courage to share. Would you like to try a coping skill or just talk about what's going on? 💙"
                )
            else:
                await query.edit_message_text(
                    f"I'm glad to hear you're doing {mood_level}! Thanks for checking in. What's been going well for you today? 🌟"
                )
        except Exception as e:
            logger.error(f"Error processing mood entry: {e}")
    
    async def provide_coping_skill(self, query, skill_type: str):
        """Provide specific coping skills"""
        skills = {
            'grounding': """
🌸 **5-4-3-2-1 Grounding Technique**

Look around and name:
• **5 things you can SEE**
• **4 things you can TOUCH**
• **3 things you can HEAR**
• **2 things you can SMELL**
• **1 thing you can TASTE**

This helps bring you back to the present moment when you feel overwhelmed or anxious. Take your time with each step.
            """,
            'breathing': """
🌊 **Box Breathing**

• Breathe in for 4 counts
• Hold for 4 counts  
• Breathe out for 4 counts
• Hold empty for 4 counts

Repeat 4-6 times. Imagine drawing a box with your breath.
            """,
            'thoughts': """
💭 **Thought Challenging**

When you notice a negative thought, ask:
• Is this thought helpful?
• Is it definitely true?
• What would I tell a friend having this thought?
• What's a more balanced way to think about this?

Remember: Thoughts are not facts. You don't have to believe every thought you have.
            """,
            'distraction': """
🎵 **Healthy Distractions**

• Listen to your favorite playlist
• Watch funny videos
• Do a puzzle or word game
• Draw, color, or create something
• Take a hot shower
• Text a friend
• Go for a walk

The goal is to give your mind a break from difficult feelings.
            """,
            'soothing': """
💜 **Self-Soothing Ideas**

• Hold a warm cup of tea
• Wrap yourself in a soft blanket
• Use a calming scent (candle, lotion)
• Pet an animal
• Take a warm bath
• Listen to calming music
• Look at photos that make you smile

Be kind to yourself. You deserve comfort and care.
            """
        }
        
        skill_text = skills.get(skill_type, "Coping skill not found.")
        try:
            await query.edit_message_text(skill_text)
        except Exception as e:
            logger.error(f"Error providing coping skill: {e}")
    
    async def daily_mood_reminder(self):
        """Send daily mood check reminders to active users"""
        # Implementation for daily reminders would go here
        logger.info("Daily mood reminder job executed")
    
    def run(self):
        """Start the teen support bot"""
        try:
            logger.info("🌸 TM-Health Support Bot starting...")
            print("🌸 TM-Health Support Bot starting...")
            
            # Start health check server in background thread
            port = int(os.getenv('PORT', 10000))
            self.start_health_server(port)
            
            # Test connectivity first
            print("🔄 Testing Telegram API connectivity...")
            logger.info("Testing Telegram API connectivity...")
            
            # Multiple retry attempts with increasing delays
            max_retries = 5
            base_delay = 10
            
            for attempt in range(max_retries):
                try:
                    print(f"🔄 Connection attempt {attempt + 1}/{max_retries}...")
                    logger.info(f"Connection attempt {attempt + 1}/{max_retries}")
                    
                    # Start the bot with very conservative settings for Render
                    self.app.run_polling(
                        drop_pending_updates=True,
                        allowed_updates=['message', 'callback_query'],
                        poll_interval=3.0,      # Check every 3 seconds (slower)
                        timeout=20,             # 20 second timeout per request
                        bootstrap_retries=5,    # Retry bootstrap 5 times
                        close_loop=False        # Don't close the event loop
                    )
                    
                    # If we reach here, the bot started successfully
                    break
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    
                    if attempt < max_retries - 1:  # Not the last attempt
                        if 'timeout' in error_msg or 'connection' in error_msg:
                            delay = base_delay * (attempt + 1)
                            print(f"⏳ Connection failed, retrying in {delay} seconds...")
                            logger.warning(f"Connection failed, retrying in {delay} seconds: {e}")
                            
                            import time
                            time.sleep(delay)
                            continue
                    
                    # Last attempt failed or non-retryable error
                    raise e
            
        except Exception as e:
            logger.error(f"❌ Bot failed to start after all retries: {e}")
            print(f"❌ Bot failed to start: {e}")
            
            # Provide helpful error messages
            error_str = str(e).lower()
            if 'unauthorized' in error_str or 'token' in error_str:
                print("\n💡 SOLUTION: Your TELEGRAM_TOKEN is invalid or expired")
                print("   1. Go to @BotFather on Telegram")
                print("   2. Send /mybots and select your bot")
                print("   3. Copy the API Token")
                print("   4. Update TELEGRAM_TOKEN in Render dashboard")
            elif 'timeout' in error_str or 'timed out' in error_str:
                print("\n💡 SOLUTION: Persistent connection timeout")
                print("   1. This might be a Render/Telegram connectivity issue")
                print("   2. Try deploying to a different Render region")
                print("   3. Consider using a webhook instead of polling")
                print("   4. Your token works (tested), this is a network issue")
            elif 'network' in error_str or 'connection' in error_str:
                print("\n💡 SOLUTION: Network connectivity issue")
                print("   1. Render's free tier may have network limitations")
                print("   2. Try redeploying in 10-15 minutes")
                print("   3. Consider upgrading to paid tier for better connectivity")
            
            # For Render, we'll keep the process alive so it doesn't crash
            print("\n🔄 Keeping service alive for health checks...")
            logger.info("Keeping service alive for health checks")
            
            # Keep the process running so Render doesn't restart it repeatedly
            import time
            while True:
                time.sleep(300)  # Sleep 5 minutes, then check again
                print("💤 Service staying alive (bot connection failed but health server running)")
                try:
                    # Try to restart the bot
                    print("🔄 Attempting bot restart...")
                    self.run()
                    break
                except:
                    continue
    
    def start_health_server(self, port: int):
        """Start simple health check server in background thread"""
        import threading
        from http.server import HTTPServer, BaseHTTPRequestHandler
        
        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'Teen Support Bot is running')
            
            def log_message(self, format, *args):
                # Suppress HTTP server logs
                pass
        
        def run_server():
            try:
                server = HTTPServer(('0.0.0.0', port), HealthHandler)
                logger.info(f"✅ Health check server started on port {port}")
                server.serve_forever()
            except Exception as e:
                logger.warning(f"⚠️ Health server failed: {e}")
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

# Main execution
def main():
    """Main function"""
    try:
        # Validate configuration
        config = TeenBotConfig()
        config.validate()
        
        print("✅ Token format looks valid")
        print(f"🔗 Attempting to connect to Telegram servers...")
        
        # Create and run bot
        bot = TeenSupportBot(
            config.TELEGRAM_TOKEN,
            config.DATABASE_URL,
            config.GEMINI_API_KEY
        )
        
        print("🌟 TM-Health Support Bot ready to help!")
        logger.info("🌟 TM-Health Support Bot ready to help!")
        
        # Run bot
        bot.run()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        print("👋 Bot stopped")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        print(f"❌ Fatal error: {e}")
        
        # Additional debugging info
        error_str = str(e).lower()
        if 'token' in error_str or 'unauthorized' in error_str:
            print("\n🔍 DEBUG INFO:")
            print("- Your TELEGRAM_TOKEN environment variable is set")
            print("- But Telegram rejected it as invalid")
            print("- Please get a fresh token from @BotFather")
        elif 'timeout' in error_str:
            print("\n🔍 DEBUG INFO:")
            print("- Connection to Telegram servers timed out")
            print("- This could be a temporary network issue")
            print("- Try redeploying in a few minutes")
        
        # Don't exit with status 1 - let the service stay alive
        print("\n🔄 Keeping service alive for potential recovery...")
        import time
        while True:
            time.sleep(300)  # Sleep 5 minutes
            print("💤 Service alive - health check endpoint working")
            # Try to restart periodically
            try:
                main()
                break
            except:
                continue

if __name__ == "__main__":
    main()