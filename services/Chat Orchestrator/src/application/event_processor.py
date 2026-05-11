import os
from src.schemas.event import BehaviorEvent, ProblemType, ProactiveTrigger
from src.infrastructure.clients.web_client import send_proactive_message

IDLE_THRESH = int(os.getenv("PROACTIVE_IDLE_SEC", 120))
BACK_THRESH = int(os.getenv("PROACTIVE_BACK_COUNT", 3))

async def process_behavior_event(event: BehaviorEvent):
    problem = None
    
    if event.idle_sec > IDLE_THRESH:
        if "оплат" in event.page.lower() or "payment" in event.page.lower():
            problem = ProblemType.PAYMENT_STUCK
        elif "регистрац" in event.page.lower() or "registr" in event.page.lower():
            problem = ProblemType.REGISTRATION_STUCK
        else:
            problem = ProblemType.GENERAL_IDLE
    elif event.back_count >= BACK_THRESH:
        problem = ProblemType.NAVIGATION_LOOP
    elif event.form_error:
        problem = ProblemType.FORM_ERROR
    
    if problem:
        messages = {
            ProblemType.PAYMENT_STUCK: "Заметили, что вы задержались на странице оплаты. Нужна помощь с выбором способа?",
            ProblemType.REGISTRATION_STUCK: "Вижу, вы заполняете форму регистрации. Возникли вопросы?",
            ProblemType.NAVIGATION_LOOP: "Похоже, вы ищете что-то конкретное. Могу помочь найти?",
            ProblemType.FORM_ERROR: f"Обнаружена ошибка в форме: {event.form_error}. Нужна подсказка?",
            ProblemType.GENERAL_IDLE: "Заметили, что вы задержались. Нужна помощь?"
        }
        
        trigger = ProactiveTrigger(
            session_id=event.session_id,
            problem_type=problem,
            message=messages.get(problem, "Нужна помощь?"),
            options=["Да, нужна помощь", "Нет, просто изучаю"]
        )
        
        await send_proactive_message(trigger)