import json
import os
from datetime import date
from typing import Literal, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

#SETTINGS
WAITING_LIMIT = 5
SENIOR_AGE = 60
CANCEL_FEE=50
VALID_ROLES = ["admin", "passenger"]

#STORAGE
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRAINS_FILE = os.path.join(BASE_DIR, "trains.json")
PASSENGERS_FILE = os.path.join(BASE_DIR, "passengers.json")
TICKETS_FILE = os.path.join(BASE_DIR, "tickets.json")
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
#MODELS
TicketStatus = Literal["booked","waiting", "cancelled"]
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
#HELPERS
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
    
def count_status(train_id, travel_date, status):
    return sum(
        1 for t in tickets
        if t["train_id"] == train_id and t["date"] == travel_date and t["status"] == status
    )


#ENDPOINTS
app =FastAPI(title="Railway API",)
#book ticket 
@app.post("/tickets",status_code=201,response_model=TicketOut)
def create_ticket(ticket:TicketIn, x_role:Optional[str]=Header(None)):
    #role check
    check_role(x_role, allowed=["admin","passenger"])
    #existence 
    if ticket.train_id not in [train["id"] for train in trains] or ticket.passenger_id not in [passenger["id"] for passenger in passengers]:
        raise HTTPException(status_code=404,detail="Train or Passenger not found")
    #date format validation
    try:
        date.fromisoformat(ticket.date)
    except Exception:
        raise HTTPException(status_code=422,detail="bad date")
    #date validation
    if date.fromisoformat(ticket.date)<date.today():
        raise HTTPException(status_code=400,detail="date in past")
    #duplicate booking check
    for t in tickets:
        if t["train_id"]==ticket.train_id and t["passenger_id"]==ticket.passenger_id and t["date"]==ticket.date and t["status"] in ("booked","waiting"):
            raise HTTPException(status_code=409,detail="duplicate booking")
    #seat status
    status=""
    for train in trains:
        if ticket.train_id==train["id"]:
            if train["seats"]-count_status(ticket.train_id, ticket.date, "booked") > 0:
                status="booked"
            elif count_status(ticket.train_id, ticket.date, "waiting") < WAITING_LIMIT:
                status="waiting"
            else:
                raise HTTPException(status_code=409,detail="no seats available")
    #fare calculation
    fare=[train["fare"] for train in trains if train["id"]==ticket.train_id][0]
    for passenger in passengers:
        if passenger["id"]==ticket.passenger_id and passenger["age"]>=SENIOR_AGE:
            fare=int(fare*0.6)
    #Save ticket
    ticket_out= {
        "id": len(tickets)+1,
        "train_id": train["id"],
        "passenger_id": passenger["id"],
        "date": ticket.date,
        "status": status,
        "fare": fare,    # copied in: the train's fare may change later
        "booked_on": date.today().isoformat(),
        "cancelled_on": None,
        "refund": 0,
    }
    save_data(TICKETS_FILE,tickets)
    return ticket_out

@app.post("/tickets/{ticket_id}/cancel",response_model=TicketOut,status_code=200)
def cancel_ticket(ticket_id:int, x_role:Optional[str]=Header(None)):
    #role and ticket check
    if (x_role is None or x_role not in VALID_ROLES) and ticket_id>len(tickets):
        raise HTTPException(status_code=404,detail="Send the header X-Role with the value admin or passenger")
    if tickets[ticket_id-1]["status"]=="cancelled":
        raise HTTPException(status_code=409,detail="ticket already cancelled")
    #refund
    refund=0
    if tickets[ticket_id-1]["status"]=="waiting":
        refund=tickets[ticket_id-1]["fare"]
    else:
        refund=max(tickets[ticket_id-1]["fare"]-CANCEL_FEE,0)
        #promotion
        for t in tickets:
            if t["status"]=="waiting":
                t["status"]="booked"
    #setting status,refund,cancelled_date
    tickets[ticket_id-1]["status"]="cancelled"
    tickets[ticket_id-1]["refund"]=refund
    tickets[ticket_id-1]["cancelled on"]=date.today()
    save_data(TICKETS_FILE,tickets)
    return tickets[ticket_id-1]



