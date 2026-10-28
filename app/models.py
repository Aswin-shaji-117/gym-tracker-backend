
from pydantic import BaseModel, Field,EmailStr
from typing import Optional

class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)

class ExerciseIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    muscle_group: str = Field(default="General", max_length=50)
    sets: int = Field(default=3, ge=1, le=20)
    reps: int = Field(default=10, ge=1, le=100)
    target_weight_kg: float = Field(default=0, ge=0, le=1000)
    rest_seconds: int = Field(default=90, ge=0, le=3600)
    notes: str = Field(default="", max_length=1000)

class PlanCreate(BaseModel):
    day: str
    title: str = Field(default="Workout", max_length=100)
    exercises: list[ExerciseIn] = []

class PlanUpdate(BaseModel):
    day: Optional[str] = None
    title: Optional[str] = None
    exercises: Optional[list[ExerciseIn]] = None

class SetLog(BaseModel):
    set_number: int = Field(ge=1, le=50)
    reps: int = Field(ge=0, le=100)
    weight_kg: float = Field(ge=0, le=1000)

class SessionCreate(BaseModel):
    plan_id: Optional[str] = None
    date: str
    title: str
    notes: str = ""
    exercises: list[dict] = []

class BodyMetricCreate(BaseModel):
    date: str
    weight_kg: float = Field(gt=0, le=1000)
    height_cm: float = Field(gt=0, le=300)
    notes: str = ""

class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)