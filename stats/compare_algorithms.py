import subprocess
import re
import time


def run_benchmark():
    # The list of seeding algorithms defined in your system
    algorithms = ["DBSCAN", "RND", "CLWR", "DSTR", "SWEEP"]

    # Dictionary to store the parsed results
    results = []

    # Regex pattern to match the exact print statement from algorithm.py:
    # Example: "Gen 900 | Best Fitness: 145.20 | Valid Archieved: 1280"
    log_pattern = re.compile(r"Best Fitness:\s+([\d.]+)\s+\|\s+Valid Archieved:\s+(\d+)")

    print("Starting Algorithm Benchmark Suite...")
    print("-" * 50)

    for alg in algorithms:
        print(f"⏳ Running {alg}... (This may take a few moments)")
        start_time = time.time()

        try:
            # Execute main.py with the algorithm argument
            process = subprocess.run(
                ["python", "main.py", alg],  # Changed back to "main.py"
                cwd="..",
                capture_output=True,
                text=True,
                check=True
            )

            output = process.stdout

            # Find all matches of the log pattern in the terminal output
            matches = log_pattern.findall(output)

            if matches:
                # Get the very last match (the final generation's stats)
                final_best_fitness = float(matches[-1][0])
                final_clusterizations = int(matches[-1][1])
            else:
                final_best_fitness = "N/A (Failed to parse)"
                final_clusterizations = 0

            elapsed_time = time.time() - start_time

            # Store the extracted data
            results.append({
                "Algorithm": alg,
                "Best Fitness (Min)": final_best_fitness,
                "Valid Clusterizations": final_clusterizations,
                "Execution Time (s)": round(elapsed_time, 2)
            })

        except subprocess.CalledProcessError as e:
            print(f"❌ Error running {alg}: {e.stderr}")
            results.append({
                "Algorithm": alg,
                "Best Fitness (Min)": "ERROR",
                "Valid Clusterizations": "ERROR",
                "Execution Time (s)": "ERROR"
            })

    # --- Print the Final Markdown Table ---
    print("\n" + "=" * 65)
    print("🏆 ALGORITHM BENCHMARK RESULTS")
    print("=" * 65)

    # Table Header
    header = f"| {'Algorithm':<10} | {'Best Fitness Score':<20} | {'Total Clusterizations':<23} |"
    print(header)
    print("|" + "-" * 12 + "|" + "-" * 22 + "|" + "-" * 25 + "|")

    # Table Rows
    for res in results:
        alg = str(res['Algorithm'])
        fit = str(res['Best Fitness (Min)'])
        clust = str(res['Valid Clusterizations'])

        row = f"| {alg:<10} | {fit:<20} | {clust:<23} |"
        print(row)

    print("=" * 65)


if __name__ == "__main__":
    run_benchmark()
