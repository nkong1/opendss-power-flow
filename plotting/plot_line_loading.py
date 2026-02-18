import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np


# ------------------------------------------------------
# Helper: remove phase suffix "BUS.1.2.3" → "BUS"
# ------------------------------------------------------
def strip_phase_suffix(bus):
    return bus.split(".")[0]


# Load input data
# ------------------------------------------------------
lines = pd.read_csv("results/line_loading_timeseries.csv")
buses = pd.read_csv("results/bus_info.csv")

volt = pd.read_csv("results/voltage_timeseries.csv")
volt["bus"] = volt["bus"].apply(strip_phase_suffix)

# Identify PV buses
pv_flags = volt.groupby("bus")["has_pv"].max().to_dict()

# Strip suffixes on line endpoints
lines["from_bus"] = lines["from_bus"].apply(strip_phase_suffix)
lines["to_bus"] = lines["to_bus"].apply(strip_phase_suffix)

# Build coordinate lookup
bus_coords = buses.set_index("bus")[["x", "y"]].to_dict(orient="index")


# Figure setup
fig, ax = plt.subplots(figsize=(12, 9), facecolor='white')

# Normalize line loading for color
pct_loading = lines["max_pct_loading"]
norm = mcolors.Normalize(vmin=0, vmax=max(100, pct_loading.max()))
cmap = plt.get_cmap("hot")

print(f"max line loading: {lines["max_pct_loading"].max()}")
# ------------------------------------------------------
# Dynamic scaling for arrows based on feeder size
# ------------------------------------------------------
x_range = buses['y'].max() - buses['y'].min()
y_range = buses['x'].max() - buses['x'].min()
feeder_scale = max(x_range, y_range)

ARROW_SCALE = 0.015 * feeder_scale     # arrow length
ARROW_HEAD = 0.015 * feeder_scale     # arrow head size


# ------------------------------------------------------
# Plot each line segment
# ------------------------------------------------------
for _, row in lines.iterrows():
    fb = row["from_bus"]
    tb = row["to_bus"]

    if fb not in bus_coords or tb not in bus_coords:
        continue

    x1, y1 = bus_coords[fb]["y"], bus_coords[fb]["x"]
    x2, y2 = bus_coords[tb]["y"], bus_coords[tb]["x"]

    # Plot line (colored by loading)
    ax.plot([x1, x2], [y1, y2],
            color=cmap(norm(row["max_pct_loading"])),
            linewidth=1.4,
            alpha=0.85,
            solid_capstyle='round',
            zorder=2)

   # ---- Small directional markers instead of arrows ----
    direction = 1 if row["kw"] >= 0 else -1

    dx = x2 - x1
    dy = y2 - y1
    length = np.hypot(dx, dy)


    if length > 0.0001:
        # Midpoint of the line
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2

        # Unit direction vector
        ux = (dx / length) * direction
        uy = (dy / length) * direction

        # Marker size (scaled to feeder)
        marker_size = 0.10 * 0.00065  

        # Perpendicular vector for triangle width
        px = -uy
        py = ux

        # Triangle points
        p1 = (mid_x + ux * marker_size,     mid_y + uy * marker_size)     # tip
        p2 = (mid_x - ux * marker_size/2 + px * marker_size/2,
            mid_y - uy * marker_size/2 + py * marker_size/2)
        p3 = (mid_x - ux * marker_size/2 - px * marker_size/2,
            mid_y - uy * marker_size/2 - py * marker_size/2)

        # Draw triangle
        ax.fill(
            [p1[0], p2[0], p3[0]],
            [p1[1], p2[1], p3[1]],
            color="black",
            alpha=0.65,
            zorder=5
        )




# ------------------------------------------------------
# Plot buses
# ------------------------------------------------------
ax.scatter(
    buses["y"], buses["x"],
    s=35,
    color="#2c3e50",
    edgecolors="white",
    linewidths=0.6*2,
    alpha=0.9,
    zorder=3
)

# PV buses: orange outline
for _, row in buses.iterrows():
    b = row["bus"]
    if pv_flags.get(b, False):
        ax.scatter(
            row["y"], row["x"],
            s=30,
            facecolor="orange",
            edgecolor="black",
            linewidth=1.3,
            zorder=4,
        )


# ------------------------------------------------------
# Colorbar
# ------------------------------------------------------
sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
sm.set_array([])

cbar = fig.colorbar(sm, ax=ax, fraction=0.046, pad=0.04)
cbar.set_label("Line Loading (%)", fontsize=12, weight='semibold')
cbar.ax.tick_params(labelsize=10)
cbar.ax.axhline(y=100, color='white', linestyle='--',
                linewidth=2, alpha=0.8)


# ------------------------------------------------------
# Formatting
# ------------------------------------------------------
ax.set_title("Distribution Line Loading Map - Phase A",
             fontsize=17, pad=20, weight='bold')
ax.set_xlabel("Longitude", fontsize=13, weight='semibold')
ax.set_ylabel("Latitude", fontsize=13, weight='semibold')

# Format axis tick labels to show actual lat/lon values
ax.ticklabel_format(style='plain', useOffset=False)
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:.3f}'))
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, p: f'{y:.3f}'))

ax.grid(True, linestyle="--", alpha=0.3)

# Extend view for padding
x_min, x_max = buses['y'].min(), buses['y'].max()
y_min, y_max = buses['x'].min(), buses['x'].max()
pad_x = 0.08 * (x_max - x_min)
pad_y = 0.08 * (y_max - y_min)

ax.set_xlim(x_min - pad_x, x_max + pad_x)
ax.set_ylim(y_min - pad_y, y_max + pad_y)

# Legend
bus_handle = plt.Line2D([], [], marker='o', color='none',
                        markerfacecolor='#2c3e50',
                        markeredgecolor='white',
                        markersize=6, linewidth=0)

pv_handle = plt.Line2D([], [], marker='o', color='none',
                       markerfacecolor='orange',
                       markeredgecolor='black',
                       markersize=6, linewidth=0)

ax.legend(handles=[bus_handle, pv_handle],
          labels=["Bus", "PV Bus"],
          loc='upper right', fontsize=11,
          frameon=True, framealpha=0.97,
          edgecolor='#7f8c8d')

ax.set_aspect("equal", adjustable="box")

plt.tight_layout()
plt.savefig("plots/line_loading.png", dpi=300, bbox_inches="tight")
plt.show()
