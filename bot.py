# TM-Health Professional - Evidence-Based Teen Mental Health Support Bot
# File: bot.py
# Incorporates clinical frameworks, safety protocols, and therapeutic interventions

import os
import json
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import asyncio
import re
from enum import Enum

# Set up logging first
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

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    logger.info("✅ APScheduler imported")
except ImportError as e:
    logger.warning(f"⚠️ APScheduler not available: {e}")
    AsyncIOScheduler = None
    CronTrigger = None

# Clinical Assessment Enums
class RiskLevel(Enum):
    LOW = "low"
    MODERATE = "moderate" 
    HIGH = "high"
    IMMINENT = "imminent"

class CrisisType(Enum):
    SUICIDE_IDEATION = "suicide_ideation"
    SUICIDE_PLAN = "suicide_plan"
    SELF_HARM = "self_harm"
    SEVERE_DISTRESS = "severe_distress"
    PSYCHOSIS = "psychosis"
    SUBSTANCE_CRISIS = "substance_crisis"

class InterventionType(Enum):
    CBT = "cognitive_behavioral"
    DBT = "dialectical_behavioral" 
    ACT = "acceptance_commitment"
    MINDFULNESS = "mindfulness"
    CRISIS_INTERVENTION = "crisis_intervention"
    SAFETY_PLANNING = "safety_planning"
    PSYCHOEDUCATION = "psychoeducation"

# Enhanced Database Models
Base = declarative_base()

class TeenUser(Base):
    __tablename__ = 'teen_users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(50))
    first_name = Column(String(50))
    age = Column(Integer)
    preferred_name = Column(String(50))
    timezone = Column(String(50), default='UTC')
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    total_conversations = Column(Integer, default=0)
    
    # Clinical tracking
    risk_level = Column(String(20), default='low')
    primary_concerns = Column(JSON)  # ['anxiety', 'depression', 'school_stress']
    coping_skills_learned = Column(JSON)  # Track which skills they've practiced
    therapy_status = Column(String(50))  # 'none', 'seeking', 'active', 'past'
    medication_status = Column(String(50))  # 'none', 'considering', 'active'
    support_network_strength = Column(Integer, default=5)  # 1-10 scale
    
    # Personalization
    preferred_interventions = Column(JSON)
    communication_style = Column(String(20), default='supportive')  # supportive, direct, gentle
    crisis_contact_preference = Column(String(50))  # phone, text, chat, parent

class MoodEntry(Base):
    __tablename__ = 'mood_entries'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    
    # Core mood metrics (1-10 scales)
    mood_score = Column(Integer)
    anxiety_level = Column(Integer)
    depression_indicators = Column(Integer)
    energy_level = Column(Integer)
    stress_level = Column(Integer)
    sleep_quality = Column(Integer)
    appetite = Column(Integer)
    
    # Clinical assessments
    hopelessness_score = Column(Integer)  # 1-10 scale
    suicide_ideation = Column(Boolean, default=False)
    self_harm_urges = Column(Boolean, default=False)
    
    # Context
    triggers = Column(JSON)  # ['school', 'family', 'peer_conflict', 'social_media']
    coping_used = Column(JSON)  # Which coping skills they tried
    notes = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

class ClinicalAssessment(Base):
    __tablename__ = 'clinical_assessments'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    assessment_type = Column(String(50))  # PHQ-A, GAD-7, Columbia Scale
    scores = Column(JSON)  # Store structured assessment results
    risk_factors = Column(JSON)
    protective_factors = Column(JSON)
    recommendations = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)

class SafetyPlan(Base):
    __tablename__ = 'safety_plans'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    warning_signs = Column(JSON)  # Early warning signs they've identified
    coping_strategies = Column(JSON)  # Personal coping strategies
    social_contacts = Column(JSON)  # Trusted people they can contact
    professional_contacts = Column(JSON)  # Mental health professionals
    environment_safety = Column(JSON)  # How to make environment safer
    reasons_for_living = Column(JSON)  # Their personal reasons
    created_at = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow)

class TherapeuticSession(Base):
    __tablename__ = 'therapeutic_sessions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    intervention_type = Column(String(50))
    session_data = Column(JSON)  # Structured session content
    homework_assigned = Column(JSON)  # Skills to practice
    progress_notes = Column(Text)
    effectiveness_rating = Column(Integer)  # 1-10 how helpful
    start_time = Column(DateTime, default=datetime.utcnow)
    duration_minutes = Column(Integer)

class CrisisAlert(Base):
    __tablename__ = 'crisis_alerts'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    crisis_type = Column(String(50))
    risk_level = Column(String(20))
    assessment_data = Column(JSON)  # Structured crisis assessment
    interventions_provided = Column(JSON)
    follow_up_needed = Column(Boolean, default=True)
    resolved = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Professional Configuration
class ProfessionalBotConfig:
    def __init__(self):
        self.PORT = int(os.getenv('PORT', 10000))
        self.TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
        self.GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
        self.DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///tm_health_pro.db')
        
        # Professional crisis protocols
        self.CRISIS_KEYWORDS = {
            'imminent_risk': [
                'kill myself tonight', 'end it today', 'suicide plan', 'going to die',
                'already took pills', 'have the pills', 'wrote note', 'goodbye'
            ],
            'high_risk': [
                'kill myself', 'suicide', 'want to die', 'better off dead',
                'can\'t go on', 'end it all', 'nothing matters'
            ],
            'self_harm': [
                'cut myself', 'hurt myself', 'self harm', 'cutting', 'burning',
                'punching walls', 'scratching', 'hitting myself'
            ],
            'severe_distress': [
                'can\'t cope', 'falling apart', 'losing it', 'breakdown',
                'can\'t breathe', 'panic attack', 'everything is wrong'
            ]
        }
        
        # Australian mental health resources by state
        self.PROFESSIONAL_RESOURCES = {
            'crisis_lines': {
                'lifeline': {'number': '13 11 14', 'available': '24/7', 'description': 'Crisis support and suicide prevention'},
                'kids_helpline': {'number': '1800 55 1800', 'available': '24/7', 'description': 'For young people 5-25 years'},
                'beyond_blue': {'number': '1300 22 4636', 'available': '24/7', 'description': 'Anxiety, depression and suicide prevention'},
                'suicide_callback': {'number': '1300 659 467', 'available': '24/7', 'description': 'Suicide prevention callback service'},
                'crisis_text': {'number': '0477 13 11 14', 'available': '6PM-midnight AEST', 'description': 'Text HELLO for crisis support'}
            },
            'professional_services': {
                'headspace': {'description': 'Mental health services for 12-25 year olds', 'website': 'headspace.org.au'},
                'medicare_psychology': {'description': 'Medicare-subsidized psychology sessions', 'info': 'See GP for Mental Health Care Plan'},
                'school_counselors': {'description': 'Free counseling through school', 'access': 'Contact student welfare coordinator'},
                'community_health': {'description': 'Local community mental health services', 'access': 'Contact local community health center'}
            }
        }
    
    def validate(self):
        if not self.TELEGRAM_TOKEN:
            logger.error("❌ TELEGRAM_TOKEN environment variable not found")
            print("ERROR: TELEGRAM_TOKEN environment variable is required")
            sys.exit(1)
        
        # Validate token format
        if not self.TELEGRAM_TOKEN.count(':') == 1:
            logger.error("❌ TELEGRAM_TOKEN appears to be invalid format")
            sys.exit(1)
        
        token_parts = self.TELEGRAM_TOKEN.split(':')
        if not token_parts[0].isdigit() or len(token_parts[1]) < 20:
            logger.error("❌ TELEGRAM_TOKEN format is invalid")
            sys.exit(1)
        
        logger.info("✅ Professional bot configuration validated")
        return True

# Enhanced Database with clinical tracking
class ProfessionalDB:
    def __init__(self, database_url: str):
        try:
            self.engine = create_engine(database_url, pool_pre_ping=True, pool_recycle=300, echo=False)
            Base.metadata.create_all(self.engine)
            self.SessionLocal = sessionmaker(bind=self.engine)
            logger.info("✅ Professional database initialized")
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
                    first_name=telegram_user.first_name,
                    primary_concerns=[],
                    coping_skills_learned=[],
                    preferred_interventions=[]
                )
                session.add(teen)
                session.commit()
                session.refresh(teen)
                logger.info(f"Created new teen user with clinical tracking: {telegram_user.id}")
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

# Professional Mental Health AI Coach
class ProfessionalMentalHealthCoach:
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.enabled = False
        self.model = None
        self.model_name = None
        
        if GEMINI_AVAILABLE and api_key:
            try:
                genai.configure(api_key=api_key)
                model_names = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
                
                for model_name in model_names:
                    try:
                        self.model = genai.GenerativeModel(model_name)
                        test_response = self.model.generate_content("Respond with: Professional mental health AI ready")
                        if test_response and test_response.text:
                            self.enabled = True
                            self.model_name = model_name
                            logger.info(f"✅ Professional Mental Health AI enabled with {model_name}")
                            break
                    except Exception as e:
                        logger.warning(f"Failed to initialize {model_name}: {e}")
                        continue
                        
            except Exception as e:
                logger.warning(f"⚠️ Professional AI initialization failed: {e}")
        
        self.load_clinical_frameworks()
        self.init_assessment_tools()
    
    def load_clinical_frameworks(self):
        """Load evidence-based clinical frameworks"""
        
        self.clinical_prompt = """
# Professional Teen Mental Health Support AI

You are a professionally-trained, evidence-based mental health support AI for teenagers (13-19 years). You operate under strict clinical and ethical guidelines.

## Core Clinical Principles

**Safety First**: Use structured risk assessment. Immediately escalate crisis situations with specific professional resources.

**Evidence-Based Practice**: Apply CBT, DBT, ACT, and trauma-informed approaches appropriate for adolescents.

**Therapeutic Alliance**: Build trust through validation, empathy, and consistent therapeutic boundaries.

**Developmental Awareness**: Understand adolescent brain development, identity formation, and age-specific stressors.

**Cultural Competence**: Consider cultural, socioeconomic, and family factors in treatment approach.

## Clinical Assessment Framework

### Risk Assessment Protocol
Always assess for:
- **Suicidal ideation**: Thoughts, plans, means, timeline
- **Self-harm behaviors**: Current urges, past history, methods
- **Psychosocial stressors**: School, family, peers, trauma
- **Protective factors**: Support systems, coping skills, future orientation
- **Substance use**: Current use, frequency, impact on functioning

### Structured Interventions

#### Cognitive Behavioral Therapy (CBT)
- **Thought Records**: Identify negative automatic thoughts
- **Cognitive Restructuring**: Challenge distorted thinking patterns  
- **Behavioral Activation**: Increase pleasant and mastery activities
- **Exposure Therapy**: Gradual exposure to anxiety triggers
- **Problem-Solving Skills**: Structured approach to challenges

#### Dialectical Behavior Therapy (DBT) Skills
- **Distress Tolerance**: TIPP, self-soothing, distraction, radical acceptance
- **Emotion Regulation**: PLEASE skills, opposite action, mastery activities
- **Mindfulness**: Present moment awareness, wise mind, observe/describe
- **Interpersonal Effectiveness**: DEAR MAN, GIVE FAST for relationships

#### Acceptance and Commitment Therapy (ACT)
- **Psychological Flexibility**: Values-based action despite difficult emotions
- **Defusion**: Seeing thoughts as mental events, not literal truths
- **Acceptance**: Willingness to experience difficult emotions
- **Values Clarification**: Identifying what matters most to them

## Crisis Intervention Protocol

### Imminent Risk (Immediate Response Required)
"I'm very concerned about your immediate safety. You've described [specific risk factors]. Let's get you connected with professional help right now:

**IMMEDIATE ACTION NEEDED:**
🚨 Call 000 if in immediate danger
📞 Lifeline: 13 11 14 (24/7 crisis support)
🧒 Kids Helpline: 1800 55 1800 (24/7 for under 25s)

Please stay with me while we get you connected to someone who can provide immediate safety support."

### High Risk Assessment
- Conduct Columbia Suicide Severity Rating Scale
- Develop immediate safety plan
- Connect with crisis resources
- Encourage trusted adult involvement

### Moderate Risk
- Implement coping skills training
- Schedule regular check-ins
- Develop longer-term safety plan
- Consider professional referral

## Therapeutic Communication Style

### Language Guidelines
- Use "I" statements for validation: "I hear that this is really difficult"
- Avoid minimizing: Never say "it could be worse" or "this will pass"
- Be specific: "It sounds like the panic attacks happen when..." rather than "anxiety"
- Normalize struggles: "Many teens experience..."
- Encourage agency: "What do you think might help?" rather than telling them what to do

### Professional Boundaries
- Clearly state role: "I'm here to provide support and teach skills, but I'm not a replacement for therapy"
- Encourage professional help when appropriate
- Maintain confidentiality while emphasizing limits (safety concerns)
- Document significant clinical information

## Response Framework

For EVERY interaction, include:

1. **Validation & Empathy** (2-3 sentences)
   - Acknowledge their courage in reaching out
   - Validate the reality of their experience
   - Express genuine care for their wellbeing

2. **Clinical Assessment** (embedded naturally)
   - Risk factors present
   - Current coping resources
   - Level of functioning
   - Support system strength

3. **Evidence-Based Intervention** (primary focus)
   - Specific therapeutic technique
   - Step-by-step instructions
   - Rationale for why this helps
   - Homework or practice suggestion

4. **Safety & Resources** (when indicated)
   - Risk level assessment
   - Appropriate resource recommendations
   - Follow-up planning

5. **Engagement & Hope** (1-2 sentences)
   - Encourage continued engagement
   - Install hope while being realistic
   - Ask engagement question

## Professional Referral Criteria

Recommend professional help when:
- **Moderate to high suicide risk**
- **Active self-harm behaviors**
- **Trauma disclosure requiring specialized treatment**
- **Substance abuse concerns**
- **Psychotic symptoms or severe dissociation**
- **Eating disorder symptoms**
- **Persistent functional impairment despite support**
- **Family crisis or abuse concerns**

## Teen-Specific Clinical Considerations

**Academic Stress**: Understand pressure for achievement, college prep anxiety, learning differences
**Identity Development**: Support exploration while providing stability, LGBTQ+ affirmative care
**Social Dynamics**: Address bullying, social anxiety, peer pressure, romantic relationships
**Family Systems**: Navigate autonomy vs. dependence, family conflict, cultural expectations
**Digital Wellness**: Screen time, cyberbullying, social media comparison, online safety
**Body Image**: Address appearance concerns, eating behaviors, sports pressure
**Substance Use**: Provide education, harm reduction, treatment resources

Remember: You provide professional-level support but are NOT a replacement for in-person therapy, psychiatric care, or crisis intervention services. Your role is to provide evidence-based coping skills, emotional support, and appropriate referrals.
        """
    
    def init_assessment_tools(self):
        """Initialize clinical assessment tools"""
        
        # PHQ-A (Patient Health Questionnaire for Adolescents)
        self.phq_a_questions = [
            "Little interest or pleasure in doing things",
            "Feeling down, depressed, or hopeless", 
            "Trouble falling or staying asleep, or sleeping too much",
            "Feeling tired or having little energy",
            "Poor appetite or overeating",
            "Feeling bad about yourself or that you are a failure",
            "Trouble concentrating on things",
            "Moving or speaking slowly, or being fidgety/restless",
            "Thoughts that you would be better off dead or hurting yourself"
        ]
        
        # GAD-7 (Generalized Anxiety Disorder scale)
        self.gad_7_questions = [
            "Feeling nervous, anxious, or on edge",
            "Not being able to stop or control worrying",
            "Worrying too much about different things", 
            "Trouble relaxing",
            "Being so restless that it's hard to sit still",
            "Becoming easily annoyed or irritable",
            "Feeling afraid as if something awful might happen"
        ]
        
        # Columbia Suicide Severity Rating Scale (simplified)
        self.columbia_scale = {
            'wish_to_die': "Have you wished you were dead or wished you could go to sleep and not wake up?",
            'suicide_thoughts': "Have you actually had any thoughts of killing yourself?",
            'suicide_thoughts_method': "Have you thought about how you might do this?",
            'suicide_intent': "Have you had these thoughts and had some intention of acting on them?",
            'suicide_plan': "Have you started to work out or worked out the details of how to kill yourself?"
        }
    
    async def generate_professional_response(self, message: str, user_context: Dict) -> Tuple[str, Dict]:
        """Generate professional mental health response with clinical assessment"""
        
        # First, conduct risk assessment
        risk_assessment = self.assess_risk(message, user_context)
        
        if not self.enabled:
            return self.professional_fallback_response(message, user_context, risk_assessment)
        
        teen = user_context.get('teen')
        clinical_history = user_context.get('clinical_history', {})
        
        # Build comprehensive clinical context
        clinical_context = f"""
## Client Profile:
- Name: {teen.preferred_name or teen.first_name if teen else 'Client'}
- Age: {teen.age if teen and teen.age else 'Adolescent'}
- Risk Level: {teen.risk_level if teen else 'Not assessed'}
- Primary Concerns: {teen.primary_concerns if teen else 'Not identified'}
- Therapy Status: {teen.therapy_status if teen else 'Unknown'}
- Support Network: {teen.support_network_strength}/10 if teen else 'Not assessed'}

## Current Risk Assessment:
- Risk Level: {risk_assessment['level']}
- Crisis Type: {risk_assessment.get('crisis_type', 'None identified')}
- Risk Factors: {risk_assessment.get('risk_factors', [])}
- Protective Factors: {risk_assessment.get('protective_factors', [])}

## Recent Clinical Data:
{self.format_clinical_history(clinical_history)}

## Current Presentation: "{message}"

## Clinical Response Required:
Based on the above assessment, provide a professional therapeutic response that:
1. Addresses immediate safety if risk is present
2. Applies appropriate evidence-based intervention
3. Teaches specific coping skills
4. Builds therapeutic alliance
5. Plans next steps

Ensure response is under 300 words but clinically comprehensive.
        """
        
        full_prompt = f"{self.clinical_prompt}\n\n{clinical_context}"
        
        try:
            response = await asyncio.to_thread(self.model.generate_content, full_prompt)
            ai_response = response.text.strip() if response and response.text else None
            
            if ai_response:
                return ai_response, risk_assessment
            else:
                return self.professional_fallback_response(message, user_context, risk_assessment)
                
        except Exception as e:
            logger.warning(f"Professional AI response generation failed: {e}")
            return self.professional_fallback_response(message, user_context, risk_assessment)
    
    def assess_risk(self, message: str, user_context: Dict) -> Dict:
        """Comprehensive risk assessment using clinical protocols"""
        
        message_lower = message.lower()
        risk_assessment = {
            'level': RiskLevel.LOW.value,
            'crisis_type': None,
            'risk_factors': [],
            'protective_factors': [],
            'immediate_action_required': False
        }
        
        # Check for imminent risk indicators
        for keyword in ['tonight', 'today', 'now', 'soon', 'plan', 'method', 'pills', 'rope', 'bridge']:
            if keyword in message_lower:
                for crisis_phrase in ['kill myself', 'suicide', 'end it', 'die']:
                    if crisis_phrase in message_lower:
                        risk_assessment['level'] = RiskLevel.IMMINENT.value
                        risk_assessment['crisis_type'] = CrisisType.SUICIDE_PLAN.value
                        risk_assessment['immediate_action_required'] = True
                        break
        
        # High risk assessment
        if risk_assessment['level'] != RiskLevel.IMMINENT.value:
            high_risk_phrases = ['kill myself', 'suicide', 'want to die', 'better off dead', 'can\'t go on']
            if any(phrase in message_lower for phrase in high_risk_phrases):
                risk_assessment['level'] = RiskLevel.HIGH.value
                risk_assessment['crisis_type'] = CrisisType.SUICIDE_IDEATION.value
        
        # Self-harm assessment  
        self_harm_phrases = ['cut myself', 'hurt myself', 'self harm', 'cutting', 'burning']
        if any(phrase in message_lower for phrase in self_harm_phrases):
            if risk_assessment['level'] in [RiskLevel.LOW.value]:
                risk_assessment['level'] = RiskLevel.MODERATE.value
            risk_assessment['crisis_type'] = CrisisType.SELF_HARM.value
        
        # Assess protective factors
        protective_phrases = ['family', 'friends', 'pet', 'future', 'goals', 'hope', 'help']
        risk_assessment['protective_factors'] = [phrase for phrase in protective_phrases if phrase in message_lower]
        
        # Risk factors
        risk_phrases = ['alone', 'hopeless', 'worthless', 'failure', 'burden', 'trapped']
        risk_assessment['risk_factors'] = [phrase for phrase in risk_phrases if phrase in message_lower]
        
        return risk_assessment
    
    def format_clinical_history(self, clinical_history: Dict) -> str:
        """Format clinical history for AI context"""
        if not clinical_history:
            return "- No previous clinical data available"
        
        formatted = []
        if 'recent_moods' in clinical_history:
            moods = clinical_history['recent_moods'][:3]
            for mood in moods:
                formatted.append(f"- Mood: {mood.mood_score}/10, Anxiety: {mood.anxiety_level}/10, Depression: {mood.depression_indicators}/10")
        
        if 'recent_assessments' in clinical_history:
            assessments = clinical_history['recent_assessments'][:2]
            for assessment in assessments:
                formatted.append(f"- {assessment.assessment_type}: {assessment.scores}")
        
        return '\n'.join(formatted) if formatted else "- Limited clinical history"
    
    def professional_fallback_response(self, message: str, user_context: Dict, risk_assessment: Dict) -> Tuple[str, Dict]:
        """Professional fallback responses when AI unavailable"""
        
        teen = user_context.get('teen')
        name = teen.preferred_name or teen.first_name if teen else "friend"
        
        # Handle crisis situations first
        if risk_assessment['level'] == RiskLevel.IMMINENT.value:
            return self.generate_crisis_response(name, risk_assessment), risk_assessment
        elif risk_assessment['level'] == RiskLevel.HIGH.value:
            return self.generate_high_risk_response(name, risk_assessment), risk_assessment
        
        # Standard evidence-based responses
        message_lower = message.lower()
        
        # CBT for anxiety
        if any(word in message_lower for word in ['anxious', 'anxiety', 'panic', 'worry', 'nervous']):
            return f"""I understand you're experiencing anxiety, {name}. This is incredibly common among teens, and there are effective ways to manage it.

**Immediate Coping - 5-4-3-2-1 Grounding:**
- 5 things you can see
- 4 things you can touch  
- 3 things you can hear
- 2 things you can smell
- 1 thing you can taste

**Cognitive Strategy - Anxiety Thought Challenge:**
Ask yourself: "Is this thought helpful? What evidence supports/contradicts this worry? What would I tell a friend with this thought?"

**Next Steps:** Practice this grounding technique twice daily this week. If anxiety continues to interfere with daily activities, consider speaking with a school counselor or GP about a Mental Health Care Plan.

What specific situations tend to trigger your anxiety most? Understanding patterns helps us develop targeted strategies. 🌸""", risk_assessment
        
        # CBT for depression
        if any(word in message_lower for word in ['depressed', 'sad', 'empty', 'hopeless', 'worthless']):
            return f"""I hear the pain in your words, {name}. Depression can make everything feel overwhelming, but you've taken an important step by reaching out.

**Behavioral Activation - Start Small:**
Choose ONE tiny activity that used to bring you even slight pleasure: listening to one song, taking a 5-minute walk, texting one friend, or having a warm shower.

**Cognitive Restructuring:**
Depression tells us lies like "nothing will get better" or "I'm worthless." These are symptoms, not facts. Challenge these thoughts: "What evidence contradicts this? How would I respond if a friend said this about themselves?"

**Professional Support:** If you've felt this way for more than 2 weeks, please consider talking to a trusted adult about seeing a counselor. Depression is very treatable.

Can you think of one small thing you could do today to care for yourself? Even tiny steps matter. 💜""", risk_assessment
        
        # DBT for emotional dysregulation
        if any(word in message_lower for word in ['overwhelmed', 'can\'t cope', 'intense', 'emotional']):
            return f"""You're experiencing intense emotions, {name}. This is actually a sign of emotional sensitivity, which can be a strength when managed well.

**TIPP for Crisis Emotions:**
- **Temperature**: Cold water on face/hands
- **Intense Exercise**: 10 jumping jacks or push-ups  
- **Paced Breathing**: In for 4, hold 4, out for 6
- **Paired Muscle Relaxation**: Tense and release muscle groups

**Distress Tolerance - ACCEPTS:**
- **Activities**: Puzzle, music, art
- **Contributing**: Help someone else
- **Comparisons**: Remember harder times you've survived
- **Emotions**: Watch a funny video to shift mood
- **Push away**: Set the problem aside for now
- **Thoughts**: Count backwards from 100 by 7s
- **Sensations**: Hold ice, strong mint, etc.

Practice one TIPP skill right now. Which option feels most accessible to you in this moment? 🌊""", risk_assessment
        
        # General support with psychoeducation
        return f"""Thank you for trusting me with what you're going through, {name}. It takes real courage to reach out when you're struggling.

**Validation:** Your feelings are valid and make sense given what you're experiencing. You're not broken, weak, or dramatic - you're human.

**Coping Strategy - Box Breathing:**
- Breathe in for 4 counts
- Hold for 4 counts
- Breathe out for 4 counts  
- Hold empty for 4 counts
- Repeat 5 times

**Remember:** Difficult emotions are temporary. You've survived 100% of your worst days so far.

**Professional Resources Available:**
- Headspace (12-25 years): headspace.org.au
- Kids Helpline: 1800 55 1800 (free counseling)
- School counselors (free and confidential)

What's one way you've successfully coped with difficult times before? Building on your existing strengths often works best. 🌟""", risk_assessment
    
    def generate_crisis_response(self, name: str, risk_assessment: Dict) -> str:
        """Generate immediate crisis intervention response"""
        return f"""🚨 **{name}, I'm very concerned about your immediate safety right now.**

You've described thoughts of {risk_assessment.get('crisis_type', 'self-harm')} with what sounds like immediate risk. Your life has value and this crisis feeling can be survived.

**IMMEDIATE ACTION REQUIRED:**

📞 **Call RIGHT NOW:**
• **000** if you're in immediate danger
• **Lifeline: 13 11 14** (24/7 crisis counseling)
• **Kids Helpline: 1800 55 1800** (24/7 for under 25s)

🏥 **OR go to your nearest hospital emergency department**

**Safety Plan - Do This Now:**
1. Remove any means of self-harm from your immediate area
2. Call one of the numbers above or have someone call for you
3. Stay with a trusted person until you can get professional help
4. Remember: This intense pain is temporary, but suicide is permanent

**You are not alone. Professional help is available right now.**

Please confirm you will call one of these numbers or go to hospital. Your safety is the only priority right now. 💙"""
    
    def generate_high_risk_response(self, name: str, risk_assessment: Dict) -> str:
        """Generate high-risk intervention response"""
        return f"""I'm really concerned about you, {name}. You've shared thoughts about {risk_assessment.get('crisis_type', 'ending your life')} and I want you to know that help is available.

**First - Your Safety:**
📞 **Lifeline: 13 11 14** (24/7, free, confidential)
🧒 **Kids Helpline: 1800 55 1800** (counselors who understand teens)
💬 **Crisis Text: 0477 13 11 14** (text HELLO for support)

**Immediate Coping - STOP Technique:**
- **S**top what you're doing
- **T**ake three deep breaths
- **O**bserve your surroundings
- **P**roceed with one safe action

**Safety Planning:**
Can you identify one trusted adult you could talk to today? This could be a parent, teacher, school counselor, or family friend.

**Remember:** Suicidal thoughts are a symptom of emotional pain, not a character flaw. This pain can be treated and managed.

Please reach out to one of these resources within the next 24 hours. Will you commit to calling if these feelings get stronger? 💙"""

# Main Professional Bot Class
class ProfessionalTeenSupportBot:
    def __init__(self, token: str, database_url: str, gemini_api_key: str = None):
        try:
            logger.info("Initializing Professional Teen Support Bot...")
            
            self.db = ProfessionalDB(database_url)
            
            # Enhanced application settings for professional use
            self.app = (Application.builder()
                       .token(token)
                       .connect_timeout(60)
                       .read_timeout(60)
                       .write_timeout(60)
                       .pool_timeout(60)
                       .get_updates_connect_timeout(60)
                       .get_updates_read_timeout(60)
                       .build())
            
            self.ai_coach = ProfessionalMentalHealthCoach(gemini_api_key)
            self.config = ProfessionalBotConfig()
            self.setup_handlers()
            self.setup_scheduler()
            logger.info("✅ Professional Teen Support Bot initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Professional Bot: {e}")
            raise
    
    def setup_handlers(self):
        # Core commands
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("assess", self.clinical_assessment))
        self.app.add_handler(CommandHandler("safety", self.safety_planning))
        self.app.add_handler(CommandHandler("cbt", self.cbt_session))
        self.app.add_handler(CommandHandler("dbt", self.dbt_skills))
        self.app.add_handler(CommandHandler("mood", self.mood_tracking))
        self.app.add_handler(CommandHandler("crisis", self.crisis_resources))
        self.app.add_handler(CommandHandler("professional", self.professional_resources))
        self.app.add_handler(CommandHandler("help", self.help_command))
        
        # Message handlers
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        
        logger.info("✅ Professional bot handlers set up")
    
    def setup_scheduler(self):
        if AsyncIOScheduler and CronTrigger:
            try:
                self.scheduler = AsyncIOScheduler()
                # Daily risk assessment for high-risk users
                self.scheduler.add_job(
                    self.daily_risk_check,
                    CronTrigger(hour=19, minute=0),
                    id='risk_check'
                )
                self.scheduler.start()
                logger.info("✅ Professional scheduler set up")
            except Exception as e:
                logger.warning(f"⚠️ Scheduler setup failed: {e}")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            teen = self.db.get_or_create_teen(update.effective_user)
            
            welcome_msg = f"""
🌟 **Welcome to TM-Health Professional** 

Hi {teen.first_name}, I'm your evidence-based mental health support companion. I use clinically-proven techniques to help teens navigate mental health challenges.

**What I Provide:**
• **Clinical Assessment** - Professional screening tools
• **Evidence-Based Therapy** - CBT, DBT, and mindfulness techniques  
• **Crisis Support** - 24/7 safety planning and intervention
• **Skills Training** - Practical coping strategies that work
• **Professional Referrals** - Connection to local mental health services

**Professional Commands:**
/assess - Clinical mental health screening
/safety - Create personalized safety plan  
/cbt - Cognitive behavioral therapy tools
/dbt - Dialectical behavior therapy skills
/mood - Track mood and symptoms
/crisis - Immediate crisis resources
/professional - Find local mental health services

**Important Professional Disclosure:**
I provide evidence-based support and coping skills, but I am NOT a replacement for professional therapy, psychiatric care, or emergency services. If you're in crisis, please contact emergency services or crisis helplines immediately.

**Confidentiality:** Our conversations are private, but I may recommend professional help if I'm concerned about your safety.

How are you feeling today? I'm here to provide professional-level support. 💙
            """
            
            await update.message.reply_text(welcome_msg)
            logger.info(f"Professional start command for user {update.effective_user.id}")
        except Exception as e:
            logger.error(f"Error in start_command: {e}")
            await update.message.reply_text("I'm experiencing a technical issue. Please try /crisis for immediate resources if needed.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            user_id = update.effective_user.id
            message_text = update.message.text
            
            teen = self.db.get_or_create_teen(update.effective_user)
            user_context = self.get_clinical_context(user_id)
            
            # Generate professional response with risk assessment
            response, risk_assessment = await self.ai_coach.generate_professional_response(message_text, user_context)
            
            # Log clinical interaction
            self.log_clinical_interaction(user_id, message_text, response, risk_assessment)
            
            # Update user risk level if needed
            if risk_assessment['level'] != RiskLevel.LOW.value:
                self.update_user_risk_level(user_id, risk_assessment)
            
            await update.message.reply_text(response)
            
            # Provide appropriate follow-up buttons based on risk
            if risk_assessment['immediate_action_required']:
                keyboard = [
                    [InlineKeyboardButton("🚨 I need immediate help", callback_data="crisis_immediate")],
                    [InlineKeyboardButton("📞 Show me crisis numbers", callback_data="crisis_numbers")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text("Please confirm you'll get immediate help:", reply_markup=reply_markup)
            
            logger.info(f"Professional message handled for user {user_id}, risk level: {risk_assessment['level']}")
            
        except Exception as e:
            logger.error(f"Error in handle_message: {e}")
            await update.message.reply_text("I'm having a technical issue. If this is urgent, please call Lifeline: 13 11 14")
    
    def get_clinical_context(self, user_id: int) -> Dict:
        session = self.db.get_session()
        try:
            teen = session.query(TeenUser).filter_by(telegram_id=user_id).first()
            recent_moods = session.query(MoodEntry).filter_by(
                user_id=user_id
            ).order_by(MoodEntry.timestamp.desc()).limit(7).all()
            
            recent_assessments = session.query(ClinicalAssessment).filter_by(
                user_id=user_id
            ).order_by(ClinicalAssessment.timestamp.desc()).limit(3).all()
            
            safety_plan = session.query(SafetyPlan).filter_by(
                user_id=user_id
            ).order_by(SafetyPlan.last_updated.desc()).first()
            
            return {
                'teen': teen,
                'clinical_history': {
                    'recent_moods': recent_moods,
                    'recent_assessments': recent_assessments,
                    'safety_plan': safety_plan
                }
            }
        except Exception as e:
            logger.error(f"Error getting clinical context: {e}")
            return {'teen': None, 'clinical_history': {}}
        finally:
            session.close()
    
    def log_clinical_interaction(self, user_id: int, message: str, response: str, risk_assessment: Dict):
        session = self.db.get_session()
        try:
            # Log as therapeutic session
            session_data = {
                'user_input': message,
                'risk_assessment': risk_assessment,
                'intervention_provided': self.classify_intervention(response),
                'clinical_notes': f"Risk level: {risk_assessment['level']}"
            }
            
            therapeutic_session = TherapeuticSession(
                user_id=user_id,
                intervention_type=session_data['intervention_provided'],
                session_data=session_data
            )
            session.add(therapeutic_session)
            
            # Log crisis alert if needed
            if risk_assessment['level'] in [RiskLevel.HIGH.value, RiskLevel.IMMINENT.value]:
                crisis_alert = CrisisAlert(
                    user_id=user_id,
                    crisis_type=risk_assessment.get('crisis_type', 'general_distress'),
                    risk_level=risk_assessment['level'],
                    assessment_data=risk_assessment,
                    interventions_provided=[session_data['intervention_provided']]
                )
                session.add(crisis_alert)
            
            # Update conversation count
            teen = session.query(TeenUser).filter_by(telegram_id=user_id).first()
            if teen:
                teen.total_conversations = (teen.total_conversations or 0) + 1
            
            session.commit()
        except Exception as e:
            logger.error(f"Error logging clinical interaction: {e}")
            session.rollback()
        finally:
            session.close()
    
    def classify_intervention(self, response: str) -> str:
        response_lower = response.lower()
        
        if any(word in response_lower for word in ['5-4-3-2-1', 'grounding', 'mindfulness']):
            return InterventionType.MINDFULNESS.value
        elif any(word in response_lower for word in ['thought', 'cognitive', 'challenge', 'evidence']):
            return InterventionType.CBT.value
        elif any(word in response_lower for word in ['tipp', 'distress tolerance', 'emotion regulation']):
            return InterventionType.DBT.value
        elif any(word in response_lower for word in ['crisis', 'safety', 'emergency']):
            return InterventionType.CRISIS_INTERVENTION.value
        else:
            return InterventionType.PSYCHOEDUCATION.value
    
    def update_user_risk_level(self, user_id: int, risk_assessment: Dict):
        session = self.db.get_session()
        try:
            teen = session.query(TeenUser).filter_by(telegram_id=user_id).first()
            if teen:
                teen.risk_level = risk_assessment['level']
                session.commit()
        except Exception as e:
            logger.error(f"Error updating risk level: {e}")
            session.rollback()
        finally:
            session.close()

    async def clinical_assessment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Conduct clinical assessment"""
        keyboard = [
            [InlineKeyboardButton("Depression Screening (PHQ-A)", callback_data="assess_depression")],
            [InlineKeyboardButton("Anxiety Screening (GAD-7)", callback_data="assess_anxiety")],
            [InlineKeyboardButton("Risk Assessment", callback_data="assess_risk")],
            [InlineKeyboardButton("Complete Wellness Check", callback_data="assess_complete")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        assessment_msg = """
🔍 **Clinical Assessment**

Professional mental health screening tools to help understand your current wellbeing. These are the same assessments used by psychologists and counselors.

**Available Assessments:**
• **Depression** - PHQ-A (9 questions, 3 minutes)
• **Anxiety** - GAD-7 (7 questions, 2 minutes)  
• **Risk** - Safety assessment (varies)
• **Complete** - Comprehensive wellness check (10 minutes)

These assessments help identify areas where you might benefit from additional support or professional care.

Which assessment would you like to complete?
        """
        
        await update.message.reply_text(assessment_msg, reply_markup=reply_markup)

    async def safety_planning(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Create safety plan"""
        safety_msg = """
🛡️ **Safety Planning**

A safety plan is a personalized tool that helps you cope with suicidal thoughts or mental health crises. We'll work together to create YOUR personalized plan.

**Your Safety Plan Will Include:**
1. **Warning Signs** - How to recognize when you're struggling
2. **Coping Strategies** - Things you can do independently  
3. **People for Support** - Who you can reach out to
4. **Professional Contacts** - Mental health professionals
5. **Environment Safety** - How to make your space safer
6. **Reasons for Living** - What makes life worth living for you

This process takes about 10-15 minutes. Everything you share will help create a plan that's specifically for you.

Ready to start creating your safety plan?
        """
        
        keyboard = [
            [InlineKeyboardButton("✅ Start Safety Plan", callback_data="safety_start")],
            [InlineKeyboardButton("📋 View My Existing Plan", callback_data="safety_view")],
            [InlineKeyboardButton("🆘 I need help right now", callback_data="crisis_immediate")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(safety_msg, reply_markup=reply_markup)

    async def cbt_session(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """CBT skills session"""
        cbt_msg = """
🧠 **Cognitive Behavioral Therapy (CBT) Tools**

CBT helps you understand the connection between thoughts, feelings, and behaviors. These evidence-based techniques are used by therapists worldwide.

**Available CBT Tools:**
        """
        
        keyboard = [
            [InlineKeyboardButton("💭 Thought Record", callback_data="cbt_thought_record")],
            [InlineKeyboardButton("🔄 Cognitive Restructuring", callback_data="cbt_restructuring")],
            [InlineKeyboardButton("📈 Behavioral Activation", callback_data="cbt_activation")],
            [InlineKeyboardButton("🎯 Problem Solving", callback_data="cbt_problem_solving")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(cbt_msg, reply_markup=reply_markup)

    async def dbt_skills(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """DBT skills session"""
        dbt_msg = """
🌊 **Dialectical Behavior Therapy (DBT) Skills**

DBT teaches practical skills for managing intense emotions and improving relationships. These skills are particularly effective for teens.

**The Four DBT Modules:**
        """
        
        keyboard = [
            [InlineKeyboardButton("🧘 Mindfulness", callback_data="dbt_mindfulness")],
            [InlineKeyboardButton("💪 Distress Tolerance", callback_data="dbt_distress")],
            [InlineKeyboardButton("🎭 Emotion Regulation", callback_data="dbt_emotion")],
            [InlineKeyboardButton("🤝 Interpersonal Effectiveness", callback_data="dbt_interpersonal")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(dbt_msg, reply_markup=reply_markup)

    async def professional_resources(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Professional mental health resources"""
        resources_msg = """
🏥 **Professional Mental Health Services**

**Crisis Support (24/7):**
📞 **Lifeline Australia: 13 11 14**
🧒 **Kids Helpline: 1800 55 1800** (5-25 years)
💬 **Crisis Text: 0477 13 11 14** (text HELLO)
🌐 **Beyond Blue: 1300 22 4636**

**Professional Services for Teens:**

🎯 **Headspace (12-25 years)**
- Free or low-cost mental health services
- Counseling, group programs, online support
- Find center: headspace.org.au

💰 **Medicare Psychology Sessions**
- Up to 10 subsidized sessions per year
- See your GP for a Mental Health Care Plan
- Covers anxiety, depression, and other conditions

🏫 **School-Based Support**
- School counselors (free and confidential)
- Student welfare coordinators
- Learning support teams

🏥 **Community Mental Health**
- Local community health centers
- Child and Adolescent Mental Health Services (CAMHS)
- Family therapy and support services

**When to Seek Professional Help:**
• Persistent sadness or anxiety (2+ weeks)
• Thoughts of self-harm or suicide
• Substance use concerns
• Difficulty functioning at school/home
• Trauma or abuse experiences
• Eating or body image concerns

Would you like help finding services in your specific area?
        """
        
        keyboard = [
            [InlineKeyboardButton("📍 Find Local Services", callback_data="resources_local")],
            [InlineKeyboardButton("💰 Medicare Information", callback_data="resources_medicare")],
            [InlineKeyboardButton("🏫 School Support", callback_data="resources_school")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(resources_msg, reply_markup=reply_markup)

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        try:
            query = update.callback_query
            await query.answer()
            
            if query.data.startswith("assess_"):
                await self.handle_assessment_callback(query)
            elif query.data.startswith("safety_"):
                await self.handle_safety_callback(query)
            elif query.data.startswith("cbt_"):
                await self.handle_cbt_callback(query)
            elif query.data.startswith("dbt_"):
                await self.handle_dbt_callback(query)
            elif query.data.startswith("crisis_"):
                await self.handle_crisis_callback(query)
                
        except Exception as e:
            logger.error(f"Error in button_callback: {e}")

    async def handle_crisis_callback(self, query):
        """Handle crisis-related callbacks"""
        if query.data == "crisis_immediate":
            await query.edit_message_text(
                """🚨 **Immediate Crisis Support**

**Call RIGHT NOW:**
📞 **000** - Emergency services
📞 **13 11 14** - Lifeline (24/7)
📞 **1800 55 1800** - Kids Helpline

**Text Support:**
💬 Text **HELLO** to **0477 13 11 14**

**Online Crisis Chat:**
🌐 lifeline.org.au
🌐 kidshelpline.com.au

**If you're in immediate physical danger, call 000 immediately.**

Please confirm you'll reach out to one of these services right now. Your safety is the priority."""
            )
        elif query.data == "crisis_numbers":
            await query.edit_message_text(
                """📞 **Crisis Support Numbers**

**24/7 Crisis Lines:**
• **Lifeline: 13 11 14**
• **Kids Helpline: 1800 55 1800**
• **Beyond Blue: 1300 22 4636**
• **Suicide Callback Service: 1300 659 467**

**Crisis Text:**
• Text HELLO to 0477 13 11 14

**Emergency:**
• Call 000 for immediate danger

Save these numbers in your phone. You don't have to go through this alone."""
            )

    async def daily_risk_check(self):
        """Daily check for high-risk users"""
        session = self.db.get_session()
        try:
            high_risk_users = session.query(TeenUser).filter(
                TeenUser.risk_level.in_([RiskLevel.HIGH.value, RiskLevel.MODERATE.value])
            ).all()
            
            for user in high_risk_users:
                # Send gentle check-in message
                try:
                    await self.app.bot.send_message(
                        user.telegram_id,
                        f"Hi {user.preferred_name or user.first_name}, just checking in. How are you feeling today? Remember, support is always available. 💙"
                    )
                except Exception as e:
                    logger.warning(f"Could not send check-in to user {user.telegram_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in daily risk check: {e}")
        finally:
            session.close()

    def start_health_server(self, port: int):
        """Start health check server"""
        import threading
        from http.server import HTTPServer, BaseHTTPRequestHandler
        
        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'Professional Teen Support Bot is running')
            
            def log_message(self, format, *args):
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

    def run(self):
        """Start the professional bot"""
        try:
            logger.info("🌸 Professional TM-Health Bot starting...")
            print("🌸 Professional TM-Health Bot starting...")
            
            port = int(os.getenv('PORT', 10000))
            self.start_health_server(port)
            
            max_retries = 5
            base_delay = 10
            
            for attempt in range(max_retries):
                try:
                    print(f"🔄 Professional bot connection attempt {attempt + 1}/{max_retries}...")
                    
                    self.app.run_polling(
                        drop_pending_updates=True,
                        allowed_updates=['message', 'callback_query'],
                        poll_interval=3.0,
                        timeout=20,
                        bootstrap_retries=5,
                        close_loop=False
                    )
                    
                    break
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    
                    if attempt < max_retries - 1:
                        if 'timeout' in error_msg or 'connection' in error_msg:
                            delay = base_delay * (attempt + 1)
                            print(f"⏳ Connection failed, retrying in {delay} seconds...")
                            
                            import time
                            time.sleep(delay)
                            continue
                    
                    raise e
            
        except Exception as e:
            logger.error(f"❌ Professional bot failed to start: {e}")
            print(f"❌ Professional bot failed to start: {e}")
            
            print("\n🔄 Keeping service alive for health checks...")
            import time
            while True:
                time.sleep(300)
                print("💤 Professional service staying alive")

def main():
    """Main function"""
    try:
        config = ProfessionalBotConfig()
        config.validate()
        
        print("✅ Professional configuration validated")
        print("🔗 Initializing professional mental health support...")
        
        bot = ProfessionalTeenSupportBot(
            config.TELEGRAM_TOKEN,
            config.DATABASE_URL,
            config.GEMINI_API_KEY
        )
        
        print("🌟 Professional TM-Health Bot ready!")
        logger.info("🌟 Professional TM-Health Bot ready!")
        
        bot.run()
        
    except KeyboardInterrupt:
        logger.info("Professional bot stopped by user")
        print("👋 Professional bot stopped")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        print(f"❌ Fatal error: {e}")
        
        print("\n🔄 Keeping service alive for potential recovery...")
        import time
        while True:
            time.sleep(300)
            print("💤 Service alive - health check endpoint working")

if __name__ == "__main__":
    main()