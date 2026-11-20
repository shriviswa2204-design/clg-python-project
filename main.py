import json
import os
from datetime import date
from typing import Literal, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

app = FastAPI(title="IRCTC Train Ticket Booking API", description="This API allows you to book, view and cancel train tickets")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRAINS_FILE = os.path.join(BASE_DIR, "trains.json")
PASSENGERS_FILE = os.path.join(BASE_DIR, "passengers.json")
TICKETS_FILE = os.path.join(BASE_DIR, "tickets.json")

#STORAGE
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

#TICKET MODELS 
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

#PASSENGER MODELS 
class PassengerIn(BaseModel):
    name: str = Field(..., min_length=1,max_length = 50)
    age: int = Field(..., ge = 0)

class PassengerOut(BaseModel):
    id: int
    name: str
    age: int

#

#HELPERS 

# ENDPOINTS -M4
@app.post("/passengers", response_model=PassengerOut, status_code=201)
def create_passenger(passenger: PassengerIn):
    largest_id = 0
    for p in passengers:               # Dictionary used to find largest id, we will assign +1 to the largest so far
        if p["id"] > largest_id:
            largest_id = p["id"]

    add_passenger = {"id": largest_id +1, "name": passenger.name, "age": passenger.age} 

    passengers.append(add_passenger)
    save_data(PASSENGERS_FILE, passengers)
    return add_passenger       

@app.get("/passengers")
def get_passenegers():
    return passengers

@app.get("/passengers/{passenger_id}")
def get_passenger(passenger_id :int):
    for p in passengers:
        if p["id"] == passenger_id:
            return p
    raise HTTPException(status_code = 404, detail = "No passenger with that id number found")
                    