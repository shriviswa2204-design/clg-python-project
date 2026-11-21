import json
import os
from datetime import date
from typing import Literal, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

#SETTINGS
WAITING_LIMIT = 5
SENIOR_AGE = 60
SENIOR_DISCOUNT=40
CANCEL_FEE=50
VALID_ROLES = ["admin", "passenger"]

#STORAGE
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRAINS_FILE = os.path.join(BASE_DIR, "trains.json")
PASSENGERS_FILE = os.path.join(BASE_DIR, "passengers.json")
TICKETS_FILE = os.path.join(BASE_DIR, "tickets.json")
STARTER_TRAINS = [
    {"id": 1, "name": "Shatabdi Express", "source": "Chennai", "destination": "Bengaluru", "seats": 3, "fare": 800, "date": "2026-12-11"},
    {"id": 2, "name": "Rajdhani Express", "source": "Mumbai", "destination": "New Delhi", "seats": 5, "fare": 1500, "date": "2026-11-29"},
    {"id": 3, "name": "Mysuru Express", "source": "Bengaluru", "destination": "Mysuru", "seats": 4, "fare": 250, "date": "2026-12-07"},
    {"id": 4, "name": "Vande Bharat", "source": "Chennai", "destination": "Mysuru", "seats": 6, "fare": 1200, "date": "2026-12-20"},
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

#MODELS
TicketStatus = Literal["booked", "waiting", "cancelled"]

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

class TrainIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=60)
    source: str = Field(..., min_length=2, max_length=40)
    destination: str = Field(..., min_length=2, max_length=40)
    seats: int = Field(..., ge=1, le=500)
    fare: int = Field(..., ge=1, le=100000)      # whole rupees, never a float
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")   # travel date, e.g. 2026-12-05

class TrainUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=60)
    source: Optional[str] = Field(None, min_length=2, max_length=40)
    destination: Optional[str] = Field(None, min_length=2, max_length=40)
    seats: Optional[int] = Field(None, ge=1, le=500)
    fare: Optional[int] = Field(None, ge=1, le=100000)
    date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")   # travel date, e.g. 2026-12-05


class TrainOut(BaseModel):
    id: int
    name: str
    source: str
    destination: str
    seats: int
    fare: int
    seats_left: Optional[int] = None     # calculated for a ?date=, not stored
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")   # travel date, e.g. 2026-12-05

#PASSENGER MODELS
class PassengerIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    age: int = Field(..., ge=0)

class PassengerOut(BaseModel):
    id: int
    name: str
    age: int

#HELPERS
def check_role(x_role, allowed):
    """401 = we do not know who you are. 403 = we know, but you may not."""
    role = x_role.strip().lower() if x_role else None
    allowed_lower = [r.lower() for r in allowed]
    if role is None or role not in VALID_ROLES:
        raise HTTPException(
            status_code=401,
            detail="Not valid",
        )
    if role not in allowed_lower:
        raise HTTPException(
            status_code=403,
            detail=f"The role '{x_role}' is not allowed to do this",
        )

def count_status(train_id, travel_date, status):
    return sum(
        1 for t in tickets
        if t["train_id"] == train_id and t["date"] == travel_date and t["status"].lower() == status.lower()
    )

def train_active(train_id):
    for tk in tickets:
        if tk["train_id"] == train_id and tk["status"].lower() in ("booked", "waiting"):
            return True
    return False

def train_update(body, changes):
    """Collect only the fields the client sent, and return them as a dict."""
    if body.name is not None:
        changes["name"] = body.name
    if body.source is not None :
        changes["source"] = body.source
    if body.destination is not None:
        changes["destination"] = body.destination
    if body.seats is not None:
        changes["seats"] = body.seats
    if body.fare is not None:
        changes["fare"] = body.fare
    if body.date is not None:
        changes["date"] = body.date
    test=dict(body)
    if list(test.values())==[None,None,None,None,None,None]:
        raise HTTPException(status_code=422, detail="Send at least one field to change")

    return changes

def find_train(train_id):
    for t in trains:
        if t["id"] == train_id:
            return t
    raise HTTPException(status_code=404, detail="Train not found")

def next_id(items):
    return max((item["id"] for item in items), default=0) + 1

def has_active_tickets(key, value):
    for ticket in tickets:
        if ticket[key] == value and ticket["status"].lower() in ["booked", "waiting"]:
            return True
    return False

#-------ENDPOINTS------
app = FastAPI(title="IRCTC Ticket Booking", description = "API for train ticket booking")

@app.get("/health")
def health():
    return {"status": "ok"}

#--------trains------------------
@app.get("/trains", response_model=list[TrainOut])
def list_trains(source: Optional[str] = None, destination: Optional[str] = None):
    result = trains
    if source:
        result = [t for t in result if t["source"].lower() == source.strip().lower()]
    if destination:
        result = [t for t in result if t["destination"].lower() == destination.strip().lower()]
    return result

@app.post("/trains", response_model=TrainOut, status_code=201)
def add_train(body: TrainIn, x_role: Optional[str] = Header(None)):
    check_role(x_role, ["admin"])

    for t in trains:
        if (t["name"].lower() == body.name.lower()
                and t["source"].lower() == body.source.lower()
                and t["destination"].lower() == body.destination.lower()
                and t["date"] == body.date):
            raise HTTPException(status_code=409, detail="Train already exists")

    train = {"id": next_id(trains), **body.model_dump()}
    trains.append(train)
    save_data(TRAINS_FILE, trains)
    return train

@app.get("/trains/{train_id}")
def get_train(train_id: int, travel_date: Optional[str] = Query(None, alias="date")):
    train = find_train(train_id)
    result = dict(train)

    target_date = travel_date or result["date"]
    booked = count_status(train_id, target_date, "booked")
    result["seats_left"] = train["seats"] - booked
    return result

@app.delete("/trains/{train_id}", status_code=204)
def delete_train(train_id: int, x_role: Optional[str] = Header(default=None)):
    check_role(x_role, ["admin"])
    train = find_train(train_id)

    if train_active(train_id):
        raise HTTPException(status_code=409, detail="Train has active tickets")

    trains.remove(train)
    save_data(TRAINS_FILE, trains)
    return Response(status_code=204)

@app.patch("/trains/{train_id}", response_model=TrainOut)
def patch_train(train_id: int, body: TrainUpdate, x_role: Optional[str] = Header(default=None)):
    check_role(x_role, ["admin"])
    train = find_train(train_id)
    changes = dict(train)
    train_update(body, changes)

    if "seats" in changes:
        per_date = {}
        for tk in tickets:
            if tk["train_id"] == train_id and tk["status"].lower() == "booked":
                per_date[tk["date"]] = per_date.get(tk["date"], 0) + 1
        highest = max(per_date.values(), default=0)
        if changes["seats"] < highest:
            raise HTTPException(status_code=409, detail="Fewer seats than already-booked tickets")

    for other in trains:
        if other["id"] != train_id and (
            other["name"].lower() == changes["name"].lower()
            and other["source"].lower() == changes["source"].lower()
            and other["destination"].lower() == changes["destination"].lower()
            and other["date"] == changes["date"]
        ):
            raise HTTPException(status_code=409, detail="This train already exists")

    trains.remove(train)
    trains.append(changes)
    save_data(TRAINS_FILE, trains)
    return changes

# passenger data
@app.post("/passengers", response_model=PassengerOut, status_code=201)
def create_passenger(passenger: PassengerIn, x_role: str = Header(None)):
    check_role(x_role, ["admin", "passenger"])
    add_passenger = {"id": next_id(passengers), "name": passenger.name, "age": passenger.age}
    passengers.append(add_passenger)
    save_data(PASSENGERS_FILE, passengers)
    return add_passenger

@app.get("/passenger_list")
def get_passengers(x_role: str = Header(None)):
    check_role(x_role, ["admin"])
    return passengers

@app.get("/passengers/{passenger_id}")
def get_passenger(passenger_id: int, x_role: str = Header(None)):
    check_role(x_role, ["admin", "passenger"])
    for p in passengers:
        if p["id"] == passenger_id:
            return p
    raise HTTPException(status_code=404, detail="No passenger with that id number found")

#-----passengers and ticket--------
@app.get("/passengers/{passenger_id}/tickets", response_model=list[TicketOut])
def passenger_tickets(passenger_id: int, x_role: Optional[str] = Header(None)):
    check_role(x_role, ["admin", "passenger"])

    for p in passengers:
        if p["id"] == passenger_id:
            break
    else:
        raise HTTPException(status_code=404, detail="Passenger not found")

    return [t for t in tickets if t["passenger_id"] == passenger_id]


@app.get("/tickets", response_model=list[TicketOut])
def list_tickets(
    status: Optional[TicketStatus] = Query(None),
    date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    x_role: Optional[str] = Header(None),
):
    check_role(x_role, ["admin"])
    result = tickets

    if status is not None:
        result = [t for t in result if t["status"].lower() == status.lower()]

    if date is not None:
        result = [t for t in result if t["date"] == date]

    return result


@app.delete("/passengers/{passenger_id}", status_code=204)
def delete_passenger(passenger_id: int, x_role: Optional[str] = Header(None)):
    check_role(x_role, ["admin"])
    for p in passengers:
        if p["id"] == passenger_id:
            break
    else:
        raise HTTPException(status_code=404, detail="Passenger not found")

    if has_active_tickets("passenger_id", passenger_id):
        raise HTTPException(status_code=409, detail="Passenger has active tickets")

    passengers.remove(p)
    save_data(PASSENGERS_FILE, passengers)
    return Response(status_code=204)

#book ticket
@app.post("/tickets", status_code=201, response_model=TicketOut)
def create_ticket(ticket: TicketIn, x_role: Optional[str] = Header(None)):
    check_role(x_role, allowed=["admin", "passenger"])
    train = find_train(ticket.train_id)
    passenger = next((p for p in passengers if p["id"] == ticket.passenger_id), None)
    if passenger is None:
        raise HTTPException(status_code=404, detail="Passenger not found")
    if ticket.date != train["date"]:
        raise HTTPException(status_code=404, detail="Train not found for date")

    try:
        parsed_date = date.fromisoformat(ticket.date)
    except Exception:
        raise HTTPException(status_code=422, detail="bad date")

    if parsed_date < date.today():
        raise HTTPException(status_code=400, detail="date in past")

    for t in tickets:
        if (t["train_id"] == ticket.train_id
                and t["passenger_id"] == ticket.passenger_id
                and t["date"] == ticket.date
                and t["status"].lower() in ("booked", "waiting")):
            raise HTTPException(status_code=409, detail="duplicate booking")

    status = ""
    if train["seats"] - count_status(ticket.train_id, ticket.date, "booked") > 0:
        status = "booked"
    elif count_status(ticket.train_id, ticket.date, "waiting") < WAITING_LIMIT:
        status = "waiting"
    else:
        raise HTTPException(status_code=409, detail="no seats available")

    fare = train["fare"]
    if passenger["age"] >= SENIOR_AGE:
        fare = int(fare * (100-SENIOR_DISCOUNT)//100)

    ticket_out = {
        "id": next_id(tickets),
        "train_id": train["id"],
        "passenger_id": passenger["id"],
        "date": ticket.date,
        "status": status,
        "fare": fare,    # copied in: the train's fare may change later
        "booked_on": date.today().isoformat(),
        "cancelled_on": None,
        "refund": 0,
    }
    tickets.append(ticket_out)
    save_data(TICKETS_FILE, tickets)
    return ticket_out

@app.post("/tickets/{ticket_id}/cancel", response_model=TicketOut, status_code=200)
def cancel_ticket(ticket_id: int, x_role: Optional[str] = Header(None)):
    check_role(x_role, ["admin", "passenger"])
    target = next((t for t in tickets if t["id"] == ticket_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if target["status"].lower() == "cancelled":
        raise HTTPException(status_code=409, detail="ticket already cancelled")

    prev_status = target["status"].lower()
    if prev_status == "waiting":
        refund = target["fare"]
    else:
        refund = max(target["fare"] - CANCEL_FEE, 0)
        for t in tickets:
            if (t["id"] != target["id"]
                    and t["train_id"] == target["train_id"]
                    and t["date"] == target["date"]
                    and t["status"].lower() == "waiting"):
                t["status"] = "booked"
                break

    target["status"] = "cancelled"
    target["refund"] = refund
    target["cancelled_on"] = date.today().isoformat()
    save_data(TICKETS_FILE, tickets)
    return target

#-----report-----
@app.get("/stats")
def stats(x_role: Optional[str] = Header(default=None)):
    check_role(x_role, ["admin"])
    booked = [t for t in tickets if t["status"].lower() == "booked"]
    waiting = [t for t in tickets if t["status"].lower() == "waiting"]
    cancelled = [t for t in tickets if t["status"].lower() == "cancelled"]

    # Revenue = fares of booked tickets + the fee kept on cancelled ones.
    revenue = sum(t["fare"] for t in booked) + sum(t["fare"] - t["refund"] for t in cancelled)

    per_train = {}
    for t in booked:
        per_train[t["train_id"]] = per_train.get(t["train_id"], 0) + 1
    busiest = max(per_train, key=per_train.get) if per_train else None

    return {
        "trains": len(trains),
        "passengers": len(passengers),
        "booked": len(booked),
        "waiting": len(waiting),
        "cancelled": len(cancelled),
        "total_revenue": revenue,
        "busiest_train_id": busiest,
    }
