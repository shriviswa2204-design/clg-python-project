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