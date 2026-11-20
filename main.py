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
    {"id": 1, "name": "Shatabdi Express", "source": "Chennai", "destination": "Bengaluru", "seats": 3, "fare": 800, "date": 2026-12-11},
    {"id": 2, "name": "Rajdhani Express", "source": "Mumbai", "destination": "New Delhi", "seats": 5, "fare": 1500, "date": 2026-11-29},
    {"id": 3, "name": "Mysuru Express", "source": "Bengaluru", "destination": "Mysuru", "seats": 4, "fare": 250, "date": 2026-12-7},
    {"id": 4, "name": "Vande Bharat", "source": "Chennai", "destination": "Mysuru", "seats": 6, "fare": 1200, "date": 2026-12-20},
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
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")   # travel date, e.g. 2026-12-05


class TrainOut(BaseModel):
    id: int
    name: str
    source: str
    destination: str
    seats: int
    fare: int
    seats_left: Optional[int] = None     # calculated for a ?date=, not stored
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")   # travel date, e.g. 2026-12-05

app = FastAPI(title= "Railway Reservation API")   

@app.get("/trains/{train_id}")
def get_train(train_id : int | None = None):
    train = None
    for t in trains:
        if t["id"] == train_id :
            train = t
            break
    if train is None :
        raise HTTPException(404,"train not found")      # 404 error , "train not found"
    result = dict(train)

    if date :                                           #seats left in the train
        confirmed = 0
        for tk in tickets:
            if tk["train_id"] == train_id and tk["date"] == result["date"] and tk["status"] == "confirmed" :
                confirmed += 1

        result["seats_left"] = train["seats"] - confirmed
    return result        

@app.delete("/trains/{train_id}", status_code=204)
def delete_train(train_id: int, x_role: Optional[str] = Header(default=None)):
    #checking the role of user
    if x_role is None or (x_role != "admin" and x_role != "passenger"):
        raise HTTPException(status_code=401, detail="Send the header X-Role with the value admin or passenger")
    if x_role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete a train")
    #checking if the train exists    
    train = None
    for t in trains:
        if t["id"] == train_id:
            train = t
    if train is None:
        raise HTTPException(status_code=404, detail="Train not found")
    #trains that are confirmed or in waiting list cannot be removed
    has_active = False
    for tk in tickets:
        if tk["train_id"] == train_id:
            if tk["status"] == "confirmed": 
                has_active = True
            if tk["status"] == "waiting":
                has_active = True
    if has_active:
        raise HTTPException(status_code=409, detail="Train has active tickets")
    #removing train if all checkpoints have passed
    trains.remove(train)
    save_data(TRAINS_FILE,trains)

    return Response(status_code=204)