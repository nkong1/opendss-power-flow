import pandas as pd
import matplotlib.pyplot as plt

# Read CSV
load_data = pd.read_csv(r"raw_data\load_timeseries_data.csv", index_col=0)

# Convert all columns to numeric, coercing any text (e.g., empty cells) to NaN
load_data = load_data.apply(pd.to_numeric, errors='coerce')

# Now sum across buildings for each 15-min interval
total_power = load_data.sum(axis=1)

# Optional: add datetime index
start_time = pd.Timestamp("2023-01-01 00:00")
total_power.index = pd.date_range(start=start_time, periods=len(total_power), freq="15min")

# Plot
plt.figure(figsize=(7,5))
plt.plot(total_power.index, total_power, color='steelblue')
plt.title("Total District Power Draw")
plt.xlabel("Time")
plt.ylabel("Power (kW)")
plt.grid(True)
plt.tight_layout()
plt.show()
