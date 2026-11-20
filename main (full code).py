"""Railway Reservation API (IRCTC style) - FastAPI + JSON files.

Run:   pip install fastapi uvicorn
       uvicorn main:app --reload
Open:  http://127.0.0.1:8000/docs

Five sections, always in this order:
1 Settings, 2 Storage, 3 Models, 4 Helpers, 5 Endpoints.
"""

import json
import os
from datetime import date
from typing import Literal, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

app = FastAPI(title="Railway Reservation API")


# =====================================================================
# 1 · SETTINGS  (change a rule = change one line here)
# =====================================================================
WAITING_LIMIT = 5        # max waiting tickets per train per date
SENIOR_AGE = 60          # age at which the discount starts
SENIOR_DISCOUNT = 40     # percent off the fare
CANCEL_FEE = 50          # rupees kept when a CONFIRMED ticket is cancelled
VALID_ROLES = ["admin", "passenger"]


# =====================================================================
# 2 · STORAGE
# =====================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRAINS_FILE = os.path.join(BASE_DIR, "trains.json")
PASSENGERS_FILE = os.path.join(BASE_DIR, "passengers.json")
TICKETS_FILE = os.path.join(BASE_DIR, "tickets.json")

# Small seat counts on purpose: easy to fill a train and see the waiting list.
STARTER_TRAINS = [
    {"id": 1, "name": "Shatabdi Express", "source": "Chennai", "destination": "Bengaluru", "seats": 3, "fare": 800},
    {"id": 2, "name": "Rajdhani Express", "source": "Mumbai", "destination": "New Delhi", "seats": 5, "fare": 1500},
    {"id": 3, "name": "Mysuru Express", "source": "Bengaluru", "destination": "Mysuru", "seats": 4, "fare": 250},
    {"id": 4, "name": "Vande Bharat", "source": "Chennai", "destination": "Mysuru", "seats": 6, "fare": 1200},
]
STARTER_PASSENGERS = [
    {"id": 1, "name": "Asha Rao", "age": 28},
    {"id": 2, "name": "Ramesh Iyer", "age": 65},
]
STARTER_TICKETS = []


def save_data(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_data(path, starter):
    """Load a list from a JSON file.

    First start (file missing) -> create it with the starter data.
    Damaged file -> do not crash: fall back to the starter data.
    (This is the 'safe against a bad data file' requirement, item 10.)
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("file does not hold a list")
        return data
    except (FileNotFoundError, ValueError, OSError):
        data = [dict(item) for item in starter]
        save_data(path, data)
        return data


trains = load_data(TRAINS_FILE, STARTER_TRAINS)
passengers = load_data(PASSENGERS_FILE, STARTER_PASSENGERS)
tickets = load_data(TICKETS_FILE, STARTER_TICKETS)


# =====================================================================
# 3 · MODELS
# =====================================================================
TicketStatus = Literal["confirmed", "waiting", "cancelled"]


class TrainIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=60)
    source: str = Field(..., min_length=2, max_length=40)
    destination: str = Field(..., min_length=2, max_length=40)
    seats: int = Field(..., ge=1, le=500)
    fare: int = Field(..., ge=1, le=100000)      # whole rupees, never a float


class TrainUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=60)
    source: Optional[str] = Field(None, min_length=2, max_length=40)
    destination: Optional[str] = Field(None, min_length=2, max_length=40)
    seats: Optional[int] = Field(None, ge=1, le=500)
    fare: Optional[int] = Field(None, ge=1, le=100000)


class TrainOut(BaseModel):
    id: int
    name: str
    source: str
    destination: str
    seats: int
    fare: int
    seats_left: Optional[int] = None     # calculated for a ?date=, not stored


class PassengerIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=60)
    age: int = Field(..., ge=0, le=120)


class PassengerOut(BaseModel):
    id: int
    name: str
    age: int


class TicketIn(BaseModel):
    train_id: int = Field(..., gt=0)
    passenger_id: int = Field(..., gt=0)
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")   # travel date, e.g. 2026-12-05


class TicketOut(BaseModel):
    id: int
    train_id: int
    passenger_id: int
    date: str
    status: TicketStatus
    fare: int
    booked_on: str
    cancelled_on: Optional[str] = None
    refund: int = 0


# =====================================================================
# 4 · HELPERS
# =====================================================================
def check_role(x_role, allowed):
    """401 = we do not know who you are. 403 = we know, but you may not."""
    if x_role is None or x_role not in VALID_ROLES:
        raise HTTPException(
            status_code=401,
            detail="Send the header X-Role with the value admin or passenger",
        )
    if x_role not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"The role '{x_role}' is not allowed to do this",
        )


def parse_date(text, field="date"):
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{field} must look like 2026-12-05")


def today_of(today):
    """The ?today= switch: lets us test 'past date' without waiting."""
    if today is None:
        return date.today()
    return parse_date(today, "today")


def next_id(items):
    return max((item["id"] for item in items), default=0) + 1


def find_train(train_id):
    for t in trains:
        if t["id"] == train_id:
            return t
    raise HTTPException(status_code=404, detail=f"Train {train_id} not found")


def find_passenger(passenger_id):
    for p in passengers:
        if p["id"] == passenger_id:
            return p
    raise HTTPException(status_code=404, detail=f"Passenger {passenger_id} not found")


def find_ticket(ticket_id):
    for t in tickets:
        if t["id"] == ticket_id:
            return t
    raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")


def count_status(train_id, travel_date, status):
    return sum(
        1 for t in tickets
        if t["train_id"] == train_id and t["date"] == travel_date and t["status"] == status
    )


def max_confirmed(train_id):
    """Most confirmed tickets on any one date (guards lowering a train's seats)."""
    per_date = {}
    for t in tickets:
        if t["train_id"] == train_id and t["status"] == "confirmed":
            per_date[t["date"]] = per_date.get(t["date"], 0) + 1
    return max(per_date.values(), default=0)


def has_active_tickets(key, value):
    return any(t[key] == value and t["status"] in ("confirmed", "waiting") for t in tickets)


def fare_for(train, passenger):
    """Whole-rupee fare; seniors get SENIOR_DISCOUNT percent off."""
    if passenger["age"] >= SENIOR_AGE:
        return train["fare"] * (100 - SENIOR_DISCOUNT) // 100
    return train["fare"]


# =====================================================================
# 5 · ENDPOINTS
# Every endpoint that changes data: role -> 404s -> rules (409) ->
# change data -> save -> reply.
# =====================================================================

# ---------- health ----------
@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- trains ----------
@app.get("/trains", response_model=list[TrainOut])
def list_trains(
    source: Optional[str] = Query(None, description="filter by source station"),
    destination: Optional[str] = Query(None, description="filter by destination station"),
):
    result = trains
    if source is not None:
        result = [t for t in result if t["source"].lower() == source.lower()]
    if destination is not None:
        result = [t for t in result if t["destination"].lower() == destination.lower()]
    return result


@app.get("/trains/{train_id}", response_model=TrainOut)
def get_train(
    train_id: int,
    date_: Optional[str] = Query(None, alias="date", description="travel date, e.g. 2026-12-05"),
):
    train = dict(find_train(train_id))
    if date_ is not None:
        parse_date(date_)
        train["seats_left"] = train["seats"] - count_status(train_id, date_, "confirmed")
    return train


@app.post("/trains", response_model=TrainOut, status_code=201)
def add_train(body: TrainIn, x_role: Optional[str] = Header(default=None)):
    check_role(x_role, ["admin"])
    for t in trains:
        if (t["name"].lower() == body.name.lower()
                and t["source"].lower() == body.source.lower()
                and t["destination"].lower() == body.destination.lower()):
            raise HTTPException(status_code=409, detail="This train already exists")
    train = {"id": next_id(trains), **body.model_dump()}
    trains.append(train)
    save_data(TRAINS_FILE, trains)
    return train


@app.patch("/trains/{train_id}", response_model=TrainOut)
def update_train(train_id: int, body: TrainUpdate, x_role: Optional[str] = Header(default=None)):
    check_role(x_role, ["admin"])
    train = find_train(train_id)
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}

    if "seats" in changes and changes["seats"] < max_confirmed(train_id):
        raise HTTPException(status_code=409, detail="Fewer seats than already-confirmed tickets")

    new = {**train, **changes}
    for other in trains:
        if (other["id"] != train_id
                and other["name"].lower() == new["name"].lower()
                and other["source"].lower() == new["source"].lower()
                and other["destination"].lower() == new["destination"].lower()):
            raise HTTPException(status_code=409, detail="This train already exists")

    train.update(changes)
    save_data(TRAINS_FILE, trains)
    return train


@app.delete("/trains/{train_id}", status_code=204)
def delete_train(train_id: int, x_role: Optional[str] = Header(default=None)):
    check_role(x_role, ["admin"])
    train = find_train(train_id)
    if has_active_tickets("train_id", train_id):
        raise HTTPException(status_code=409, detail="Train has active tickets")
    trains.remove(train)
    save_data(TRAINS_FILE, trains)
    return Response(status_code=204)


# ---------- passengers ----------
@app.post("/passengers", response_model=PassengerOut, status_code=201)
def add_passenger(body: PassengerIn, x_role: Optional[str] = Header(default=None)):
    check_role(x_role, ["admin", "passenger"])
    passenger = {"id": next_id(passengers), **body.model_dump()}
    passengers.append(passenger)
    save_data(PASSENGERS_FILE, passengers)
    return passenger


@app.get("/passengers", response_model=list[PassengerOut])
def list_passengers(x_role: Optional[str] = Header(default=None)):
    check_role(x_role, ["admin"])
    return passengers


@app.get("/passengers/{passenger_id}", response_model=PassengerOut)
def get_passenger(passenger_id: int, x_role: Optional[str] = Header(default=None)):
    check_role(x_role, ["admin", "passenger"])
    return find_passenger(passenger_id)


@app.delete("/passengers/{passenger_id}", status_code=204)
def delete_passenger(passenger_id: int, x_role: Optional[str] = Header(default=None)):
    check_role(x_role, ["admin"])
    passenger = find_passenger(passenger_id)
    if has_active_tickets("passenger_id", passenger_id):
        raise HTTPException(status_code=409, detail="Passenger has active tickets")
    passengers.remove(passenger)
    save_data(PASSENGERS_FILE, passengers)
    return Response(status_code=204)


@app.get("/passengers/{passenger_id}/tickets", response_model=list[TicketOut])
def passenger_tickets(passenger_id: int, x_role: Optional[str] = Header(default=None)):
    check_role(x_role, ["admin", "passenger"])
    find_passenger(passenger_id)
    return [t for t in tickets if t["passenger_id"] == passenger_id]


# ---------- tickets ----------
@app.post("/tickets", response_model=TicketOut, status_code=201)
def book_ticket(
    body: TicketIn,
    today: Optional[str] = Query(None, description="pretend today is this date (testing)"),
    x_role: Optional[str] = Header(default=None),
):
    # 1 role
    check_role(x_role, ["admin", "passenger"])
    # 2 everything exists (404) and the date is valid (422)
    train = find_train(body.train_id)
    passenger = find_passenger(body.passenger_id)
    travel_date = parse_date(body.date)
    today_date = today_of(today)
    # 3 rules, stop at the first that fails
    if travel_date < today_date:
        raise HTTPException(status_code=400, detail="Cannot book a journey in the past")
    for t in tickets:
        if (t["train_id"] == train["id"] and t["passenger_id"] == passenger["id"]
                and t["date"] == body.date and t["status"] in ("confirmed", "waiting")):
            raise HTTPException(status_code=409, detail="Passenger already has a ticket on this train and date")
    if count_status(train["id"], body.date, "confirmed") < train["seats"]:
        status = "confirmed"
    elif count_status(train["id"], body.date, "waiting") < WAITING_LIMIT:
        status = "waiting"
    else:
        raise HTTPException(status_code=409, detail="Train is full and the waiting list is full")
    # 4 change data, save
    ticket = {
        "id": next_id(tickets),
        "train_id": train["id"],
        "passenger_id": passenger["id"],
        "date": body.date,
        "status": status,
        "fare": fare_for(train, passenger),    # copied in: the train's fare may change later
        "booked_on": today_date.isoformat(),
        "cancelled_on": None,
        "refund": 0,
    }
    tickets.append(ticket)
    save_data(TICKETS_FILE, tickets)
    # 5 reply
    return ticket


@app.post("/tickets/{ticket_id}/cancel", response_model=TicketOut)
def cancel_ticket(
    ticket_id: int,
    today: Optional[str] = Query(None, description="pretend today is this date (testing)"),
    x_role: Optional[str] = Header(default=None),
):
    check_role(x_role, ["admin", "passenger"])
    ticket = find_ticket(ticket_id)
    today_date = today_of(today)
    if ticket["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="Ticket is already cancelled")
    if parse_date(ticket["date"]) < today_date:
        raise HTTPException(status_code=400, detail="Cannot cancel a journey that has already happened")

    was_confirmed = ticket["status"] == "confirmed"
    # Confirmed: refund fare minus fee. Waiting: nothing was used, full refund.
    ticket["refund"] = max(ticket["fare"] - CANCEL_FEE, 0) if was_confirmed else ticket["fare"]
    ticket["status"] = "cancelled"
    ticket["cancelled_on"] = today_date.isoformat()

    # A freed seat goes to the FIRST waiting ticket (lowest id) on that train and date.
    if was_confirmed:
        waiting = [
            t for t in tickets
            if t["train_id"] == ticket["train_id"] and t["date"] == ticket["date"]
            and t["status"] == "waiting"
        ]
        if waiting:
            min(waiting, key=lambda t: t["id"])["status"] = "confirmed"

    save_data(TICKETS_FILE, tickets)
    return ticket


@app.get("/tickets", response_model=list[TicketOut])
def list_tickets(
    status: Optional[TicketStatus] = Query(None),      # bad value -> 422 automatically
    date_: Optional[str] = Query(None, alias="date"),
    x_role: Optional[str] = Header(default=None),
):
    check_role(x_role, ["admin"])
    result = tickets
    if status is not None:
        result = [t for t in result if t["status"] == status]
    if date_ is not None:
        parse_date(date_)
        result = [t for t in result if t["date"] == date_]
    return result


# ---------- report ----------
@app.get("/stats")
def stats(x_role: Optional[str] = Header(default=None)):
    check_role(x_role, ["admin"])
    confirmed = [t for t in tickets if t["status"] == "confirmed"]
    waiting = [t for t in tickets if t["status"] == "waiting"]
    cancelled = [t for t in tickets if t["status"] == "cancelled"]

    # Revenue = fares of confirmed tickets + the fee kept on cancelled ones.
    revenue = sum(t["fare"] for t in confirmed) + sum(t["fare"] - t["refund"] for t in cancelled)

    per_train = {}
    for t in confirmed:
        per_train[t["train_id"]] = per_train.get(t["train_id"], 0) + 1
    busiest = max(per_train, key=per_train.get) if per_train else None

    return {
        "trains": len(trains),
        "passengers": len(passengers),
        "confirmed": len(confirmed),
        "waiting": len(waiting),
        "cancelled": len(cancelled),
        "total_revenue": revenue,
        "busiest_train_id": busiest,
    }
