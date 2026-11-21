import json
import os
from datetime import date
from typing import Literal, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field


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

#coding

def has_active_tickets(key, value):
    for ticket in tickets:
        if ticket[key]== value and ticket["status"] in ["confirmed","waiting"]:
            return True
    return False

def check_role(x_role, allowed):
    """401 = we do not know who you are. 403 = we know, but you may not."""
    if x_role is None or x_role not in VALID_ROLES:
        raise HTTPException(
            status_code=401,
            detail="not valid role",
        )
    if x_role not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"The role '{x_role}' is not allowed to do this",
        )

@app.get("/passengers/{passenger_id}/tickets", response_model=list[TicketOut])
def passenger_tickets(passenger_id: int, x_role: Optional[str] = Header(None)):
    check_role(x_role,["admin,passenger"])

    for p in passengers:
        if p["id"] == passenger_id:
            break
    else:
        raise HTTPException(status_code=404,detail="Passenger not found")
    
    return [t for t in tickets if t["passenger_id"] == passenger_id]



@app.get("/tickets", response_model=list[TicketOut])
def list_tickets(
    status: Optional[TicketStatus] = Query(None),
    date: Optional[str] =   Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    x_role: Optional[str] = Header(None),
):

    check_role(x_role,["admin"])
    result = tickets

    if status is not None:
        result = [t for t in result if t["status"] == status]

    if date is not None:
        result = [t for t in result if t["date"] == date]

    return result


@app.delete("/passengers/{passenger_id}", status_code=204)
def delete_passenger(passenger_id: int, x_role: Optional[str] = Header(None)):
    check_role(x_role,["admin"])
    for p in passengers:
        if p["id"] == passenger_id:
            break

        else:
            raise HTTPException(status_code=404,detail="Passenger not found")

    if has_active_tickets("passenger_id", passenger_id):
        raise HTTPException(status_code=409,detail="Passenger has active tickets") 

    passengers.remove(p)
    save_data(PASSENGERS_FILE, passengers)
    return Response(status_code=204)  