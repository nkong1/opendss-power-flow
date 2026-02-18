import pandas as pd
import matplotlib.pyplot as plt

# ---------------------------------------------------
# USER INPUT
# ---------------------------------------------------
RESULTS_DIR = "results"     # folder containing voltage_timeseries.csv
HOUR = 1837                 # hour you want to plot
SAVE = True                # set True to save PNG

def main():
    # Load timeseries
    df = pd.read_csv(f"{RESULTS_DIR}/voltage_timeseries.csv")

    # Filter for the selected hour
    df_hour = df[df["hour"] == HOUR]
    if df_hour.empty:
        raise ValueError(f"No data found for hour {HOUR}")

    # Phase A voltage data
    data = df_hour["pu_a"].dropna()

    # Plot
    plt.figure(figsize=(5, 4))
    plt.hist(data, bins=50, color="#e74c3c", alpha=0.7, edgecolor="black")

    plt.xlabel("Voltage (per unit)", fontweight="bold")
    plt.ylabel("Number of Buses", fontweight="bold")
    plt.title(f"Phase A Voltage Distribution", fontweight="bold")
    plt.grid(True, alpha=0.3)

    plt.tight_layout()

    if SAVE:
        out = f"plots/hist_phase_a_hour_{HOUR}.png"
        plt.savefig(out, dpi=300, bbox_inches="tight")
        print(f"Saved: {out}")

    plt.show()


if __name__ == "__main__":
    main()
