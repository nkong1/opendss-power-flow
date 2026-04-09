import pandas as pd
import matplotlib.pyplot as plt

# Read CSV
load_data = pd.read_csv("raw_data/load_timeseries_data.csv", index_col=0)

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

# --- Compute monthly energy use (kWh) ---

# Convert 15-minute power data (kW) to energy (kWh)
energy_15min = total_power * 0.25  # 15 minutes = 0.25 hours

# Monthly energy (kWh)
monthly_energy = energy_15min.resample("M").sum()

print("Monthly Energy Use (kWh):")
print(monthly_energy)

# Average monthly energy (kWh)
monthly_energy_avg = monthly_energy.mean()
print("\nAverage Monthly Energy Use (kWh):")
print(monthly_energy_avg)

# --- Plot monthly energy ---
plt.figure(figsize=(9,5))
plt.bar(monthly_energy.index.strftime("%Y-%m"), monthly_energy.values, label="Monthly Energy (kWh)")
plt.axhline(monthly_energy_avg, linestyle="--",
            label=f"Average = {monthly_energy_avg:.0f} kWh")

plt.title("Monthly District Energy Use (kWh)")
plt.xlabel("Month")
plt.ylabel("Energy (kWh)")
plt.xticks(rotation=45)
plt.legend()
plt.tight_layout()
plt.show()

# --- Compute 30-minute peak load (kW) ---

# Convert 15-min data into 30-min averaged load
power_30min = total_power.resample("30T").mean()

# Monthly peak based on 30-min averages
monthly_peaks = power_30min.resample("M").max()

print("\nMonthly 30-min Peak Load (kW):")
print(monthly_peaks)

# Average monthly peak load
monthly_peak_avg = monthly_peaks.mean()
print("\nAverage Monthly 30-min Peak Load (kW):")
print(monthly_peak_avg)

# --- Plot monthly 30-min peak load ---
plt.figure(figsize=(9,5))
plt.bar(monthly_peaks.index.strftime("%Y-%m"), monthly_peaks.values,
        label="Monthly 30-min Peak Load (kW)", color='orange')

plt.axhline(monthly_peak_avg, linestyle="--",
            label=f"Average Peak = {monthly_peak_avg:.1f} kW")

plt.title("Monthly 30-min Peak District Load (kW)")
plt.xlabel("Month")
plt.ylabel("Peak Load (kW)")
plt.xticks(rotation=45)
plt.legend()
plt.tight_layout()
plt.show()
