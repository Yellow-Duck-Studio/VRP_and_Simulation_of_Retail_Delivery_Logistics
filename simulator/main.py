#!/usr/bin/env python3
"""
Main entry point for the Retail Delivery Logistics Simulator.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from simulator import (
    SimulationController,
    load_simulation_data,
)


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
    
    args = parser.parse_args()
    
    start_time = datetime.fromisoformat(args.start_time)
    controller = SimulationController(
        start_time=start_time,
        time_step_minutes=args.time_step
    )
    
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file {args.input} not found")
        return 1
    
    print(f"Loading simulation data from {args.input}...")
    load_simulation_data(str(input_path), controller.state_manager)
    
    print("\n=== Initial State ===")
    print(f"Warehouses: {len(controller.state_manager.warehouses)}")
    print(f"Courier Types: {len(controller.state_manager.courier_types)}")
    print(f"Couriers: {len(controller.state_manager.couriers)}")
    print(f"Orders: {len(controller.state_manager.orders)}")
    print(f"Routes: {len(controller.state_manager.routes)}")
    
    print("\n=== Warehouses ===")
    for wh_id, wh in controller.state_manager.warehouses.items():
        print(f"  {wh_id}: {wh.location.address or 'No address'}")
        print(f"    Location: ({wh.location.latitude:.4f}, {wh.location.longitude:.4f})")
    
    print("\n=== Courier Types ===")
    for ct_id, ct in controller.state_manager.courier_types.items():
        print(f"  {ct_id}: {ct.name}")
        print(f"    Capacity: {ct.capacity_kg} kg, Speed: {ct.speed_kmh} km/h")
    
    print("\n=== Couriers ===")
    for c_id, courier in controller.state_manager.couriers.items():
        ct = controller.state_manager.courier_types.get(courier.courier_type_id)
        print(f"  {c_id}: {ct.name if ct else 'Unknown'}")
        print(f"    Status: {courier.status}, Load: {courier.current_load} kg")
        print(f"    Location: ({courier.current_location.latitude:.4f}, {courier.current_location.longitude:.4f})")
    
    print("\n=== Orders ===")
    for o_id, order in controller.state_manager.orders.items():
        print(f"  {o_id}: Customer {order.customer_id}")
        print(f"    Warehouse: {order.warehouse_id}")
        print(f"    Mass: {order.mass_kg} kg")
        print(f"    Time Window: {order.time_window.start.strftime('%H:%M')} - {order.time_window.end.strftime('%H:%M')}")
        print(f"    Ready Time: {order.ready_time.strftime('%H:%M')}")
        print(f"    Status: {order.status}")
    
    print(f"\n=== Running Simulation ===")
    print(f"Start Time: {start_time.isoformat()}")
    print(f"Time Step: {args.time_step} minutes")
    print(f"Max Steps: {args.max_steps}")
    
    controller.run(max_steps=args.max_steps)
    
    print("\n=== Simulation Results ===")
    metrics = controller.get_metrics()
    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2%}" if "rate" in key else f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")
    
    print("\n=== Event Summary ===")
    events = controller.event_manager.get_events()
    print(f"Total Events: {len(events)}")
    
    from simulator.core import EventType
    for event_type in EventType:
        event_count = len(controller.event_manager.get_events(event_type))
        if event_count > 0:
            print(f"  {event_type.value}: {event_count}")
    
    # Save results if output path specified
    if args.output:
        output_path = Path(args.output)
        results = {
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
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.output}")
    
    return 0


if __name__ == "__main__":
    exit(main())
