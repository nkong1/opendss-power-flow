import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# =========================
# LOAD DATA
# =========================
csv_path = "critical_hours.csv" 
df = pd.read_csv(csv_path)

# Sort just in case
df = df.sort_values("hour_index").reset_index(drop=True)

# =========================
# CREATE TIME AXIS
# =========================
# Convert hour_index → datetime (assuming starts Jan 1)
start_date = pd.Timestamp("2023-01-01")  # change year if needed
df["datetime"] = start_date + pd.to_timedelta(df["hour_index"], unit="h")

# =========================
# PLOT
# =========================
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)


# -------------------------
# TOP: PV vs Load (ENHANCED COLORS)
# -------------------------
ax1.plot(
    df["datetime"],
    df["total_pv_kW"],
    label="Total PV Generation",
    color="#f59e0b",      # vibrant amber
    linewidth=1,
    alpha=0.9
)

ax1.plot(
    df["datetime"],
    df["total_load_kW"],
    label="Total Load",
    color="#2563eb",      # strong blue
    linewidth=1,
    alpha=0.9
)

# Optional: subtle fill under PV to make it stand out more
ax1.fill_between(
    df["datetime"],
    df["total_pv_kW"],
    alpha=0.15,
    color="#f59e0b"
)


ax1.set_title("Hourly District PV Generation vs Load")
ax1.set_ylabel("Power (kW)")
ax1.legend()
ax1.grid(True, alpha=0.3)
# -------------------------
# BOTTOM: Net Generation (THIN LINES + NEW COLORS)
# -------------------------
net = df["net_generation_kW"]

# Negative (deficit)
ax2.plot(
    df["datetime"],
    net,
    color="#b3a8a8",   
    linewidth=1.2,
    alpha=0.9,
)


# Zero line
ax2.axhline(0, color="black", linewidth=1, alpha=0.7)

# Annotate max
max_idx = net.idxmax()
ax2.annotate(
    "maximum",
    xy=(df.loc[max_idx, "datetime"], net[max_idx]),
    xytext=(df.loc[max_idx, "datetime"], net[max_idx] + 150),
    arrowprops=dict(arrowstyle="->"),
)

ax2.set_title("Hourly Net Generation")
ax2.set_ylabel("Net Generation (kW)")
ax2.set_xlabel("Month")
ax2.legend(frameon=False)
ax2.grid(True, alpha=0.3)

# -------------------------
# FORMAT X-AXIS (MONTHS)
# -------------------------
ax2.xaxis.set_major_locator(plt.matplotlib.dates.MonthLocator())
ax2.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%b'))

plt.tight_layout()
plt.savefig("pf_plots/critical_hours.png", dpi=300, bbox_inches="tight")
plt.show()