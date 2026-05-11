from fastapi import APIRouter, HTTPException
from src.schemas.event import BehaviorEvent, ProactiveTrigger
from src.application.event_processor import process_behavior_event

router = APIRouter()

@router.post("/events")
async def handle_behavior_event(event: BehaviorEvent):
    await process_behavior_event(event)
    return {"status": "received"}

@router.post("/proactive")
async def handle_proactive(trigger: ProactiveTrigger):
    return {"status": "triggered", "message": trigger.message}