from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from calculations import CalculationInput, CalculationResult, calculate

app = FastAPI(title="Kentsel Dönüşüm Karar Destek API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/calculate", response_model=CalculationResult)
def calculate_endpoint(payload: CalculationInput) -> CalculationResult:
    return calculate(payload)


@app.get("/health")
def health():
    return {"status": "ok"}
