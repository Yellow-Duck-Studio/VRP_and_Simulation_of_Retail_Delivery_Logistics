from typing import Dict, Optional

class PaymentCalculator:
    """Calculates courier payment"""
    def __init__(self, config: Dict):
        self.config = config
        self.rate_per_km = config.get("rate_per_km", {})
        self.hourly_rate = config.get("hourly_rate", {})
        self.window_bonus = config.get("window_bonus", 100.0)
        self.base_fee = config.get("base_fee", 0.0)
        self.affiliation_multipliers = config.get("affiliation_multipliers", {})

    def calculate(self, courier, distance_km: float, in_window: bool, duration_hours: float = 0.0) -> float:
        """Returns the payment amount"""
        vehicle_type = courier.courier_type_id
        affiliation = courier.affiliation_type

        if affiliation == "shift":
            rate = self.hourly_rate.get(vehicle_type, 200.0)
            payment = rate * duration_hours
            payment *= self.affiliation_multipliers.get("shift", 1.0)
            return payment

        rate_per_km = self.rate_per_km.get(vehicle_type, 50.0)
        payment = rate_per_km * distance_km + self.base_fee

        if in_window:
            payment += self.window_bonus

        multiplier = self.affiliation_multipliers.get(affiliation, 1.0)
        payment *= multiplier

        return payment