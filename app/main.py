
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
from pwdlib import PasswordHash

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field


# ============================================================
# Configuration
# ============================================================

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

JWT_SECRET_KEY = os.getenv("GYM_SECRET_KEY")
if not JWT_SECRET_KEY:
    # Development fallback. Set GYM_SECRET_KEY in your environment
    # for persistent, secure tokens, especially outside local testing.
    JWT_SECRET_KEY = "dev-only-change-this-secret-before-deployment"

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

password_hash = PasswordHash.recommended()
security = HTTPBearer(auto_error=False)

app = FastAPI(title="Personal Gym Tracker API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# JSON storage helpers
# ============================================================

def data_file(collection: str) -> Path:
    return DATA_DIR / f"{collection}.json"


def read_all(collection: str) -> list[dict[str, Any]]:
    path = data_file(collection)

    if not path.exists():
        path.write_text("[]", encoding="utf-8")
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        raise HTTPException(
            status_code=500,
            detail=f"Unable to read {collection}.json",
        )


def write_all(collection: str, records: list[dict[str, Any]]) -> None:
    path = data_file(collection)
    temp_path = path.with_suffix(".tmp")

    try:
        temp_path.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temp_path.replace(path)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to save {collection}.json: {exc}",
        )


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_record(
    collection: str,
    record_id: str,
    user_id: str,
) -> dict[str, Any] | None:
    return next(
        (
            record
            for record in read_all(collection)
            if record.get("id") == record_id
            and record.get("user_id") == user_id
        ),
        None,
    )


def save_or_update_record(
    collection: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    records = read_all(collection)
    existing_index = next(
        (
            index
            for index, item in enumerate(records)
            if item.get("id") == record.get("id")
        ),
        None,
    )

    if existing_index is None:
        records.append(record)
    else:
        records[existing_index] = record

    write_all(collection, records)
    return record


def delete_record(
    collection: str,
    record_id: str,
    user_id: str,
) -> bool:
    records = read_all(collection)
    filtered = [
        item
        for item in records
        if not (
            item.get("id") == record_id
            and item.get("user_id") == user_id
        )
    ]

    if len(filtered) == len(records):
        return False

    write_all(collection, filtered)
    return True


# ============================================================
# Pydantic request models
# ============================================================

class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class Exercise(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    muscle_group: str = "Chest"
    sets: int = Field(default=3, ge=1, le=100)
    reps: int = Field(default=10, ge=1, le=1000)
    target_weight_kg: float = Field(default=0, ge=0)
    rest_seconds: int = Field(default=90, ge=0)
    notes: str = ""


class PlanRequest(BaseModel):
    day: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=150)
    exercises: list[Exercise] = Field(default_factory=list)


class LoggedSet(BaseModel):
    set_number: int = Field(ge=1)
    reps: int = Field(ge=0)
    weight_kg: float = Field(ge=0)


class LoggedExercise(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    muscle_group: str = ""
    sets: list[LoggedSet] = Field(default_factory=list)
    notes: str = ""


class SessionRequest(BaseModel):
    plan_id: str
    date: date
    title: str = Field(min_length=1, max_length=150)
    notes: str = ""
    exercises: list[LoggedExercise] = Field(default_factory=list)


class BodyMetricRequest(BaseModel):
    date: date
    weight_kg: float = Field(gt=0, le=1000)
    height_cm: float = Field(gt=0, le=300)
    notes: str = ""


# ============================================================
# Authentication helpers
# ============================================================

def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
    }


def create_access_token(user_id: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    return jwt.encode(
        {
            "sub": user_id,
            "exp": expires_at,
        },
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, Any]:
    # Define this function BEFORE any endpoint that uses Depends().
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication token",
            )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = next(
        (item for item in read_all("users") if item.get("id") == user_id),
        None,
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return public_user(user)


# ============================================================
# Basic endpoints
# ============================================================

@app.get("/")
def root():
    return {"message": "Personal Gym Tracker API is running"}


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ============================================================
# Authentication endpoints
# ============================================================

@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest):
    users = read_all("users")
    normalized_email = str(request.email).strip().lower()

    if any(
        user.get("email", "").lower() == normalized_email
        for user in users
    ):
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists",
        )

    user = {
        "id": new_id(),
        "name": request.name.strip(),
        "email": normalized_email,
        "password_hash": password_hash.hash(request.password),
        "created_at": now_iso(),
    }

    users.append(user)
    write_all("users", users)

    return {
        "message": "Registration successful",
        "user": public_user(user),
    }


@app.post("/api/auth/login")
def login(request: LoginRequest):
    normalized_email = str(request.email).strip().lower()

    user = next(
        (
            item
            for item in read_all("users")
            if item.get("email", "").lower() == normalized_email
        ),
        None,
    )

    if not user or not password_hash.verify(
        request.password,
        user["password_hash"],
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
        )

    return {
        "access_token": create_access_token(user["id"]),
        "token_type": "bearer",
        "user": public_user(user),
    }


@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    return user


# ============================================================
# Workout plans
# ============================================================

@app.get("/api/plans")
def get_plans(user: dict = Depends(get_current_user)):
    plans = [
        item
        for item in read_all("plans")
        if item.get("user_id") == user["id"]
    ]
    return sorted(plans, key=lambda item: item.get("day", ""))


@app.post("/api/plans", status_code=status.HTTP_201_CREATED)
def create_plan(
    request: PlanRequest,
    user: dict = Depends(get_current_user),
):
    plans = read_all("plans")

    # One plan per user per weekday. Re-save that day to update it.
    existing = next(
        (
            item
            for item in plans
            if item.get("user_id") == user["id"]
            and item.get("day", "").lower() == request.day.lower()
        ),
        None,
    )

    timestamp = now_iso()
    plan = {
        "id": existing["id"] if existing else new_id(),
        "user_id": user["id"],
        "day": request.day,
        "title": request.title.strip(),
        "exercises": [item.model_dump() for item in request.exercises],
        "created_at": existing.get("created_at", timestamp) if existing else timestamp,
        "updated_at": timestamp,
    }

    if existing:
        index = plans.index(existing)
        plans[index] = plan
        write_all("plans", plans)
    else:
        plans.append(plan)
        write_all("plans", plans)

    return plan


@app.put("/api/plans/{plan_id}")
def update_plan(
    plan_id: str,
    request: PlanRequest,
    user: dict = Depends(get_current_user),
):
    plans = read_all("plans")
    index = next(
        (
            i
            for i, item in enumerate(plans)
            if item.get("id") == plan_id
            and item.get("user_id") == user["id"]
        ),
        None,
    )

    if index is None:
        raise HTTPException(status_code=404, detail="Workout plan not found")

    # Prevent two plans for the same user on the same weekday.
    duplicate_day = any(
        item.get("user_id") == user["id"]
        and item.get("id") != plan_id
        and item.get("day", "").lower() == request.day.lower()
        for item in plans
    )
    if duplicate_day:
        raise HTTPException(
            status_code=409,
            detail="You already have a plan for this day",
        )

    old_plan = plans[index]
    updated_plan = {
        **old_plan,
        "day": request.day,
        "title": request.title.strip(),
        "exercises": [item.model_dump() for item in request.exercises],
        "updated_at": now_iso(),
    }

    plans[index] = updated_plan
    write_all("plans", plans)
    return updated_plan


@app.delete("/api/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_plan(
    plan_id: str,
    user: dict = Depends(get_current_user),
):
    if not delete_record("plans", plan_id, user["id"]):
        raise HTTPException(status_code=404, detail="Workout plan not found")
    return None


# ============================================================
# Workout sessions / history
# ============================================================

@app.get("/api/sessions")
def get_sessions(user: dict = Depends(get_current_user)):
    sessions = [
        item
        for item in read_all("sessions")
        if item.get("user_id") == user["id"]
    ]
    return sorted(
        sessions,
        key=lambda item: item.get("date", ""),
        reverse=True,
    )


@app.post("/api/sessions")
def save_session(
    request: SessionRequest,
    user: dict = Depends(get_current_user),
):
    # Verify that the selected plan belongs to the logged-in user.
    plan = find_record("plans", request.plan_id, user["id"])
    if not plan:
        raise HTTPException(
            status_code=404,
            detail="Workout plan not found for this user",
        )

    sessions = read_all("sessions")
    session_date = request.date.isoformat()

    # KEY FIX:
    # If this user already logged this plan on this date, update it.
    # Do not append another history record.
    existing = next(
        (
            item
            for item in sessions
            if item.get("user_id") == user["id"]
            and item.get("plan_id") == request.plan_id
            and item.get("date") == session_date
        ),
        None,
    )

    timestamp = now_iso()
    session = {
        "id": existing["id"] if existing else new_id(),
        "user_id": user["id"],
        "plan_id": request.plan_id,
        "date": session_date,
        "title": request.title.strip(),
        "notes": request.notes,
        "exercises": [item.model_dump() for item in request.exercises],
        "created_at": existing.get("created_at", timestamp) if existing else timestamp,
        "updated_at": timestamp,
    }

    if existing:
        index = sessions.index(existing)
        sessions[index] = session
    else:
        sessions.append(session)

    write_all("sessions", sessions)
    return session


@app.put("/api/sessions/{session_id}")
def update_session(
    session_id: str,
    request: SessionRequest,
    user: dict = Depends(get_current_user),
):
    sessions = read_all("sessions")
    index = next(
        (
            i
            for i, item in enumerate(sessions)
            if item.get("id") == session_id
            and item.get("user_id") == user["id"]
        ),
        None,
    )

    if index is None:
        raise HTTPException(status_code=404, detail="Workout session not found")

    plan = find_record("plans", request.plan_id, user["id"])
    if not plan:
        raise HTTPException(status_code=404, detail="Workout plan not found")

    # Avoid updating one session into a date/plan combination that already exists.
    duplicate = any(
        item.get("user_id") == user["id"]
        and item.get("id") != session_id
        and item.get("plan_id") == request.plan_id
        and item.get("date") == request.date.isoformat()
        for item in sessions
    )
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail="A session already exists for this plan and date",
        )

    old_session = sessions[index]
    updated_session = {
        **old_session,
        "plan_id": request.plan_id,
        "date": request.date.isoformat(),
        "title": request.title.strip(),
        "notes": request.notes,
        "exercises": [item.model_dump() for item in request.exercises],
        "updated_at": now_iso(),
    }

    sessions[index] = updated_session
    write_all("sessions", sessions)
    return updated_session


@app.delete("/api/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_session(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    if not delete_record("sessions", session_id, user["id"]):
        raise HTTPException(status_code=404, detail="Workout session not found")
    return None


# ============================================================
# Body metrics / BMI
# ============================================================

@app.get("/api/body-metrics")
def get_body_metrics(user: dict = Depends(get_current_user)):
    metrics = [
        item
        for item in read_all("body_metrics")
        if item.get("user_id") == user["id"]
    ]
    return sorted(metrics, key=lambda item: item.get("date", ""))


@app.post("/api/body-metrics")
def save_body_metric(
    request: BodyMetricRequest,
    user: dict = Depends(get_current_user),
):
    metrics = read_all("body_metrics")
    metric_date = request.date.isoformat()

    # Update the measurement for the same user and date rather than
    # creating multiple entries for that date.
    existing = next(
        (
            item
            for item in metrics
            if item.get("user_id") == user["id"]
            and item.get("date") == metric_date
        ),
        None,
    )

    bmi = round(
        request.weight_kg / ((request.height_cm / 100) ** 2),
        2,
    )
    timestamp = now_iso()

    metric = {
        "id": existing["id"] if existing else new_id(),
        "user_id": user["id"],
        "date": metric_date,
        "weight_kg": request.weight_kg,
        "height_cm": request.height_cm,
        "bmi": bmi,
        "notes": request.notes,
        "created_at": existing.get("created_at", timestamp) if existing else timestamp,
        "updated_at": timestamp,
    }

    if existing:
        metrics[metrics.index(existing)] = metric
    else:
        metrics.append(metric)

    write_all("body_metrics", metrics)
    return metric
