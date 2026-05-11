from pydantic import BaseModel, Field
from enum import Enum

class ProblemType(str, Enum):
    PAYMENT_STUCK = "payment_stuck"
    REGISTRATION_STUCK = "registration_stuck"
    NAVIGATION_LOOP = "navigation_loop"
    FORM_ERROR = "form_error"
    GENERAL_IDLE = "general_idle"

class BehaviorEvent(BaseModel):
    session_id: str = Field(min_length=8, max_length=128)
    page: str = Field(min_length=1, max_length=500)
    idle_sec: int = Field(ge=0)
    back_count: int = Field(ge=0)
    form_error: str | None = None
    cursor_area: str | None = None

class ProactiveTrigger(BaseModel):
    session_id: str
    problem_type: ProblemType
    message: str
    options: list[str] = ["Да", "Нет"]