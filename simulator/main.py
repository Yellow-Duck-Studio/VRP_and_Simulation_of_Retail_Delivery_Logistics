#!/usr/bin/env python3
"""
Main entry point for the Retail Delivery Logistics Simulator.
"""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from simulator import (
    SimulationController,
    load_simulation_data,
)
from simulator.utils.logger import get_logger, Colors


def main():
    parser = argparse.ArgumentParser(
        description="Retail Delivery Logistics Simulator"
    )
    parser.add_argument(
        "--input",
        type=str,
        default="test_data_innopolis.json",
        help="Path to input JSON file with simulation data"
    )
    parser.add_argument(
        "--start-time",
        type=str,
        default="2024-06-17T09:00:00",
        help="Simulation start time (ISO format)"
    )
    parser.add_argument(
        "--time-step",
        type=int,
        default=5,
        help="Time step in minutes"
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=100,
        help="Maximum number of simulation steps"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to output JSON file for results"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail fast if validation fails"
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level"
    )

    args = parser.parse_args()

    os.environ["LOG_LEVEL"] = args.log_level
    logger = get_logger("Main")

    base_dir = Path(__file__).resolve().parent
    input_path = Path(args.input)

    if not input_path.is_absolute():
        input_path = base_dir / input_path

    if not input_path.exists():
        fallback_path = base_dir / "simulator" / input_path.name
        if fallback_path.exists():
            input_path = fallback_path

    if not input_path.exists():
        logger.error(f"Input file not found at {input_path}")
        return 1

    start_time = datetime.fromisoformat(args.start_time)
    controller = SimulationController(
        start_time=start_time,
        time_step_minutes=args.time_step,
        strict_validation=args.strict
    )

    logger.info(f"{Colors.BLUE}------------------------------- Data Loading -------------------------------{Colors.RESET}")
    logger.info(f"Loading simulation data from {input_path}...")
    load_simulation_data(str(input_path), controller.state_manager)

    logger.debug(f"{Colors.BLUE}-------------------------------- Warehouses --------------------------------{Colors.RESET}")
    for wh_id, wh in controller.state_manager.warehouses.items():
        logger.debug(f"{wh_id}: {wh.location.address or 'No address'}")
        logger.debug(f"  Location: ({wh.location.latitude:.4f}, {wh.location.longitude:.4f})")

    logger.debug(f"{Colors.BLUE}------------------------------- Courier Types -------------------------------{Colors.RESET}")
    for ct_id, ct in controller.state_manager.courier_types.items():
        logger.debug(f"{ct_id}: {ct.name}")
        logger.debug(f"  Capacity: {ct.capacity_kg} kg, Speed: {ct.speed_kmh} km/h")

    logger.debug(f"{Colors.BLUE}---------------------------------- Couriers ---------------------------------{Colors.RESET}")
    for c_id, courier in controller.state_manager.couriers.items():
        ct = controller.state_manager.courier_types.get(courier.courier_type_id)
        logger.debug(f"{c_id}: {ct.name if ct else 'Unknown'}")
        logger.debug(f"  Status: {courier.status}, Load: {courier.current_load} kg")
        logger.debug(f"  Location: ({courier.current_location.latitude:.4f}, {courier.current_location.longitude:.4f})")

    logger.debug(f"{Colors.BLUE}---------------------------------- Orders ----------------------------------{Colors.RESET}")
    for o_id, order in controller.state_manager.orders.items():
        logger.debug(f"  Warehouse ID: {order.warehouse_id}")
        logger.debug(f"  Mass: {order.mass_kg} kg")
        logger.debug(f"  Time Window: {order.delivery_time_window.start.strftime('%H:%M')} - {order.delivery_time_window.end.strftime('%H:%M')}")
        logger.debug(f"  Ready Time: {order.ready_time.strftime('%H:%M')}")
        logger.debug(f"  Status: {order.status}")

    logger.info(f"{Colors.BLUE}------------------------------ Validation Summary ----------------------------{Colors.RESET}")
    validation_report = controller.validate_routes()
    for key, value in validation_report.summary.items():
        if isinstance(value, dict):
            dict_items = ", ".join([f"{k.upper()}: {v}" for k, v in value.items()])
            logger.info(f"{key}: {dict_items}")
        else:
            logger.info(f"{key}: {value}")

    logger.info(f"{Colors.BLUE}----------------------------- Running Simulation -----------------------------{Colors.RESET}")
    logger.info(f"Start Time: {start_time.isoformat()}")
    logger.info(f"Time Step: {args.time_step} minutes")
    logger.info(f"Max Steps: {args.max_steps}")

    controller.run(max_steps=args.max_steps)

    logger.info(f"{Colors.BLUE}----------------------------- Simulation Results -----------------------------{Colors.RESET}")
    metrics = controller.get_metrics()
    for key, value in metrics.items():
        if isinstance(value, float):
            if "rate" in key:
                logger.info(f"{key}: {value:.2%}")
            else:
                logger.info(f"{key}: {value:.2f}")
        else:
            logger.info(f"{key}: {value}")

    logger.info(f"{Colors.BLUE}-------------------------------- Event Summary -------------------------------{Colors.RESET}")
    events = controller.event_manager.get_events()
    logger.info(f"Total Events: {len(events)}")

    from simulator.engine import EventType
    for event_type in EventType:
        event_count = len(controller.event_manager.get_events(event_type))
        if event_count > 0:
            logger.info(f"{event_type.value}: {event_count}")

    results = controller.get_results()

    logger.info(f"{Colors.BLUE}------------------------------ Delivery Results ------------------------------{Colors.RESET}")
    for order_id, delivery_time in results["order_delivery_times"].items():
        in_window = results["order_delivered_in_window"][order_id]
        logger.info(f"Order {order_id}: delivered at {delivery_time}, in window: {in_window}")

    logger.info(f"{Colors.BLUE}------------------------------ Courier Payments ------------------------------{Colors.RESET}")
    for courier_id, payment in results["courier_payments"].items():
        logger.info(f"Courier {courier_id}: {payment:.2f} rub")

    logger.info(f"Total delivery cost: {results['total_delivery_cost']:.2f} rub")

    # Save results if output path specified
    if args.output:
        output_path = Path(args.output)
        results_json = {
            "metrics": metrics,
            "events": [
                {
                    "type": e.event_type.value,
                    "timestamp": e.timestamp.isoformat(),
                    "entity_id": e.entity_id,
                    "data": e.data
                }
                for e in events
            ],
            "final_state": {
                "orders": {
                    order_id: {
                        "status": order.status.value,
                        "mass_kg": order.mass_kg
                    }
                    for order_id, order in controller.state_manager.orders.items()
                },
                "couriers": {
                    courier_id: {
                        "status": courier.status.value,
                        "current_load": courier.current_load,
                        "assigned_orders": courier.assigned_order_ids
                    }
                    for courier_id, courier in controller.state_manager.couriers.items()
                }
            }
        }

        with open(output_path, 'w') as f:
            json.dump(results_json, f, indent=2)
        logger.info(f"Results saved to {args.output}")

    return 0


if __name__ == "__main__":
    exit(main())
