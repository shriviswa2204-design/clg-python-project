# 1. Your starter data (goes in Section 2)
STARTER_TRAINS = [
    {"id": 1, "name": "Shatabdi Express", "source": "Chennai", "destination": "Bengaluru", "seats": 3, "fare": 800},
    {"id": 2, "name": "Rajdhani Express", "source": "Mumbai", "destination": "New Delhi", "seats": 5, "fare": 1500},
    {"id": 3, "name": "Mysuru Express", "source": "Bengaluru", "destination": "Mysuru", "seats": 4, "fare": 250},
]

# 2. Your models (goes in Section 3)
class TrainIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=60)
    source: str = Field(..., min_length=2, max_length=40)
    destination: str = Field(..., min_length=2, max_length=40)
    seats: StrictInt = Field(..., ge=1, le=500)
    fare: StrictInt = Field(..., ge=1, le=100000)

class TrainOut(BaseModel):
    id: int
    name: str
    source: str
    destination: str
    seats: int
    fare: int
    seats_left: Optional[int] = None

# 3. Your helper (goes in Section 4)
def find_train(train_id):
    for t in trains:
        if t["id"] == train_id:
            return t
    raise HTTPException(status_code=404, detail="Train not found")

# 4. Your two endpoints (goes in Section 5)
@app.get("/trains", response_model=list[TrainOut])
def list_trains(source: Optional[str] = None, destination: Optional[str] = None):
    result = trains
    if source:
        result = [t for t in result if t["source"].lower() == source.lower()]
    if destination:
        result = [t for t in result if t["destination"].lower() == destination.lower()]
    return result

@app.post("/trains", response_model=TrainOut, status_code=201)
def add_train(body: TrainIn, x_role: Optional[str] = Header(None)):
    check_role(x_role, ["admin"])

    for t in trains:
        if (t["name"].lower() == body.name.lower()
                and t["source"].lower() == body.source.lower()
                and t["destination"].lower() == body.destination.lower()):
            raise HTTPException(status_code=409, detail="Train already exists")

    train = {"id": next_id(trains), **body.model_dump()}
    trains.append(train)
    save_data(TRAINS_FILE, trains)
    return train