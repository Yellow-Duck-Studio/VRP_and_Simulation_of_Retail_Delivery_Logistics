from simulator.utils import PaymentCalculator
from simulator.schemas import Courier, AffiliationType, Location

def test_shift_worker_payment():
    config = {
        "hourly_rate": {"car": 400.0, "foot": 200.0},
        "affiliation_multipliers": {"shift": 1.0},
        "rate_per_km": {},
    }
    calc = PaymentCalculator(config)
    courier = Courier(courier_id="c1", courier_type_id="car", affiliation_type="shift", current_location=Location(latitude=55.0, longitude=37.0))
    payment = calc.calculate(courier, distance_km=0.0, in_window=False, duration_hours=2.5)
    assert payment == 400.0 * 2.5

def test_exchange_worker_payment():
    config = {
        "rate_per_km": {"car": 60.0},
        "base_fee": 50.0,
        "window_bonus": 100.0,
        "affiliation_multipliers": {"exchange": 1.2},
    }
    calc = PaymentCalculator(config)
    courier = Courier(courier_id="c2", courier_type_id="car", affiliation_type="exchange", current_location=Location(
        latitude=55.0, longitude=37.0))
    payment = calc.calculate(courier, distance_km=2.5, in_window=False, duration_hours=0.0)
    assert payment == (60.0 * 2.5 + 50.0) * 1.2
    payment = calc.calculate(courier, distance_km=2.5, in_window=True)
    assert payment == (60.0 * 2.5 + 50.0 + 100.0) * 1.2